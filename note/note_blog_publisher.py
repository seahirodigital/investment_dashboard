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
import requests
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta
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
    "文章にはAIの整形・編集が含まれ、解釈は自己責任でお願いします。"
)
INTRO_TEXT = (
    "日本株ランキングを下に日本取引時間内の、日本株ETFでおすすめ上位銘柄や、"
    "2026年の今後の見通しの日本株銘柄最新情報、今後上がる・伸びる銘柄投資分析のための、"
    "本日の日本株取引時間での数位・チャートから分析をまとめます。\n\n"
    "後段の投資戦略 by Geminiは、セクターランキング・株価変動・オプションのデータを読み込ませて出力させています。\n\n"
    "当記事では、日本株セクターごとのETFランキング、日経オプション、明日以降の投資戦略（by Gemini）の順で簡易に結果がわかるように記載します。\n\n"
    "多忙な方はランキングや図だけを毎日見るだけでも、違ってきます。"
    "簡易に飛ばし見や、参考になれば投資戦略までお役立てください。"
    "将来的にはAIの進化でより精度が上がるはずです。（自作ですので精度はご容赦ください。）"
)
SECTOR_POLICY_TEXT = (
    "日本株の各セクターへの資金割合流入から、上がる・伸びる日本株の銘柄を分析のために、"
    "各セクターETF銘柄をTOPIXで割返すことで相対化したのが以下のランキング表です、"
    "マクロ環境や地合いの影響をなくし、各セクターへの資金流入の強弱を見るために相対化しています。"
    "トレンドに乗る・逆らわないようにするためにこの考え方を採用しています。\n\n"
    "外国人投資がが７割の日本市場においてお金が入ってくる・抜けてくるセクターを分析しています。\n\n"
    "本日の日本株セクター毎のランキングは以下です。上位が資金「流入」セクター、下位が資金「流出」セクターです。"
)
OPTION_ANALYSIS_TEXT = (
    "毎日東証から発表される日経225オプションの分析です。\n\n"
    "日経225,TOPIXは主に機関投資家が、日経225mini、マイクロは個人投資家が利用されているオプションです。"
    "オプションの増減と、建玉数、推移を示しています。\n\n"
    "また、日経オプションのCall-Putをすることで、"
    "どこで（オプションで保険をかけたいと考えている機関投資家・個人投資家が）均衡しているのかを見ています。"
    "ちょうどCallやPutが増え始める堺目を中心に、上下で上がる・下がることに対してオプションを利用しています。\n\n"
    "コール・プット前日比では、急増したオプションを見て、"
    "（主に機関投資家・外資系銀行（クライアント含む））保険を急に増減したことが判断できます。"
)
WEEKLY_FLOW_TEXT = (
    "海外投資家動向（JPX・財務省）は毎週木曜に東証から公開されます、"
    "日本市場では海外投資家（主に機関投資家）が７割と言われる市場のため、"
    "海外投資家の資金が流入・流出したのかは、"
    "翌週以降の日本株投資のランキングでおすすめETF分析をするうえで重要です。"
)
WEEKLY_FLOW_SENSITIVITY_TEXT = (
    "その際の海外投資家の資金フローを各ETFの結果で感応度計算をした結果が以下です。"
    "どのセクターから資金流出/入したかの参考になります"
    "（つまり、先週まではどのセクターに海外投資家が投資をしていたのかということです。"
    "今週の情報は、下にある各セクターごとのチャートで確認します。）"
)
FOLLOW_TEXT = (
    "最新の市場トレンドや、視覚的にわかりやすいお役立ち情報をいち早くキャッチしたい方は、"
    "ぜひ以下のリンクからフォローをお願いします。"
    "[https://x.com/RipplePhantom](https://x.com/RipplePhantom)"
)
BLOG_TITLE_TEMPLATE = "日本株投資・投資信託ランキング・今後おすすめ銘柄分析2026：{date}"
WEEKLY_FLOW_H2 = "海外投資家動向（JPX・財務省）"
SECTOR_H2 = "日本株投資・投資信託ランキング・今後おすすめ銘柄分析2026：日本株セクター毎の資金流入割合分析"
OPTION_H2 = "日本株投資・投資信託ランキング・今後おすすめ銘柄分析2026：日経225 オプション分析"
SUMMARY_H2 = "日本株投資・投資信託ランキング・今後おすすめ銘柄分析2026：投資戦略サマリー(Gemini分析)"
NOTE_PUBLISH_TAGS = "投資初心者 投資 デイトレ 日本株 日経平均 米国株 高配当 FX ドル円"
DISCORD_TEMPLATE_TAGS = "#投資初心者 #投資 #デイトレ #日本株 #日経平均 #米国株 #高配当 #FX #ドル円"
NOTE_MAGAZINE_NAME = "日本株の振り返りまとめ "
DISCORD_NOTE_TITLE = "【日本株投資・投資信託ランキングETFおすすめセクター資金流入分析】"


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
    reports = sorted(
        (
            item
            for item in REPORT_DIR.glob("*_daily_report.md")
            if re.fullmatch(r"\d{8}_daily_report\.md", item.name)
        ),
        key=lambda item: item.name[:8],
        reverse=True,
    )
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


