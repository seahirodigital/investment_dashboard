"""
市場分析自動実行スクリプト (Gemini 3.5 Flash)

データ取得済みのJSONファイルを読み込み、Gemini APIで分析・レポート生成を行う。
レポートは market_analysis/reports/ に保存し、オプションでGistの投資カレンダー「情報」タブに反映する。

ローカル実行:
  python scripts/market/gemini_analysis.py

環境変数:
  GEMINI_API_KEY  — Gemini APIキー（必須）
  GIST_TOKEN      — GitHub Gist 読み書き用PAT（任意、カレンダー連携時）
  GIST_ID         — 投資カレンダーデータのGist ID（任意、カレンダー連携時）
  DISCORD_OPTION_WEBHOOK_URL — Discord通知用Webhook（任意、Discord連携時）
"""

import argparse
import importlib.util
import json
import os
import sys
import time
import requests
from datetime import datetime, timezone, timedelta

# Windows CP932 環境での絵文字出力エラーを回避
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── 定数 ──────────────────────────────────────────────────────────
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
REPORT_DIR = os.path.join(BASE_DIR, "market_analysis", "reports")
NOTE_BLOG_PUBLISHER_PATH = os.path.join(BASE_DIR, "note", "note_blog_publisher.py")
PROMPT_TEMPLATE_PATH = os.path.join(BASE_DIR, "note", "prompt", "daily_market_analysis_prompt.md")

GEMINI_MODEL = "gemini-3.5-flash"
GEMINI_ENDPOINT = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)

JST = timezone(timedelta(hours=9))
DISCORD_CONTENT_LIMIT = 1900


def _env_int(name, default):
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def parse_args():
    parser = argparse.ArgumentParser(description="Gemini市場分析とDiscord/note配信を実行する")
    parser.add_argument(
        "--note-post-mode",
        default=os.environ.get("NOTE_POST_MODE", "skip"),
        choices=["skip", "draft", "draft-note-only", "dry-run", "publish"],
        help="note投稿モード。skip / draft / draft-note-only / dry-run / publish",
    )
    parser.add_argument("--note-dry-run-publish", action="store_true", help="note公開直前まで進め、最後の投稿ボタンは押さない")
    parser.add_argument("--note-publish", action="store_true", help="noteへ本投稿する")
    parser.add_argument("--note-draft", action="store_true", help="note下書きだけ作成する")
    parser.add_argument("--skip-note", action="store_true", help="note投稿を明示的にスキップする")
    parser.add_argument("--note-only", action="store_true", help="Gemini APIとDiscordを実行せず、既存レポートからnote投稿だけ行う")
    parser.add_argument("--note-date", default=os.environ.get("NOTE_POST_DATE", ""), help="note記事日付。YYYY-MM-DD または YYYYMMDD")
    parser.add_argument("--report-file", default=os.environ.get("NOTE_REPORT_FILE", ""), help="note投稿に使うGeminiレポートMarkdownのフルパス")
    parser.add_argument("--note-reuse-assets", action="store_true", help="note/generated 配下の生成済み画像を再利用する")
    parser.add_argument("--note-affiliate-memo", type=int, default=_env_int("NOTE_AFFILIATE_MEMO", 1), help="使用するアフィリエイトMEMO番号")
    parser.add_argument("--note-affiliate-count", type=int, default=_env_int("NOTE_AFFILIATE_COUNT", 1), help="H2ごとのアフィリエイト挿入数")
    parser.add_argument("--note-affiliate-seed", default=os.environ.get("NOTE_AFFILIATE_SEED", ""), help="アフィリエイト選定の固定シード")
    return parser.parse_args()


def resolve_note_post_mode(args):
    if args.skip_note:
        return "skip"
    if args.note_post_mode == "draft-note-only":
        return "draft-note-only"
    if args.note_publish:
        return "publish"
    if args.note_dry_run_publish:
        return "dry-run"
    if args.note_draft:
        return "draft"
    if args.note_only and args.note_post_mode == "skip":
        return "dry-run"
    return args.note_post_mode


