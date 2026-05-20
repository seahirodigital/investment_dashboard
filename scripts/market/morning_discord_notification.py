"""朝の市況Discord通知を作成・送信するスクリプト。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


CNN_URL = "https://edition.cnn.com/markets/fear-and-greed"
NIKKEI_WEEK_URL = (
    "https://indexes.nikkei.co.jp/nkave/index/profile?cid=1&idx=nk225vi#section-gist"
)
NIKKEI_WEEK_SCREENSHOT_URL = (
    "https://indexes.nikkei.co.jp/nkave/index/profile?cid=1&idx=nk225vi"
)
FINVIZ_URL = "https://finviz.com/map"
FINVIZ_RENDER_URL = "https://finviz.com/map.ashx?t=sec&st=d1"

DESKTOP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class MarketSnapshot:
    fear_greed_value: str
    nikkei_vi_value: str
    message: str
    screenshot_paths: list[Path]


def _clean_number(value: str) -> str:
    value = value.strip().replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    if not match:
        raise ValueError(f"数値を抽出できませんでした: {value}")
    return match.group(0)


def _click_optional_text(page, text_patterns: Iterable[str]) -> None:
    for pattern in text_patterns:
        try:
            page.get_by_text(pattern, exact=False).first.click(timeout=1500)
            return
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue


def _dismiss_consent_and_overlays(page) -> None:
    _click_optional_text(
        page,
        [
            "Agree",
            "Accept All",
            "Accept",
            "I Agree",
            "同意",
            "OK",
        ],
    )
    page.wait_for_timeout(1000)
    page.evaluate(
        """() => {
          if (!document.body) return;
          const body = document.body;

          const selectors = [
            '[role="dialog"]',
            '[aria-modal="true"]',
            '#onetrust-banner-sdk',
            '#onetrust-consent-sdk',
            '.fc-consent-root',
            '[id*="consent" i]',
            '[class*="consent" i]',
            '[id*="privacy" i]',
            '[class*="privacy" i]'
          ];

          for (const selector of selectors) {
            for (const element of document.querySelectorAll(selector)) {
              if (element === body || element === document.documentElement) continue;
              const rect = element.getBoundingClientRect();
              const text = (element.innerText || element.textContent || '').toLowerCase();
              const isLikelyConsent =
                text.includes('agree') ||
                text.includes('accept') ||
                text.includes('consent') ||
                text.includes('privacy') ||
                text.includes('cookie') ||
                rect.width * rect.height > window.innerWidth * 80;
              if (isLikelyConsent) element.remove();
            }
          }

          for (const element of Array.from(body.querySelectorAll('*'))) {
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            const zIndex = Number.parseInt(style.zIndex || '0', 10);
            const coversMuchOfScreen =
              rect.width > window.innerWidth * 0.45 &&
              rect.height > window.innerHeight * 0.08;
            if (
              (style.position === 'fixed' || style.position === 'sticky') &&
              Number.isFinite(zIndex) &&
              zIndex >= 1000 &&
              coversMuchOfScreen
            ) {
              element.remove();
            }
          }

          document.documentElement.style.overflow = 'auto';
          document.body.style.overflow = 'auto';
        }"""
    )


def _largest_visible_locator(page, selector: str):
    best_index = None
    best_area = 0.0
    locator = page.locator(selector)
    for index in range(locator.count()):
        item = locator.nth(index)
        try:
            if not item.is_visible(timeout=1000):
                continue
            box = item.bounding_box(timeout=1000)
        except Exception:
            continue
        if not box:
            continue
        area = box["width"] * box["height"]
        if area > best_area:
            best_area = area
            best_index = index

    if best_index is None:
        raise RuntimeError(f"表示中の要素が見つかりませんでした: {selector}")
    return locator.nth(best_index)


def _page_clip_from_boxes(page, boxes, padding: int = 16) -> dict[str, float]:
    viewport = page.viewport_size or {"width": 1366, "height": 1200}
    left = max(0, min(box["x"] for box in boxes) - padding)
    top = max(0, min(box["y"] for box in boxes) - padding)
    right = min(viewport["width"], max(box["x"] + box["width"] for box in boxes) + padding)
    bottom = min(viewport["height"], max(box["y"] + box["height"] for box in boxes) + padding)
    return {
        "x": left,
        "y": top,
        "width": max(1, right - left),
        "height": max(1, bottom - top),
    }


def _extract_fear_greed_value(page) -> str:
    selectors = [
        ".market-fng-gauge__meter-container",
        ".market-feature-ribbon__column-content",
    ]
    for selector in selectors:
        try:
            text = page.locator(selector).first.inner_text(timeout=5000)
            value = _clean_number(text)
            if 0 <= float(value) <= 100:
                return value
        except Exception:
            continue

    body_text = page.locator("body").inner_text(timeout=10000)
    match = re.search(r"Fear\s*&\s*Greed\s+Index\s+(\d{1,3})", body_text, re.I)
    if match:
        return match.group(1)
    raise RuntimeError("CNN Fear & Greed Indexの値を取得できませんでした。")


def _capture_fear_greed(page, output_dir: Path) -> tuple[str, Path]:
    page.set_viewport_size({"width": 1024, "height": 1150})
    page.goto(CNN_URL, wait_until="domcontentloaded", timeout=90000)
    _dismiss_consent_and_overlays(page)
    page.wait_for_timeout(7000)
    _dismiss_consent_and_overlays(page)

    value = _extract_fear_greed_value(page)
    screenshot_path = output_dir / "fear_greed_index.png"

    try:
        title = page.locator(".headline_section-banner").first
        gauge = _largest_visible_locator(page, ".layout__main .market-fng-gauge")
        title.wait_for(state="visible", timeout=15000)
        gauge.wait_for(state="visible", timeout=15000)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(1000)
        title_box = title.bounding_box(timeout=10000)
        gauge_box = gauge.bounding_box(timeout=10000)
        if title_box and gauge_box:
            clip = _page_clip_from_boxes(page, [title_box, gauge_box], padding=18)
            clip["x"] = 0
            clip["width"] = min(page.viewport_size["width"], gauge_box["x"] + gauge_box["width"] + 32)
            page.screenshot(path=str(screenshot_path), clip=clip)
            return value, screenshot_path
    except Exception:
        pass

    for selector in [".layout__main .market-fng-gauge", ".market-tabbed-container"]:
        try:
            locator = _largest_visible_locator(page, selector)
            locator.wait_for(state="visible", timeout=15000)
            locator.scroll_into_view_if_needed(timeout=10000)
            page.wait_for_timeout(1000)
            locator.screenshot(path=str(screenshot_path))
            return value, screenshot_path
        except Exception:
            continue

    page.screenshot(path=str(screenshot_path), full_page=False)
    return value, screenshot_path


def _capture_nikkei_vi(page, output_dir: Path) -> tuple[str, Path]:
    page.set_viewport_size({"width": 1366, "height": 1050})
    page.goto(NIKKEI_WEEK_SCREENSHOT_URL, wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(3000)

    value = _clean_number(page.locator("#price").inner_text(timeout=15000))
    chart = page.locator(".idx-individual-chart").first
    chart.wait_for(state="visible", timeout=15000)

    try:
        active_periods = [
            period.strip()
            for period in page.locator(".idx-individual-chart-controller .active").all_inner_texts()
        ]
        if "1w" not in active_periods:
            raise RuntimeError("日経VIチャートの1w表示を確認できませんでした。")
    except Exception as exc:
        raise RuntimeError("日経VIチャートの1w表示を確認できませんでした。") from exc

    page.wait_for_function(
        "() => Array.from(document.images).every((image) => image.complete)",
        timeout=15000,
    )
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(1000)

    screenshot_path = output_dir / "nikkei_vi_1w_chart.png"
    try:
        header = page.locator(".idx-header-pagetitle").first
        header.wait_for(state="visible", timeout=15000)
        header_box = header.bounding_box(timeout=10000)
        chart_box = chart.bounding_box(timeout=10000)
        if header_box and chart_box:
            clip = _page_clip_from_boxes(page, [header_box, chart_box], padding=24)
            page.screenshot(path=str(screenshot_path), clip=clip)
            return value, screenshot_path
    except Exception:
        pass

    chart.screenshot(path=str(screenshot_path))
    return value, screenshot_path


def _capture_finviz_heatmap(page, output_dir: Path) -> Path:
    page.set_viewport_size({"width": 1840, "height": 1100})

    response = page.context.request.get(
        FINVIZ_RENDER_URL,
        headers={"User-Agent": DESKTOP_USER_AGENT},
        timeout=60000,
    )
    if response.status != 200:
        raise RuntimeError(f"FinvizヒートマップHTMLを取得できませんでした: HTTP {response.status}")
    html = response.text()

    def fulfill_finviz_map(route):
        route.fulfill(
            status=200,
            headers={"content-type": "text/html; charset=utf-8"},
            body=html,
        )

    page.context.route("https://finviz.com/map", fulfill_finviz_map)
    page.context.route("https://finviz.com/map?**", fulfill_finviz_map)

    page.goto(FINVIZ_URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(12000)
    page.locator("#map canvas.chart").first.wait_for(state="visible", timeout=45000)

    screenshot_path = output_dir / "finviz_heatmap.png"
    map_area = page.locator("#map").first
    try:
        map_area.screenshot(path=str(screenshot_path))
    except Exception:
        page.screenshot(path=str(screenshot_path), full_page=False)
    return screenshot_path


def _build_message(fear_greed_value: str, nikkei_vi_value: str) -> str:
    return "\n".join(
        [
            f"Feaar % Greed Index：{fear_greed_value}",
            CNN_URL,
            "",
            f"日経VIX:{nikkei_vi_value}",
            NIKKEI_WEEK_URL,
            "",
            "米株ヒートマップ",
            FINVIZ_URL,
            "",
            "#デイトレ #米国株 #日本株 #日経平均 #FX  #CFD ",
            "",
        ]
    )


def build_snapshot(output_dir: Path) -> MarketSnapshot:
    output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            ignore_https_errors=True,
            viewport={"width": 1366, "height": 1200},
            user_agent=DESKTOP_USER_AGENT,
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
        )
        page = context.new_page()
        try:
            fear_greed_value, fear_greed_path = _capture_fear_greed(page, output_dir)
            nikkei_vi_value, nikkei_vi_path = _capture_nikkei_vi(page, output_dir)
            finviz_path = _capture_finviz_heatmap(page, output_dir)
        finally:
            context.close()
            browser.close()

    message = _build_message(fear_greed_value, nikkei_vi_value)
    message_path = output_dir / "discord_message.txt"
    message_path.write_text(message, encoding="utf-8")

    metadata = {
        "fear_greed_value": fear_greed_value,
        "nikkei_vi_value": nikkei_vi_value,
        "urls": {
            "fear_greed": CNN_URL,
            "nikkei_vi": NIKKEI_WEEK_URL,
            "finviz": FINVIZ_URL,
        },
        "screenshots": [str(finviz_path), str(fear_greed_path), str(nikkei_vi_path)],
        "message_file": str(message_path),
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return MarketSnapshot(
        fear_greed_value=fear_greed_value,
        nikkei_vi_value=nikkei_vi_value,
        message=message,
        screenshot_paths=[finviz_path, fear_greed_path, nikkei_vi_path],
    )


def send_to_discord(webhook_url: str, snapshot: MarketSnapshot) -> None:
    if not webhook_url:
        raise RuntimeError("Discord Webhook URLが設定されていません。")

    file_handles = []
    files = []
    try:
        for index, path in enumerate(snapshot.screenshot_paths):
            handle = path.open("rb")
            file_handles.append(handle)
            files.append((f"files[{index}]", (path.name, handle, "image/png")))

        response = requests.post(
            webhook_url,
            data={"content": snapshot.message},
            files=files,
            timeout=60,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Discord送信に失敗しました: HTTP {response.status_code} {response.text[:500]}"
            )
    finally:
        for handle in file_handles:
            handle.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="朝の市況Discord通知を生成します。")
    parser.add_argument(
        "--output-dir",
        default="artifacts/morning_market_notification",
        help="生成物の保存先ディレクトリ。",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="生成後にDiscordへ送信します。",
    )
    parser.add_argument(
        "--webhook-env",
        default="DISCORD_OPTION_WEBHOOK_URL",
        help="Discord Webhook URLを読む環境変数名。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)

    snapshot = build_snapshot(output_dir)
    print(snapshot.message)
    print(f"生成先: {output_dir.resolve()}")

    if args.send:
        webhook_url = os.environ.get(args.webhook_env) or os.environ.get("DISCORD_WEBHOOK_URL", "")
        send_to_discord(webhook_url, snapshot)
        print("Discordへの送信が完了しました。")
    else:
        print("Discord送信はスキップしました。")


if __name__ == "__main__":
    main()
