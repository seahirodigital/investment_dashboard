"""
JPX 空売り集計（日次）データ取得スクリプト

空売り集計PDFから以下を抽出:
  (a) 実売り（現物売り）売買代金
  (b) 空売り（価格規制あり）売買代金
  (c) 空売り（価格規制なし）売買代金
  (d) 合計売買代金

計算:
  現物買い = (d) - (b)
  ネット買い = 現物買い - 現物売り = (d) - (b) - (a)

出力: data/short_selling.json
"""

import os
import sys
import json
import re
import requests
import pdfplumber
import io
from datetime import datetime
from bs4 import BeautifulSoup

# プロジェクトルートを基準にパスを解決
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..'))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
OUTPUT_FILE = os.path.join(DATA_DIR, 'short_selling.json')

BASE_URL = "https://www.jpx.co.jp"
SHORT_SELLING_BASE = "https://www.jpx.co.jp/markets/statistics-equities/short-selling/"

# アーカイブページ定義（最新 → 過去の順）
ARCHIVE_PAGES = {
    "current": "index.html",
    "archive_01": "00-archives-01.html",
    "archive_02": "00-archives-02.html",
    "archive_03": "00-archives-03.html",
    "archive_04": "00-archives-04.html",
    "archive_05": "00-archives-05.html",
}


def get_pdf_links_from_page(page_url):
    """ページから空売り集計（-m.pdf）のPDFリンクと日付を取得"""
    try:
        print(f"  ページ取得中: {page_url}")
        resp = requests.get(page_url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, 'html.parser')

        results = []
        table = soup.find('table')
        if not table:
            print(f"  警告: テーブルが見つかりません: {page_url}")
            return results

        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 2:
                continue

            # 1列目: 日付テキスト（例: 2026/03/23）
            date_text = cells[0].get_text(strip=True)
            date_match = re.match(r'(\d{4})/(\d{2})/(\d{2})', date_text)
            if not date_match:
                continue

            date_str = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"

            # 2列目: 空売り集計PDFリンク（-m.pdf）
            link = cells[1].find('a', href=True)
            if not link:
                continue

            href = link['href']
            if '-m.pdf' not in href.lower():
                continue

            if href.startswith('/'):
                pdf_url = BASE_URL + href
            elif href.startswith('http'):
                pdf_url = href
            else:
                pdf_url = BASE_URL + '/' + href

            results.append({'date': date_str, 'url': pdf_url})

        print(f"  → {len(results)}件のPDFリンクを発見")
        return results

    except Exception as e:
        print(f"  ページ取得エラー: {e}")
        return []


def extract_data_from_pdf(pdf_url):
    """PDFをダウンロードしてテーブルデータを抽出（保存不要）"""
    try:
        resp = requests.get(pdf_url, timeout=30)
        resp.raise_for_status()

        with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
            page = pdf.pages[0]
            tables = page.extract_tables()

            if not tables:
                raise ValueError("テーブルが見つかりません")

            table = tables[0]
            # データ行は最後の行（Row 2: 日付, (a), ratio, (b), ratio, (c), ratio, (d)）
            data_row = table[-1]

            if len(data_row) < 8:
                raise ValueError(f"列数不足: {len(data_row)}列")

            def parse_number(val):
                """カンマ区切り数値をintに変換"""
                if val is None:
                    return None
                cleaned = str(val).strip().replace(',', '').replace('\n', '')
                match = re.search(r'[\d]+', cleaned)
                if match:
                    return int(cleaned.replace(' ', '').split('.')[0].replace(',', ''))
                return None

            # (a) 実売り売買代金（百万円）
            a_val = parse_number(data_row[1])
            # (b) 空売り（価格規制あり）売買代金（百万円）
            b_val = parse_number(data_row[3])
            # (c) 空売り（価格規制なし）売買代金（百万円）
            c_val = parse_number(data_row[5])
            # (d) 合計売買代金（百万円）
            d_val = parse_number(data_row[7])

            if any(v is None for v in [a_val, b_val, c_val, d_val]):
                raise ValueError(f"数値抽出失敗: a={a_val}, b={b_val}, c={c_val}, d={d_val}")

            # 計算（百万円単位）
            genbutsu_uri = a_val          # 現物売り = (a)
            karauri = b_val               # 空売り = (b) 価格規制あり
            genbutsu_kai = d_val - b_val  # 現物買い = (d) - (b)
            net_kai = genbutsu_kai - genbutsu_uri  # ネット買い

            return {
                'genbutsu_uri': genbutsu_uri,   # 現物売り（百万円）
                'karauri': karauri,             # 空売り（百万円）
                'genbutsu_kai': genbutsu_kai,   # 現物買い（百万円）
                'net_kai': net_kai,             # ネット買い（百万円）
                'total': d_val,                 # 合計（百万円）
                'karauri_free': c_val,          # 空売り規制なし（百万円）
            }

    except Exception as e:
        print(f"    PDF抽出エラー: {e}")
        return None


