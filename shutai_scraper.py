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
    # 色付きspanタグなどが含まれる場合があるため、テキストのみ抽出後に処理することを想定するが
    # BS4の .text で取得していればタグは消えている。記号の処理を行う。
    if '▼' in clean_text:
        clean_text = '-' + clean_text.replace('▼', '').replace('%', '')
    elif '▲' in clean_text:
        clean_text = clean_text.replace('▲', '').replace('+', '').replace('%', '')
    elif '+' in clean_text:
        clean_text = clean_text.replace('+', '').replace('%', '')
        
    try:
        # 小数点が含まれるかチェック
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

        # 最初の2行はヘッダーなのでスキップ
        for row in rows[2:]:
            # クラスに 'yy' が含まれる行（月計・年計）はスキップ
            if 'yy' in row.get('class', []):
                continue

            cols = row.find_all('td')
            # データ行でない場合はスキップ
            if not cols or len(cols) < 5:
                continue

            # 日付の取得 (timeタグがある場合と直接テキストの場合に対応)
            date_tag = cols[0].find('time')
            date_str = date_tag.text.strip() if date_tag else cols[0].text.strip()
            
            # 日付フォーマットの正規化 (YYYY/MM/DD -> YYYY-MM-DD)
            try:
                date_obj = datetime.strptime(date_str, '%Y/%m/%d')
                formatted_date = date_obj.strftime('%Y-%m-%d')
            except ValueError:
                # 日付変換できない行はスキップ
                continue

            # データ抽出 (列インデックスはHTML構造に基づく)
            # 0: 日付, 1: 日経平均, 2: 変化(除外), 3: 海外, 4: 証券自己
            # 5: 個人計, 6: 現金, 7: 信用, 8: 投資信託
            # 9: 事業法人, 10: その他法人, 11: 信託銀行, 12: 生保損保, 13: 都銀地銀
            
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

        # データのマージ (日付をキーにして重複排除・更新)
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
