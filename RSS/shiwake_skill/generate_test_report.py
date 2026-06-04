"""過去RSS配信ログを日米仕訳し、確認しやすいMarkdownを生成します。"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from classifier import classify_news_text, load_rules


BASE_DIR = Path(__file__).resolve().parent
RSS_DIR = BASE_DIR.parent
DEFAULT_LOG_PATH = RSS_DIR / "news_delivery_log.jsonl"
DEFAULT_OUTPUT_PATH = BASE_DIR / "testfile.md"
DEFAULT_FULL_OUTPUT_PATH = BASE_DIR / "testfile_full.md"
SAMPLE_LIMIT_PER_GROUP = 20


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                record = json.loads(text)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"{path.resolve()} の {line_number} 行目をJSONとして読めません: {exc}") from exc
            if isinstance(record, dict):
                records.append(record)
    return records


def _escape_markdown(value: Any) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\n", " ")
        .replace("\r", " ")
    )


def _classification_label(result: dict[str, Any]) -> str:
    labels = result.get("labels") or []
    return "+".join(str(label) for label in labels) if labels else "無印"


def _matched_terms_text(result: dict[str, Any]) -> str:
    matched_terms = result.get("matched_terms") or {}
    parts: list[str] = []
    for key, terms in matched_terms.items():
        if not terms:
            continue
        parts.append(f"{key}: {', '.join(str(term) for term in terms)}")
    return " / ".join(parts)


def _tags_text(result: dict[str, Any]) -> str:
    tags = result.get("tags") or {}
    parts: list[str] = []
    for key, tag in tags.items():
        marker = str(tag.get("marker", ""))
        terms = tag.get("matched_terms") or []
        if marker:
            parts.append(f"{key}: {marker} {', '.join(str(term) for term in terms)}")
    return " / ".join(parts)


def _context_text(result: dict[str, Any]) -> str:
    context_tags = result.get("context_tags") or {}
    parts: list[str] = []
    for key, terms in context_tags.items():
        if terms:
            parts.append(f"{key}: {', '.join(str(term) for term in terms)}")
    return " / ".join(parts)


def _classify_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter[str], Counter[str], Counter[str], Counter[str]]:
    rules = load_rules()
    rows: list[dict[str, Any]] = []
    marker_counter: Counter[str] = Counter()
    label_counter: Counter[str] = Counter()
    keyword_counter: Counter[str] = Counter()
    context_counter: Counter[str] = Counter()

    for index, record in enumerate(records, start=1):
        title = str(record.get("title", ""))
        result = classify_news_text(title, rules)
        marker = str(result.get("marker") or "無印")
        label = _classification_label(result)
        marker_counter[marker] += 1
        label_counter[label] += 1
        for terms in (result.get("matched_terms") or {}).values():
            for term in terms:
                keyword_counter[str(term)] += 1
        for key, terms in (result.get("context_tags") or {}).items():
            if terms:
                context_counter[key] += 1
        rows.append(
            {
                "index": index,
                "published_display": record.get("published_display") or "",
                "marker": marker,
                "region_marker": str(result.get("region_marker") or "無印"),
                "tag_marker": str(result.get("tag_marker") or ""),
                "label": label,
                "source": record.get("source") or "",
                "matched_terms": _matched_terms_text(result),
                "tags": _tags_text(result),
                "context": _context_text(result),
                "title": title,
                "link": record.get("link") or "",
            }
        )

    return rows, marker_counter, label_counter, keyword_counter, context_counter


def _append_counter_table(lines: list[str], title: str, left_name: str, counter: Counter[str], limit: int | None = None) -> None:
    lines.extend(["", f"## {title}", "", f"|{left_name}|件数|", "|---|---:|"])
    items = counter.most_common(limit)
    if not items:
        lines.append("|なし|0|")
        return
    for key, count in items:
        lines.append(f"|{_escape_markdown(key)}|{count}|")


def _append_rows_table(lines: list[str], title: str, rows: list[dict[str, Any]]) -> None:
    lines.extend(
        [
            "",
            f"## {title}",
            "",
            "|No|日時|印|分類|ソース|一致語|タグ|参考タグ|タイトル|",
            "|---:|---|---|---|---|---|---|---|---|",
        ]
    )
    if not rows:
        lines.append("|-|-|-|-|-|-|-|-|なし|")
        return
    for row in rows:
        lines.append(
            "|{index}|{published_display}|{marker}|{label}|{source}|{matched_terms}|{tags}|{context}|{title}|".format(
                index=row["index"],
                published_display=_escape_markdown(row["published_display"]),
                marker=_escape_markdown(row["marker"]),
                label=_escape_markdown(row["label"]),
                source=_escape_markdown(row["source"]),
                matched_terms=_escape_markdown(row["matched_terms"]),
                tags=_escape_markdown(row["tags"]),
                context=_escape_markdown(row["context"]),
                title=_escape_markdown(row["title"]),
            )
        )


def build_summary_report(
    rows: list[dict[str, Any]],
    marker_counter: Counter[str],
    label_counter: Counter[str],
    keyword_counter: Counter[str],
    context_counter: Counter[str],
    log_path: Path,
    output_path: Path,
    full_output_path: Path,
) -> str:
    generated_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    lines: list[str] = [
        "# RSS日米仕訳テスト結果",
        "",
        "## 目的",
        "",
        "Discord通知前に、過去RSSログへ米国フラグ `★★★` と日本フラグ `●●●` を試験付与し、どの単語で仕分けられたか確認するための軽量レポートです。",
        "",
        "## 対象",
        "",
        f"- 対象ログ: `{log_path.resolve()}`",
        f"- 軽量結果: `{output_path.resolve()}`",
        f"- 全件結果: `{full_output_path.resolve()}`",
        f"- 生成日時: `{generated_at}`",
        f"- 対象件数: `{len(rows)}`",
        "",
        "## 開きやすくした変更",
        "",
        "- `testfile.md` は集計と代表例だけにしました。",
        "- 全666件の詳細は `testfile_full.md` に分けました。",
        "- 米国は `★`、日本は `●` で、数が重要度を表します。",
        "- 指標系は2つ、政策・要人・金利・債券系は3つ、個別株系は1つです。",
        "- 通貨系は国別印とは別に `【FX】` を付けます。",
        "- 韓国系ニュースは参考タグだけ付け、米国・日本キーワードがなければ無印にしています。",
    ]

    _append_counter_table(lines, "判定件数", "印", marker_counter)
    _append_counter_table(lines, "分類件数", "分類", label_counter)
    _append_counter_table(lines, "一致語トップ30", "一致語", keyword_counter, 30)
    _append_counter_table(lines, "韓国系参考タグ", "タグ", context_counter)

    grouped_samples = [
        ("米国レベル3代表例", [row for row in rows if row["region_marker"] == "★★★"]),
        ("米国レベル2代表例", [row for row in rows if row["region_marker"] == "★★"]),
        ("米国レベル1代表例", [row for row in rows if row["region_marker"] == "★"]),
        ("日本レベル3代表例", [row for row in rows if row["region_marker"] == "●●●"]),
        ("日本レベル2代表例", [row for row in rows if row["region_marker"] == "●●"]),
        ("日本レベル1代表例", [row for row in rows if row["region_marker"] == "●"]),
        ("FXタグ代表例", [row for row in rows if row["tag_marker"]]),
        ("無印代表例", [row for row in rows if row["region_marker"] == "無印" and not row["tag_marker"]]),
        ("韓国系参考タグ代表例", [row for row in rows if row["context"]]),
    ]
    for title, group_rows in grouped_samples:
        _append_rows_table(lines, title, group_rows[:SAMPLE_LIMIT_PER_GROUP])

    lines.append("")
    return "\n".join(lines)


def build_full_report(
    rows: list[dict[str, Any]],
    log_path: Path,
    full_output_path: Path,
) -> str:
    generated_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    lines: list[str] = [
        "# RSS日米仕訳テスト全件結果",
        "",
        f"- 対象ログ: `{log_path.resolve()}`",
        f"- 出力ファイル: `{full_output_path.resolve()}`",
        f"- 生成日時: `{generated_at}`",
        f"- 対象件数: `{len(rows)}`",
        "",
        "## 全件仕訳",
        "",
        "|No|日時|印|分類|ソース|一致語|タグ|参考タグ|タイトル|URL|",
        "|---:|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "|{index}|{published_display}|{marker}|{label}|{source}|{matched_terms}|{tags}|{context}|{title}|{link}|".format(
                index=row["index"],
                published_display=_escape_markdown(row["published_display"]),
                marker=_escape_markdown(row["marker"]),
                label=_escape_markdown(row["label"]),
                source=_escape_markdown(row["source"]),
                matched_terms=_escape_markdown(row["matched_terms"]),
                tags=_escape_markdown(row["tags"]),
                context=_escape_markdown(row["context"]),
                title=_escape_markdown(row["title"]),
                link=_escape_markdown(row["link"]),
            )
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="RSS過去ログを日米仕訳してMarkdownへ出力します。")
    parser.add_argument("--log-path", default=str(DEFAULT_LOG_PATH), help="解析対象のJSONLログ完全フルパス")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="軽量Markdownの完全フルパス")
    parser.add_argument("--full-output", default=str(DEFAULT_FULL_OUTPUT_PATH), help="全件Markdownの完全フルパス")
    args = parser.parse_args()

    log_path = Path(args.log_path)
    output_path = Path(args.output)
    full_output_path = Path(args.full_output)
    records = _read_jsonl(log_path)
    rows, marker_counter, label_counter, keyword_counter, context_counter = _classify_records(records)

    summary_report = build_summary_report(
        rows,
        marker_counter,
        label_counter,
        keyword_counter,
        context_counter,
        log_path,
        output_path,
        full_output_path,
    )
    full_report = build_full_report(rows, log_path, full_output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(summary_report)
    with full_output_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(full_report)

    print(f"RSS日米仕訳テスト軽量版を出力しました: {output_path.resolve()}")
    print(f"RSS日米仕訳テスト全件版を出力しました: {full_output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