def _date_is_thursday(dashed_date: str) -> bool:
    return datetime.strptime(dashed_date, "%Y-%m-%d").weekday() == 3


def _page_clip_from_boxes(page, boxes: list[dict[str, float]], padding: int = 24) -> dict[str, float]:
    usable_boxes = [
        box
        for box in boxes
        if box
        and float(box.get("width") or 0) > 0
        and float(box.get("height") or 0) > 0
    ]
    if not usable_boxes:
        raise RuntimeError("スクリーンショット対象の要素位置を取得できませんでした。")

    document_size = page.evaluate(
        """() => ({
          width: Math.max(document.body.scrollWidth, document.documentElement.scrollWidth),
          height: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight),
        })"""
    )
    x0 = max(0, min(float(box["x"]) for box in usable_boxes) - padding)
    y0 = max(0, min(float(box["y"]) for box in usable_boxes) - padding)
    x1 = min(float(document_size["width"]), max(float(box["x"]) + float(box["width"]) for box in usable_boxes) + padding)
    y1 = min(float(document_size["height"]), max(float(box["y"]) + float(box["height"]) for box in usable_boxes) + padding)
    return {
        "x": x0,
        "y": y0,
        "width": max(1, x1 - x0),
        "height": max(1, y1 - y0),
    }


def _capture_boxes_from_js(page, js: str, output_path: Path, padding: int = 24) -> Path:
    boxes = page.evaluate(js)
    clip = _page_clip_from_boxes(page, boxes, padding=padding)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output_path), clip=clip)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"スクリーンショットを生成できませんでした: {output_path}")
    return output_path


def _sector_three_week_range_for_capture(dashed_date: str) -> tuple[str, str]:
    end_date = datetime.strptime(dashed_date, "%Y-%m-%d").date()
    start_date = end_date - timedelta(days=21)
    return start_date.isoformat(), end_date.isoformat()


def _latest_sector_three_week_range() -> tuple[str, str]:
    path = BASE_DIR / "data" / "sector_data.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    weeks = sorted(
        {
            (str(row.get("week_start")), str(row.get("week_end")))
            for row in payload.get("data", [])
            if row.get("week_start") and row.get("week_end")
        },
        key=lambda item: item[1],
    )
    if not weeks:
        raise RuntimeError(f"セクター別感応度の週次データが見つかりません: {path}")
    target_weeks = weeks[-3:] if len(weeks) >= 3 else weeks
    return target_weeks[0][0], target_weeks[-1][1]


