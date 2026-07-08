#!/usr/bin/env python3
"""Oracleサーバーで日本株セクター資金流入Discord通知を送信する。"""

from __future__ import annotations

import argparse
import contextlib
import functools
import json
import os
import re
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, time as local_time, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests
from PIL import Image, ImageOps
from playwright.sync_api import sync_playwright


if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


BASE_DIR = Path(__file__).resolve().parents[2]
MARKET_SCRIPT_DIR = Path(__file__).resolve().parent
if str(MARKET_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(MARKET_SCRIPT_DIR))

from mooview_fund_flow_discord import send_jp_fund_flow  # noqa: E402
from oci_mooview_screenshot import _normalize_base_url, capture_mooview  # noqa: E402


JST = timezone(timedelta(hours=9), "JST")
DISCORD_TIMEOUT_SECONDS = 60
SLOT_TO_DELIVERY_NAME = {
    "midday": "jp-midday",
    "close": "jp-close",
}


@dataclass(frozen=True)
class RunContext:
    slot: str
    delivery_key: str
    jst_date: str
    output_dir: Path
    marker_path: Path


class QuietHTTPRequestHandler(SimpleHTTPRequestHandler):
    """ローカル撮影用HTTPサーバーのアクセスログを抑制する。"""

    def log_message(self, format: str, *args: object) -> None:
        return


def _jst_now() -> datetime:
    return datetime.now(JST)


def _resolve_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


def _resolve_slot(slot: str, now: datetime) -> str:
    if slot in SLOT_TO_DELIVERY_NAME:
        return slot

    current = now.time()
    if local_time(10, 30) <= current <= local_time(13, 0):
        return "midday"
    if local_time(14, 30) <= current <= local_time(17, 30):
        return "close"
    raise RuntimeError(
        "slot=autoで前場/大引けを判定できません。"
        f"現在のJST時刻は {now.strftime('%Y-%m-%d %H:%M:%S %Z')} です。"
    )


def _build_context(args: argparse.Namespace, slot: str, now: datetime) -> RunContext:
    jst_date = now.strftime("%Y%m%d")
    delivery_key = f"sector-category-delivery-{SLOT_TO_DELIVERY_NAME[slot]}-{jst_date}"
    state_dir = _resolve_path(args.state_dir)
    output_root = _resolve_path(args.output_root)
    run_name = f"{jst_date}_{slot}_{now.strftime('%H%M%S')}"
    return RunContext(
        slot=slot,
        delivery_key=delivery_key,
        jst_date=jst_date,
        output_dir=output_root / run_name,
        marker_path=state_dir / f"{delivery_key}.json",
    )


def _is_jp_weekday(now: datetime) -> bool:
    return now.weekday() < 5


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