def load_existing_data():
    """既存のJSONデータを読み込み"""
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"data": [], "generated_at": None}


def save_data(data_dict):
    """JSONファイルに保存"""
    os.makedirs(DATA_DIR, exist_ok=True)

    now = datetime.now()
    data_dict["generated_at"] = now.strftime("%Y-%m-%dT%H:%M:%S")
    data_dict["generated_at_jst"] = now.strftime("%Y-%m-%d %H:%M JST")

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data_dict, f, ensure_ascii=False, indent=2)

    print(f"\n保存完了: {OUTPUT_FILE} ({len(data_dict['data'])}件)")


def fetch_all_data(pages_to_fetch=None):
    """
    指定ページからデータを全取得
    pages_to_fetch: 取得するページキーのリスト。Noneなら全ページ
    """
    if pages_to_fetch is None:
        pages_to_fetch = ["current"]

    existing = load_existing_data()
    existing_dates = {d['date'] for d in existing.get('data', [])}

    new_records = []
    for key in pages_to_fetch:
        if key not in ARCHIVE_PAGES:
            print(f"警告: 不明なページキー: {key}")
            continue

        page_url = SHORT_SELLING_BASE + ARCHIVE_PAGES[key]
        pdf_entries = get_pdf_links_from_page(page_url)

        for entry in pdf_entries:
            date_str = entry['date']
            if date_str in existing_dates:
                print(f"  スキップ（既存）: {date_str}")
                continue

            print(f"  処理中: {date_str} ... ", end="", flush=True)
            result = extract_data_from_pdf(entry['url'])
            if result:
                record = {'date': date_str, **result}
                new_records.append(record)
                existing_dates.add(date_str)
                print(f"OK 現物買:{result['genbutsu_kai']/1000000:.2f}兆 ネット買:{result['net_kai']/1000000:.2f}兆")
            else:
                print("NG 失敗")

    # 既存データとマージ
    all_data = existing.get('data', []) + new_records
    # 日付でソート（新しい順）
    all_data.sort(key=lambda x: x['date'], reverse=True)
    # 重複除去
    seen = set()
    unique_data = []
    for d in all_data:
        if d['date'] not in seen:
            seen.add(d['date'])
            unique_data.append(d)

    result = {"data": unique_data}
    save_data(result)
    return len(new_records)


def fetch_historical(months_back=3):
    """過去データを一括取得（初回セットアップ用）"""
    print("\n=== 空売り集計: 過去データ一括取得 ===")

    pages = ["current"]
    for i in range(1, months_back + 1):
        key = f"archive_{i:02d}"
        if key in ARCHIVE_PAGES:
            pages.append(key)

    print(f"取得対象ページ: {pages}")
    return fetch_all_data(pages_to_fetch=pages)


def fetch_latest():
    """日次更新: 当月ページから新しいデータのみ取得"""
    print("\n=== 空売り集計: 日次更新 ===")
    return fetch_all_data(pages_to_fetch=["current"])


if __name__ == "__main__":
    # 引数で動作を切り替え
    if len(sys.argv) > 1 and sys.argv[1] == '--historical':
        # 過去データ一括取得
        months = int(sys.argv[2]) if len(sys.argv) > 2 else 3
        count = fetch_historical(months_back=months)
        print(f"\n新規取得: {count}件")
    else:
        # 日次更新（デフォルト）
        # 初回はデータファイルが無いので過去データも取得
        existing = load_existing_data()
        if len(existing.get('data', [])) < 5:
            count = fetch_historical(months_back=3)
        else:
            count = fetch_latest()
        print(f"\n新規取得: {count}件")
