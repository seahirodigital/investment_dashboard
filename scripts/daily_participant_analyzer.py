import os
import json
import requests
import pandas as pd
import io
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
    """JSONファイルのURLを構築"""
    return f"{BASE_JSON_URL}{json_type}_{year_month}.json"

def fetch_json_data(url):
    """JSONデータを取得"""
    try:
        print(f"Fetching JSON: {url}")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 404:
            print("  JSON not found (404).")
            return None
            
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"  Failed to fetch JSON: {e}")
        return None

def fetch_and_parse_excel(url):
    """ExcelファイルのURLから直接データを読み込んで解析 (強化版)"""
    try:
        print(f"  Downloading Excel: {url}")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Excelを読み込む (エンジンは自動判定)
        # header=Noneで全行読み込み、後で探す
        try:
            df = pd.read_excel(io.BytesIO(response.content), header=None)
        except Exception as e:
            print(f"    Excel read failed: {e}")
            return []
        
        # 1. ヘッダー行を探す ("参加者"などのキーワード)
        header_row_idx = -1
        keywords = ["参加者", "Participant", "証券会社", "Member", "Nan"]
        
        for i, row in df.iterrows():
            # 最初の20行だけチェック（高速化）
            if i > 20: break
            
            row_str = row.astype(str).values
            if any(k in str(s) for s in row_str for k in keywords):
                header_row_idx = i
                break
        
        # 2. ヘッダーが見つからない場合のフォールバック
        # 「列数が多く、かつ数値データが多い行」の1つ上をヘッダーと仮定する、などの処理も可能だが
        # ここでは「見つからなければ 0行目などを強制的にヘッダー扱い」して解析を試みる
        if header_row_idx == -1:
            print("    Warning: Explicit header row not found. Trying auto-detection...")
            # データが入っていそうな行を探す（NaNが少ない行）
            header_row_idx = 0 

        # データフレームの再構築
        df.columns = df.iloc[header_row_idx]
        df = df.iloc[header_row_idx + 1:].reset_index(drop=True)
        
        # カラム名のクリーニング（改行削除、空白削除）
        df.columns = [str(c).replace('\n', '').strip() for c in df.columns]

        # 3. 参加者名カラムを特定する
        col_participant = None
        
        # A. キーワードで探す
        for col in df.columns:
            if any(k in col for k in ["参加者", "Participant", "証券", "Member"]):
                col_participant = col
                break
        
        # B. 見つからない場合、最初の「文字列データが含まれる列」を参加者列とみなす (強力なフォールバック)
        if not col_participant:
            print("    Participant column not found by name. Searching by content...")
            for col in df.columns:
                # その列のユニークな値の多くが文字列かどうか
                sample_vals = df[col].dropna().head(10)
                if len(sample_vals) > 0 and all(isinstance(x, str) for x in sample_vals):
                    # 数字だけの列や "-" だけの列は除外したい
                    if not all(x.replace(',','').replace('-','').isdigit() for x in sample_vals):
                        col_participant = col
                        print(f"    Guessed participant column: {col}")
                        break
        
        if not col_participant:
            print("    Error: Could not identify participant column.")
            return []

        # 4. データ抽出
        result = []
        for _, row in df.iterrows():
            p_name = row[col_participant]
            
            # 無効な行をスキップ
            if pd.isna(p_name) or str(p_name).strip() == "":
                continue
            
            p_name_str = str(p_name).strip()
            
            # 合計行などをスキップ
            if any(x in p_name_str for x in ["合計", "Total", "J-NET", "立会", "平均"]):
                continue
            
            category = get_category(p_name_str)

            # 数値データの抽出
            products = {}
            for col in df.columns:
                if col == col_participant:
                    continue
                
                val = row[col]
                try:
                    # NaNチェック
                    if pd.isna(val): continue
                    
                    val_str = str(val).strip()
                    if val_str in ["-", "", "nan"]: continue

                    # カンマ削除して数値化
                    val_clean = val_str.replace(',', '')
                    val_float = float(val_clean)
                    
                    if val_float != 0:
                        # カラム名が長い場合があるので簡略化したり、そのままキーにしたり
                        products[col] = int(val_float)
                except:
                    pass
            
            # 有効なデータがあれば追加
            if products:
                result.append({
                    "name": p_name_str,
                    "category": category,
                    "data": products
                })

        print(f"    Extracted {len(result)} records.")
        return result

    except Exception as e:
        print(f"    Excel parse critical error: {e}")
        return []

def main():
    print("=== Starting Daily Participant Analysis (Enhanced) ===")
    
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
        print(f"Processing Night Session... (URL: {night_url})")
        night_data = fetch_and_parse_excel(night_url)

    # 日中セッションURL (立会)
    day_url = latest_entry.get("DaySession")
    if day_url and day_url != "-":
        print(f"Processing Day Session... (URL: {day_url})")
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
        
        # 簡易チェック: データが空なら警告
        if len(night_data) == 0 and len(day_data) == 0:
            print("WARNING: Output data is empty! Check parsing logic.")
            
    except Exception as e:
        print(f"Error saving JSON file: {e}")

if __name__ == "__main__":
    main()
