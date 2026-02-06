import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
import traceback
import sys

# 環境変数からデバッグモードを取得
DEBUG_MODE = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
DATA_FILE = 'data/shutai_data.json'
TARGET_URL = 'https://nikkei225jp.com/data/shutai.php'

def log(msg):
    """ログを即時出力するための関数"""
    print(f"[Scraper] {msg}", flush=True)

def parse_number(text):
    if not text:
        return 0
    clean_text = text.strip().replace(',', '')
    if '▼' in clean_text:
        clean_text = '-' + clean_text.replace('▼', '').replace('%', '')
    elif '▲' in clean_text:
        clean_text = clean_text.replace('▲', '').replace('+', '').replace('%', '')
    elif '+' in clean_text:
        clean_text = clean_text.replace('+', '').replace('%', '')
    try:
        return float(clean_text) if '.' in clean_text else int(clean_text)
    except ValueError:
        return 0

def scrape_shutai_data():
    log(f"Starting scraping process. Target: {TARGET_URL}")
    log(f"Debug Mode: {DEBUG_MODE}")

    # ヘッダー偽装（必須）
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    }

    try:
        session = requests.Session()
        response = session.get(TARGET_URL, headers=headers, timeout=20)
        
        log(f"Response Status Code: {response.status_code}")
        response.encoding = response.apparent_encoding
        log(f"Encoding used: {response.encoding}")

        if response.status_code != 200:
            log(f"Error: Failed to fetch page. Status: {response.status_code}")
            return

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # テーブル特定
        table = soup.find('table', id='datatbl')
        if not table:
            log("CRITICAL ERROR: Table 'datatbl' NOT FOUND.")
            log("Dumping first 1000 chars of HTML for inspection:")
            log(response.text[:1000].replace('\n', ' '))
            return

        rows = table.find_all('tr')
        log(f"Found {len(rows)} rows in table.")

        new_data = []
        parse_errors = 0
        success_count = 0

        # データ抽出ループ
        for i, row in enumerate(rows):
            # ヘッダー行スキップ (最初の2行)
            if i < 2:
                continue
                
            # 月計・年計スキップ
            row_class = row.get('class', [])
            if 'yy' in row_class:
                continue

            cols = row.find_all('td')
            if not cols or len(cols) < 5:
                continue

            # 日付取得
            try:
                date_tag = cols[0].find('time')
                date_text = date_tag.text.strip() if date_tag else cols[0].text.strip()
                
                # 日付変換
                date_obj = datetime.strptime(date_text, '%Y/%m/%d')
                formatted_date = date_obj.strftime('%Y-%m-%d')
                
                # データマッピング
                row_data = {
                    "date": formatted_date,
                    "nikkei_avg": parse_number(cols[1].text),
                    "foreign": parse_number(cols[3].text),
                    "securities_self": parse_number(cols[4].text),
                    "individual_total": parse_number(cols[5].text),
                    "individual_cash": parse_number(cols[6].text),
                    "individual_credit": parse_number(cols[7].text),
                    "investment_trust": parse_number(cols[8].text),
                    "business_corp": parse_number(cols[9].text),
                    "trust_banks": parse_number(cols[11].text)
                }
                new_data.append(row_data)
                success_count += 1
                
                # デバッグ時: 最初の1件だけログに出して正しくパースできているか確認
                if success_count == 1:
                    log(f"Sample parsed data (Row {i}): {json.dumps(row_data, ensure_ascii=False)}")

            except Exception as e:
                parse_errors += 1
                # エラーが多い場合のみログ出力
                if parse_errors <= 5:
                    log(f"Row {i} parse error: {e} | Text: {cols[0].text.strip() if cols else 'No cols'}")
                continue

        log(f"Extraction complete. Valid records: {success_count}, Errors: {parse_errors}")

        if success_count == 0:
            log("WARNING: No valid data extracted! JSON will not be updated.")
            return

        # === 保存処理 ===
        final_list = []

        if DEBUG_MODE:
            log("DEBUG MODE: Overwriting ALL data with fetched content.")
            final_list = sorted(new_data, key=lambda x: x['date'])
        else:
            log("NORMAL MODE: Merging with existing data.")
            existing_data = []
            if os.path.exists(DATA_FILE):
                try:
                    with open(DATA_FILE, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                    log(f"Loaded {len(existing_data)} existing records.")
                except Exception as e:
                    log(f"Failed to load existing JSON: {e}")
            
            # マージ処理
            data_map = {item['date']: item for item in existing_data}
            for item in new_data:
                data_map[item['date']] = item
            
            final_list = sorted(data_map.values(), key=lambda x: x['date'])

        # ディレクトリ確認
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        
        # ファイル書き込み
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(final_list, f, indent=4, ensure_ascii=False)
        
        log(f"Successfully saved {len(final_list)} records to {DATA_FILE}")

    except Exception as e:
        log(f"FATAL ERROR: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    scrape_shutai_data()
