import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
import traceback
import re

# 環境変数からデバッグモードを取得
DEBUG_MODE = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
DATA_FILE = 'data/shutai_data.json'
TARGET_URL = 'https://nikkei225jp.com/data/shutai.php'

def log(msg):
    print(f"[Shutai Scraper] {msg}", flush=True)

def parse_value(text):
    """テキストを数値に変換"""
    if not text or text.strip() == '-':
        return 0
    
    s_val = str(text).strip()
    
    # 不要な文字の削除
    s_val = s_val.replace(',', '').replace('%', '').replace(' ', '').replace('\n', '').replace('\t', '')
    
    # 記号処理（▼はマイナス、▲/+はプラス）
    if '▼' in s_val:
        s_val = '-' + s_val.replace('▼', '')
    elif '▲' in s_val:
        s_val = s_val.replace('▲', '')
    elif s_val.startswith('+'):
        s_val = s_val[1:]
        
    try:
        if '.' in s_val:
            return float(s_val)
        return int(s_val)
    except ValueError:
        return 0

def scrape_shutai_data():
    log(f"Starting scraping process. Target: {TARGET_URL}")
    log(f"Debug Mode: {DEBUG_MODE}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8'
    }

    try:
        # 1. HTML取得
        response = requests.get(TARGET_URL, headers=headers, timeout=20)
        response.encoding = response.apparent_encoding
        
        if response.status_code != 200:
            log(f"Error: HTTP {response.status_code}")
            return

        html_content = response.text
        log(f"HTML Content Length: {len(html_content)}")

        # 2. BeautifulSoupでパース
        soup = BeautifulSoup(html_content, 'lxml')
        
        # テーブルを検索
        table = soup.find('table', {'id': 'datatbl'})
        
        if not table:
            log("CRITICAL: No table found with id='datatbl'")
            return
        
        log(f"✓ Table found with id='datatbl'")
        
        # デバッグ: テーブルのHTML構造を詳細確認
        log("--- Table Structure Debug ---")
        log(f"Table name: {table.name}")
        log(f"Table attrs: {table.attrs}")
        
        # 子要素を確認
        direct_children = [c for c in table.children if hasattr(c, 'name') and c.name]
        log(f"Direct children: {[c.name for c in direct_children]}")
        
        # テーブル内のすべての要素を検索
        all_trs = table.find_all('tr')
        all_tds = table.find_all('td')
        all_ths = table.find_all('th')
        
        log(f"Total <tr> found: {len(all_trs)}")
        log(f"Total <td> found: {len(all_tds)}")
        log(f"Total <th> found: {len(all_ths)}")
        
        # テーブルのHTML（最初の2000文字）を表示
        table_str = str(table)[:2000]
        log(f"Table HTML (first 2000 chars):\n{table_str}\n")
        
        # 3. データ行を抽出
        rows = table.find_all('tr')
        log(f"Processing {len(rows)} rows...")
        
        if len(rows) == 0:
            log("ERROR: No <tr> elements found!")
            
            # 正規表現で日付パターンを探す
            date_pattern = r'<time>(\d{4}/\d{2}/\d{2})</time>'
            dates_found = re.findall(date_pattern, html_content)
            log(f"Found {len(dates_found)} date patterns in raw HTML")
            if dates_found:
                log(f"Sample dates: {dates_found[:5]}")
            
            return
        
        # データ処理
        new_data = []
        
        for idx, row in enumerate(rows):
            # ヘッダー行はスキップ
            if row.find('th'):
                continue
            
            # セルを取得
            cells = row.find_all('td')
            
            if len(cells) < 14:
                continue
            
            # class="yy"の行（月計・年計）を除外
            row_class = row.get('class')
            if row_class and 'yy' in row_class:
                continue
            
            try:
                # 日付の取得
                first_cell = cells[0]
                time_tag = first_cell.find('time')
                if time_tag:
                    date_text = time_tag.get_text().strip()
                else:
                    date_text = first_cell.get_text().strip()
                
                # 月計・年計を除外
                if '月計' in date_text or '年計' in date_text:
                    continue
                
                date_clean = date_text.split()[0].split('\n')[0]
                date_obj = datetime.strptime(date_clean, '%Y/%m/%d')
                formatted_date = date_obj.strftime('%Y-%m-%d')
                
                # データの抽出
                record = {
                    "date": formatted_date,
                    "nikkei_avg": parse_value(cells[1].get_text()),
                    "foreign": parse_value(cells[3].get_text()),
                    "securities_self": parse_value(cells[4].get_text()),
                    "individual_total": parse_value(cells[5].get_text()),
                    "individual_cash": parse_value(cells[6].get_text()),
                    "individual_credit": parse_value(cells[7].get_text()),
                    "investment_trust": parse_value(cells[8].get_text()),
                    "business_corp": parse_value(cells[9].get_text()),
                    "other_corp": parse_value(cells[10].get_text()),
                    "trust_banks": parse_value(cells[11].get_text()),
                    "insurance": parse_value(cells[12].get_text()),
                    "city_banks": parse_value(cells[13].get_text())
                }
                
                new_data.append(record)
                
                if len(new_data) <= 3:
                    log(f"✓ Parsed: {formatted_date}, 海外={record['foreign']}, 個人計={record['individual_total']}")
                
            except Exception as e:
                continue
        
        log(f"Extracted {len(new_data)} valid weekly records")
        
        if len(new_data) == 0:
            log("WARNING: Valid data count is 0. Aborting save.")
            return
        
        # 最新5件を表示
        log("Sample data (latest 5 records):")
        for record in new_data[-5:]:
            log(f"  {record['date']}: 海外={record['foreign']:,}, 個人計={record['individual_total']:,}")
        
        # 4. 保存ロジック
        final_list = []
        
        if DEBUG_MODE:
            log("DEBUG MODE: Overwriting ALL data.")
            final_list = sorted(new_data, key=lambda x: x['date'])
        else:
            log("NORMAL MODE: Merging with existing data.")
            existing_data = []
            if os.path.exists(DATA_FILE):
                try:
                    with open(DATA_FILE, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                    log(f"Loaded {len(existing_data)} existing records.")
                except:
                    pass
            
            data_map = {item['date']: item for item in existing_data}
            for item in new_data:
                data_map[item['date']] = item
            
            final_list = sorted(data_map.values(), key=lambda x: x['date'])
        
        # 保存
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(final_list, f, indent=4, ensure_ascii=False)
        
        log(f"✓ Successfully saved {len(final_list)} records to {DATA_FILE}")

    except Exception as e:
        log(f"FATAL ERROR: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    scrape_shutai_data()
