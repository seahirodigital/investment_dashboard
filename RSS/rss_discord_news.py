"""RSSニュースを取得し、Discordへ時間帯制御つきで配信するスクリプト。"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
import requests

try:
    from zoneinfo import ZoneInfo

    JST = ZoneInfo("Asia/Tokyo")
except ImportError:
    JST = timezone(timedelta(hours=9), "Asia/Tokyo")


if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


STATE_VERSION = 1
MIN_FETCH_INTERVAL_SECONDS = 10 * 60
MAX_SEEN_IDS = 800
DISCORD_CONTENT_LIMIT = 1900

FEEDS = [
    {
        "name": "ブルームバーグ",
        "url": "https://assets.wor.jp/rss/rdf/bloomberg/markets.rdf",
    },
    {
        "name": "ロイター",
        "url": "https://assets.wor.jp/rss/rdf/reuters/top.rdf",
    },
]

USER_AGENT = (
    "investment-dashboard-rss-news/1.0 "
    "(GitHub Actions; RSS hourly fetch; Discord notification)"
)


@dataclass(frozen=True)
class NewsItem:
    item_id: str
    source: str
    title: str
    link: str
    published_at: str | None
    fetched_at: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "id": self.item_id,
            "source": self.source,
            "title": self.title,
            "link": self.link,
            "published_at": self.published_at,
            "fetched_at": self.fetched_at,
        }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _isoformat_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    text = value.strip()
    if not text:
        return None

    try:
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        pass

    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _child_text(node: ET.Element, names: set[str]) -> str:
    for child in list(node):
        if _local_name(child.tag).lower() in names:
            return _normalize_text(child.text)
    return ""


def _attribute_value(node: ET.Element, names: set[str]) -> str:
    for key, value in node.attrib.items():
        if _local_name(key).lower() in names:
            return _normalize_text(value)
    return ""


def _make_item_id(source: str, raw_id: str, title: str, link: str) -> str:
    base = raw_id or link or f"{source}:{title}"
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()
    return f"{source}:{digest[:32]}"


def _sort_key(item: NewsItem) -> tuple[datetime, str]:
    parsed = _parse_datetime(item.published_at) or _parse_datetime(item.fetched_at)
    if parsed is None:
        parsed = datetime.min.replace(tzinfo=timezone.utc)
    return parsed, item.item_id


def _format_datetime_for_message(value: str | None) -> str:
    parsed = _parse_datetime(value)
    if parsed is None:
        return ""
    return parsed.astimezone(JST).strftime("%Y/%m/%d/%H:%M")


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "version": STATE_VERSION,
            "feeds": {},
            "seen_ids": [],
            "pending_items": [],
        }

    with path.open("r", encoding="utf-8") as handle:
        state = json.load(handle)

    state.setdefault("version", STATE_VERSION)
    state.setdefault("feeds", {})
    state.setdefault("seen_ids", [])
    state.setdefault("pending_items", [])
    return state


def save_state(path: Path, state: dict[str, Any]) -> None:
    state["version"] = STATE_VERSION
    state["seen_ids"] = list(dict.fromkeys(state.get("seen_ids", [])))[-MAX_SEEN_IDS:]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def should_fetch(feed_state: dict[str, Any], now: datetime) -> bool:
    last_fetch_at = _parse_datetime(feed_state.get("last_fetch_at"))
    if last_fetch_at is None:
        return True
    elapsed = (now - last_fetch_at).total_seconds()
    return elapsed >= MIN_FETCH_INTERVAL_SECONDS


def parse_feed_content(feed: dict[str, str], content: bytes, now: datetime) -> list[NewsItem]:
    root = ET.fromstring(content)
    fetched_at = _isoformat_utc(now)
    items: list[NewsItem] = []

    for node in root.findall(".//{*}item"):
        title = _child_text(node, {"title"})
        link = _child_text(node, {"link"})
        if not title:
            continue

        raw_id = (
            _child_text(node, {"guid", "id"})
            or _attribute_value(node, {"about"})
            or link
            or title
        )
        published_text = _child_text(node, {"pubdate", "date", "updated", "published"})
        published_at = None
        published_datetime = _parse_datetime(published_text)
        if published_datetime is not None:
            published_at = _isoformat_utc(published_datetime)

        items.append(
            NewsItem(
                item_id=_make_item_id(feed["name"], raw_id, title, link),
                source=feed["name"],
                title=title,
                link=link,
                published_at=published_at,
                fetched_at=fetched_at,
            )
        )

    return sorted(items, key=_sort_key)


def fetch_feed(feed: dict[str, str], now: datetime) -> list[NewsItem]:
    response = requests.get(
        feed["url"],
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/rdf+xml, application/xml;q=0.9, */*;q=0.8",
        },
        timeout=30,
    )
    response.raise_for_status()
    return parse_feed_content(feed, response.content, now)


def is_delivery_time(now: datetime) -> bool:
    now_jst = now.astimezone(JST)
    return 6 <= now_jst.hour < 24


def add_pending_items(state: dict[str, Any], items: list[NewsItem]) -> int:
    seen_id_list = list(dict.fromkeys(state.get("seen_ids", [])))
    seen_ids = set(seen_id_list)
    pending_items = state.setdefault("pending_items", [])
    pending_ids = {item.get("id") for item in pending_items}
    added = 0

    for item in items:
        if item.item_id in seen_ids or item.item_id in pending_ids:
            continue
        pending_items.append(item.to_dict())
        seen_ids.add(item.item_id)
        seen_id_list.append(item.item_id)
        pending_ids.add(item.item_id)
        added += 1

    state["seen_ids"] = list(dict.fromkeys(seen_id_list))[-MAX_SEEN_IDS:]
    return added


def _pending_to_items(state: dict[str, Any]) -> list[NewsItem]:
    result: list[NewsItem] = []
    for item in state.get("pending_items", []):
        if not isinstance(item, dict):
            continue
        result.append(
            NewsItem(
                item_id=str(item.get("id", "")),
                source=str(item.get("source", "")),
                title=str(item.get("title", "")),
                link=str(item.get("link", "")),
                published_at=item.get("published_at"),
                fetched_at=str(item.get("fetched_at", "")),
            )
        )
    return sorted(result, key=_sort_key)


def build_discord_messages(items: list[NewsItem], now: datetime) -> list[str]:
    if not items:
        return []

    timestamp = now.astimezone(JST).strftime("%Y-%m-%d %H:%M JST")
    header = f"NEWS配信\n{timestamp}\n"
    messages: list[str] = []
    current = header

    for item in items:
        published = _format_datetime_for_message(item.published_at)
        title = _truncate(item.title, 220)
        lines = []
        if published:
            lines.append(published)
        lines.append(title)
        if item.link:
            lines.append(item.link)
        block = "\n" + "\n".join(lines) + "\n"

        if len(current) + len(block) > DISCORD_CONTENT_LIMIT:
            messages.append(current.rstrip())
            current = header + block
        else:
            current += block

    if current.strip():
        messages.append(current.rstrip())

    return messages


def _normalize_webhook_url(webhook_url: str) -> str:
    return webhook_url.replace(
        "https://discordapp.com/api/webhooks/",
        "https://discord.com/api/webhooks/",
        1,
    )


def send_to_discord(webhook_url: str, messages: list[str]) -> None:
    if not webhook_url:
        raise RuntimeError("Discord Webhook URLが設定されていません。")

    normalized_webhook_url = _normalize_webhook_url(webhook_url)

    for index, message in enumerate(messages, start=1):
        payload = {
            "content": message,
            "allowed_mentions": {"parse": []},
        }

        try:
            response = requests.post(
                normalized_webhook_url,
                json=payload,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Discord送信に失敗しました: {exc.__class__.__name__}") from None

        if response.status_code == 429:
            retry_after = response.json().get("retry_after", 1)
            time.sleep(float(retry_after) + 0.5)
            try:
                response = requests.post(
                    normalized_webhook_url,
                    json=payload,
                    timeout=30,
                )
            except requests.RequestException as exc:
                raise RuntimeError(f"Discord再送信に失敗しました: {exc.__class__.__name__}") from None

        if response.status_code >= 400:
            raise RuntimeError(
                f"Discord送信に失敗しました: HTTP {response.status_code} {response.text[:500]}"
            )

        print(f"DiscordへNEWS配信を送信しました: {index}/{len(messages)}")
        time.sleep(0.8)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RSSニュースをDiscordへ配信します。")
    parser.add_argument(
        "--state-path",
        default=str(Path(__file__).resolve().parent / "news_state.json"),
        help="状態JSONの保存先です。",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="配信可能時間帯にDiscordへ送信します。",
    )
    parser.add_argument(
        "--webhook-env",
        default="DISCORD_NEWS_WEBHOOK_URL",
        help="Discord Webhook URLを読む環境変数名です。",
    )
    parser.add_argument(
        "--now",
        default="",
        help="テスト用の現在時刻です。ISO 8601形式で指定します。",
    )
    parser.add_argument(
        "--test-message",
        action="store_true",
        help="RSS取得を行わず、Discordへの疎通確認メッセージだけを送信します。",
    )
    return parser.parse_args()


def resolve_now(value: str) -> datetime:
    if not value:
        return _utc_now()
    parsed = _parse_datetime(value)
    if parsed is None:
        raise ValueError(f"現在時刻を解釈できません: {value}")
    return parsed.replace(microsecond=0)


def main() -> int:
    args = parse_args()
    state_path = Path(args.state_path)
    now = resolve_now(args.now)

    if args.test_message:
        message = "\n".join(
            [
                "NEWS配信テスト",
                now.astimezone(JST).strftime("%Y-%m-%d %H:%M JST"),
                "RSS NEWS配信用Webhookの疎通確認です。",
            ]
        )
        if args.send:
            webhook_url = os.environ.get(args.webhook_env, "")
            try:
                send_to_discord(webhook_url, [message])
                print("Discordへのテスト通知が完了しました。")
            except Exception as exc:
                print(f"Discordへのテスト通知に失敗しました: {exc}", file=sys.stderr)
                return 1
        else:
            print(message)
        return 0

    state = load_state(state_path)
    exit_code = 0

    try:
        for feed in FEEDS:
            feed_state = state.setdefault("feeds", {}).setdefault(feed["url"], {})
            if not should_fetch(feed_state, now):
                print(f"{feed['name']} は1時間以内に取得済みのためスキップしました。")
                continue

            feed_state["last_fetch_at"] = _isoformat_utc(now)
            feed_state.pop("last_error", None)

            try:
                items = fetch_feed(feed, now)
                added = add_pending_items(state, items)
                print(f"{feed['name']} を取得しました: 新規 {added} 件 / RSS内 {len(items)} 件")
            except Exception as exc:
                feed_state["last_error"] = str(exc)
                exit_code = 1
                print(f"{feed['name']} の取得に失敗しました: {exc}", file=sys.stderr)

        pending_items = _pending_to_items(state)
        delivery_time = is_delivery_time(now)
        if not delivery_time:
            print(f"現在は夜間保留時間帯です。未配信NEWS {len(pending_items)} 件を保持します。")
            return exit_code

        if not pending_items:
            print("配信対象のNEWSはありません。")
            return exit_code

        messages = build_discord_messages(pending_items, now)
        if not args.send:
            print(f"Discord送信は未指定です。配信予定メッセージ {len(messages)} 件を作成しました。")
            return exit_code

        webhook_url = os.environ.get(args.webhook_env, "")
        try:
            send_to_discord(webhook_url, messages)
            state["pending_items"] = []
            print(f"DiscordへのNEWS配信が完了しました: {len(pending_items)} 件")
        except Exception as exc:
            exit_code = 1
            print(f"DiscordへのNEWS配信に失敗しました。未配信NEWSを保持します: {exc}", file=sys.stderr)

        return exit_code
    finally:
        save_state(state_path, state)
        print(f"状態JSONを保存しました: {state_path.resolve()}")


if __name__ == "__main__":
    raise SystemExit(main())
