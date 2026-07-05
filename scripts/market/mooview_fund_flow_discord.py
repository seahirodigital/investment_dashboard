#!/usr/bin/env python3
"""MooViewの日本株資金フロー画像を既存Discordへ送信する。"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests


if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


JP_FUND_FLOW_MESSAGE = "\n".join(
    [
        "#日本株 今日の資金フロー",
        "▼セクター/TPX",
        "",
        "強：",
        "弱：",
        "",
        "",
        "▼半導体/TPX",
        "",
        "強：",
        "弱：",
        "",
        "",
        " [#デイトレ](https://x.com/hashtag/%E3%83%87%E3%82%A4%E3%83%88%E3%83%AC?src=hashtag_click) "
        "[#日本株](https://x.com/hashtag/%E6%97%A5%E6%9C%AC%E6%A0%AA?src=hashtag_click) "
        "[#日経平均](https://x.com/hashtag/%E6%97%A5%E7%B5%8C%E5%B9%B3%E5%9D%87?src=hashtag_click) "
        "[#米国株](https://x.com/hashtag/%E7%B1%B3%E5%9B%BD%E6%A0%AA?src=hashtag_click) "
        "#株クラ #投資家さんと繋がりたい",
    ]
)


def _resolve_capture_images(capture_dir: Path) -> list[Path]:
    image_paths = [
        capture_dir / "jp_market_sector_chart.png",
        capture_dir / "jp_market_semiconductor_charts.png",
    ]
    missing = [str(path) for path in image_paths if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise FileNotFoundError(f"Discord送信用のMooView画像が見つかりません: {missing}")
    return image_paths


def send_jp_fund_flow(webhook_url: str, capture_dir: Path) -> None:
    if not webhook_url:
        raise RuntimeError("Discord Webhook URLが設定されていません。")

    image_paths = _resolve_capture_images(capture_dir)
    file_handles = []
    files = []
    try:
        for index, image_path in enumerate(image_paths):
            handle = image_path.open("rb")
            file_handles.append(handle)
            files.append((f"files[{index}]", (image_path.name, handle, "image/png")))

        response = requests.post(
            webhook_url,
            data={"content": JP_FUND_FLOW_MESSAGE},
            files=files,
            timeout=60,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"日本株資金フローのDiscord送信に失敗しました: "
                f"HTTP {response.status_code} {response.text[:500]}"
            )
    finally:
        for handle in file_handles:
            handle.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MooViewの日本株資金フロー画像をDiscordへ送信する")
    parser.add_argument(
        "--capture-dir",
        default="artifacts/oci_mooview_capture",
        help="MooView撮影画像のディレクトリ。",
    )
    parser.add_argument(
        "--webhook-env",
        default="DISCORD_OPTION_WEBHOOK_URL",
        help="既存Discord Webhook URLを読む環境変数名。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    webhook_url = os.environ.get(args.webhook_env, "").strip()
    send_jp_fund_flow(webhook_url, Path(args.capture_dir))
    print("日本株資金フロー画像2枚のDiscord送信が完了しました。")


if __name__ == "__main__":
    main()
