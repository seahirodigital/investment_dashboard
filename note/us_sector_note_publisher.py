#!/usr/bin/env python3
"""朝の米国株セクター材料からnote記事を生成して投稿する。"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests


BASE_DIR = Path(__file__).resolve().parents[1]
NOTE_DIR = BASE_DIR / "note"
GENERATED_DIR = NOTE_DIR / "generated" / "us_sector"
TOC_MARKER = "[[NOTION_NOTE_TOC]]"
BODY_IMAGE_MARKER_TEMPLATE = "[[NOTE_BLOG_BODY_IMAGE_{index:03d}]]"
AFFILIATE_SLOT_TEMPLATE = "[[NOTION_NOTE_AFFILIATE_{index:03d}]]"

CNN_URL = "https://edition.cnn.com/markets/fear-and-greed"
FINVIZ_URL = "https://finviz.com/map"
SOX_URL = "https://www.tradingview.com/symbols/NASDAQ-SOX/"
NIKKEI_VI_URL = "https://indexes.nikkei.co.jp/nkave/index/profile?cid=1&idx=nk225vi#section-gist"

TITLE_PREFIX = "米国株ランキング分析・日本株今後おすすめ銘柄分析向け"
BLOG_TITLE_TEMPLATE = f"{TITLE_PREFIX}2026：{{date}}"
NOTE_PUBLISH_TAGS = "投資初心者 投資 デイトレ 日本株 日経平均 米国株 高配当 FX ドル円"
DISCORD_TEMPLATE_TAGS = "#投資初心者 #投資 #デイトレ #日本株 #日経平均 #米国株 #高配当 #FX #ドル円"
NOTE_MAGAZINE_NAME = "米国株のニュース・動向まとめ"
DISCORD_NOTE_TITLE = "【米国株投資セクター資金流入分析】"
JST = timezone(timedelta(hours=9))

INTRO_TEXT = (
    "米国株のランキング（セクター）をもとに、今日上昇・下落の可能性がある日本株銘柄の参考情報を提供します。"
    "つまり、米国で上昇・下落したセクターと日本での上下動がある程度相関する研究を踏まえ、"
    "米国での資金流入セクターを分析します。\n\n"
    "日本取引時間内の、日本株ETFでおすすめ上位銘柄や、2026年の今後の見通しの日本株銘柄最新情報、"
    "今後上がる・伸びる銘柄投資分析のための、本日の米国取引時間での推移とチャートから分析をまとめます。\n\n"
    "また、前段では、現状のマクロ環境での動きを抑えるために、４つの重要情報を添付します。\n\n"
    "多忙な方はランキングや図だけを毎日見るだけでも、マクロ環境への意識が違ってきます。"
    "簡易に飛ばし見や、参考になれば投資戦略までお役立てください。"
)
DISCLOSURE_TEXT = (
    "Amazonのアソシエイトとして本アカウントは適格販売により収入を得ています。"
    "文章にはAIの整形・編集が含まれ、解釈は自己責任でお願いします。"
)
FOLLOW_TEXT = (
    "最新の市場トレンドや、視覚的にわかりやすいお役立ち情報をいち早くキャッチしたい方は、"
    "ぜひ以下のリンクからフォローをお願いします。[https://x.com/RipplePhantom](https://x.com/RipplePhantom)"
)


def _reconfigure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_reconfigure_stdio()


def _default_us_session_date() -> str:
    today = datetime.now(JST).date()
    candidate = today - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate.strftime("%Y-%m-%d")


def _normalize_date(value: str) -> tuple[str, str, str]:
    raw = (value or "").strip() or _default_us_session_date()
    compact = raw.replace("-", "").replace("/", "")
    if not re.fullmatch(r"\d{8}", compact):
        raise ValueError(f"日付は YYYY-MM-DD または YYYYMMDD で指定してください: {value}")
    dashed = f"{compact[0:4]}-{compact[4:6]}-{compact[6:8]}"
    display = f"{compact[0:4]}/{compact[4:6]}/{compact[6:8]}"
    return dashed, compact, display


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Pythonモジュールを読み込めません: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _resolve_note_project_dir() -> Path:
    env_value = os.getenv("NOTE_PROJECT_DIR", "").strip()
    candidates: list[Path] = []
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


def _read_tags(note_project_dir: Path) -> str:
    tag_file = note_project_dir / "tag.md"
    if tag_file.exists():
        tags = re.sub(r"\s+", " ", tag_file.read_text(encoding="utf-8")).strip()
        if tags:
            return tags
    print(f"   [警告] tag.md が読めないため既定タグを使います: {tag_file}")
    return NOTE_PUBLISH_TAGS


def _apply_affiliate_links(
    markdown: str,
    note_project_dir: Path,
    memo_number: int,
    affiliate_count: int,
    seed: str,
) -> tuple[str, int]:
    notion_post = _load_module(
        "investment_dashboard_us_sector_notion_post_runtime",
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


def _note_url_from_result(result: dict[str, Any]) -> str:
    candidates = [
        result.get("published_url"),
        result.get("final_url"),
        result.get("url"),
    ]
    publish_result = ((result.get("editor_result") or {}).get("publish") or {})
    candidates.extend(
        [
            publish_result.get("final_url"),
            (publish_result.get("post_result") or {}).get("final_url_after_click"),
        ]
    )
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return value
    return ""


def _notify_discord_after_note(result: dict[str, Any], mode: str) -> dict[str, Any]:
    webhook_url = (
        os.getenv("NOTION2NOTE_DISCORD_WEBHOOK", "").strip()
        or os.getenv("DISCORD_OPTION_WEBHOOK_URL", "").strip()
    )
    note_url = _note_url_from_result(result)
    status: dict[str, Any] = {
        "attempted": False,
        "success": False,
        "webhook_configured": bool(webhook_url),
        "url": note_url,
        "mode": mode,
        "error": "",
    }
    if not note_url:
        status["error"] = "note URL が空のためDiscord通知をスキップしました。"
        print(f"   [警告] {status['error']}")
        return status
    if not webhook_url:
        status["error"] = "NOTION2NOTE_DISCORD_WEBHOOK / DISCORD_OPTION_WEBHOOK_URL が未設定のためDiscord通知をスキップしました。"
        print(f"   [情報] {status['error']}")
        return status

    prefix = "【下書き】" if mode != "publish" else ""
    message = f"{prefix}{DISCORD_NOTE_TITLE}  \n\n{note_url}\n\n{DISCORD_TEMPLATE_TAGS}"
    status["attempted"] = True
    try:
        response = requests.post(webhook_url, json={"content": message}, timeout=15)
    except requests.RequestException as exc:
        status["error"] = str(exc)
        print(f"   [警告] Discord通知に失敗しました: {exc}")
        return status
    if response.ok:
        status["success"] = True
        print("   [OK] Discordへnote完了通知を送信しました")
        return status
    status["error"] = f"Discord API {response.status_code}: {response.text[:300]}"
    print(f"   [警告] Discord通知に失敗しました: {status['error']}")
    return status


def _post_to_note(
    markdown: str,
    note_project_dir: Path,
    mode: str,
    thumbnail_path: Path,
    body_image_uploads: list[dict[str, Any]],
) -> dict[str, Any]:
    os.environ["NOTE_PUBLISH_MAGAZINE_NAME"] = os.getenv("NOTE_PUBLISH_MAGAZINE_NAME", NOTE_MAGAZINE_NAME)
    publish_tags = _read_tags(note_project_dir)
    if mode == "draft":
        note_engine = _load_module(
            "investment_dashboard_us_sector_note_engine_runtime",
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

    original_discord_webhook = os.environ.get("NOTION2NOTE_DISCORD_WEBHOOK")
    os.environ["NOTION2NOTE_DISCORD_WEBHOOK"] = ""
    try:
        publisher = _load_module(
            "investment_dashboard_us_sector_note_publisher_runtime",
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
    finally:
        if original_discord_webhook is None:
            os.environ.pop("NOTION2NOTE_DISCORD_WEBHOOK", None)
        else:
            os.environ["NOTION2NOTE_DISCORD_WEBHOOK"] = original_discord_webhook


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
    thumbnail = ImageOps.fit(
        source,
        (1600, 836),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    thumbnail.save(output_path, quality=92)
    return output_path


def _copy_image(source_path: Path, output_path: Path) -> Path:
    if not source_path.exists():
        raise FileNotFoundError(f"画像が見つかりません: {source_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, output_path)
    return output_path


def _ensure_morning_snapshot(source_dir: Path) -> dict[str, Any]:
    metadata_path = source_dir / "metadata.json"
    if not metadata_path.exists():
        print(f"   [情報] 朝の市況画像が見つからないため生成します: {source_dir}")
        module = _load_module(
            "investment_dashboard_morning_discord_runtime",
            BASE_DIR / "scripts" / "market" / "morning_discord_notification.py",
        )
        module.build_snapshot(source_dir)
    if not metadata_path.exists():
        raise FileNotFoundError(f"朝の市況メタデータが見つかりません: {metadata_path}")
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def _find_screenshot_by_name(metadata: dict[str, Any], source_dir: Path, stem: str) -> Path:
    for item in metadata.get("screenshots") or []:
        path = Path(str(item))
        if not path.is_absolute():
            path = (BASE_DIR / path).resolve()
        if path.stem == stem:
            return path
    fallback = source_dir / f"{stem}.png"
    if fallback.exists():
        return fallback
    raise FileNotFoundError(f"朝の市況スクリーンショットが見つかりません: {stem}")


def load_market_assets(source_dir: Path, image_dir: Path) -> dict[str, Any]:
    metadata = _ensure_morning_snapshot(source_dir)
    finviz = _copy_image(
        _find_screenshot_by_name(metadata, source_dir, "finviz_heatmap"),
        image_dir / "01_finviz_heatmap.png",
    )
    fear_greed = _copy_image(
        _find_screenshot_by_name(metadata, source_dir, "fear_greed_index"),
        image_dir / "02_fear_greed_index.png",
    )
    sox = _copy_image(
        _find_screenshot_by_name(metadata, source_dir, "sox_index_1w_chart"),
        image_dir / "03_sox_index_1w_chart.png",
    )
    nikkei_vi = _copy_image(
        _find_screenshot_by_name(metadata, source_dir, "nikkei_vi_1w_chart"),
        image_dir / "04_nikkei_vi_1w_chart.png",
    )
    return {
        "fear_greed_value": str(metadata.get("fear_greed_value") or "").strip(),
        "nikkei_vi_value": str(metadata.get("nikkei_vi_value") or "").strip(),
        "images": {
            "finviz": finviz,
            "fear_greed": fear_greed,
            "sox": sox,
            "nikkei_vi": nikkei_vi,
        },
        "metadata": metadata,
    }


def capture_us_sector_assets(output_dir: Path) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    output_dir.mkdir(parents=True, exist_ok=True)
    with _static_server() as base_url:
        page_url = f"{base_url}/sector_category.html?embed=us-sector&period=1d#full-sector-flow"
        card_selector = '#full-sector-flow[data-capture="full-sector-card"]'
        chart_selector = '[data-capture="full-sector-chart"]'
        ranking_selector = '[data-capture="full-sector-ranking"]'

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 2200})
            page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
            page.locator(card_selector).first.wait_for(state="visible", timeout=45000)
            page.wait_for_function(
                """() => {
                  const card = document.querySelector('#full-sector-flow[data-capture="full-sector-card"]');
                  return card?.dataset.market === 'us'
                    && card?.dataset.usMode === 'relative'
                    && card?.querySelector('h3')?.textContent.includes('vs SPY');
                }""",
                timeout=45000,
            )
            page.wait_for_timeout(5000)

            card = page.locator(card_selector).first
            chart = card.locator(chart_selector).first
            ranking = card.locator(ranking_selector).first
            chart.wait_for(state="visible", timeout=45000)
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
            top_chart = output_dir / "us_sector_top7_chart.png"
            top_ranking = output_dir / "us_sector_top7_ranking.png"
            chart.screenshot(path=str(top_chart))
            ranking.screenshot(path=str(top_ranking))
            top_combined = _combine_images(top_chart, top_ranking, output_dir / "05_us_sector_top7_with_ranking.png")

            card.locator('[data-capture="show-bottom7"]').click()
            page.wait_for_timeout(2500)
            show_ranking_slice("bottom")
            page.wait_for_timeout(500)
            bottom_chart = output_dir / "us_sector_bottom7_chart.png"
            bottom_ranking = output_dir / "us_sector_bottom7_ranking.png"
            chart.screenshot(path=str(bottom_chart))
            ranking.screenshot(path=str(bottom_ranking))
            bottom_combined = _combine_images(
                bottom_chart,
                bottom_ranking,
                output_dir / "06_us_sector_bottom7_with_ranking.png",
            )
            browser.close()

    return {
        "top7": ranking_items[:7],
        "bottom7": list(reversed(ranking_items[-7:])),
        "images": [top_combined, bottom_combined],
    }


def _body_image_upload(path: Path, marker: str, caption: str) -> dict[str, Any]:
    return {
        "marker": marker,
        "path": str(path),
        "source": str(path),
        "caption": caption,
        "text_candidates": [marker, path.name, path.stem],
    }


def _append_image_marker(
    lines: list[str],
    uploads: list[dict[str, Any]],
    image_path: Path,
    index: int,
    caption: str,
) -> int:
    marker = BODY_IMAGE_MARKER_TEMPLATE.format(index=index)
    lines.extend([marker, ""])
    uploads.append(_body_image_upload(image_path, marker, caption))
    return index + 1


def _format_ranking_items(items: list[dict[str, Any]]) -> str:
    return " ".join(f"{item['name']}: {item['performance']}" for item in items)


def build_blog_markdown(
    date_display: str,
    market_assets: dict[str, Any],
    sector_assets: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    title = BLOG_TITLE_TEMPLATE.format(date=date_display)
    section_prefix = f"{TITLE_PREFIX}{date_display}"
    images = market_assets["images"]
    fear_greed_value = market_assets.get("fear_greed_value") or "取得値未確認"
    nikkei_vi_value = market_assets.get("nikkei_vi_value") or "取得値未確認"

    body_uploads: list[dict[str, Any]] = []
    image_index = 1
    lines: list[str] = [
        f"# {title}",
        "",
        INTRO_TEXT,
        "",
        AFFILIATE_SLOT_TEMPLATE.format(index=1),
        "",
        TOC_MARKER,
        "",
        DISCLOSURE_TEXT,
        "",
        f"## {section_prefix}:米国ヒートマップ",
        "",
        f"本日付の米国でのヒートマップを以下に添付します。米株ヒートマップ [{FINVIZ_URL}]({FINVIZ_URL})",
        "",
    ]
    image_index = _append_image_marker(lines, body_uploads, images["finviz"], image_index, "米国株ヒートマップ")

    lines.extend(
        [
            f"## {section_prefix}:米国Fear&Greed Index",
            "",
            f"米国：Fear & Greed Index：{fear_greed_value}  [{CNN_URL}]({CNN_URL})",
            "",
        ]
    )
    image_index = _append_image_marker(lines, body_uploads, images["fear_greed"], image_index, "米国Fear & Greed Index")
    lines.extend([AFFILIATE_SLOT_TEMPLATE.format(index=2), ""])

    lines.extend(
        [
            f"## {section_prefix}:SOX指数",
            "",
            f"米国での半導体：SOX指数 [{SOX_URL}]({SOX_URL})",
            "",
        ]
    )
    image_index = _append_image_marker(lines, body_uploads, images["sox"], image_index, "SOX指数")

    lines.extend(
        [
            f"## {section_prefix}:日経恐怖指数の日経VIX",
            "",
            f"日本での恐怖指数：日経VIX:{nikkei_vi_value}[{NIKKEI_VI_URL}]({NIKKEI_VI_URL})",
            "",
        ]
    )
    image_index = _append_image_marker(lines, body_uploads, images["nikkei_vi"], image_index, "日経VIX")
    lines.extend([AFFILIATE_SLOT_TEMPLATE.format(index=3), ""])

    lines.extend(
        [
            f"## {section_prefix}:米国セクター資金流入ランキング",
            "",
        ]
    )
    image_index = _append_image_marker(
        lines,
        body_uploads,
        sector_assets["images"][0],
        image_index,
        "米国セクター資金流入ランキング上位7件",
    )
    lines.extend(["▼上位7件", _format_ranking_items(sector_assets["top7"]), ""])
    image_index = _append_image_marker(
        lines,
        body_uploads,
        sector_assets["images"][1],
        image_index,
        "米国セクター資金流入ランキング下位7件",
    )
    lines.extend(
        [
            "▼下位7件",
            _format_ranking_items(sector_assets["bottom7"]),
            "",
            AFFILIATE_SLOT_TEMPLATE.format(index=4),
            "",
            FOLLOW_TEXT,
        ]
    )
    return "\n".join(lines).strip() + "\n", body_uploads


def publish_us_sector_note(
    date_value: str,
    mode: str,
    market_assets_dir: str,
    affiliate_memo: int = 1,
    affiliate_count: int = 1,
    affiliate_seed: str = "",
) -> dict[str, Any]:
    dashed_date, compact_date, display_date = _normalize_date(date_value)
    requested_mode = (mode or "skip").strip().lower().replace("_", "-")
    if requested_mode in {"none", "off", "false"}:
        requested_mode = "skip"
    post_mode = "draft" if requested_mode == "draft-note-only" else requested_mode
    if post_mode not in {"skip", "draft", "dry-run", "publish"}:
        raise ValueError(
            "NOTE_POST_MODE は skip / draft / draft-note-only / dry-run / publish のいずれかを指定してください: "
            f"{mode}"
        )
    if post_mode == "skip":
        return {"success": True, "skipped": True, "mode": requested_mode, "post_mode": post_mode, "date": dashed_date}

    note_project_dir = _resolve_note_project_dir()
    run_dir = GENERATED_DIR / compact_date
    image_dir = run_dir / "images"
    run_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)

    source_dir = Path(market_assets_dir)
    if not source_dir.is_absolute():
        source_dir = (BASE_DIR / source_dir).resolve()

    market_assets = load_market_assets(source_dir, image_dir)
    print("   [情報] note用の米国セクターランキング画像を生成します")
    sector_assets = capture_us_sector_assets(image_dir)
    thumbnail_path = _create_note_thumbnail(market_assets["images"]["finviz"], image_dir / "00_note_thumbnail.jpg")
    markdown, body_image_uploads = build_blog_markdown(display_date, market_assets, sector_assets)
    markdown, affiliate_insertions = _apply_affiliate_links(
        markdown,
        note_project_dir,
        memo_number=affiliate_memo,
        affiliate_count=affiliate_count,
        seed=affiliate_seed or compact_date,
    )

    markdown_path = run_dir / "us_sector_note_article.md"
    markdown_path.write_text(markdown, encoding="utf-8")
    print(f"   [情報] 米国株note記事Markdownを書き出しました: {markdown_path}")

    result = _post_to_note(
        markdown,
        note_project_dir=note_project_dir,
        mode=post_mode,
        thumbnail_path=thumbnail_path,
        body_image_uploads=body_image_uploads,
    )
    result["discord_notification"] = _notify_discord_after_note(result, mode=post_mode)
    result.update(
        {
            "mode": requested_mode,
            "post_mode": post_mode,
            "date": dashed_date,
            "markdown_path": str(markdown_path),
            "thumbnail_path": str(thumbnail_path),
            "body_image_count": len(body_image_uploads),
            "affiliate_insertions": affiliate_insertions,
            "note_project_dir": str(note_project_dir),
            "market_assets_dir": str(source_dir),
            "fear_greed_value": market_assets.get("fear_greed_value", ""),
            "nikkei_vi_value": market_assets.get("nikkei_vi_value", ""),
            "top7": sector_assets["top7"],
            "bottom7": sector_assets["bottom7"],
        }
    )
    result_path = run_dir / "us_sector_note_post_result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   [情報] 米国株note投稿結果を書き出しました: {result_path}")
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="朝の米国株セクター材料をnoteブログへ投稿する")
    parser.add_argument("--date", default=os.getenv("NOTE_POST_DATE", ""), help="記事日付。空なら直近の米国市場日。")
    parser.add_argument(
        "--mode",
        default=os.getenv("NOTE_POST_MODE", "dry-run"),
        choices=["skip", "draft", "draft-note-only", "dry-run", "publish"],
        help="note投稿モード。",
    )
    parser.add_argument(
        "--market-assets-dir",
        default=os.getenv("MORNING_MARKET_ASSETS_DIR", "artifacts/morning_market_notification"),
        help="朝の市況画像とmetadata.jsonの保存先。",
    )
    parser.add_argument("--affiliate-memo", type=int, default=int(os.getenv("NOTE_AFFILIATE_MEMO", "1")))
    parser.add_argument("--affiliate-count", type=int, default=int(os.getenv("NOTE_AFFILIATE_COUNT", "1")))
    parser.add_argument("--affiliate-seed", default=os.getenv("NOTE_AFFILIATE_SEED", ""))
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = publish_us_sector_note(
        date_value=args.date,
        mode=args.mode,
        market_assets_dir=args.market_assets_dir,
        affiliate_memo=args.affiliate_memo,
        affiliate_count=args.affiliate_count,
        affiliate_seed=args.affiliate_seed,
    )
    if not result.get("success", True):
        raise RuntimeError(f"米国株note投稿に失敗しました: {json.dumps(result, ensure_ascii=False)[:1000]}")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])


if __name__ == "__main__":
    main()
