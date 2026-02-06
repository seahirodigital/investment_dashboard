import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime

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
    try:
        response = requests.get(TARGET_URL, timeout=15)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')
        
        table = soup.find('table', id='datatbl')
        if not table:
            print("Table 'datatbl' not found.")
            return

        rows = table.find_all('tr')
        new_data = []

        # ヘッダー(最初の2行)を除外して処理
        for row in rows[2:]:
            # 月計・年計（class="yy"）はスキップ
            if 'yy' in row.get('class', []):
                continue

            cols = row.find_all('td')
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
                continue

            # データ抽出 (HTML構造に基づく列インデックス)
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

        # 既存データの読み込み
        existing_data = []
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except json.JSONDecodeError:
                existing_data = []

        # データのマージ (日付をキーにして重複排除)
        data_map = {item['date']: item for item in existing_data}
        
        # 新しいデータを上書き/追加
        for item in new_data:
            data_map[item['date']] = item

        # リストに戻して日付順（昇順：古い日付が先）にソート
        final_list = list(data_map.values())
        final_list.sort(key=lambda x: x['date'])

        # 保存
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(final_list, f, indent=4, ensure_ascii=False)
        
        print(f"Successfully updated {DATA_FILE}. Total records: {len(final_list)}")

    except Exception as e:
        print(f"Error in scrape_shutai_data: {e}")

if __name__ == "__main__":
    scrape_shutai_data()
