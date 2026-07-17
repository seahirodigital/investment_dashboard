"""日本株・米国株の週間振り返り記事をnoteへ投稿する。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from note import note_blog_publisher as daily_note
from scripts.market.morning_discord_notification import (
    capture_weekly_finviz_heatmap,
)


GENERATED_DIR = BASE_DIR / "note" / "generated" / "weekend_market"
TOC_MARKER = daily_note.TOC_MARKER
AFFILIATE_SLOT_TEMPLATE = daily_note.AFFILIATE_SLOT_TEMPLATE
BODY_IMAGE_MARKER_TEMPLATE = daily_note.BODY_IMAGE_MARKER_TEMPLATE
NOTE_MAGAZINE_NAME = "日本株の振り返りまとめ "
DISCORD_NOTE_TITLE = "【今週の日本株・米国株投資セクター資金流入分析】"
DISCORD_TEMPLATE_TAGS = daily_note.DISCORD_TEMPLATE_TAGS

TITLE_TEMPLATE = "日本株今後の見通しと米国株の見通しを振り返りから分析：{date}"
INTRO_TEXT = """平日は毎日、日本株・米国株ランキングを元に日本取引時間内の、日本株ETFでおすすめ上位銘柄や、2026年の今後の見通しの日本株銘柄最新情報、今後上がる・伸びる銘柄投資分析のための、本日の日本株取引時間での数位・チャートから分析をまとめています。

また、毎日の記事内の投資戦略 by Geminiは、セクターランキング・株価変動・オプションの「データ」を読み込ませた上で、出力させています。

週末の 当記事では、

・日本株セクターごとに週次の各セクターでより強い・弱いETFランキング
・米国株セクターごとに週次の各セクターでより強い・弱いETFランキング
・先週の海外投資家の資金フロー
をまとめて配信します。

Trading Viewの無料版ではSP500の割返した複数銘柄を１つのチャートに表示できないため、多忙な方はフォローいただき、毎日日本株なら、TOPIX、米国株ならSP500ので割返したランキングを毎日見るだけでも、マクロ環境へのセクターフロー意識が違って来ると思います。"""

JAPAN_HEADING = "日本株今後の見通しと米国株の見通しを振り返りから分析：先週の日本株"
JAPAN_TEXT = """以下が直近の日本株のヒートマップと、先週１週間のセクターパフォーマンスです。
TOPIXで割返しているため、TOPIXから見てアウトパフォーム、アンダーパフォームしているかの確認にご利用ください。

また、半導体の中でも、半導体部品、素材、半導体装置、化学等がある中で、どのセクションに半導体投資の資金流入・流出したのかの参考にご利用ください。"""

US_HEADING = "日本株今後の見通しと米国株の見通しを振り返りから分析：先週の米国株"
US_TEXT = """以下が先週の米国株のヒートマップと、先週１週間のセクターパフォーマンスです。
SP500で割返しているため、SP500から見てアウトパフォーム、アンダーパフォームしているかの確認にご利用ください。"""

INVESTOR_HEADING = "日本株今後の見通しと米国株の見通しを振り返りから分析：先週の海外投資家動向（JPX・財務省）"
INVESTOR_TEXT = """海外投資家動向（JPX・財務省）は毎週木曜に東証から公開されます、日本市場では海外投資家（主に機関投資家）が７割と言われる市場のため、海外投資家の資金が流入・流出したのかは、翌週以降の日本株投資のランキングでおすすめETF分析をするうえで重要です。

その際の海外投資家の資金フローを各ETFの結果で感応度計算をした結果が以下です。どのセクターから資金流出/入したかの参考になります（つまり、先週まではどのセクターに海外投資家が投資をしていたのかということです。今週の情報は、下にある各セクターごとのチャートで確認します。）"""

SUMMARY_HEADING = "日本株今後の見通しと米国株の見通しを振り返りから分析：まとめ"
SUMMARY_TEXT = """いかがでしたでしょうか？毎日データをもとにAIを活用した市場分析と資金フローを確認しています。

