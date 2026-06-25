#!/usr/bin/env python3
"""note公開ボタンのクリック戦略を投資ダッシュボード側で統一する。"""

from __future__ import annotations

from typing import Any


def _click_publish_next_role_button_first(note_engine: Any, page: Any) -> str:
    """米国株記事で成功している「公開に進む」通常クリックに寄せる。"""

    candidates = [
        ("role_button_公開に進む", page.get_by_role("button", name="公開に進む")),
        ("button_text_公開に進む", page.locator("button").filter(has_text="公開に進む")),
    ]
    errors: list[str] = []

    for strategy, locator in candidates:
        try:
            total = locator.count()
        except Exception as exc:
            errors.append(f"{strategy}: count失敗={exc}")
            continue

        for index in range(total - 1, -1, -1):
            candidate = locator.nth(index)
            candidate_strategy = f"{strategy}#{index}"
            try:
                candidate.wait_for(state="visible", timeout=1500)
                candidate.scroll_into_view_if_needed(timeout=4000)
                if not candidate.is_enabled(timeout=500):
                    errors.append(f"{candidate_strategy}: disabled")
                    continue
                candidate.click(timeout=10_000)
                page.wait_for_timeout(1000)
                print(f"   ✅ 公開に進む: {candidate_strategy} (通常click)")
                return candidate_strategy
            except Exception as exc:
                errors.append(f"{candidate_strategy}: 通常click失敗={exc}")

    raise RuntimeError("公開に進む を通常クリックできませんでした: " + " / ".join(errors[:6]))


def patch_note_publisher_publish_next(publisher: Any) -> Any:
    """notion2note の note_engine 読み込み時に公開ボタン戦略だけ差し替える。"""

    original_load_note_engine = publisher._load_note_engine

    def patched_load_note_engine() -> Any:
        note_engine = original_load_note_engine()
        if getattr(note_engine, "_investment_dashboard_publish_button_patch", False):
            return note_engine

        def patched_click_publish_next(page: Any) -> str:
            return _click_publish_next_role_button_first(note_engine, page)

        note_engine._click_publish_next = patched_click_publish_next
        note_engine._investment_dashboard_publish_button_patch = True
        print("   [情報] note公開ボタン戦略を role_button 通常click 優先に統一しました")
        return note_engine

    publisher._load_note_engine = patched_load_note_engine
    return publisher
