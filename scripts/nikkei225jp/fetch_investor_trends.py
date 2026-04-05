"""
日経225JP「投資主体別 売買状況」スクレイパー

データソース:
  https://nikkei225jp.com/data/shutai.php

取得方法:
  Playwright (Chromium ヘッドレス) でページを描画し、
  「投資主体別 売買状況」テーブルを DOM から抽出する。
  requests だけでは JS レンダリング後のテーブルが取れないため
  Playwright を使用している。

出力:
  data/investor_trends.json
  {
    "updated_at": "<ISO timestamp, JST>",
    "source": "<URL>",
    "row_count": <int>,
    "rows": [
      {
        "date": "YYYY/MM/DD",
        "nikkei": <float>,
        "change": "<変化率文字列>",
        "foreign": <int>,
        "proprietary": <int>,
        "individual": <int>,
        "individual_cash": <int>,
        "individual_margin": <int>,
        "trust": <int>,
        "business": <int>,
        "other": <int>,
        "trustBank": <int>,
        "insurance": <int>,
        "cityBank": <int>
      },
      ...
    ]
  }

実行タイミング:
  GitHub Actions で毎週木曜 17:20 JST（UTC 08:20）に自動実行。
  既存データと日付キーでマージするため、重複なく蓄積され続ける。
  ローカルでは `python scripts/nikkei225jp/fetch_investor_trends.py`
"""

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

from playwright.sync_api import sync_playwright

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
OUTPUT_FILE = os.path.join(DATA_DIR, "investor_trends.json")

SOURCE_URL = "https://nikkei225jp.com/data/shutai.php"

DATE_RE = re.compile(r"^\d{4}/\d{2}/\d{2}$")

# 列インデックスマッピング（DOM テーブル列 → フィールド名）
# 0:日付 1:日経終値 2:変化率 3:海外 4:証券自己 5:個人計
# 6:個人(現金) 7:個人(信用) 8:投資信託 9:事業法人 10:その他法人
# 11:信託銀行 12:生保損保 13:都銀地銀
COL_MAP = [
    ("date",             str),
    ("nikkei",           float),
    ("change",           str),
    ("foreign",          int),
    ("proprietary",      int),
    ("individual",       int),
    ("individual_cash",  int),
    ("individual_margin",int),
    ("trust",            int),
    ("business",         int),
    ("other",            int),
    ("trustBank",        int),
    ("insurance",        int),
    ("cityBank",         int),
]


def clean_num(s: str) -> int:
    """符号付き数値文字列を int に変換。例: '+159,891' → 159891"""
    s = s.replace(",", "").replace("+", "").replace("▲", "").replace("▼", "-").replace("△", "")
    try:
        return int(float(s))
    except ValueError:
        return 0


def clean_float(s: str) -> float:
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_row(cells: list[str]) -> dict | None:
    """テーブルの1行（セルリスト）を構造化dictに変換。14列未満はスキップ。"""
    if len(cells) < 14:
        return None
    if not DATE_RE.match(cells[0]):
        return None

    converters = [str, clean_float, str,
                  clean_num, clean_num, clean_num,
                  clean_num, clean_num, clean_num,
                  clean_num, clean_num, clean_num,
                  clean_num, clean_num]
    row = {}
    for i, (field, _) in enumerate(COL_MAP):
        try:
            row[field] = converters[i](cells[i].strip())
        except Exception:
            row[field] = 0
    return row


def extract_rows_from_page(page) -> list[dict]:
    """ページ内の全テーブルから、日付行が最多のテーブルを選んで行を返す。"""
    tables = page.query_selector_all("table")
    print(f"  テーブル候補: {len(tables)} 個")

    best_rows: list[dict] = []
    for tbl_idx, tbl in enumerate(tables):
        trs = tbl.query_selector_all("tr")
        candidate_rows = []
        for tr in trs:
            cells = tr.query_selector_all("th, td")
            texts = [c.inner_text().strip() for c in cells]
            if texts and DATE_RE.match(texts[0]):
                parsed = parse_row(texts)
                if parsed:
                    candidate_rows.append(parsed)
        if len(candidate_rows) > len(best_rows):
            best_rows = candidate_rows
            print(f"  表 #{tbl_idx}: 日付行 {len(candidate_rows)} 件")

    return best_rows


def load_existing_rows() -> dict[str, dict]:
    """既存の investor_trends.json から rows を日付キーで読み込む。"""
    if not os.path.exists(OUTPUT_FILE):
        return {}
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        rows = data.get("rows", [])
        return {r["date"]: r for r in rows if "date" in r}
    except Exception as e:
        print(f"  既存データ読み込みエラー（無視して続行）: {e}", file=sys.stderr)
        return {}


def now_jst_iso() -> str:
    jst = timezone(timedelta(hours=9))
    return datetime.now(jst).replace(microsecond=0).isoformat()


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    # ── 既存データをロード ───────────────────────────────────────
    existing = load_existing_rows()
    print(f"既存データ: {len(existing)} 件")

    # ── Playwright でスクレイプ ─────────────────────────────────
    print(f"ページ取得中: {SOURCE_URL}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()
        page.goto(SOURCE_URL, wait_until="networkidle", timeout=60000)
        try:
            page.wait_for_selector("table", timeout=30000)
        except Exception as e:
            print(f"  table 要素待機タイムアウト: {e}", file=sys.stderr)

        new_rows = extract_rows_from_page(page)
        browser.close()

    if not new_rows:
        print("エラー: 有効な日付行を含むテーブルが見つかりませんでした", file=sys.stderr)
        sys.exit(1)

    print(f"取得行数: {len(new_rows)}")

    # ── 既存データとマージ（日付キー、新データ優先） ─────────────
    for row in new_rows:
        existing[row["date"]] = row

    # 日付昇順でソート
    merged = sorted(existing.values(), key=lambda r: r["date"])

    payload = {
        "updated_at": now_jst_iso(),
        "source": SOURCE_URL,
        "row_count": len(merged),
        "rows": merged,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"保存完了: {OUTPUT_FILE}")
    print(f"  合計行数: {len(merged)} 件（既存 {len(existing) - len(new_rows)} + 新規/更新 {len(new_rows)}）")
    print(f"  期間: {merged[0]['date']} 〜 {merged[-1]['date']}")


if __name__ == "__main__":
    main()