def load_note_blog_publisher():
    if not os.path.exists(NOTE_BLOG_PUBLISHER_PATH):
        raise FileNotFoundError(f"note投稿モジュールが見つかりません: {NOTE_BLOG_PUBLISHER_PATH}")
    spec = importlib.util.spec_from_file_location("investment_dashboard_note_blog_publisher", NOTE_BLOG_PUBLISHER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"note投稿モジュールを読み込めません: {NOTE_BLOG_PUBLISHER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["investment_dashboard_note_blog_publisher"] = module
    spec.loader.exec_module(module)
    return module


def run_note_post_process(report_text, today_str, args):
    mode = resolve_note_post_mode(args)
    if mode == "skip":
        print("⏭️ note投稿モードは skip のため、note投稿をスキップします")
        return {"success": True, "skipped": True, "mode": mode}

    print(f"📝 note投稿プロセスを開始します: mode={mode}")
    note_blog_publisher = load_note_blog_publisher()
    result = note_blog_publisher.publish_note_blog(
        report_text=report_text,
        date_value=args.note_date or today_str,
        mode=mode,
        report_file=args.report_file,
        affiliate_memo=args.note_affiliate_memo,
        affiliate_count=args.note_affiliate_count,
        affiliate_seed=args.note_affiliate_seed,
        reuse_assets=args.note_reuse_assets,
    )
    if not result.get("success"):
        raise RuntimeError(f"note投稿に失敗しました: {json.dumps(result, ensure_ascii=False)[:1000]}")
    print(f"✅ note投稿プロセス完了: mode={mode}, url={result.get('url', '')}, published={result.get('published_url', '')}")
    return result


# ── データ読み込みユーティリティ ───────────────────────────────────
def load_json(filename):
    """data/ 配下のJSONファイルを読み込む"""
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        print(f"⚠️ ファイルが見つかりません: {path}", file=sys.stderr)
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def summarize_intraday(intraday_data):
    """etf_intraday.json から銘柄ごとの本日始値・終値・騰落率のみ抽出（大幅トークン節約）"""
    dates = intraday_data.get("dates", [])
    prices = intraday_data.get("prices", {})
    if not dates:
        return {}

    # 日付ごとのインデックスを構築
    unique_dates = sorted(set(d.split(" ")[0] for d in dates))
    today = unique_dates[-1]
    yesterday = unique_dates[-2] if len(unique_dates) >= 2 else None

    today_indices = [i for i, d in enumerate(dates) if d.split(" ")[0] == today]
    yest_indices = [i for i, d in enumerate(dates) if yesterday and d.split(" ")[0] == yesterday]

    # 銘柄ラベル辞書を構築
    labels = {}
    for mapping_key in ["sectors", "semiconductor_jp", "semiconductor_us", "topix100", "us_sectors"]:
        mapping = intraday_data.get(mapping_key, {})
        if mapping:
            labels.update(mapping)

    result = {"date": today, "tickers": {}}
    for ticker, vals in prices.items():
        if not today_indices:
            continue
        today_vals = [vals[i] for i in today_indices if i < len(vals) and vals[i] is not None]
        if not today_vals:
            continue
        open_price = today_vals[0]
        close_price = today_vals[-1]
        if open_price and open_price != 0:
            change_pct = round((close_price - open_price) / open_price * 100, 2)
        else:
            change_pct = 0
        # 前日終値も取得
        prev_close = None
        if yest_indices:
            yest_vals = [vals[i] for i in yest_indices if i < len(vals) and vals[i] is not None]
            if yest_vals:
                prev_close = yest_vals[-1]
        daily_change = None
        if prev_close and prev_close != 0:
            daily_change = round((close_price - prev_close) / prev_close * 100, 2)

        name = labels.get(ticker, ticker)
        result["tickers"][ticker] = {
            "name": name,
            "open": open_price,
            "close": close_price,
            "intraday_pct": change_pct,
            "daily_pct": daily_change,
        }
    return result


def summarize_etf_data(etf_data):
    """etf_data.json から直近5日 + 20日前の終値を抽出して騰落率を計算"""
    dates = etf_data.get("dates", [])
    prices = etf_data.get("prices", {})
    if not dates or len(dates) < 2:
        return {}

    labels = {}
    for mapping_key in ["sectors", "semiconductor_jp", "semiconductor_us", "topix100", "us_sectors"]:
        mapping = etf_data.get(mapping_key, {})
        if mapping:
            labels.update(mapping)

    result = {"latest_date": dates[-1], "tickers": {}}
    for ticker, vals in prices.items():
        if not vals or vals[-1] is None:
            continue
        latest = vals[-1]
        # 前日比
        prev = vals[-2] if len(vals) >= 2 and vals[-2] is not None else None
        d1 = round((latest - prev) / prev * 100, 2) if prev and prev != 0 else None
        # 5日前比
        p5 = vals[-6] if len(vals) >= 6 and vals[-6] is not None else None
        d5 = round((latest - p5) / p5 * 100, 2) if p5 and p5 != 0 else None
        # 20日前比
        p20 = vals[-21] if len(vals) >= 21 and vals[-21] is not None else None
        d20 = round((latest - p20) / p20 * 100, 2) if p20 and p20 != 0 else None

        name = labels.get(ticker, ticker)
        result["tickers"][ticker] = {
            "name": name,
            "latest": latest,
            "daily_pct": d1,
            "weekly_pct": d5,
            "monthly_pct": d20,
        }
    return result


def summarize_option_history(option_history):
    """option_history.json から直近2日分のみ抽出"""
    if not option_history:
        return {}
    keys = sorted(option_history.keys())
    latest_keys = keys[-2:] if len(keys) >= 2 else keys
    return {k: option_history[k] for k in latest_keys}


# ── プロンプト構築 ─────────────────────────────────────────────────
def _json_for_prompt(value):
    return json.dumps(value, ensure_ascii=False, indent=1)


def _load_prompt_template():
    if not os.path.exists(PROMPT_TEMPLATE_PATH):
        raise FileNotFoundError(f"Gemini分析プロンプトが見つかりません: {PROMPT_TEMPLATE_PATH}")
    with open(PROMPT_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return f.read()


def build_prompt(short_selling, teguchi, option_history, etf_intraday, etf_data, today_str):
    """分析用プロンプトを構築"""
    replacements = {
        "{{today_str}}": today_str,
        "{{short_selling_json}}": _json_for_prompt(short_selling),
        "{{teguchi_json}}": _json_for_prompt(teguchi),
        "{{option_history_json}}": _json_for_prompt(option_history),
        "{{etf_intraday_json}}": _json_for_prompt(etf_intraday),
        "{{etf_data_json}}": _json_for_prompt(etf_data),
    }
    prompt = _load_prompt_template()
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)
    unresolved = [item for item in replacements if item in prompt]
    if unresolved:
        raise RuntimeError(f"Gemini分析プロンプトの置換に失敗しました: {unresolved}")
    return prompt


# ── Gemini API 呼び出し ────────────────────────────────────────────
def call_gemini(prompt, api_key, max_retries=3):
    """Gemini API を呼び出す（リトライ付き）"""
    url = f"{GEMINI_ENDPOINT}?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": 65536,
            "temperature": 0.3,
        },
    }

    for attempt in range(1, max_retries + 1):
        print(f"📡 Gemini API ({GEMINI_MODEL}) を呼び出し中... (試行 {attempt}/{max_retries})")
        response = requests.post(url, json=payload, timeout=180)

        if response.status_code == 200:
            break
        if response.status_code in (429, 503) and attempt < max_retries:
            wait = 30 * attempt
            print(f"⏳ HTTP {response.status_code} — {wait}秒待機してリトライ...")
            time.sleep(wait)
            continue
        print(f"❌ Gemini API エラー: HTTP {response.status_code}", file=sys.stderr)
        print(response.text, file=sys.stderr)
        sys.exit(1)

    result = response.json()
    candidates = result.get("candidates", [])
    if not candidates:
        print("❌ Gemini API: 応答候補なし", file=sys.stderr)
        print(json.dumps(result, indent=2, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    text = candidates[0]["content"]["parts"][0]["text"]
    usage = result.get("usageMetadata", {})
    print(f"✅ 応答取得完了 (入力: {usage.get('promptTokenCount', '?')} tokens, 出力: {usage.get('candidatesTokenCount', '?')} tokens)")
    return text


# ── レポート保存 ───────────────────────────────────────────────────
def save_report(report_text, today_str):
    """レポートをファイルに保存"""
    os.makedirs(REPORT_DIR, exist_ok=True)
    filename = f"{today_str.replace('-', '')}_daily_report.md"
    filepath = os.path.join(REPORT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"📄 レポート保存: {filepath}")
    return filepath


# ── Discord 通知 ──────────────────────────────────────────────────
def split_discord_messages(text, limit=DISCORD_CONTENT_LIMIT):
    """Discordの本文制限に収まるよう、Markdownを行単位で分割する"""
    chunks = []
    current = ""

    for line in text.splitlines():
        next_line = f"{line}\n"
        if len(next_line) > limit:
            if current:
                chunks.append(current.rstrip())
                current = ""
            for start in range(0, len(next_line), limit):
                chunks.append(next_line[start:start + limit].rstrip())
            continue

        if len(current) + len(next_line) > limit:
            chunks.append(current.rstrip())
            current = next_line
        else:
            current += next_line

    if current.strip():
        chunks.append(current.rstrip())

    return chunks or [text[:limit]]


def post_discord_message(webhook_url, content, files=None, max_retries=3):
    """Discord Webhookへ送信する。レート制限時はDiscordの指示秒数だけ待つ"""
    for attempt in range(1, max_retries + 1):
        response = requests.post(
            webhook_url,
            data={"content": content},
            files=files,
            timeout=60,
        )

        if response.status_code in (200, 204):
            return True

        if response.status_code == 429 and attempt < max_retries:
            try:
                retry_after = float(response.json().get("retry_after", 1.0))
            except (ValueError, json.JSONDecodeError):
                retry_after = 1.0
            wait = max(retry_after, 1.0)
            print(f"⏳ Discordレート制限 — {wait:.1f}秒待機してリトライ...")
            time.sleep(wait)
            continue

        print(f"❌ Discord通知エラー: HTTP {response.status_code}", file=sys.stderr)
        print(response.text[:500], file=sys.stderr)
        return False

    return False


def send_discord_market_report(report_text, today_str, webhook_url):
    """Geminiの投資戦略サマリーをDiscordへ全文通知する"""
    if not webhook_url:
        print("⏭️ Discord Webhook設定なし — Discord通知をスキップ")
        return

    compact_date = today_str.replace("-", "")
    header = (
        f"{compact_date} #日経225 オプション分析 Gemini投資戦略サマリー\n"
        "#日経平均 #株式投資 #デイトレ #N225 #オプション #CFD\n"
        "https://seahirodigital.github.io/investment_dashboard/option.html\n"
        "https://seahirodigital.github.io/investment_dashboard/\n\n"
        "以下、投資カレンダー「情報」タブと同じ内容です。"
    )
    chunks = split_discord_messages(report_text)

    first_content = f"{header}\n\n---\n{chunks[0]}"
    if len(first_content) > DISCORD_CONTENT_LIMIT:
        first_content = f"{header}\n\n続きは分割メッセージと添付Markdownで確認してください。"

    file_name = f"{compact_date}_gemini_option_strategy_summary.md"
    files = {
        "files[0]": (
            file_name,
            report_text.encode("utf-8"),
            "text/markdown; charset=utf-8",
        )
    }

    print(f"📣 DiscordへGemini投資戦略サマリーを送信中... ({len(chunks)}分割)")
    if not post_discord_message(webhook_url, first_content, files=files):
        return

    remaining = chunks[1:] if first_content.endswith(chunks[0]) else chunks
    for index, chunk in enumerate(remaining, start=2):
        content = f"**Gemini投資戦略サマリー 続き {index}/{len(remaining) + 1}**\n{chunk}"
        if len(content) > DISCORD_CONTENT_LIMIT:
            content = chunk[:DISCORD_CONTENT_LIMIT]
        if not post_discord_message(webhook_url, content):
            return

    print("✅ Discord通知完了")


# ── Gist カレンダー更新 ────────────────────────────────────────────
def update_gist_calendar(report_text, today_str, gist_token, gist_id):
    """投資カレンダーのGistデータの「情報」タブを更新（raw_url方式でデータ保護）"""
    if not gist_token or not gist_id:
        print("⏭️ Gist設定なし — カレンダー更新をスキップ")
        return

    print(f"☁️ Gist ({gist_id}) から投資カレンダーデータを取得中...")

    headers = {
        "Authorization": f"token {gist_token}",
        "Accept": "application/vnd.github.v3+json",
    }

    # 1. Gistメタデータを取得し、raw_url を得る（truncation回避）
    resp = requests.get(f"https://api.github.com/gists/{gist_id}", headers=headers, timeout=30)
    if resp.status_code != 200:
        print(f"❌ Gist取得エラー: HTTP {resp.status_code}", file=sys.stderr)
        return

    gist_data = resp.json()
    market_file = gist_data.get("files", {}).get("market_data.json", {})
    raw_url = market_file.get("raw_url")

    if not raw_url:
        print("❌ Gist内に market_data.json が見つかりません", file=sys.stderr)
        return

    # 2. raw_url から完全なコンテンツを取得（大きなファイルでも切り詰められない）
    raw_resp = requests.get(raw_url, headers=headers, timeout=30)
    if raw_resp.status_code != 200:
        print(f"❌ Gist raw_url 取得エラー: HTTP {raw_resp.status_code}", file=sys.stderr)
        return

    try:
        content = json.loads(raw_resp.text)
    except json.JSONDecodeError:
        print("❌ Gist内のJSONパースエラー", file=sys.stderr)
        return

    # 3. history[today].info のみ更新（他のフィールドは一切触らない）
    history = content.get("history", {})
    date_key = today_str  # "2026-03-25" 形式
    if date_key not in history:
        history[date_key] = {}

    old_info_len = len(history[date_key].get("info", ""))
    history[date_key]["info"] = report_text
    content["history"] = history
    content["lastUpdated"] = datetime.now(JST).isoformat()

    # 4. Gistを更新
    resp2 = requests.patch(
        f"https://api.github.com/gists/{gist_id}",
        headers={**headers, "Content-Type": "application/json"},
        json={"files": {"market_data.json": {"content": json.dumps(content, ensure_ascii=False)}}},
        timeout=30,
    )
    if resp2.status_code == 200:
        print(f"✅ 投資カレンダー「情報」タブ更新完了 ({date_key}, info: {old_info_len}→{len(report_text)}文字)")
    else:
        print(f"❌ Gist更新エラー: HTTP {resp2.status_code}", file=sys.stderr)
        print(resp2.text[:500], file=sys.stderr)


# ── メイン ─────────────────────────────────────────────────────────
def main():
    args = parse_args()

    # 本日の日付 (JST)
    now_jst = datetime.now(JST)
    today_str = now_jst.strftime("%Y-%m-%d")

    if args.note_only:
        print(f"🧪 note-only モードで実行します: {args.note_date or today_str}")
        run_note_post_process("", today_str, args)
        print("✅ note-only モード完了")
        return

    # APIキー取得
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ 環境変数 GEMINI_API_KEY が設定されていません", file=sys.stderr)
        sys.exit(1)

    print(f"📅 分析日: {today_str}")

    # データ読み込み
    print("📂 データファイル読み込み中...")
    short_selling = load_json("short_selling.json")
    teguchi = load_json("teguchi.json")
    option_history = load_json("option_history.json")
    etf_intraday_raw = load_json("etf_intraday.json")
    etf_data_raw = load_json("etf_data.json")

    if not all([short_selling, teguchi, option_history, etf_intraday_raw, etf_data_raw]):
        print("❌ 必要なデータファイルが不足しています", file=sys.stderr)
        sys.exit(1)

    # データを軽量化（トークン節約：生データ→サマリーに変換）
    etf_intraday = summarize_intraday(etf_intraday_raw)
    etf_data = summarize_etf_data(etf_data_raw)
    option_hist = summarize_option_history(option_history)

    # プロンプト構築
    prompt = build_prompt(short_selling, teguchi, option_hist, etf_intraday, etf_data, today_str)
    prompt_size_kb = len(prompt.encode("utf-8")) / 1024
    print(f"📝 プロンプトサイズ: {prompt_size_kb:.0f} KB")

    # Gemini API 呼び出し
    report_text = call_gemini(prompt, api_key)

    # レポート保存
    save_report(report_text, today_str)

    # Gist カレンダー更新（環境変数が設定されている場合のみ）
    gist_token = os.environ.get("GIST_TOKEN")
    gist_id = os.environ.get("GIST_ID")
    update_gist_calendar(report_text, today_str, gist_token, gist_id)

    # Discord通知（環境変数が設定されている場合のみ）
    discord_webhook_url = os.environ.get("DISCORD_OPTION_WEBHOOK_URL")
    send_discord_market_report(report_text, today_str, discord_webhook_url)

    # note投稿（Discord通知完了後に実行）
    run_note_post_process(report_text, today_str, args)

    print("🎉 市場分析完了")


if __name__ == "__main__":
    main()