@contextlib.contextmanager
def _serve_repo(port: int):
    handler = functools.partial(QuietHTTPRequestHandler, directory=str(BASE_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    actual_port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield actual_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _combine_images(left_path: Path, right_path: Path, output_path: Path) -> None:
    left = Image.open(left_path).convert("RGB")
    right = Image.open(right_path).convert("RGB")
    if right.height != left.height:
        if right.height < left.height:
            right = ImageOps.pad(
                right,
                (right.width, left.height),
                color="white",
                centering=(0.5, 0.0),
            )
        else:
            right = right.crop((0, 0, right.width, left.height))

    gap = 18
    canvas = Image.new("RGB", (left.width + gap + right.width, left.height), "white")
    canvas.paste(left, (0, 0))
    canvas.paste(right, (left.width + gap, 0))
    canvas.save(output_path)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"結合画像を生成できませんでした: {output_path.resolve()}")


def _write_jp_summary(output_dir: Path, items: list[dict[str, str]]) -> None:
    if len(items) < 10:
        raise RuntimeError(f"ランキング件数が不足しています: {len(items)}件")

    top_items = items[:5]
    bottom_items = list(reversed(items[-5:]))
    report_date = _jst_now().strftime("%Y%m%d")

    lines = [
        f"{report_date} セクター資金流入割合分析",
        "",
        "▼上位5件",
    ]
    lines.extend(f"{item['name']}: {item['performance']}" for item in top_items)
    lines.extend(
        [
            "",
            "▼下位5件",
        ]
    )
    lines.extend(f"{item['name']}: {item['performance']}" for item in bottom_items)
    lines.extend(
        [
            "",
            "#日経平均 #株式投資 #デイトレ #TOPIX #N225 #オプション #CFD",
            "",
            "https://seahirodigital.github.io/investment_dashboard/sector_category.html#full-sector-flow",
            "https://seahirodigital.github.io/investment_dashboard/",
        ]
    )

    (output_dir / "discord_message.txt").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def capture_sector_category_screenshots(output_dir: Path, page_port: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "mode.txt").write_text("jp", encoding="utf-8")

    page_url = f"http://127.0.0.1:{page_port}/sector_category.html?period=1d#full-sector-flow"
    card_selector = '#full-sector-flow[data-capture="full-sector-card"][data-market="jp"]'
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
            """() => document.querySelectorAll(
              '#full-sector-flow [data-capture="full-sector-ranking"] .relative.group.h-8'
            ).length > 0""",
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
                raise RuntimeError(
                    f"{position}ランキングの表示件数が7件ではありません: {visible_count}"
                )

        def restore_ranking_rows() -> None:
            ranking.evaluate(
                """element => {
                  element.querySelectorAll('.relative.group.h-8').forEach((row) => {
                    row.style.display = 'flex';
                  });
                }"""
            )

        ranking_rows = ranking.evaluate(
            """element => Array.from(element.querySelectorAll('.relative.group.h-8')).map(row => {
              const nameEl = row.querySelector('[title]');
              const perfEl = row.querySelector('.font-mono');
              return {
                name: (nameEl?.getAttribute('title') || nameEl?.textContent || '').trim(),
                performance: (perfEl?.textContent || '').trim(),
              };
            }).filter(item => item.name && item.performance)"""
        )
        ranking_items = []
        for row in ranking_rows:
            performance = re.sub(r"\s+", "", row["performance"])
            ranking_items.append({"name": row["name"], "performance": performance})
        _write_jp_summary(output_dir, ranking_items)

        card.locator('[data-capture="show-top7"]').click()
        page.wait_for_timeout(2500)
        show_ranking_slice("top")
        page.wait_for_timeout(500)
        top_chart = output_dir / "sector_category_top7_chart.png"
        top_ranking = output_dir / "sector_category_top7_ranking.png"
        chart.screenshot(path=str(top_chart))
        ranking.screenshot(path=str(top_ranking))
        _combine_images(
            top_chart,
            top_ranking,
            output_dir / "sector_category_top7_with_ranking.png",
        )

        card.locator('[data-capture="show-bottom7"]').click()
        page.wait_for_timeout(2500)
        show_ranking_slice("bottom")
        page.wait_for_timeout(500)
        bottom_chart = output_dir / "sector_category_bottom7_chart.png"
        bottom_ranking = output_dir / "sector_category_bottom7_ranking.png"
        chart.screenshot(path=str(bottom_chart))
        ranking.screenshot(path=str(bottom_ranking))
        _combine_images(
            bottom_chart,
            bottom_ranking,
            output_dir / "sector_category_bottom7_with_ranking.png",
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
        ranking.screenshot(path=str(output_dir / "sector_category_full_ranking.png"))
        browser.close()


def _require_files(paths: list[Path]) -> None:
    missing = [
        str(path.resolve())
        for path in paths
        if not path.is_file() or path.stat().st_size == 0
    ]
    if missing:
        raise FileNotFoundError(f"Discord送信用ファイルが見つかりません: {missing}")


def send_sector_category_to_discord(webhook_url: str, screenshot_dir: Path) -> None:
    message_path = screenshot_dir / "discord_message.txt"
    image_paths = [
        screenshot_dir / "sector_category_full_ranking.png",
        screenshot_dir / "sector_category_top7_with_ranking.png",
        screenshot_dir / "sector_category_bottom7_with_ranking.png",
    ]
    _require_files([message_path, *image_paths])

    handles = []
    files = []
    try:
        for index, image_path in enumerate(image_paths):
            handle = image_path.open("rb")
            handles.append(handle)
            files.append((f"files[{index}]", (image_path.name, handle, "image/png")))

        response = requests.post(
            webhook_url,
            data={"content": message_path.read_text(encoding="utf-8")},
            files=files,
            timeout=DISCORD_TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                "日本株セクター資金流入通知のDiscord送信に失敗しました: "
                f"HTTP {response.status_code} {response.text[:500]}"
            )
    finally:
        for handle in handles:
            handle.close()


def _execute_once(args: argparse.Namespace) -> bool:
    now = _jst_now()
    slot = _resolve_slot(args.slot, now)

    if not args.allow_weekend and not _is_jp_weekday(now):
        print(f"[終了] 日本時間の平日ではないため送信しません: {now.isoformat()}")
        return True

    context = _build_context(args, slot, now)
    if context.marker_path.exists() and not args.force:
        print(f"[終了] {context.delivery_key} は配信済みです: {context.marker_path.resolve()}")
        return True

    webhook_url = os.environ.get(args.webhook_env, "").strip()
    if not webhook_url and not args.dry_run:
        raise RuntimeError(
            f"Discord Webhook URLが環境変数 {args.webhook_env} に設定されていません。"
        )

    context.output_dir.mkdir(parents=True, exist_ok=True)
    sector_output_dir = context.output_dir / "sector_category_screenshots"
    mooview_output_dir = context.output_dir / "oci_mooview_capture"

    print(f"[開始] {context.delivery_key} の通知処理を開始します。")
    print(f"[情報] 出力先: {context.output_dir.resolve()}")

    if not args.skip_fund_flow:
        probe_symbols = tuple(
            symbol.strip() for symbol in args.probe_symbols.split(",") if symbol.strip()
        )
        if not probe_symbols:
            raise RuntimeError("--probe-symbols に1銘柄以上を指定してください。")
        capture_mooview(
            base_url=_normalize_base_url(args.mooview_base_url),
            output_dir=mooview_output_dir,
            timeout_seconds=args.timeout_seconds,
            refresh_wait_seconds=args.refresh_wait_seconds,
            viewport_width=args.viewport_width,
            viewport_height=args.viewport_height,
            probe_symbols=probe_symbols,
            display_range="d",
        )

    with _serve_repo(args.sector_page_port) as page_port:
        capture_sector_category_screenshots(sector_output_dir, page_port)

    if args.dry_run:
        _write_json(
            context.output_dir / "dry_run_result.json",
            {
                "delivery_key": context.delivery_key,
                "slot": context.slot,
                "jst_date": context.jst_date,
                "output_dir": str(context.output_dir.resolve()),
                "completed_at": _jst_now().isoformat(),
                "sent": False,
            },
        )
        print("[完了] dry-runのためDiscord送信と成功マーカー作成は行いません。")
        return True

    send_sector_category_to_discord(webhook_url, sector_output_dir)
    print("[成功] 日本株セクターランキング画像3枚をDiscordへ送信しました。")

    if not args.skip_fund_flow:
        send_jp_fund_flow(webhook_url, mooview_output_dir)
        print("[成功] MooView日本株資金フロー画像2枚をDiscordへ送信しました。")

    _write_json(
        context.marker_path,
        {
            "delivery_key": context.delivery_key,
            "slot": context.slot,
            "jst_date": context.jst_date,
            "output_dir": str(context.output_dir.resolve()),
            "completed_at": _jst_now().isoformat(),
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "sent": True,
        },
    )
    print(f"[完了] 成功マーカーを保存しました: {context.marker_path.resolve()}")
    return True


def _run_with_retries(args: argparse.Namespace) -> None:
    for attempt in range(1, args.retry_count + 1):
        try:
            if _execute_once(args):
                return
        except Exception as exc:
            if attempt >= args.retry_count:
                raise
            print(
                f"[再試行] {attempt}/{args.retry_count}回目が失敗しました。"
                f"{args.retry_interval_seconds}秒後に再実行します: {exc}"
            )
            time.sleep(args.retry_interval_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Oracleサーバーで日本株セクター資金流入Discord通知を送信する"
    )
    parser.add_argument("--slot", choices=["midday", "close", "auto"], default="auto")
    parser.add_argument(
        "--state-dir",
        default=str(BASE_DIR / "artifacts" / "sector_category_delivery"),
        help="配信成功マーカーを保存するディレクトリ。",
    )
    parser.add_argument(
        "--output-root",
        default=str(BASE_DIR / "artifacts" / "oracle_sector_category_discord"),
        help="実行ごとの画像と診断結果を保存するディレクトリ。",
    )
    parser.add_argument(
        "--webhook-env",
        default="DISCORD_OPTION_WEBHOOK_URL",
        help="Discord Webhook URLを読む環境変数名。",
    )
    parser.add_argument(
        "--mooview-base-url",
        default="https://mooview-oci.taild87712.ts.net",
        help="MooViewのHTTPS URL。",
    )
    parser.add_argument("--sector-page-port", type=int, default=0)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--refresh-wait-seconds", type=int, default=10)
    parser.add_argument("--viewport-width", type=int, default=1800)
    parser.add_argument("--viewport-height", type=int, default=1000)
    parser.add_argument("--probe-symbols", default="JP.1306,US.VOO")
    parser.add_argument("--retry-count", type=int, default=4)
    parser.add_argument("--retry-interval-seconds", type=int, default=600)
    parser.add_argument("--force", action="store_true", help="配信済みマーカーを無視して実行する。")
    parser.add_argument("--dry-run", action="store_true", help="撮影まで実行し、Discord送信は行わない。")
    parser.add_argument("--allow-weekend", action="store_true", help="土日でも実行する。検証用。")
    parser.add_argument(
        "--skip-fund-flow",
        action="store_true",
        help="MooView資金フロー撮影と送信を省略する。検証用。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.timeout_seconds < 30:
        raise SystemExit("--timeout-seconds は30以上を指定してください。")
    if not 10 <= args.refresh_wait_seconds <= 30:
        raise SystemExit("--refresh-wait-seconds は10以上30以下を指定してください。")
    if args.viewport_width < 1200 or args.viewport_height < 700:
        raise SystemExit("撮影領域は幅1200以上、高さ700以上を指定してください。")
    if args.retry_count < 1:
        raise SystemExit("--retry-count は1以上を指定してください。")
    if args.retry_interval_seconds < 1:
        raise SystemExit("--retry-interval-seconds は1以上を指定してください。")

    _run_with_retries(args)


if __name__ == "__main__":
    main()
