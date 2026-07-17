#!/usr/bin/env python3
"""note記事へアフィリエイト枠を挿入する内部ユーティリティ。"""

from __future__ import annotations

import random
import re
from pathlib import Path


AFFILIATE_SLOT_RE = re.compile(r"\[\[NOTION_NOTE_AFFILIATE_(\d{3})\]\]")


def _read_memo(path: Path, memo_number: int) -> str:
    if not path.exists():
        print(f"   [警告] アフィリエイトファイルが見つかりません: {path}")
        return ""
    parts = re.split(r"===MEMO(\d+)===", path.read_text(encoding="utf-8"))
    if len(parts) <= 1:
        return parts[0].strip()
    for index in range(1, len(parts), 2):
        if int(parts[index]) == memo_number:
            body = (parts[index + 1] if index + 1 < len(parts) else "").strip()
            return body.split("---", 1)[-1].strip()
    return ""


def _blocks(memo: str) -> list[str]:
    blocks = [block.strip() for block in re.split(r"(?=▼)", memo) if block.strip().startswith("▼")]
    return blocks or ([memo.strip()] if memo.strip() else [])


def _normalize(markdown: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", markdown).strip() + "\n"


def insert_affiliate_after_each_h2(
    markdown: str,
    affiliate_file: Path,
    memo_number: int,
    per_h2_count: int,
    seed: str = "",
) -> tuple[str, int]:
    """既存の枠を優先し、枠がない場合だけ各H2末尾へ挿入する。"""
    blocks = _blocks(_read_memo(affiliate_file, memo_number))
    slots = list(dict.fromkeys(match.group(0) for match in AFFILIATE_SLOT_RE.finditer(markdown)))
    if slots:
        if not blocks or per_h2_count <= 0:
            return _normalize(AFFILIATE_SLOT_RE.sub("", markdown)), 0
        rng = random.Random(seed) if seed else random.SystemRandom()
        selected = rng.sample(blocks, len(slots)) if len(blocks) >= len(slots) else [rng.choice(blocks) for _ in slots]
        for slot, block in zip(slots, selected):
            markdown = markdown.replace(slot, block, 1)
        return _normalize(markdown), len(selected)

    if not blocks or per_h2_count <= 0:
        return markdown, 0
    rng = random.Random(seed) if seed else random.SystemRandom()
    lines = markdown.splitlines(keepends=True)
    h2_indices = [index for index, line in enumerate(lines) if line.startswith("## ") and not line.startswith("### ")]
    insertions: list[tuple[int, str]] = []
    for order, h2_index in enumerate(h2_indices):
        next_h2_index = h2_indices[order + 1] if order + 1 < len(h2_indices) else len(lines)
        insert_index = next_h2_index
        while insert_index > h2_index + 1 and not lines[insert_index - 1].strip():
            insert_index -= 1
        selected = rng.sample(blocks, per_h2_count) if len(blocks) >= per_h2_count else [rng.choice(blocks) for _ in range(per_h2_count)]
        insertions.append((insert_index, "\n\n" + "\n\n".join(selected) + "\n\n"))
    for insert_index, block in reversed(insertions):
        lines[insert_index:insert_index] = [block]
    return "".join(lines), len(insertions) * per_h2_count
