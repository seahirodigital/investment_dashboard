import requests
import pandas as pd
import json
import os
from datetime import datetime
import traceback
import io

# 環境変数からデバッグモードを取得
DEBUG_MODE = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
DATA_FILE = 'data/shutai_data.json'
TARGET_URL = 'https://nikkei225jp.com/data/shutai.php'

def log(msg):
    print(f"[Shutai Scraper] {msg}", flush=True)

def parse_value(val):
    """Pandasの値を数値に変換"""
    if pd.isna(val) or str(val).strip() == '-':
        return 0
    
    s_val = str(val).strip()
    
    # 不要な文字の削除
    s_val = s_val.replace(',', '').replace('%', '').replace(' ', '').replace('\n', '')
    
    # 記号処理（▼はマイナス、▲/+はプラス）
    if '▼' in s_val:
        s_val = '-' + s_val.replace('▼', '')
    elif '▲' in s_val:
        s_val = s_val.replace('▲', '')
    elif '+' in s_val:
        s_val = s_val.replace('+', '')
        
    try:
        if '.' in s_val:
            return float(s_val)
        return int(s_val)
    except ValueError:
        return 0

def is_summary_row(date_str):
    """月計・年計行かどうかを判定"""
    # "2026/01 月計", "2025 年計" などを除外
    return '月計' in date_str or '年計' in date_str or 'class="yy"' in date_str

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

        # 2. Pandasでテーブル抽出
        try:
            dfs = pd.read_html(io.StringIO(html_content), attrs={'id': 'datatbl'}, flavor='lxml')
        except Exception as e:
            log(f"Pandas(lxml) failed: {e}. Trying bs4...")
            try:
                dfs = pd.read_html(io.StringIO(html_content), attrs={'id': 'datatbl'}, flavor='bs4')
            except Exception as e2:
                log(f"Pandas(bs4) also failed: {e2}")
                return

        if not dfs:
            log("CRITICAL: No tables found matching id='datatbl'")
            return
            
        df = dfs[0]
        log(f"Table extracted. Rows: {len(df)}")
        
        # 3. データ処理（週次データのみ）
        new_data = []
        
        for idx, row in df.iterrows():
            # 列数チェック
            if len(row) < 12:
                continue

            # 日付カラムの値を確認
            date_val = str(row.iloc[0])
            
            # 月計・年計行を除外
            if is_summary_row(date_val):
                continue
            
            # 日付フォーマットチェック (YYYY/MM/DD形式のみ)
            try:
                # "2026/01/30" のような形式を抽出
                date_clean = date_val.split(' ')[0].split('\n')[0].strip()
                date_obj = datetime.strptime(date_clean, '%Y/%m/%d')
                formatted_date = date_obj.strftime('%Y-%m-%d')
            except ValueError:
                # 日付変換できない行はスキップ
                continue

            try:
                # データマッピング（全投資主体を取得）
                record = {
                    "date": formatted_date,
                    "nikkei_avg": parse_value(row.iloc[1]),           # 日経平均
                    "foreign": parse_value(row.iloc[3]),              # 海外
                    "securities_self": parse_value(row.iloc[4]),      # 証券自己
                    "individual_total": parse_value(row.iloc[5]),     # 個人計
                    "individual_cash": parse_value(row.iloc[6]),      # 個人(現金)
                    "individual_credit": parse_value(row.iloc[7]),    # 個人(信用)
                    "investment_trust": parse_value(row.iloc[8]),     # 投資信託
                    "business_corp": parse_value(row.iloc[9]),        # 事業法人
                    "other_corp": parse_value(row.iloc[10]),          # その他法人
                    "trust_banks": parse_value(row.iloc[11]),         # 信託銀行
                    "insurance": parse_value(row.iloc[12]),           # 生保損保
                    "city_banks": parse_value(row.iloc[13])           # 都銀地銀
                }
                new_data.append(record)
            except Exception as e:
                log(f"Error parsing row {idx}: {e}")
                continue

        log(f"Extracted {len(new_data)} valid weekly records (excluding monthly/yearly summaries).")

        if len(new_data) == 0:
            log("WARNING: Valid data count is 0. Aborting save.")
            return

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
