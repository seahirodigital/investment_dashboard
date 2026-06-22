#!/usr/bin/env python3
"""Discord配信済みの市場材料からnote記事を生成して投稿する。"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
import random
import re
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
NOTE_DIR = BASE_DIR / "note"
GENERATED_DIR = NOTE_DIR / "generated"
REPORT_DIR = BASE_DIR / "market_analysis" / "reports"
TOC_MARKER = "[[NOTION_NOTE_TOC]]"
BODY_IMAGE_MARKER_TEMPLATE = "[[NOTE_BLOG_BODY_IMAGE_{index:03d}]]"
AFFILIATE_SLOT_TEMPLATE = "[[NOTION_NOTE_AFFILIATE_{index:03d}]]"
DISCLOSURE_TEXT = (
    "Amazonのアソシエイトとして本アカウントは適格販売により収入を得ています。"
    "文章にはAIの整形・編集が含まれます。"
)
INTRO_TEXT = (
    "日本株ランキングを下に日本取引時間内の、日本株ETFでおすすめ上位銘柄や、"
    "2026年の今後の見通しの日本株銘柄最新情報、今後上がる・伸びる銘柄投資分析のための情報をまとめます。"
)
SECTOR_POLICY_TEXT = (
    "基本方針として、日本株の各セクターへの資金割合流入を見ます、"
    "上がる・伸びる日本株の銘柄を分析のために、各セクターETF銘柄をTOPIXで割返しています。"
)
FOLLOW_TEXT = (
    "最新の市場トレンドや、視覚的にわかりやすいお役立ち情報をいち早くキャッチしたい方は、"
    "ぜひ以下のリンクからフォローをお願いします。"
    "[https://x.com/RipplePhantom](https://x.com/RipplePhantom)"
)
BLOG_TITLE_TEMPLATE = "日本株投資・投資信託ランキング・今後おすすめ銘柄分析2026：{date}"
SECTOR_H2 = "日本株投資・投資信託ランキング・今後おすすめ銘柄分析2026：日本株セクター毎の資金流入割合分析"
OPTION_H2 = "日経225 オプション分析"
SUMMARY_H2 = "投資戦略サマリー(Gemini分析)"


def _reconfigure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_reconfigure_stdio()


def _normalize_date(value: str) -> tuple[str, str, str]:
    raw = (value or "").strip()
    if not raw:
        raw = datetime.now().strftime("%Y-%m-%d")
    compact = raw.replace("-", "").replace("/", "")
    if not re.fullmatch(r"\d{8}", compact):
        raise ValueError(f"日付は YYYY-MM-DD または YYYYMMDD で指定してください: {value}")
    dashed = f"{compact[0:4]}-{compact[4:6]}-{compact[6:8]}"
    display = f"{compact[0:4]}/{compact[4:6]}/{compact[6:8]}"
    return dashed, compact, display


def _resolve_note_project_dir() -> Path:
    env_value = os.getenv("NOTE_PROJECT_DIR", "").strip()
    candidates = []
    if env_value:
        candidates.append(Path(env_value))
    candidates.extend(
        [
            BASE_DIR.parent / "notion2note",
            Path(r"C:\Users\mahha\OneDrive\開発\notion2note"),
        ]
    )
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if (resolved / "scripts" / "note_engine" / "note_draft_poster.py").exists():
            return resolved
    checked = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"notion2note が見つかりません。確認パス: {checked}")


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Pythonモジュールを読み込めません: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _read_report_text(date_compact: str, report_file: str = "") -> str:
    if report_file:
        path = Path(report_file).expanduser().resolve()
        return path.read_text(encoding="utf-8")
    preferred = REPORT_DIR / f"{date_compact}_daily_report.md"
    if preferred.exists():
        return preferred.read_text(encoding="utf-8")
    reports = sorted(REPORT_DIR.glob("*_daily_report.md"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not reports:
        raise FileNotFoundError(f"Gemini投資戦略サマリーが見つかりません: {REPORT_DIR}")
    print(f"   [警告] 指定日のレポートがないため最新レポートを使います: {reports[0]}")
    return reports[0].read_text(encoding="utf-8")


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextlib.contextmanager
def _static_server():
    port = _find_free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=str(BASE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(2)
        yield f"http://127.0.0.1:{port}"
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def _combine_images(left_path: Path, right_path: Path, output_path: Path) -> Path:
    from PIL import Image, ImageOps

    left = Image.open(left_path).convert("RGB")
    right = Image.open(right_path).convert("RGB")
    if right.height != left.height:
        if right.height < left.height:
            right = ImageOps.pad(right, (right.width, left.height), color="white", centering=(0.5, 0.0))
        else:
            right = right.crop((0, 0, right.width, left.height))

    gap = 18
    canvas = Image.new("RGB", (left.width + gap + right.width, left.height), "white")
    canvas.paste(left, (0, 0))
    canvas.paste(right, (left.width + gap, 0))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"結合画像を生成できませんでした: {output_path}")
    return output_path


def _create_note_thumbnail(source_path: Path, output_path: Path) -> Path:
    from PIL import Image, ImageOps

    source = Image.open(source_path).convert("RGB")
    width, height = source.size
    one_third = max(1, height // 3)
    top = source.crop((0, 0, width, one_third))
    bottom = source.crop((0, max(0, height - one_third), width, height))

    canvas_width, canvas_height = 1600, 836
    half_width = canvas_width // 2
    left = ImageOps.fit(top, (half_width, canvas_height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.0))
    right = ImageOps.fit(bottom, (canvas_width - half_width, canvas_height), method=Image.Resampling.LANCZOS, centering=(0.5, 1.0))

    canvas = Image.new("RGB", (canvas_width, canvas_height), "white")
    canvas.paste(left, (0, 0))
    canvas.paste(right, (half_width, 0))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, quality=92)
    return output_path


def capture_sector_assets(output_dir: Path) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    output_dir.mkdir(parents=True, exist_ok=True)
    with _static_server() as base_url:
        page_url = f"{base_url}/sector_category.html?period=1d#full-sector-flow"
        card_selector = '#full-sector-flow[data-capture="full-sector-card"]'
        chart_selector = '[data-capture="full-sector-chart"]'
        ranking_selector = '[data-capture="full-sector-ranking"]'

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 2200})
            page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
            page.locator(card_selector).first.wait_for(state="visible", timeout=45000)
            page.wait_for_timeout(8000)

            card = page.locator(card_selector).first
            chart = card.locator(chart_selector).first
            chart.wait_for(state="visible", timeout=45000)
            ranking = card.locator(ranking_selector).first
            ranking.wait_for(state="visible", timeout=45000)
            page.wait_for_function(
                """() => document.querySelectorAll('#full-sector-flow [data-capture="full-sector-ranking"] .relative.group.h-8').length > 0""",
                timeout=45000,
            )

            def show_ranking_slice(position: str) -> None:
                visible_count = ranking.evaluate(
                    """(element, position) => {
                      const rows = Array.from(element.querySelectorAll('.relative.group.h-8'));
                      const start = position === 'bottom' ? Math.max(0, rows.length - 7) : 0;
                      const end = Math.min(rows.length, start + 7);
                      rows.forEach((row, index) => {
                        row.style.display = index >= start && index < end ? 'flex' : 'none';
                      });
                      const scroller = element.querySelector('.overflow-y-auto');
                      if (scroller) scroller.scrollTop = 0;
                      return rows.filter((row) => row.style.display !== 'none').length;
                    }""",
                    position,
                )
                if visible_count != 7:
                    raise RuntimeError(f"{position}ランキングの表示件数が7件ではありません: {visible_count}")

            def restore_ranking_rows() -> None:
                ranking.evaluate(
                    """element => {
                      element.querySelectorAll('.relative.group.h-8').forEach((row) => {
                        row.style.display = 'flex';
                      });
                    }"""
                )

            ranking_items = ranking.evaluate(
                """element => Array.from(element.querySelectorAll('.relative.group.h-8')).map(row => {
                  const nameEl = row.querySelector('[title]');
                  const perfEl = row.querySelector('.font-mono');
                  return {
                    name: (nameEl?.getAttribute('title') || nameEl?.textContent || '').trim(),
                    performance: (perfEl?.textContent || '').trim(),
                  };
                }).filter(item => item.name && item.performance)"""
            )
            for item in ranking_items:
                item["performance"] = re.sub(r"\s+", "", str(item.get("performance") or ""))

            card.locator('[data-capture="show-top7"]').click()
            page.wait_for_timeout(2500)
            show_ranking_slice("top")
            page.wait_for_timeout(500)
            top_chart = output_dir / "sector_top7_chart.png"
            top_ranking = output_dir / "sector_top7_ranking.png"
            chart.screenshot(path=str(top_chart))
            ranking.screenshot(path=str(top_ranking))
            top_combined = _combine_images(top_chart, top_ranking, output_dir / "02_sector_top7_with_ranking.png")

            card.locator('[data-capture="show-bottom7"]').click()
            page.wait_for_timeout(2500)
            show_ranking_slice("bottom")
            page.wait_for_timeout(500)
            bottom_chart = output_dir / "sector_bottom7_chart.png"
            bottom_ranking = output_dir / "sector_bottom7_ranking.png"
            chart.screenshot(path=str(bottom_chart))
            ranking.screenshot(path=str(bottom_ranking))
            bottom_combined = _combine_images(
                bottom_chart,
                bottom_ranking,
                output_dir / "03_sector_bottom7_with_ranking.png",
            )

            restore_ranking_rows()
            ranking.evaluate(
                """element => {
                  const scroller = element.querySelector('.overflow-y-auto');
                  if (scroller) {
                    scroller.style.overflow = 'visible';
                    scroller.style.height = 'auto';
                    scroller.style.maxHeight = 'none';
                  }
                  element.style.height = 'auto';
                  element.style.maxHeight = 'none';
                  element.style.overflow = 'visible';
                  let parent = element.parentElement;
                  for (let i = 0; i < 6 && parent; i += 1) {
                    parent.style.height = 'auto';
                    parent.style.maxHeight = 'none';
                    parent.style.overflow = 'visible';
                    parent = parent.parentElement;
                  }
                }"""
            )
            page.wait_for_timeout(1000)
            full_ranking = output_dir / "01_sector_full_ranking.png"
            ranking.screenshot(path=str(full_ranking))
            browser.close()

    top5 = ranking_items[:5]
    bottom5 = list(reversed(ranking_items[-5:]))
    return {
        "top5": top5,
        "bottom5": bottom5,
        "images": [full_ranking, top_combined, bottom_combined],
    }


def capture_option_assets(output_dir: Path) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    output_dir.mkdir(parents=True, exist_ok=True)
    targets = [
        ("chartPurpose1_Diff", "04_option_major_diff.png"),
        ("chartPurpose1_Total", "05_option_major_total.png"),
        ("chartTrend", "06_option_major_trend.png"),
        ("chartPurpose2_225_OI", "07_option_n225_oi_by_strike.png"),
        ("chartPurpose2_225_Diff", "08_option_n225_diff_by_strike.png"),
    ]

    with _static_server() as base_url:
        page_url = f"{base_url}/option.html?source=json&capture=1&strikeCenter=67000&strikeHalfRange=11000"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1920, "height": 3000})
            page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_function(
                """() => window.optionChartsReady === true || Boolean(window.optionChartsError)""",
                timeout=60000,
            )
            chart_error = page.evaluate("() => window.optionChartsError")
            if chart_error:
                raise RuntimeError(f"オプションチャートの描画に失敗しました: {chart_error}")

            def assert_canvas_has_content(element_id: str):
                locator = page.locator(f"#{element_id}")
                locator.wait_for(state="visible", timeout=30000)
                has_content = locator.evaluate(
                    """canvas => {
                      const context = canvas.getContext('2d');
                      if (!context || canvas.width === 0 || canvas.height === 0) return false;
                      const image = context.getImageData(0, 0, canvas.width, canvas.height);
                      let paintedPixels = 0;
                      for (let index = 0; index < image.data.length; index += 4) {
                        const alpha = image.data[index + 3];
                        if (alpha === 0) continue;
                        const red = image.data[index];
                        const green = image.data[index + 1];
                        const blue = image.data[index + 2];
                        if (!(red > 248 && green > 248 && blue > 248)) {
                          paintedPixels += 1;
                          if (paintedPixels > 50) return true;
                        }
                      }
                      return false;
                    }"""
                )
                if not has_content:
                    raise RuntimeError(f"Canvas #{element_id} が空白、またはほぼ空白です。")
                return locator

            images: list[Path] = []
            for element_id, file_name in targets:
                output_path = output_dir / file_name
                assert_canvas_has_content(element_id).screenshot(path=str(output_path))
                images.append(output_path)
            browser.close()
    return {"images": images}


def _body_image_upload(path: Path, marker: str, caption: str) -> dict[str, Any]:
    return {
        "marker": marker,
        "path": str(path),
        "source": str(path),
        "caption": caption,
        "text_candidates": [marker, path.name, path.stem],
    }


def _append_image_markers(
    lines: list[str],
    uploads: list[dict[str, Any]],
    image_paths: list[Path],
    start_index: int,
    caption_prefix: str,
) -> int:
    index = start_index
    for image_path in image_paths:
        marker = BODY_IMAGE_MARKER_TEMPLATE.format(index=index)
        lines.extend([marker, ""])
        uploads.append(_body_image_upload(image_path, marker, f"{caption_prefix}{index:03d}"))
        index += 1
    return index


def _demote_report_headings(markdown: str) -> str:
    updated_lines: list[str] = []
    for line in (markdown or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.startswith("## ") and not line.startswith("### "):
            updated_lines.append(f"### {line[3:].strip()}")
        else:
            updated_lines.append(line)
    return "\n".join(updated_lines).strip()


def _format_ranking_lines(label: str, items: list[dict[str, Any]]) -> list[str]:
    lines = [label, ""]
    lines.extend(f"{item['name']}: {item['performance']}" for item in items)
    return lines


def build_blog_markdown(
    report_text: str,
    date_display: str,
    sector_assets: dict[str, Any],
    option_assets: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    title = BLOG_TITLE_TEMPLATE.format(date=date_display)
    body_uploads: list[dict[str, Any]] = []
    lines: list[str] = [
        f"# {title}",
        "",
        INTRO_TEXT,
        "",
        TOC_MARKER,
        "",
        DISCLOSURE_TEXT,
        "",
        f"## {SECTOR_H2}",
        "",
        SECTOR_POLICY_TEXT,
        "",
    ]
    next_image_index = _append_image_markers(
        lines,
        body_uploads,
        list(sector_assets["images"]),
        start_index=1,
        caption_prefix="日本株セクター資金流入割合分析 画像",
    )
    lines.extend(_format_ranking_lines("▼上位5件", list(sector_assets.get("top5") or [])))
    lines.extend(["", *_format_ranking_lines("▼下位5件", list(sector_assets.get("bottom5") or [])), ""])
    lines.extend([AFFILIATE_SLOT_TEMPLATE.format(index=1), "", f"## {OPTION_H2}", ""])
    next_image_index = _append_image_markers(
        lines,
        body_uploads,
        list(option_assets["images"]),
        start_index=next_image_index,
        caption_prefix="日経225オプション分析 画像",
    )
    lines.extend([AFFILIATE_SLOT_TEMPLATE.format(index=2), "", f"## {SUMMARY_H2}", ""])
    lines.extend([_demote_report_headings(report_text), "", AFFILIATE_SLOT_TEMPLATE.format(index=3), "", FOLLOW_TEXT])
    return "\n".join(lines).strip() + "\n", body_uploads


def _apply_affiliate_links(
    markdown: str,
    note_project_dir: Path,
    memo_number: int,
    affiliate_count: int,
    seed: str,
) -> tuple[str, int]:
    notion_post = _load_module(
        "investment_dashboard_notion_post_runtime",
        note_project_dir / "scripts" / "notion_note" / "post_from_notion.py",
    )
    affiliate_file = note_project_dir / "affiliate_links.txt"
    return notion_post._insert_affiliate_after_each_h2(
        markdown,
        affiliate_file=affiliate_file,
        memo_number=max(1, memo_number),
        per_h2_count=max(0, affiliate_count),
        seed=seed,
    )


def _read_tags(note_project_dir: Path) -> str:
    publisher = _load_module(
        "investment_dashboard_note_publisher_tags_runtime",
        note_project_dir / "scripts" / "note_post" / "note_post_publisher.py",
    )
    return publisher._read_tags(note_project_dir / "tag.md")


def _post_to_note(
    markdown: str,
    note_project_dir: Path,
    mode: str,
    thumbnail_path: Path,
    body_image_uploads: list[dict[str, Any]],
) -> dict[str, Any]:
    publish_tags = _read_tags(note_project_dir)
    if mode == "draft":
        note_engine = _load_module(
            "investment_dashboard_note_engine_runtime",
            note_project_dir / "scripts" / "note_engine" / "note_draft_poster.py",
        )
        return note_engine.post_draft_to_note(
            markdown,
            run_ogp=True,
            run_top_image=True,
            insert_toc=True,
            publish=False,
            dry_run_publish=False,
            publish_tags=publish_tags,
            top_image_path=str(thumbnail_path),
            body_image_uploads=body_image_uploads,
        )

    publisher = _load_module(
        "investment_dashboard_note_publisher_runtime",
        note_project_dir / "scripts" / "note_post" / "note_post_publisher.py",
    )
    return publisher.publish_markdown_to_note(
        markdown,
        run_ogp=True,
        run_top_image=True,
        insert_toc=True,
        publish_tags=publish_tags,
        top_image_path=str(thumbnail_path),
        body_image_uploads=body_image_uploads,
        dry_run_publish=(mode == "dry-run"),
    )


def publish_note_blog(
    report_text: str,
    date_value: str,
    mode: str = "skip",
    report_file: str = "",
    affiliate_memo: int = 1,
    affiliate_count: int = 1,
    affiliate_seed: str = "",
    reuse_assets: bool = False,
) -> dict[str, Any]:
    dashed_date, compact_date, display_date = _normalize_date(date_value)
    normalized_mode = (mode or "skip").strip().lower().replace("_", "-")
    if normalized_mode in {"none", "off", "false"}:
        normalized_mode = "skip"
    if normalized_mode not in {"skip", "draft", "dry-run", "publish"}:
        raise ValueError(f"NOTE_POST_MODE は skip / draft / dry-run / publish のいずれかを指定してください: {mode}")
    if normalized_mode == "skip":
        return {"success": True, "skipped": True, "mode": normalized_mode, "date": dashed_date}

    note_project_dir = _resolve_note_project_dir()
    run_dir = GENERATED_DIR / compact_date
    image_dir = run_dir / "images"
    run_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)

    if not report_text:
        report_text = _read_report_text(compact_date, report_file=report_file)

    if reuse_assets and (image_dir / "01_sector_full_ranking.png").exists():
        sector_assets = {
            "top5": [],
            "bottom5": [],
            "images": [
                image_dir / "01_sector_full_ranking.png",
                image_dir / "02_sector_top7_with_ranking.png",
                image_dir / "03_sector_bottom7_with_ranking.png",
            ],
        }
    else:
        print("   [情報] note用の日本株セクター画像を生成します")
        sector_assets = capture_sector_assets(image_dir)

    if reuse_assets and (image_dir / "04_option_major_diff.png").exists():
        option_assets = {
            "images": [
                image_dir / "04_option_major_diff.png",
                image_dir / "05_option_major_total.png",
                image_dir / "06_option_major_trend.png",
                image_dir / "07_option_n225_oi_by_strike.png",
                image_dir / "08_option_n225_diff_by_strike.png",
            ],
        }
    else:
        print("   [情報] note用の日経225オプション画像を生成します")
        option_assets = capture_option_assets(image_dir)

    thumbnail_path = _create_note_thumbnail(
        Path(sector_assets["images"][0]),
        image_dir / "00_note_thumbnail.jpg",
    )
    markdown, body_image_uploads = build_blog_markdown(report_text, display_date, sector_assets, option_assets)
    markdown, affiliate_insertions = _apply_affiliate_links(
        markdown,
        note_project_dir,
        memo_number=affiliate_memo,
        affiliate_count=affiliate_count,
        seed=affiliate_seed or compact_date,
    )

    markdown_path = run_dir / "note_article.md"
    markdown_path.write_text(markdown, encoding="utf-8")
    print(f"   [情報] note記事Markdownを書き出しました: {markdown_path}")

    result = _post_to_note(
        markdown,
        note_project_dir=note_project_dir,
        mode=normalized_mode,
        thumbnail_path=thumbnail_path,
        body_image_uploads=body_image_uploads,
    )
    result.update(
        {
            "mode": normalized_mode,
            "date": dashed_date,
            "markdown_path": str(markdown_path),
            "thumbnail_path": str(thumbnail_path),
            "body_image_count": len(body_image_uploads),
            "affiliate_insertions": affiliate_insertions,
            "note_project_dir": str(note_project_dir),
        }
    )
    result_path = run_dir / "note_post_result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   [情報] note投稿結果を書き出しました: {result_path}")
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discord配信材料をnoteブログへ投稿する")
    parser.add_argument("--date", default="", help="記事日付。YYYY-MM-DD または YYYYMMDD")
    parser.add_argument("--report-file", default="", help="Gemini投資戦略サマリーMarkdownのフルパス")
    parser.add_argument("--report-text", default="", help="Gemini投資戦略サマリー本文を直接指定")
    parser.add_argument("--mode", default=os.getenv("NOTE_POST_MODE", "dry-run"), choices=["skip", "draft", "dry-run", "publish"])
    parser.add_argument("--affiliate-memo", type=int, default=int(os.getenv("NOTE_AFFILIATE_MEMO", "1")))
    parser.add_argument("--affiliate-count", type=int, default=int(os.getenv("NOTE_AFFILIATE_COUNT", "1")))
    parser.add_argument("--affiliate-seed", default=os.getenv("NOTE_AFFILIATE_SEED", ""))
    parser.add_argument("--reuse-assets", action="store_true", help="生成済み画像があれば再利用する")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report_text = args.report_text
    if not report_text and args.report_file:
        report_text = Path(args.report_file).expanduser().resolve().read_text(encoding="utf-8")
    result = publish_note_blog(
        report_text=report_text,
        date_value=args.date,
        mode=args.mode,
        report_file=args.report_file,
        affiliate_memo=args.affiliate_memo,
        affiliate_count=args.affiliate_count,
        affiliate_seed=args.affiliate_seed,
        reuse_assets=args.reuse_assets,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2)[:4000])
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