本noteか以下のXでのフォローで最新の市場トレンドや、視覚的にわかりやすいお役立ち情報をいち早くキャッチしたい方は、ぜひ以下のリンクからフォローをお願いします。

https://x.com/RipplePhantom"""

MOOVIEW_WEEKLY_FILES = {
    "jp_sector_tpx": "weekend_jp_sector_tpx_w.png",
    "us_sector_spy": "weekend_us_sector_spy_w.png",
    "semiconductor_tpx": "weekend_semiconductor_tpx_w.png",
    "semiconductor_sector": "weekend_semiconductor_sector_w.png",
}


def _capture_with_retry(label: str, operation, attempts: int = 3):
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            print(
                f"   [再試行] {label}の生成に失敗しました"
                f"（{attempt}/{attempts}）: {exc}"
            )
            time.sleep(15)
    raise RuntimeError(
        f"{label}を{attempts}回試行しても生成できませんでした: {last_error}"
    ) from last_error


def _resolve_mooview_assets_dir(value: str = "") -> Path:
    raw_value = value.strip() or os.getenv("MOOVIEW_CAPTURE_DIR", "").strip()
    if not raw_value:
        raw_value = str(BASE_DIR / "artifacts" / "oci_mooview_capture")
    path = Path(raw_value).expanduser().resolve()
    missing = [
        file_name
        for file_name in MOOVIEW_WEEKLY_FILES.values()
        if not (path / file_name).is_file()
    ]
    if missing:
        raise FileNotFoundError(
            f"週末記事用のMooView画像が不足しています: {path} / {', '.join(missing)}"
        )
    return path


