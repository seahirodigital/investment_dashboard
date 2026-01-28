import os
import json
import requests
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

# ==========================================
# 設定
# ==========================================
# JPXのデータソース (JSON形式)
BASE_JSON_URL = "https://www.jpx.co.jp/automation/markets/derivatives/participant-volume/json/"

# 出力先設定
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "daily_participant.json")

# 証券会社カテゴリ辞書 (名寄せ用)
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

def get_current_month_str():
    """現在の年月をYYYYMM形式で取得"""
    now = datetime.now()
    return now.strftime("%Y%m")

def get_json_url(json_type, year_month):
    """
    JSONファイルのURLを構築
    json_type: 'participant_volume' など
    """
    return f"{BASE_JSON_URL}{json_type}_{year_month}.json"

def fetch_json_data(url):
    """JSONデータを取得"""
    try:
        print(f"Fetching JSON: {url}")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 404:
            print("JSON not found (404).")
            return None
            
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Failed to fetch JSON: {e}")
        return None

def fetch_and_parse_excel(url):
    """ExcelファイルのURLから直接データを読み込んで解析"""
    try:
        print(f"  Downloading Excel: {url}")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Excelをバイナリとして読み込む
        df = pd.read_excel(response.content, header=None, engine='openpyxl')
        
        # ヘッダー行("参加者"などが含まれる行)を探す
        header_row_idx = -1
        for i, row in df.iterrows():
            row_str = row.astype(str).values
            if any(k in str(s) for s in row_str for k in ["参加者", "Participant", "証券会社"]):
                header_row_idx = i
                break
        
        if header_row_idx == -1:
            print("  Warning: Header row not found in Excel.")
            return []

        # データフレームの整形
        df.columns = df.iloc[header_row_idx]
        df = df.iloc[header_row_idx + 1:].reset_index(drop=True)
        # カラム名の改行削除
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
            
            # 無効な行をスキップ
            if pd.isna(p_name) or str(p_name).strip() == "":
                continue
            if "合計" in str(p_name) or "Total" in str(p_name):
                continue
            
            p_name = str(p_name).strip()
            category = get_category(p_name)

            # 数値データの抽出
            products = {}
            for col in df.columns:
                if col == col_participant:
                    continue
                
                val = row[col]
                try:
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
        print(f"  Excel parse error: {e}")
        return []

def main():
    print("=== Starting Daily Participant Analysis (JSON Method) ===")
    
    # フォルダ作成
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # 1. 今月のJSON URLを構築
    current_ym = get_current_month_str()
    json_url = get_json_url("participant_volume", current_ym)
    
    # 2. JSON取得
    data_obj = fetch_json_data(json_url)
    
    # データがない場合（月初の更新前など）、先月のデータを試す
    if not data_obj:
        print("Trying previous month...")
        prev_date = datetime.now() - relativedelta(months=1)
        prev_ym = prev_date.strftime("%Y%m")
        json_url = get_json_url("participant_volume", prev_ym)
        data_obj = fetch_json_data(json_url)

    if not data_obj or "TableDatas" not in data_obj:
        print("Error: Could not retrieve any valid JSON data from JPX.")
        return

    # 3. 最新の日付データを探す
    # TableDatas配列の先頭が最新とは限らないため、TradeDateでソートしてもよいが、
    # 通常JPXのJSONは日付順（または逆順）に並んでいる。ここでは配列の0番目（最新）を取得する
    # もしJPXの仕様が変わった場合に備え、リストが空でないか確認
    table_datas = data_obj["TableDatas"]
    if not table_datas:
        print("Error: JSON 'TableDatas' is empty.")
        return
    
    # 配列の先頭（最新の日付）を取得
    latest_entry = table_datas[0]
    trade_date_str = latest_entry.get("TradeDate", "Unknown") # "20260128" format
    
    # 表示用に日付整形 YYYY/MM/DD
    formatted_date = f"{trade_date_str[:4]}/{trade_date_str[4:6]}/{trade_date_str[6:8]}"
    print(f"Latest Data Date: {formatted_date}")

    # 4. ExcelファイルのURLを取得して解析
    night_data = []
    day_data = []

    # ナイトセッションURL (立会)
    night_url = latest_entry.get("NightSession")
    if night_url and night_url != "-":
        print("Processing Night Session...")
        night_data = fetch_and_parse_excel(night_url)

    # 日中セッションURL (立会)
    day_url = latest_entry.get("DaySession")
    if day_url and day_url != "-":
        print("Processing Day Session...")
        day_data = fetch_and_parse_excel(day_url)

    # 5. 結果を保存
    output_data = {
        "date": formatted_date,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "night_session": night_data,
        "day_session": day_data
    }

    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"\nSuccess! Data saved to: {OUTPUT_FILE}")
        print(f"Stats: Night({len(night_data)}) / Day({len(day_data)}) participants")
    except Exception as e:
        print(f"Error saving JSON file: {e}")

if __name__ == "__main__":
    main()