def capture_weekly_investor_assets(output_dir: Path, dashed_date: str) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    output_dir.mkdir(parents=True, exist_ok=True)
    with _static_server() as base_url:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()

            jpx_page = browser.new_page(viewport={"width": 1600, "height": 1700})
            jpx_page.goto(f"{base_url}/index.html?view=jpx", wait_until="domcontentloaded", timeout=60000)
            jpx_page.get_by_text("海外投資家動向（JPX・財務省）").first.wait_for(state="visible", timeout=45000)
            jpx_page.get_by_text("差引推移").first.wait_for(state="visible", timeout=45000)
            jpx_page.wait_for_timeout(7000)

            jpx_flow_image = _capture_boxes_from_js(
                jpx_page,
                """() => {
                  const rectOf = (element) => {
                    const rect = element.getBoundingClientRect();
                    return {
                      x: rect.left + window.scrollX,
                      y: rect.top + window.scrollY,
                      width: rect.width,
                      height: rect.height,
                    };
                  };
                  const chartCard = Array.from(document.querySelectorAll('div.bg-white.rounded-xl'))
                    .find((element) => element.innerText?.includes('差引推移'));
                  const statsGrid = Array.from(document.querySelectorAll('div.grid'))
                    .find((element) => element.innerText?.includes('最新週') && element.innerText?.includes('買い越し 平均'));
                  return [chartCard, statsGrid].filter(Boolean).map(rectOf);
                }""",
                output_dir / "09_weekly_jpx_investor_flow.png",
                padding=24,
            )

            jpx_page.wait_for_function(
                """() => {
                  const mofCard = Array.from(document.querySelectorAll('div.bg-white.rounded-xl'))
                    .find((element) => element.innerText?.includes('財務省 対内証券投資（株式・ファンド持分）'));
                  if (!mofCard) return false;
                  const text = mofCard.innerText || '';
                  return text.includes('毎週木曜更新')
                    && !text.includes('| 0件')
                    && !text.includes('データを読み込み中');
                }""",
                timeout=45000,
            )
            jpx_page.evaluate(
                """() => {
                  const mofCard = Array.from(document.querySelectorAll('div.bg-white.rounded-xl'))
                    .find((element) => element.innerText?.includes('財務省 対内証券投資（株式・ファンド持分）'));
                  if (!mofCard) throw new Error('財務省カードが見つかりません。');
                  const oneYearButton = Array.from(mofCard.querySelectorAll('button'))
                    .find((button) => button.textContent.trim() === '1年');
                  if (!oneYearButton) throw new Error('財務省カードの1年ボタンが見つかりません。');
                  oneYearButton.click();
                }"""
            )
            jpx_page.wait_for_timeout(2500)
            jpx_page.wait_for_function(
                """() => {
                  const mofCard = Array.from(document.querySelectorAll('div.bg-white.rounded-xl'))
                    .find((element) => element.innerText?.includes('財務省 対内証券投資（株式・ファンド持分）'));
                  if (!mofCard) return false;
                  const activeButton = Array.from(mofCard.querySelectorAll('button'))
                    .find((button) => button.textContent.trim() === '1年');
                  return activeButton
                    && activeButton.className.includes('bg-[#7C4DFF]')
                    && !mofCard.innerText.includes('データを読み込み中');
                }""",
                timeout=30000,
            )
            mof_image = _capture_boxes_from_js(
                jpx_page,
                """() => {
                  const rectOf = (element) => {
                    const rect = element.getBoundingClientRect();
                    return {
                      x: rect.left + window.scrollX,
                      y: rect.top + window.scrollY,
                      width: rect.width,
                      height: rect.height,
                    };
                  };
                  const mofCard = Array.from(document.querySelectorAll('div.bg-white.rounded-xl'))
                    .find((element) => element.innerText?.includes('財務省 対内証券投資（株式・ファンド持分）'));
                  return mofCard ? [rectOf(mofCard)] : [];
                }""",
                output_dir / "10_weekly_mof_inward_securities_1y.png",
                padding=24,
            )
            jpx_page.close()

            try:
                start_date, end_date = _sector_three_week_range_for_capture(dashed_date)
            except ValueError:
                start_date, end_date = _latest_sector_three_week_range()
            sensitivity_page = browser.new_page(viewport={"width": 1700, "height": 1900})
            sensitivity_page.goto(f"{base_url}/analytics.html", wait_until="domcontentloaded", timeout=60000)
            sensitivity_page.locator("#chart-container").wait_for(state="visible", timeout=45000)
            sensitivity_page.locator('input[type="date"]').nth(0).fill(start_date)
            sensitivity_page.locator('input[type="date"]').nth(1).fill(end_date)
            sensitivity_page.wait_for_timeout(2500)
            sensitivity_page.wait_for_function(
                """() => {
                  const flowChart = document.querySelector('#chart-flow');
                  if (!flowChart) return false;
                  return flowChart.querySelectorAll('.recharts-rectangle, .recharts-bar-rectangle').length >= 3;
                }""",
                timeout=30000,
            )
            sensitivity_page.evaluate("() => document.activeElement && document.activeElement.blur()")
            sensitivity_page.wait_for_timeout(500)
            sensitivity_image = _capture_boxes_from_js(
                sensitivity_page,
                """() => {
                  const rectOf = (element) => {
                    const rect = element.getBoundingClientRect();
                    return {
                      x: rect.left + window.scrollX,
                      y: rect.top + window.scrollY,
                      width: rect.width,
                      height: rect.height,
                    };
                  };
                  const filterCard = Array.from(document.querySelectorAll('div.bg-white.rounded-xl'))
                    .find((element) => element.innerText?.includes('分析期間:') && element.innerText?.includes('期間内 累積海外資金流入額'));
                  const chartContainer = document.querySelector('#chart-container');
                  return [filterCard, chartContainer].filter(Boolean).map(rectOf);
                }""",
                output_dir / "11_weekly_sector_sensitivity_3weeks.png",
                padding=24,
            )
            sensitivity_page.close()
            browser.close()

    return {"images": [jpx_flow_image, mof_image, sensitivity_image]}


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