def _resolve_reused_nikkei_heatmap() -> Path | None:
    raw_value = os.getenv("WEEKEND_NIKKEI_HEATMAP_DIR", "").strip()
    if not raw_value:
        return None
    path = Path(raw_value).expanduser().resolve()
    if path.is_file() and path.name == "00_nikkei225_heatmap.png":
        return path
    if path.is_dir():
        candidates = sorted(
            path.rglob("00_nikkei225_heatmap.png"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return candidates[0]
    print(
        "[警告] 再利用する日経225ヒートマップが見つからないため、"
        f"週末投稿内で新規取得を試します: {path}"
    )
    return None


def _existing_image_path(value: Any) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if path.is_file():
        return path
    return None


def _weekly_mooview_images(assets_dir: Path) -> dict[str, Path]:
    return {
        key: assets_dir / file_name
        for key, file_name in MOOVIEW_WEEKLY_FILES.items()
    }


def _append_images(
    lines: list[str],
    uploads: list[dict[str, Any]],
    image_paths: list[Path],
    captions: list[str],
    start_index: int,
) -> int:
    if len(image_paths) != len(captions):
        raise ValueError("画像とキャプションの件数が一致しません。")
    next_index = start_index
    for image_path, caption in zip(image_paths, captions):
        marker = BODY_IMAGE_MARKER_TEMPLATE.format(index=next_index)
        lines.extend([marker, ""])
        uploads.append(daily_note._body_image_upload(image_path, marker, caption))
        next_index += 1
    return next_index


def build_weekend_markdown(
    date_display: str,
    *,
    nikkei_heatmap: Path,
    nikkei_heatmap_caption: str = "日本株 日経225ヒートマップ",
    weekly_finviz_heatmap: Path,
    mooview_images: dict[str, Path],
    investor_images: list[Path],
    skip_mooview_keys: set[str] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    title = TITLE_TEMPLATE.format(date=date_display)
    lines: list[str] = [
        f"# {title}",
        "",
        INTRO_TEXT,
        "",
        AFFILIATE_SLOT_TEMPLATE.format(index=1),
        "",
        daily_note.DISCLOSURE_TEXT,
        "",
        TOC_MARKER,
        "",
        f"## {JAPAN_HEADING}",
        "",
        JAPAN_TEXT,
        "",
    ]
    uploads: list[dict[str, Any]] = []
    image_index = 1
    skip_mooview_keys = skip_mooview_keys or set()
    japan_image_paths = [nikkei_heatmap]
    japan_captions = [nikkei_heatmap_caption]
    for key, caption in [
        ("jp_sector_tpx", "日本株 JPセクター TOPIX比 週間チャート"),
        ("semiconductor_tpx", "日本株 半導体 TOPIX比 週間チャート"),
        ("semiconductor_sector", "日本株 半導体セクター 週間チャート"),
    ]:
        if key in skip_mooview_keys:
            continue
        japan_image_paths.append(mooview_images[key])
        japan_captions.append(caption)
    image_index = _append_images(
        lines,
        uploads,
        japan_image_paths,
        japan_captions,
        image_index,
    )
    lines.extend(
        [
            AFFILIATE_SLOT_TEMPLATE.format(index=2),
            "",
            f"## {US_HEADING}",
            "",
            US_TEXT,
            "",
        ]
    )
    image_index = _append_images(
        lines,
        uploads,
        [
            mooview_images["us_sector_spy"],
            weekly_finviz_heatmap,
        ],
        [
            "米国株 USセクター SPY比 週間チャート",
            "米国株 S&P500 1-Week Performanceヒートマップ",
        ],
        image_index,
    )
    lines.extend(
        [
            AFFILIATE_SLOT_TEMPLATE.format(index=3),
            "",
            f"## {INVESTOR_HEADING}",
            "",
            INVESTOR_TEXT,
            "",
        ]
    )
    image_index = _append_images(
        lines,
        uploads,
        investor_images,
        [
            "海外投資家動向 JPX 資金フロー",
            "海外投資家動向 財務省 対内証券投資",
            "海外投資家動向 セクター別感応度",
        ],
        image_index,
    )
    lines.extend(
        [
            AFFILIATE_SLOT_TEMPLATE.format(index=4),
            "",
            f"## {SUMMARY_HEADING}",
            "",
            SUMMARY_TEXT,
        ]
    )
    return "\n".join(lines).strip() + "\n", uploads


def _note_url_from_result(result: dict[str, Any]) -> str:
    candidates = [
        result.get("published_url"),
        result.get("final_url"),
        result.get("note_url"),
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
        os.getenv("NOTE_DISCORD_WEBHOOK", "").strip()
        or os.getenv("DISCORD_OPTION_WEBHOOK_URL", "").strip()
    )
    note_url = _note_url_from_result(result)
    status: dict[str, Any] = {
        "attempted": False,
        "success": False,
        "note_url": note_url,
    }
    if not note_url:
        status["error"] = "note URLを取得できないためDiscord通知をスキップしました。"
        print(f"   [情報] {status['error']}")
        return status
    if not webhook_url:
        status["error"] = (
            "NOTE_DISCORD_WEBHOOK / DISCORD_OPTION_WEBHOOK_URL "
            "が未設定のためDiscord通知をスキップしました。"
        )
        print(f"   [情報] {status['error']}")
        return status

    prefix = "【下書き】" if mode != "publish" else ""
    message = (
        f"{prefix}{DISCORD_NOTE_TITLE}\n\n"
        f"{note_url}\n\n"
        f"{DISCORD_TEMPLATE_TAGS}"
    )
    status["attempted"] = True
    try:
        response = requests.post(webhook_url, json={"content": message}, timeout=15)
    except requests.RequestException as exc:
        status["error"] = str(exc)
        print(f"   [警告] Discord通知に失敗しました: {status['error']}")
        return status
    if 200 <= response.status_code < 300:
        status["success"] = True
        print("   [成功] 週末note URLをDiscordへ通知しました。")
        return status
    status["error"] = f"Discord API {response.status_code}: {response.text[:300]}"
    print(f"   [警告] Discord通知に失敗しました: {status['error']}")
    return status


def publish_weekend_note(
    *,
    date_value: str,
    mode: str,
    mooview_assets_dir: str = "",
    affiliate_memo: int = 1,
    affiliate_count: int = 1,
    affiliate_seed: str = "",
    reuse_assets: bool = False,
) -> dict[str, Any]:
    dashed_date, compact_date, display_date = daily_note._normalize_date(date_value)
    requested_mode = (mode or "skip").strip().lower().replace("_", "-")
    if requested_mode in {"none", "off", "false"}:
        requested_mode = "skip"
    post_mode = "draft" if requested_mode == "draft-note-only" else requested_mode
    if post_mode not in {"skip", "draft", "dry-run", "publish"}:
        raise ValueError(
            "NOTE_POST_MODE は skip / draft / draft-note-only / dry-run / publish "
            f"のいずれかを指定してください: {mode}"
        )
    if post_mode == "skip":
        return {
            "success": True,
            "skipped": True,
            "mode": requested_mode,
            "post_mode": post_mode,
            "date": dashed_date,
        }

    note_project_dir = daily_note._resolve_note_project_dir()
    run_dir = GENERATED_DIR / compact_date
    image_dir = run_dir / "images"
    run_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)

    reused_nikkei_heatmap = _resolve_reused_nikkei_heatmap()
    nikkei_heatmap_caption = "日本株 日経225ヒートマップ"
    nikkei_heatmap = (
        reused_nikkei_heatmap
        if reused_nikkei_heatmap is not None
        else image_dir / "00_nikkei225_heatmap.png"
    )
    if reused_nikkei_heatmap is not None:
        print(
            "   [情報] 既存Actionsの最新日経225ヒートマップを再利用します: "
            f"{nikkei_heatmap}"
        )
    elif not (reuse_assets and nikkei_heatmap.is_file()):
        print("   [情報] 週末記事用の日経225ヒートマップを生成します。")
        nikkei_assets = _capture_with_retry(
            "日経225ヒートマップ",
            lambda: daily_note.capture_nikkei225_chart_assets(image_dir),
        )
        heatmap_image = _existing_image_path(nikkei_assets.get("heatmap_image"))
        contribution_image = _existing_image_path(
            nikkei_assets.get("contribution_image")
        )
        if heatmap_image is not None:
            nikkei_heatmap = heatmap_image
            print(f"   [情報] 日経225ヒートマップを使用します: {nikkei_heatmap}")
        elif contribution_image is not None:
            nikkei_heatmap = contribution_image
            nikkei_heatmap_caption = "日本株 日経225寄与度ランキング"
            print(
                "[警告] 日経225ヒートマップを取得できないため、"
                f"寄与度ランキング画像で投稿を継続します: {nikkei_heatmap}"
            )
        else:
            print(
                "[警告] 日経225ヒートマップと寄与度ランキングを取得できませんでした。"
                "MooView週次チャートで投稿継続を試します。"
            )

    weekly_finviz_heatmap = image_dir / "finviz_heatmap_1week.png"
    if not (reuse_assets and weekly_finviz_heatmap.is_file()):
        print("   [情報] Finvizの1-Week Performanceヒートマップを生成します。")
        weekly_finviz_heatmap = _capture_with_retry(
            "Finviz 1-Week Performanceヒートマップ",
            lambda: capture_weekly_finviz_heatmap(image_dir),
        )

    investor_image_paths = [
        image_dir / "09_weekly_jpx_investor_flow.png",
        image_dir / "10_weekly_mof_inward_securities_1y.png",
        image_dir / "11_weekly_sector_sensitivity_3weeks.png",
    ]
    if not (reuse_assets and all(path.is_file() for path in investor_image_paths)):
        print("   [情報] 海外投資家動向の週次画像3枚を生成します。")
        investor_assets = _capture_with_retry(
            "海外投資家動向の週次画像",
            lambda: daily_note.capture_weekly_investor_assets(
                image_dir,
                dashed_date,
            ),
        )
        investor_image_paths = [
            Path(path) for path in investor_assets["images"]
        ]

    mooview_dir = _resolve_mooview_assets_dir(mooview_assets_dir)
    mooview_images = _weekly_mooview_images(mooview_dir)
    skip_mooview_keys: set[str] = set()
    if not nikkei_heatmap.is_file():
        nikkei_heatmap = mooview_images["jp_sector_tpx"]
        nikkei_heatmap_caption = "日本株 JPセクター TOPIX比 週間チャート"
        skip_mooview_keys.add("jp_sector_tpx")
        print(
            "[警告] 日経225画像が使えないため、"
            f"MooViewの日本株週次チャートをサムネイルと本文先頭に使います: {nikkei_heatmap}"
        )
    thumbnail_path = daily_note._create_note_thumbnail(
        nikkei_heatmap,
        image_dir / "00_weekend_note_thumbnail.jpg",
    )
    markdown, body_image_uploads = build_weekend_markdown(
        display_date,
        nikkei_heatmap=nikkei_heatmap,
        nikkei_heatmap_caption=nikkei_heatmap_caption,
        weekly_finviz_heatmap=weekly_finviz_heatmap,
        mooview_images=mooview_images,
        investor_images=investor_image_paths,
        skip_mooview_keys=skip_mooview_keys,
    )
    markdown, affiliate_insertions = daily_note._apply_affiliate_links(
        markdown,
        note_project_dir,
        memo_number=affiliate_memo,
        affiliate_count=affiliate_count,
        seed=affiliate_seed or compact_date,
    )

    markdown_path = run_dir / "note_article.md"
    markdown_path.write_text(markdown, encoding="utf-8")
    print(f"   [情報] 週末note記事Markdownを書き出しました: {markdown_path}")

    os.environ["NOTE_PUBLISH_MAGAZINE_NAME"] = os.getenv(
        "NOTE_PUBLISH_MAGAZINE_NAME",
        NOTE_MAGAZINE_NAME,
    )
    result = daily_note._post_to_note(
        markdown,
        note_project_dir=note_project_dir,
        mode=post_mode,
        thumbnail_path=thumbnail_path,
        body_image_uploads=body_image_uploads,
    )
    result["discord_notification"] = _notify_discord_after_note(
        result,
        mode=post_mode,
    )
    result.update(
        {
            "mode": requested_mode,
            "post_mode": post_mode,
            "date": dashed_date,
            "markdown_path": str(markdown_path),
            "thumbnail_path": str(thumbnail_path),
            "body_image_count": len(body_image_uploads),
            "affiliate_insertions": affiliate_insertions,
            "note_project_dir": str(note_project_dir),
            "mooview_assets_dir": str(mooview_dir),
        }
    )
    result_path = run_dir / "note_post_result.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"   [情報] 週末note投稿結果を書き出しました: {result_path}")
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="日本株・米国株の週間振り返りをnoteとDiscordへ配信する"
    )
    parser.add_argument(
        "--date",
        default=os.getenv("NOTE_POST_DATE", ""),
        help="記事日付。YYYY-MM-DD または YYYYMMDD",
    )
    parser.add_argument(
        "--mode",
        default=os.getenv("NOTE_POST_MODE", "dry-run"),
        choices=["skip", "draft", "draft-note-only", "dry-run", "publish"],
    )
    parser.add_argument(
        "--mooview-assets-dir",
        default=os.getenv("MOOVIEW_CAPTURE_DIR", ""),
        help="MooViewのW表示4画像があるフォルダー",
    )
    parser.add_argument(
        "--affiliate-memo",
        type=int,
        default=int(os.getenv("NOTE_AFFILIATE_MEMO", "1")),
    )
    parser.add_argument(
        "--affiliate-count",
        type=int,
        default=int(os.getenv("NOTE_AFFILIATE_COUNT", "1")),
    )
    parser.add_argument(
        "--affiliate-seed",
        default=os.getenv("NOTE_AFFILIATE_SEED", ""),
    )
    parser.add_argument(
        "--reuse-assets",
        action="store_true",
        help="生成済み画像があれば再利用する",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = publish_weekend_note(
        date_value=args.date,
        mode=args.mode,
        mooview_assets_dir=args.mooview_assets_dir,
        affiliate_memo=args.affiliate_memo,
        affiliate_count=args.affiliate_count,
        affiliate_seed=args.affiliate_seed,
        reuse_assets=args.reuse_assets,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2)[:4000])
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
