import json
import os
from datetime import datetime
import traceback

# requests-htmlを使用（JavaScriptレンダリング対応）
try:
    from requests_html import HTMLSession
    USE_REQUESTS_HTML = True
except ImportError:
    import requests
    from bs4 import BeautifulSoup
    USE_REQUESTS_HTML = False

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
    
    # 記号処理
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

def scrape_with_requests_html():
    """requests-htmlを使用してJavaScriptレンダリング"""
    log("Using requests-html (with JavaScript rendering)")
    
    session = HTMLSession()
    
    try:
        response = session.get(TARGET_URL, timeout=30)
        
        # JavaScriptをレンダリング
        log("Rendering JavaScript...")
        response.html.render(timeout=20, sleep=2)
        
        # テーブルを検索
        table = response.html.find('#datatbl', first=True)
        
        if not table:
            log("ERROR: Table not found after rendering")
            return []
        
        log("Table found after JavaScript rendering")
        
        # 行を抽出
        rows = table.find('tr')
        log(f"Found {len(rows)} rows")
        
        new_data = []
        
        for row in rows:
            # ヘッダー行をスキップ
            if row.find('th', first=True):
                continue
            
            cells = row.find('td')
            
            if len(cells) < 14:
                continue
            
            # class="yy"を除外
            if 'yy' in row.attrs.get('class', []):
                continue
            
            try:
                # 日付取得
                date_text = cells[0].text.strip().split()[0]
                
                if '月計' in date_text or '年計' in date_text:
                    continue
                
                date_obj = datetime.strptime(date_text, '%Y/%m/%d')
                formatted_date = date_obj.strftime('%Y-%m-%d')
                
                # データ抽出
                record = {
                    "date": formatted_date,
                    "nikkei_avg": parse_value(cells[1].text),
                    "foreign": parse_value(cells[3].text),
                    "securities_self": parse_value(cells[4].text),
                    "individual_total": parse_value(cells[5].text),
                    "individual_cash": parse_value(cells[6].text),
                    "individual_credit": parse_value(cells[7].text),
                    "investment_trust": parse_value(cells[8].text),
                    "business_corp": parse_value(cells[9].text),
                    "other_corp": parse_value(cells[10].text),
                    "trust_banks": parse_value(cells[11].text),
                    "insurance": parse_value(cells[12].text),
                    "city_banks": parse_value(cells[13].text)
                }
                
                new_data.append(record)
                
            except Exception as e:
                continue
        
        session.close()
        return new_data
        
    except Exception as e:
        log(f"Error with requests-html: {e}")
        session.close()
        return []

def scrape_with_beautifulsoup():
    """BeautifulSoupでフォールバック（静的HTML用）"""
    log("Using BeautifulSoup (static HTML only)")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(TARGET_URL, headers=headers, timeout=20)
        response.encoding = response.apparent_encoding
        
        soup = BeautifulSoup(response.text, 'lxml')
        table = soup.find('table', {'id': 'datatbl'})
        
        if not table:
            log("ERROR: Table not found")
            return []
        
        rows = table.find_all('tr')
        log(f"Found {len(rows)} rows")
        
        new_data = []
        
        for row in rows:
            if row.find('th'):
                continue
            
            cells = row.find_all('td')
            
            if len(cells) < 14:
                continue
            
            if row.get('class') and 'yy' in row.get('class'):
                continue
            
            try:
                first_cell = cells[0]
                time_tag = first_cell.find('time')
                date_text = time_tag.get_text().strip() if time_tag else first_cell.get_text().strip()
                
                date_clean = date_text.split()[0]
                
                if '月計' in date_clean or '年計' in date_clean:
                    continue
                
                date_obj = datetime.strptime(date_clean, '%Y/%m/%d')
                formatted_date = date_obj.strftime('%Y-%m-%d')
                
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
                
            except Exception as e:
                continue
        
        return new_data
        
    except Exception as e:
        log(f"Error with BeautifulSoup: {e}")
        return []

def scrape_shutai_data():
    log(f"Starting scraping process. Target: {TARGET_URL}")
    log(f"Debug Mode: {DEBUG_MODE}")
    log(f"requests-html available: {USE_REQUESTS_HTML}")
    
    try:
        # requests-htmlが利用可能ならそちらを使用
        if USE_REQUESTS_HTML:
            new_data = scrape_with_requests_html()
        else:
            new_data = scrape_with_beautifulsoup()
        
        log(f"Extracted {len(new_data)} valid weekly records")
        
        if len(new_data) == 0:
            log("WARNING: Valid data count is 0. Aborting save.")
            log("TIP: Install requests-html for JavaScript rendering support:")
            log("  pip install requests-html --break-system-packages")
            return
        
        # サンプルデータ表示
        log("Sample data (latest 5 records):")
        for record in new_data[-5:]:
            log(f"  {record['date']}: 海外={record['foreign']:,}, 個人計={record['individual_total']:,}")
        
        # 保存ロジック
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