def _stitch_images_horizontally(image_paths: list[Path], output_path: Path) -> Path:
    from PIL import Image

    if not image_paths:
        raise ValueError("横結合する画像がありません。")

    opened_images = [Image.open(path).convert("RGB") for path in image_paths]
    target_height = min(image.height for image in opened_images)
    normalized_images = []
    for image in opened_images:
        if image.height != target_height:
            resized_width = max(1, round(image.width * target_height / image.height))
            image = image.resize((resized_width, target_height), Image.Resampling.LANCZOS)
        normalized_images.append(image)

    gap = 18
    canvas_width = sum(image.width for image in normalized_images) + gap * (len(normalized_images) - 1)
    canvas = Image.new("RGB", (canvas_width, target_height), "white")
    x_offset = 0
    for image in normalized_images:
        canvas.paste(image, (x_offset, 0))
        x_offset += image.width + gap

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"横結合画像を生成できませんでした: {output_path}")
    return output_path


def _create_note_thumbnail(source_path: Path, output_path: Path) -> Path:
    from PIL import Image, ImageOps

    source = Image.open(source_path).convert("RGB")
    width, height = source.size
    canvas_width, canvas_height = 1600, 836

    # noteの横長サムネイルでは、上位ランキングが一目で見える上側だけを使う。
    top_crop_height = max(1, int(height * 0.34))
    top_crop = source.crop((0, 0, width, top_crop_height))
    thumbnail = ImageOps.fit(
        top_crop,
        (canvas_width, canvas_height),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.0),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    thumbnail.save(output_path, quality=92)
    return output_path


