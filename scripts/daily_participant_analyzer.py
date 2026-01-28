import os
import re
import json
import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime

# ==========================================
# 設定
# ==========================================
TARGET_URL = "https://www.jpx.co.jp/markets/derivatives/participant-volume/index.html"
# ルート直下の data フォルダに出力
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "daily_participant.json")

# 証券会社カテゴリ辞書 (名寄せ用)
BROKER_CATEGORIES = {
    "US": ["Goldman", "Morgan", "Merrill", "BofA", "Citi", "JP Morgan", "JPMorgan", "Sachs", "モルガン", "ゴールドマン", "シティ", "アメリカ", "バンカメ"],
    "EU": ["ABN", "Societe", "Barclays", "BNP", "UBS", "Deutsche", "HSBC", "Credit Suisse", "ソシエテ", "バークレイズ", "ドイツ", "クレディ", "パリバ"],
    "JP": ["Nomura", "Daiwa", "Mizuho", "SMBC", "Mitsubishi", "Nikko", "Okasan", "Tokai", "野村", "大和", "みずほ", "三菱", "日興", "岡三", "東海", "日産", "岩井", "ちばぎん", "フィリップ"],
    "NET": ["SBI", "Rakuten", "Monex", "Matsui", "au", "kabu.com", "楽天", "マネックス", "松井", "カブコム", "GMO"]
}

# ==========================================
# 関数定義
# ==========================================
def get_category(name):
    """証券会社名からカテゴリ(US/EU/JP/NET)を判定"""
    if not isinstance(name, str):
        return "OTHERS"
    name_check = name.replace(" ", "").lower()
    for cat, keywords in BROKER_CATEGORIES.items():
        for kw in keywords:
            if kw.lower() in name_check:
                return cat
    return "OTHERS"

def download_file(url):
    """URLからファイルをメモリ上にダウンロード"""
    try:
        print(f"Downloading: {url}")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.content
    except Exception as e:
        print(f"Download failed: {url}, Error: {e}")
        return None

def find_latest_links():
    """JPXページを解析し、最新のナイト/日中(立会)ファイルのURLを取得"""
    try:
        print(f"Accessing JPX page: {TARGET_URL}")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        resp = requests.get(TARGET_URL, headers=headers, timeout=30)
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, 'html.parser')

        # ページ内のすべての行(tr)を走査
        rows = soup.find_all('tr')
        print(f"Scanned {len(rows)} rows on the page.")

        target_row = None
        latest_date = None
        
        # 上から順に走査し、最新の日付かつExcelリンクがある行を探す
        for i, row in enumerate(rows):
            cols = row.find_all(['td', 'th'])
            # カラムが足りない行はスキップ（日付、ナイトx2、日中x2 で最低5列あるはず）
            if len(cols) < 5:
                continue

            # 1列目のテキスト取得 (日付)
            date_text = cols[0].get_text(strip=True)
            
            # 日付パターンチェック (YYYY/MM/DD または YYYY年MM月DD日)
            # JPXは通常 YYYY/MM/DD だが念のため広く取る
            date_match = re.search(r'(\d{4}[/年]\d{1,2}[/月]\d{1,2})', date_text)
            
            if date_match:
                # さらに、この行に .xlsx または .xls へのリンクが含まれているか確認
                links = row.find_all('a', href=True)
                has_excel = any('xls' in link['href'].lower() for link in links)
                
                if has_excel:
                    latest_date = date_match.group(1)
                    target_row = cols
                    print(f"Found valid data row at index {i}: {latest_date}")
                    break
        
        if not target_row:
            print("Error: No valid data row found (Date + Excel link).")
            # デバッグ用：最初の数行のテキストを表示してみる
            print("Debug: Dumping first 5 rows content for check:")
            for i, row in enumerate(rows[:5]):
                print(f"Row {i}: {row.get_text(strip=True)[:50]}...")
            return None, None, None

        # JPXテーブル構造: [日付, ナイト(立会), ナイト(J-NET), 日中(立会), 日中(J-NET)]
        # インデックス: 0=日付, 1=ナイト立会, 3=日中立会
        night_link = None
        day_link = None

        # リンク取得ヘルパー
        def get_abs_url(col_idx):
            if col_idx < len(target_row):
                a_tag = target_row[col_idx].find('a', href=True)
                if a_tag:
                    href = a_tag['href']
                    if href.startswith('http'):
                        return href
                    return "https://www.jpx.co.jp" + href
            return None

        night_link = get_abs_url(1) # ナイト・立会
        day_link = get_abs_url(3)   # 日中・立会

        return latest_date, night_link, day_link

    except Exception as e:
        print(f"Scraping error: {e}")
        return None, None, None

def parse_excel_data(file_content):
    """Excelバイナリを読み込み、構造化データに変換"""
    if not file_content:
        return []

    try:
        # Excelを読み込む
        df = pd.read_excel(file_content, header=None, engine='openpyxl')
        
        # ヘッダー行を探す
        header_row_idx = -1
        for i, row in df.iterrows():
            row_str = row.astype(str).values
            # 参加者名やParticipantが含まれる行を探す
            if any(k in str(s) for s in row_str for k in ["参加者", "Participant", "証券会社"]):
                header_row_idx = i
                break
        
        if header_row_idx == -1:
            print("Warning: Header row not found in Excel.")
            return []

        # ヘッダーを設定
        df.columns = df.iloc[header_row_idx]
        df = df.iloc[header_row_idx + 1:].reset_index(drop=True)
        # カラム名の改行削除
        df.columns = [str(c).replace('\n', '').strip() for c in df.columns]

        # 参加者名カラム特定
        col_participant = None
        for col in df.columns:
            if "参加者" in col or "Participant" in col:
                col_participant = col
                break
        
        if not col_participant:
            return []

        result = []
        for _, row in df.iterrows():
            p_name = row[col_participant]
            if pd.isna(p_name) or str(p_name).strip() == "":
                continue
            if "合計" in str(p_name) or "Total" in str(p_name):
                continue
            
            p_name = str(p_name).strip()
            category = get_category(p_name)

            products = {}
            for col in df.columns:
                if col == col_participant:
                    continue
                val = row[col]
                try:
                    # ハイフンや空文字の処理
                    if pd.notna(val) and str(val).strip() not in ["-", ""]:
                        if isinstance(val, str):
                            val = float(val.replace(',', ''))
                        if val != 0:
                            products[col] = int(val)
                except:
                    pass
            
            if products:
                result.append({
                    "name": p_name,
                    "category": category,
                    "data": products
                })

        return result

    except Exception as e:
        print(f"Excel parse error: {e}")
        return []

def main():
    print("=== Starting Daily Participant Analysis ===")
    
    # dataフォルダ作成
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # 1. リンクと日付の取得
    date_str, night_url, day_url = find_latest_links()
    
    if not date_str:
        print("Today's data link not found. Exiting.")
        return

    print(f"Target Date: {date_str}")
    print(f"Night Session URL: {night_url}")
    print(f"Day Session URL:   {day_url}")

    # 2. データ取得と解析
    night_da
