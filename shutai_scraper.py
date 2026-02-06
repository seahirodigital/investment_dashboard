import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
import traceback

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

def is_valid_date_row(row):
    """週次データの行かどうかを判定（月計・年計を除外）"""
    # class="yy"は集計行
    if row.get('class') and 'yy' in row.get('class'):
        return False
    
    # 最初のセルをチェック
    first_cell = row.find('td')
    if not first_cell:
        return False
    
    text = first_cell.get_text().strip()
    
    # "月計"や"年計"を含む行は除外
    if '月計' in text or '年計' in text:
        return False
    
    # YYYY/MM/DD形式の日付かチェック
    try:
        # <time>タグの中身を取得
        time_tag = first_cell.find('time')
        if time_tag:
            date_text = time_tag.get_text().strip()
        else:
            date_text = text
        
        # スペースや改行で分割して最初の部分を取得
        date_clean = date_text.split()[0].split('\n')[0]
        datetime.strptime(date_clean, '%Y/%m/%d')
        return True
    except:
        return False

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
            # デバッグ: テーブルの存在確認
            all_tables = soup.find_all('table')
            log(f"Found {len(all_tables)} tables in total")
            return
        
        log(f"Table found successfully")
        
        # 3. データ行を抽出（週次データのみ）
        rows = table.find_all('tr')
        log(f"Total rows in table: {len(rows)}")
        
        new_data = []
        
        for row in rows:
            # ヘッダー行はスキップ
            if row.find('th'):
                continue
            
            # 週次データの行かチェック
            if not is_valid_date_row(row):
                continue
            
            # セルを取得
            cells = row.find_all('td')
            
            if len(cells) < 14:
                log(f"Skipping row with insufficient cells: {len(cells)}")
                continue
            
            try:
                # 日付の取得と整形
                first_cell = cells[0]
                time_tag = first_cell.find('time')
                if time_tag:
                    date_text = time_tag.get_text().strip()
                else:
                    date_text = first_cell.get_text().strip()
                
                date_clean = date_text.split()[0].split('\n')[0]
                date_obj = datetime.strptime(date_clean, '%Y/%m/%d')
                formatted_date = date_obj.strftime('%Y-%m-%d')
                
                # データの抽出（全投資主体）
                record = {
                    "date": formatted_date,
                    "nikkei_avg": parse_value(cells[1].get_text()),       # 日経平均
                    "foreign": parse_value(cells[3].get_text()),          # 海外
                    "securities_self": parse_value(cells[4].get_text()),  # 証券自己
                    "individual_total": parse_value(cells[5].get_text()), # 個人計
                    "individual_cash": parse_value(cells[6].get_text()),  # 個人(現金)
                    "individual_credit": parse_value(cells[7].get_text()),# 個人(信用)
                    "investment_trust": parse_value(cells[8].get_text()), # 投資信託
                    "business_corp": parse_value(cells[9].get_text()),    # 事業法人
                    "other_corp": parse_value(cells[10].get_text()),      # その他法人
                    "trust_banks": parse_value(cells[11].get_text()),     # 信託銀行
                    "insurance": parse_value(cells[12].get_text()),       # 生保損保
                    "city_banks": parse_value(cells[13].get_text())       # 都銀地銀
                }
                
                new_data.append(record)
                
            except Exception as e:
                log(f"Error parsing row: {e}")
                continue
        
        log(f"Extracted {len(new_data)} valid weekly records (excluding monthly/yearly summaries).")
        
        if len(new_data) == 0:
            log("WARNING: Valid data count is 0. Aborting save.")
            return
        
        # 最新5件を表示（デバッグ用）
        log("Sample data (latest 5 records):")
        for record in new_data[-5:]:
            log(f"  {record['date']}: 海外={record['foreign']}, 個人計={record['individual_total']}")
        
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
                    log("No existing data file found.")
            
            # 日付をキーにしてマージ（重複は最新で上書き）
            data_map = {item['date']: item for item in existing_data}
            for item in new_data:
                data_map[item['date']] = item
            
            final_list = sorted(data_map.values(), key=lambda x: x['date'])
        
        # ディレクトリ作成と保存
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(final_list, f, indent=4, ensure_ascii=False)
        
        log(f"Successfully saved {len(final_list)} records to {DATA_FILE}")

    except Exception as e:
        log(f"FATAL ERROR: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    scrape_shutai_data()