def _create_option_composite_images(image_paths: list[Path], output_dir: Path) -> list[Path]:
    if len(image_paths) < 5:
        raise RuntimeError(f"日経225オプション画像が5枚未満です: {len(image_paths)}")
    first_three = _stitch_images_horizontally(
        image_paths[:3],
        output_dir / "04_option_major_3charts_combined.png",
    )
    last_two = _stitch_images_horizontally(
        image_paths[3:5],
        output_dir / "05_option_strike_2charts_combined.png",
    )
    return [first_three, last_two]


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
    return {"images": _create_option_composite_images(images, output_dir)}


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
    weekly_assets: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    title = BLOG_TITLE_TEMPLATE.format(date=date_display)
    body_uploads: list[dict[str, Any]] = []
    next_affiliate_index = 1
    next_image_index = 1
    lines: list[str] = [
        f"# {title}",
        "",
        INTRO_TEXT,
        "",
        TOC_MARKER,
        "",
        DISCLOSURE_TEXT,
        "",
    ]

    weekly_images = list((weekly_assets or {}).get("images") or [])
    if weekly_images:
        lines.extend(
            [
                f"## {WEEKLY_FLOW_H2}",
                "",
                WEEKLY_FLOW_TEXT,
                "",
                WEEKLY_FLOW_SENSITIVITY_TEXT,
                "",
            ]
        )
        next_image_index = _append_image_markers(
            lines,
            body_uploads,
            weekly_images,
            start_index=next_image_index,
            caption_prefix="海外投資家動向 JPX 財務省 セクター別感応度 画像",
        )
        lines.extend([AFFILIATE_SLOT_TEMPLATE.format(index=next_affiliate_index), ""])
        next_affiliate_index += 1

    lines.extend([f"## {SECTOR_H2}", "", SECTOR_POLICY_TEXT, ""])
    next_image_index = _append_image_markers(
        lines,
        body_uploads,
        list(sector_assets["images"]),
        start_index=next_image_index,
        caption_prefix="日本株セクター資金流入割合分析 画像",
    )
    lines.extend(
        [
            AFFILIATE_SLOT_TEMPLATE.format(index=next_affiliate_index),
            "",
            f"## {OPTION_H2}",
            "",
            OPTION_ANALYSIS_TEXT,
            "",
        ]
    )
    next_affiliate_index += 1
    next_image_index = _append_image_markers(
        lines,
        body_uploads,
        list(option_assets["images"]),
        start_index=next_image_index,
        caption_prefix="日経225オプション分析 画像",
    )
    lines.extend([AFFILIATE_SLOT_TEMPLATE.format(index=next_affiliate_index), "", f"## {SUMMARY_H2}", ""])
    next_affiliate_index += 1
    lines.extend(
        [
            _demote_report_headings(report_text),
            "",
            AFFILIATE_SLOT_TEMPLATE.format(index=next_affiliate_index),
            "",
            FOLLOW_TEXT,
        ]
    )
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
    tag_file = note_project_dir / "tag.md"
    if tag_file.exists():
        tags = re.sub(r"\s+", " ", tag_file.read_text(encoding="utf-8")).strip()
        if tags:
            return tags
    print(f"   [警告] tag.md が読めないため既定タグを使います: {tag_file}")
    return NOTE_PUBLISH_TAGS


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
    message = f"{prefix}{DISCORD_NOTE_TITLE} \n\n{note_url}\n\n{DISCORD_TEMPLATE_TAGS}"
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

    original_discord_webhook = os.environ.get("NOTION2NOTE_DISCORD_WEBHOOK")
    os.environ["NOTION2NOTE_DISCORD_WEBHOOK"] = ""
    try:
        publisher = _load_module(
            "investment_dashboard_note_publisher_runtime",
            note_project_dir / "scripts" / "note_post" / "note_post_publisher.py",
        )
        publish_button_patch = _load_module(
            "investment_dashboard_publish_button_patch",
            NOTE_DIR / "publish_button_patch.py",
        )
        publisher = publish_button_patch.patch_note_publisher_publish_next(publisher)
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

    if not report_text:
        report_text = _read_report_text(compact_date, report_file=report_file)

    weekly_images = [
        image_dir / "09_weekly_jpx_investor_flow.png",
        image_dir / "10_weekly_mof_inward_securities_1y.png",
        image_dir / "11_weekly_sector_sensitivity_3weeks.png",
    ]
    weekly_assets: dict[str, Any] = {"images": []}
    if _date_is_thursday(dashed_date):
        if reuse_assets and all(path.exists() for path in weekly_images):
            weekly_assets = {"images": weekly_images}
        else:
            print("   [情報] 木曜用の海外投資家動向・財務省・セクター別感応度画像を生成します")
            weekly_assets = capture_weekly_investor_assets(image_dir, dashed_date)

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

    option_individual_images = [
        image_dir / "04_option_major_diff.png",
        image_dir / "05_option_major_total.png",
        image_dir / "06_option_major_trend.png",
        image_dir / "07_option_n225_oi_by_strike.png",
        image_dir / "08_option_n225_diff_by_strike.png",
    ]
    option_composite_images = [
        image_dir / "04_option_major_3charts_combined.png",
        image_dir / "05_option_strike_2charts_combined.png",
    ]
    if reuse_assets and all(path.exists() for path in option_composite_images):
        option_assets = {
            "images": option_composite_images,
        }
    elif reuse_assets and all(path.exists() for path in option_individual_images):
        option_assets = {"images": _create_option_composite_images(option_individual_images, image_dir)}
    else:
        print("   [情報] note用の日経225オプション画像を生成します")
        option_assets = capture_option_assets(image_dir)

    thumbnail_path = _create_note_thumbnail(
        Path(sector_assets["images"][0]),
        image_dir / "00_note_thumbnail.jpg",
    )
    markdown, body_image_uploads = build_blog_markdown(
        report_text,
        display_date,
        sector_assets,
        option_assets,
        weekly_assets=weekly_assets,
    )
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
            "weekly_image_count": len(weekly_assets.get("images") or []),
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
    parser.add_argument(
        "--mode",
        default=os.getenv("NOTE_POST_MODE", "dry-run"),
        choices=["skip", "draft", "draft-note-only", "dry-run", "publish"],
    )
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
