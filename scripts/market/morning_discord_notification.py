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
FINVIZ_URL = "https://finviz.com/map"


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
    page.goto(CNN_URL, wait_until="domcontentloaded", timeout=90000)
    _click_optional_text(page, ["Accept", "I Agree", "同意"])
    page.wait_for_timeout(7000)

    value = _extract_fear_greed_value(page)
    screenshot_path = output_dir / "fear_greed_index.png"

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
    page.goto(NIKKEI_WEEK_URL, wait_until="networkidle", timeout=90000)
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
    chart.scroll_into_view_if_needed(timeout=10000)
    page.wait_for_timeout(1000)

    screenshot_path = output_dir / "nikkei_vi_1w_chart.png"
    chart.screenshot(path=str(screenshot_path))
    return value, screenshot_path


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
        page = browser.new_page(
            viewport={"width": 1366, "height": 1200},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
        )
        try:
            fear_greed_value, fear_greed_path = _capture_fear_greed(page, output_dir)
            nikkei_vi_value, nikkei_vi_path = _capture_nikkei_vi(page, output_dir)
        finally:
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
        "screenshots": [str(fear_greed_path), str(nikkei_vi_path)],
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
        screenshot_paths=[fear_greed_path, nikkei_vi_path],
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
