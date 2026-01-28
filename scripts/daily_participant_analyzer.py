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
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "daily_participant.json")

# 証券会社カテゴリ辞書
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
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        resp = requests.get(TARGET_URL, headers=headers, timeout=30)
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, 'html.parser')

        # ページ内のすべてのテーブルを走査して、日付データが入っていそうなテーブルを探す
        tables = soup.find_all('table')
        print(f"Found {len(tables)} tables on the page.")

        target_row = None
        latest_date = None

        for i, table in enumerate(tables):
            rows = table.find_all('tr')
            # 各行をチェック
            for row in rows:
                cols = row.find_all(['td', 'th']) # thの場合も考慮
                if not cols:
                    continue
                
                # 1列目のテキストを取得
                first_col_text = cols[0].get_text(strip=True)
                
                # YYYY/MM/DD 形式を含んでいるかチェック
                match = re.search(r'(\d{4}/\d{2}/\d{2})', first_col_text)
                if match:
                    # Excelアイコン（リンク）が含まれているかチェック
                    links = row.find_all('a')
                    if len(links) > 0:
                        latest_date = match.group(1)
                        target_row = cols
                        print(f"Found valid data row in Table {i+1}: {latest_date}")
                        break
            if target_row:
                break
        
        if not target_row:
            print("Error: No valid data row found on JPX page.")
            return None, None, None

        # JPXテーブル構造: [日付, ナイト(立会), ナイト(J-NET), 日中(立会), 日中(J-NET)]
        # インデックス: 0=日付, 1=ナイト立会, 3=日中立会
        night_link = None
        day_link = None

        # カラム数を確認して安全に取得
        if len(target_row) > 1:
            a = target_row[1].find('a')
            if a: night_link = "https://www.jpx.co.jp" + a.get('href')

        if len(target_row) > 3:
            a = target_row[3].find('a')
            if a: day_link = "https://www.jpx.co.jp" + a.get('href')

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
        # ファイルを作らずに終了するが、エラーにはしない
        return

    print(f"Target Date: {date_str}")
    print(f"Night Session URL: {night_url}")
    print(f"Day Session URL:   {day_url}")

    # 2. データ取得と解析
    night_data = []
    day_data = []

    if night_url:
        print("\n--- Processing Night Session ---")
        content = download_file(night_url)
        night_data = parse_excel_data(content)
        print(f"Parsed {len(night_data)} participants.")
    
    if day_url:
        print("\n--- Processing Day Session ---")
        content = download_file(day_url)
        day_data = parse_excel_data(content)
        print(f"Parsed {len(day_data)} participants.")

    # 3. JSON保存
    output_data = {
        "date": date_str,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "night_session": night_data,
        "day_session": day_data
    }

    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"\nSuccess! Data saved to: {OUTPUT_FILE}")
    except Exception as e:
        print(f"Error saving JSON: {e}")

if __name__ == "__main__":
    main()
