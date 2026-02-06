import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
import traceback

# 環境変数からデバッグモードを取得 (Github Actionsのinput由来)
DEBUG_MODE = os.getenv('DEBUG_MODE', 'false').lower() == 'true'

# 保存先パス
DATA_FILE = 'data/shutai_data.json'
TARGET_URL = 'https://nikkei225jp.com/data/shutai.php'

def parse_number(text):
    """文字列から数値への変換（カンマ除去、▼▲処理）"""
    if not text:
        return 0
    clean_text = text.strip().replace(',', '')
    
    # 記号の処理
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
    print(f"Fetching data from {TARGET_URL}...")
    
    if DEBUG_MODE:
        print("!!!" + "="*40 + "!!!")
        print("   DEBUG MODE ACTIVE: Forcing FULL DATA refresh")
        print("   All existing data will be overwritten with web content.")
        print("!!!" + "="*40 + "!!!")

    # ヘッダーを追加してブラウザアクセスを模倣 (重要)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(TARGET_URL, headers=headers, timeout=20)
        response.encoding = response.apparent_encoding
        
        if response.status_code != 200:
            print(f"Error: Status code {response.status_code}")
            return

        soup = BeautifulSoup(response.text, 'html.parser')
        
        table = soup.find('table', id='datatbl')
        if not table:
            print("Error: Table 'datatbl' not found in HTML.")
            if DEBUG_MODE:
                print("HTML Preview (first 500 chars):")
                print(response.text[:500])
            return

        rows = table.find_all('tr')
        new_data = []

        print(f"Found {len(rows)} rows in table.")

        # ヘッダー(最初の2行)を除外して処理
        for i, row in enumerate(rows[2:], start=3):
            # 月計・年計（class="yy"）はスキップ
            if 'yy' in row.get('class', []):
                continue

            cols = row.find_all('td')
            # データ行としての妥当性チェック
            if not cols or len(cols) < 5:
                continue

            # 日付の取得
            date_tag = cols[0].find('time')
            date_str = date_tag.text.strip() if date_tag else cols[0].text.strip()
            
            # 日付フォーマットの正規化 (YYYY/MM/DD -> YYYY-MM-DD)
            try:
                date_obj = datetime.strptime(date_str, '%Y/%m/%d')
                formatted_date = date_obj.strftime('%Y-%m-%d')
            except ValueError:
                # 日付変換できない行はスキップ
                if DEBUG_MODE:
                    print(f"Skipping row {i}: Invalid date format '{date_str}'")
                continue

            # データ抽出
            try:
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
            except Exception as e:
                print(f"Error parsing data at row {i}: {e}")
                continue

        print(f"Extracted {len(new_data)} valid data records.")

        if len(new_data) == 0:
            print("Warning: No valid data extracted.")
            return

        # === データ保存ロジック ===
        final_list = []

        if DEBUG_MODE:
            # デバッグモード: Webから取得した全データをそのまま使用（全期間上書き）
            final_list = sorted(new_data, key=lambda x: x['date'])
            print("DEBUG MODE: Overwriting file with ALL fetched data.")
        else:
            # 通常モード: 既存データを読み込んでマージ
            existing_data = []
            if os.path.exists(DATA_FILE):
                try:
                    with open(DATA_FILE, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                    print(f"Loaded {len(existing_data)} existing records.")
                except json.JSONDecodeError:
                    print("Existing JSON is corrupt or empty.")
                    existing_data = []

            # マージ (日付キーで重複排除)
            data_map = {item['date']: item for item in existing_data}
            for item in new_data:
                data_map[item['date']] = item
            
            final_list = list(data_map.values())
            final_list.sort(key=lambda x: x['date'])
            print("Normal Mode: Merged new data.")

        # 保存実行
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(final_list, f, indent=4, ensure_ascii=False)
        
        print(f"Successfully saved to {DATA_FILE}. Total records: {len(final_list)}")

    except Exception as e:
        print(f"Fatal Error in scrape_shutai_data: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    scrape_shutai_data()
