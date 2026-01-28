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
    "JP": ["Nomura", "Daiwa", "Mizuho", "SMBC", "Mitsubishi", "Nikko", "Okasan", "Tokai", "野村", "大和", "みずほ", "三菱", "日興", "岡三", "東海", "日産", "岩井"],
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
        resp = requests.get(TARGET_URL)
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, 'html.parser')

        # JPXのテーブル構造を特定 (tbody内の行)
        table = soup.find('table')
        if not table:
            print("Error: Table not found on JPX page.")
            return None, None, None
            
        rows = table.find_all('tr')
        
        target_row = None
        latest_date = None
        
        # 最初の有効な日付行を探す
        for row in rows:
            cols = row.find_all('td')
            if not cols:
                continue
            date_text = cols[0].get_text(strip=True)
            # YYYY/MM/DD 形式をチェック
            if re.match(r'\d{4}/\d{2}/\d{2}', date_text):
                latest_date = date_text
                target_row = cols
                break
        
        if not target_row:
            print("No valid date row found.")
            return None, None, None

        # JPXテーブル構造: [日付, ナイト(立会), ナイト(J-NET), 日中(立会), 日中(J-NET)]
        # インデックス: 0=日付, 1=ナイト立会, 3=日中立会
        night_link = None
        day_link = None

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
        # Excelを読み込む (ヘッダー位置が不明なため、まずは全読み込み)
        df = pd.read_excel(file_content, header=None, engine='openpyxl')
        
        # 「参加者」または「証券会社」という言葉が含まれる行をヘッダーとみなす
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

        # ヘッダーを設定して再構成
        df.columns = df.iloc[header_row_idx]
        df = df.iloc[header_row_idx + 1:].reset_index(drop=True)

        # カラム名のクリーニング (改行削除など)
        df.columns = [str(c).replace('\n', '').strip() for c in df.columns]

        # 参加者名カラムを特定
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

            # 各カラムの数値を抽出
            products = {}
            for col in df.columns:
                if col == col_participant:
                    continue
                
                val = row[col]
                # 数値変換処理
                try:
                    if pd.notna(val) and val != "-":
                        if isinstance(val, str):
                            # カンマ削除
                            val = float(val.replace(',', ''))
                        
                        # 0以外のデータのみ保持
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
    
    # dataフォルダが存在しない場合は作成
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

    # 2. データの取得と解析
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
