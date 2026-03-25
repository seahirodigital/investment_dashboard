"""
市場分析自動実行スクリプト (Gemini 3.1 Flash Lite Preview)

データ取得済みのJSONファイルを読み込み、Gemini APIで分析・レポート生成を行う。
レポートは market_analysis/reports/ に保存し、オプションでGistの投資カレンダー「情報」タブに反映する。

ローカル実行:
  python scripts/market/gemini_analysis.py

環境変数:
  GEMINI_API_KEY  — Gemini APIキー（必須）
  GIST_TOKEN      — GitHub Gist 読み書き用PAT（任意、カレンダー連携時）
  GIST_ID         — 投資カレンダーデータのGist ID（任意、カレンダー連携時）
"""

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

GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
GEMINI_ENDPOINT = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)

JST = timezone(timedelta(hours=9))


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
def build_prompt(short_selling, teguchi, option_history, etf_intraday, etf_data, today_str):
    """分析用プロンプトを構築"""
    prompt = f"""あなたは日本株市場の専門アナリストです。以下のデータを用いて、本日（{today_str}）の市場分析レポートを作成してください。

## 分析ルール

### 売買フロー底打ち検知 (short_selling.json)
- 売買代金の膨張シグナル（S1）：20日移動平均比+30%超
- 空売り比率ピークアウトシグナル（S2）：直近ピークから相対で20%低下
- Phase判定：下落 / 反発準備 / 反転上昇

### 米系投資銀行のオプション手口分析 (teguchi.json, option_history.json)
- ゴールドマンサックス、J.P.モルガン、モルガン・スタンレーなど米系投資銀行のオプション・先物手口を分析
- 建玉の偏りから上値抵抗線（レジスタンス）と下値支持線（サポート）を推測

### セクター分析 (etf_data.json)
- 主要セクターETFの本日パフォーマンスを比較
- 最も買われているセクターと最も売られているセクターを判定

### 個別株ランキング (etf_intraday.json)
- TOPIX100全銘柄の本日パフォーマンスから上位20と下位20を抽出

### 各種インデックス評価
- US先物指数（NQmain, ESmain, YMmain）
- 日本主要指数（日経平均, TOPIX, 半導体ETF）

## データ

### 空売り・売買フローデータ (short_selling.json)
```json
{json.dumps(short_selling, ensure_ascii=False, indent=1)}
```

### 手口データ (teguchi.json)
```json
{json.dumps(teguchi, ensure_ascii=False, indent=1)}
```

### オプション建玉履歴 (option_history.json) ※直近2日分
```json
{json.dumps(option_history, ensure_ascii=False, indent=1)}
```

### ETFイントラデイ・サマリー (etf_intraday.json から集計)
各銘柄の本日始値・終値・騰落率（intraday_pct=当日始値比、daily_pct=前日終値比）
```json
{json.dumps(etf_intraday, ensure_ascii=False, indent=1)}
```

### ETF日次・サマリー (etf_data.json から集計)
各銘柄の直近終値・前日比(daily_pct)・週間比(weekly_pct)・月間比(monthly_pct)
```json
{json.dumps(etf_data, ensure_ascii=False, indent=1)}
```

## 出力フォーマット（厳格に従ってください）

### １：投資戦略サマリー（打ち手の模索）
* **明日の投資戦略**: (相場全体の強弱と、具体的なアクションプラン)
* **明日の日経225先物のレンジの想定**: (オプション手口・ボラティリティから算出される想定上限値と下限値)
* **日経225オプション建玉分析（米系の思惑を観測）**: (米系投資銀行の手口による相場の仕掛けや抵抗帯の観測結果)
* **日本のどのセクターが買い、売りなのか判定**: (セクターローテーションに基づく推奨の買いセクターと売りセクター)
* **明日見るべき個別株と、その周辺セクター**: (相場を牽引する、または底打ち反転が期待される個別注目株)

### ２：分析内容（analysis）
<!-- データに基づく市場メカニズムの解説、センチメントの背景、主要プレイヤーの動向などの定性的な深掘り -->

### ３：生ファクト詳細（data）
- **US先物・指数動向**:
  - NQmain: (数値・変動率%)
  - ESmain: (数値・変動率%)
  - YMmain: (数値・変動率%)
- **日本・主要指数**:
  - 日経平均(^N225): (数値・変動率%)
  - TOPIX(1306.T): (数値・変動率%)
  - 半導体ETF(2644.T): (数値・変動率%)
- **各セクター分類分析**: (上位セクター、下位セクターと各々の変動率)
- **売買フロー**: (売買代金と空売り比率の数値、底打ちPhase判定の結果)
- **日経225オプション動向**: (主要なストライクの建玉残高・増減、米系手口の集中ライン)
- **TOPIX100 個別株ランキング**:
  - **上位20銘柄**（必ず1銘柄ごとに改行し、1位から順に縦に並べること。横並び厳禁）:
    1. 銘柄名(騰落率%)
    2. 銘柄名(騰落率%)
    ...（20位まで）
  - **下位20銘柄**（必ず1銘柄ごとに改行し、ワーストから順に縦に並べること。横並び厳禁）:
    1. 銘柄名(騰落率%)
    2. 銘柄名(騰落率%)
    ...（20位まで）
"""
    return prompt


# ── Gemini API 呼び出し ────────────────────────────────────────────
def call_gemini(prompt, api_key, max_retries=3):
    """Gemini 3.1 Flash Lite Preview API を呼び出す（リトライ付き）"""
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
    # APIキー取得
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ 環境変数 GEMINI_API_KEY が設定されていません", file=sys.stderr)
        sys.exit(1)

    # 本日の日付 (JST)
    now_jst = datetime.now(JST)
    today_str = now_jst.strftime("%Y-%m-%d")
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

    print("🎉 市場分析完了")


if __name__ == "__main__":
    main()
