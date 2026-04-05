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
    "tsv": "<手動フォーム互換のタブ区切り文字列>",
    "row_count": <int>
  }

実行タイミング:
  GitHub Actions で毎週木曜 17:20 JST（UTC 08:20）に自動実行。
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

# index.html の parseData() が期待するヘッダー（改変禁止）
# 列: 日付 / 日経平均 / 変化(週) / 海外 / 証券自己 / 個人計 /
#     個人(現金) / 個人(信用) / 投資信託 / 事業法人 / その他法人 /
#     信託銀行 / 生保損保 / 都銀地銀
HEADER_TSV = (
    "日付\t日経平均\t日経平均\n"
    "変化(週)\t海外\t証券自己\t個人\t法人\t法人(金融)\n"
    "個人 計\t個人\n"
    "(現金)\t個人\n"
    "(信用)\t投資信託\t事業法人\tその他\n"
    "法人\t信託銀行\t生保\n"
    "損保\t都銀\n"
    "地銀"
)

DATE_RE = re.compile(r"^\d{4}/\d{2}/\d{2}$")


def extract_rows_from_page(page):
    """ページ内の全テーブルから、日付(YYYY/MM/DD)始まりの行を持つ
    「投資主体別 売買状況」テーブルを見つけて行を返す。"""
    tables = page.query_selector_all("table")
    print(f"  テーブル候補: {len(tables)} 個")

    best_rows = []
    for tbl_idx, tbl in enumerate(tables):
        trs = tbl.query_selector_all("tr")
        rows = []
        for tr in trs:
            cells = tr.query_selector_all("th, td")
            texts = [c.inner_text().strip() for c in cells]
            rows.append(texts)

        # 日付で始まる行が複数ある表のみ採用
        date_rows = [r for r in rows if r and DATE_RE.match(r[0])]
        if len(date_rows) >= 5 and len(rows[0] if rows else []) == 0:
            pass
        if len(date_rows) > len(best_rows):
            best_rows = date_rows
            print(f"  表 #{tbl_idx}: 日付行 {len(date_rows)} 件, 列数 {len(date_rows[0]) if date_rows else 0}")

    return best_rows


def normalize_row(row):
    """行を14列に正規化する。

    想定列構成（サイトの表順）:
      0: 日付
      1: 日経225 (終値)
      2: 日経225 変化(週)  例 "▲3.84%", "▼0.97%", "+0.00%"
      3: 海外
      4: 証券自己
      5: 個人 計
      6: 個人(現金)
      7: 個人(信用)
      8: 投資信託
      9: 事業法人
     10: その他法人
     11: 信託銀行
     12: 生保損保
     13: 都銀地銀

    セル数が 14 より多い/少ない場合も、最初の 14 列のみ使用する。
    """
    if len(row) < 14:
        # 不足している場合はスキップ対象
        return None
    return row[:14]


def build_tsv(rows):
    """既存 parseData() 互換の TSV を組み立てる。

    parseData() 側の判定:
      - 1列目が "日経平均" / "変化" を含む行は header として無視
      - 1列目が YYYY/MM/DD にマッチする行をデータ行として採用

    よってヘッダーは index.html の defaultData と同じ形にしておく。
    """
    lines = [HEADER_TSV]
    for row in rows:
        norm = normalize_row(row)
        if norm is None:
            continue
        lines.append("\t".join(norm))
    return "\n".join(lines)


def now_jst_iso():
    jst = timezone(timedelta(hours=9))
    return datetime.now(jst).replace(microsecond=0).isoformat()


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

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
        # テーブル描画待ち
        try:
            page.wait_for_selector("table", timeout=30000)
        except Exception as e:
            print(f"  table 要素待機でタイムアウト: {e}", file=sys.stderr)

        rows = extract_rows_from_page(page)
        browser.close()

    if not rows:
        print("エラー: 有効な日付行を含むテーブルが見つかりませんでした", file=sys.stderr)
        sys.exit(1)

    # 日付降順で並んでいる想定だが、parseData 側で昇順ソートされるので
    # ここでは取得順そのままを保存する。
    tsv = build_tsv(rows)

    payload = {
        "updated_at": now_jst_iso(),
        "source": SOURCE_URL,
        "row_count": len(rows),
        "tsv": tsv,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"保存完了: {OUTPUT_FILE}")
    print(f"  データ行数: {len(rows)}")
    print(f"  最新日付: {rows[0][0] if rows else 'N/A'}")


if __name__ == "__main__":
    main()
