"""RSSニュースタイトルを米国・日本の重要度印とFXタグへ仕分ける判定器。"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RULES_PATH = Path(__file__).resolve().with_name("rules.json")


@dataclass(frozen=True)
class LevelMatch:
    key: str
    label: str
    level: int
    level_label: str
    marker: str
    matched_terms: tuple[str, ...]


def normalize_text(value: str | None) -> str:
    """全角英数や表記ゆれを寄せ、英字は大小を無視して比較できる形にします。"""

    if not value:
        return ""
    return unicodedata.normalize("NFKC", value).casefold()


def load_rules(path: str | Path | None = None) -> dict[str, Any]:
    rules_path = Path(path) if path else RULES_PATH
    with rules_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _compile_pattern(pattern: str) -> re.Pattern[str]:
    normalized = unicodedata.normalize("NFKC", pattern)
    return re.compile(normalized, re.IGNORECASE)


def _keyword_matches(text: str, keywords: list[str]) -> list[str]:
    matches: list[str] = []
    seen_normalized: set[str] = set()
    for keyword in keywords:
        normalized_keyword = normalize_text(keyword)
        if (
            normalized_keyword
            and normalized_keyword in text
            and normalized_keyword not in seen_normalized
        ):
            matches.append(keyword)
            seen_normalized.add(normalized_keyword)
    return matches


def _regex_matches(text: str, patterns: list[str]) -> list[str]:
    matches: list[str] = []
    for pattern in patterns:
        if _compile_pattern(pattern).search(text):
            matches.append(pattern)
    return matches


def _apply_keyword_exclusions(
    text: str,
    matched_terms: list[str],
    exclusions: list[dict[str, Any]],
) -> list[str]:
    filtered = list(matched_terms)
    for exclusion in exclusions:
        keyword = str(exclusion.get("keyword", ""))
        normalized_keyword = normalize_text(keyword)
        if not normalized_keyword:
            continue
        blocked_by = [normalize_text(item) for item in exclusion.get("blocked_by", [])]
        if any(blocker and blocker in text for blocker in blocked_by):
            filtered = [
                term for term in filtered if normalize_text(term) != normalized_keyword
            ]
    return filtered


def _match_terms(text: str, rule_block: dict[str, Any]) -> list[str]:
    terms = _keyword_matches(text, list(rule_block.get("keywords", [])))
    terms.extend(_regex_matches(text, list(rule_block.get("regex_patterns", []))))
    return list(dict.fromkeys(terms))


def _match_category(text: str, key: str, category: dict[str, Any]) -> LevelMatch | None:
    symbol = str(category.get("symbol", ""))
    label = str(category.get("label", key))
    exclusions = list(category.get("keyword_exclusions", []))
    levels = category.get("levels", {})

    for level in sorted((int(value) for value in levels.keys()), reverse=True):
        level_rule = levels.get(str(level), {})
        if not isinstance(level_rule, dict):
            continue
        matched_terms = _match_terms(text, level_rule)
        matched_terms = _apply_keyword_exclusions(text, matched_terms, exclusions)
        if matched_terms:
            return LevelMatch(
                key=key,
                label=label,
                level=level,
                level_label=str(level_rule.get("label", "")),
                marker=symbol * level,
                matched_terms=tuple(matched_terms),
            )

    fallback_terms = _keyword_matches(text, list(category.get("fallback_keywords", [])))
    fallback_terms = _apply_keyword_exclusions(text, fallback_terms, exclusions)
    if fallback_terms:
        fallback_level = int(category.get("fallback_level", 1))
        return LevelMatch(
            key=key,
            label=label,
            level=fallback_level,
            level_label="地域キーワード",
            marker=symbol * fallback_level,
            matched_terms=tuple(dict.fromkeys(fallback_terms)),
        )

    return None


def _match_tags(text: str, rules: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tag_matches: dict[str, dict[str, Any]] = {}
    for key, tag_rule in rules.get("tags", {}).items():
        if not isinstance(tag_rule, dict):
            continue
        terms = _match_terms(text, tag_rule)
        if terms:
            tag_matches[key] = {
                "label": str(tag_rule.get("label", key)),
                "marker": str(tag_rule.get("marker", "")),
                "matched_terms": terms,
            }
    return tag_matches


def _match_context_tags(text: str, rules: dict[str, Any]) -> dict[str, list[str]]:
    context_matches: dict[str, list[str]] = {}
    for key, context in rules.get("context_tags", {}).items():
        if not isinstance(context, dict):
            continue
        terms = _match_terms(text, context)
        if terms:
            context_matches[key] = list(dict.fromkeys(terms))
    return context_matches


def classify_news_text(text: str, rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """タイトルなどの通知文から、付与すべき重要度印とタグを返します。"""

    active_rules = rules or load_rules()
    normalized = normalize_text(text)
    categories = active_rules.get("categories", {})
    marker_order = list(active_rules.get("marker_order", categories.keys()))
    matches_by_key: dict[str, LevelMatch] = {}

    for key in marker_order:
        category = categories.get(key)
        if not isinstance(category, dict):
            continue
        match = _match_category(normalized, key, category)
        if match:
            matches_by_key[key] = match

    ordered_matches = [matches_by_key[key] for key in marker_order if key in matches_by_key]
    tag_matches = _match_tags(normalized, active_rules)
    markers = [match.marker for match in ordered_matches]
    tag_markers = [
        str(tag.get("marker", ""))
        for tag in tag_matches.values()
        if tag.get("marker")
    ]
    marker = "".join(markers + tag_markers)
    labels = [match.label for match in ordered_matches]
    status = "classified" if ordered_matches or tag_matches else "unclassified"
    matched_terms = {
        match.key: list(match.matched_terms)
        for match in ordered_matches
    }
    levels = {
        match.key: {
            "label": match.label,
            "level": match.level,
            "level_label": match.level_label,
            "marker": match.marker,
        }
        for match in ordered_matches
    }

    reason_parts = [
        f"{match.label}{match.level}: {', '.join(match.matched_terms)}"
        for match in ordered_matches
    ]
    for tag in tag_matches.values():
        reason_parts.append(
            f"{tag.get('label')}: {', '.join(str(term) for term in tag.get('matched_terms', []))}"
        )

    return {
        "status": status,
        "marker": marker,
        "region_marker": "".join(markers),
        "tag_marker": "".join(tag_markers),
        "labels": labels,
        "primary": labels[0] if labels else None,
        "levels": levels,
        "matched_terms": matched_terms,
        "tags": tag_matches,
        "context_tags": _match_context_tags(normalized, active_rules),
        "reason": " / ".join(reason_parts),
    }


def marker_for_news_text(text: str, rules: dict[str, Any] | None = None) -> str:
    return str(classify_news_text(text, rules).get("marker", ""))


def format_discord_date_line(
    published_display: str,
    title: str,
    rules: dict[str, Any] | None = None,
) -> str:
    """Discord通知の日時行へ、判定済みの重要度印とタグを差し込みます。"""

    marker = marker_for_news_text(title, rules)
    if not published_display:
        return marker
    if not marker:
        return published_display
    return f"{published_display}　{marker}"
