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
BASE_JSON_URL = "https://www.jpx.co.jp/automation/markets/derivatives/participant-volume/json/"
JPX_DOMAIN = "https://www.jpx.co.jp"

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
    if not isinstance(name, str): return "OTHERS"
    name_check = name.replace(" ", "").lower()
    for cat, keywords in BROKER_CATEGORIES.items():
        for kw in keywords:
            if kw.lower() in name_check:
                return cat
    return "OTHERS"

def get_current_month_str():
    return datetime.now().strftime("%Y%m")

def get_json_url(json_type, year_month):
    return f"{BASE_JSON_URL}{json_type}_{year_month}.json"

def fetch_json_data(url):
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
    """ExcelファイルのURLから直接データを読み込んで解析 (ロジック強化版)"""
    
    if url.startswith("/"):
        full_url = JPX_DOMAIN + url
    else:
        full_url = url

    try:
        print(f"  Downloading Excel: {full_url}")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(full_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Excelを読み込む (ヘッダーなしで全行読み込み)
        try:
            df = pd.read_excel(io.BytesIO(response.content), header=None)
        except Exception as e:
            print(f"    Excel read failed: {e}")
            return []
        
        # デバッグ: 最初の5行を表示
        # print("    [Debug] First 5 rows of Excel:")
        # print(df.head(5))

        # ======================================================
        # 戦略: 会社名が入っている列（キーカラム）を探す
        # ======================================================
        participant_col_idx = -1
        header_row_idx = -1
        
        # 1. 有名な証券会社名が含まれている列を探す (最も確実)
        known_brokers = ["野村", "Nomura", "Goldman", "ABN", "Mizuho", "SBI", "楽天"]
        
        for col in df.columns:
            # その列の中身を文字列にしてチェック
            column_values = df[col].astype(str).tolist()
            match_count = sum(1 for val in column_values for broker in known_brokers if broker in val)
            
            # 3つ以上ヒットしたら、それが参加者名の列だと断定する
            if match_count >= 3:
                participant_col_idx = col
                print(f"    Found participant column by content detection: Col {col}")
                
                # ヘッダー行は、その列で最初にヒットした行の1つ上...ではなく
                # データ解析時に「数値以外の行」をスキップする方式にするため、厳密なヘッダー位置は不要
                break
        
        if participant_col_idx == -1:
            # 2. キーワード検索 (フォールバック)
            keywords = ["参加者", "Participant", "証券会社", "Member"]
            for i, row in df.iterrows():
                row_str = row.astype(str).values
                for col_idx, cell_val in enumerate(row_str):
                    if any(k in str(cell_val) for k in keywords):
                        header_row_idx = i
                        participant_col_idx = col_idx # そのキーワードがあった列
                        print(f"    Found header at Row {i}, Col {col_idx}")
                        break
                if participant_col_idx != -1: break

        if participant_col_idx == -1:
            print("    Error: Could not identify participant column.")
            return []

        # ======================================================
        # データ抽出処理
        # ======================================================
        result = []
        
        # 全行をループ（ヘッダー位置が不明でも、中身で判定して抽出）
        # カラム名が分からないので、列インデックス(0, 1, 2...)をそのまま使う
        # JPXのフォーマットは大体 [参加者名, ProductA_Buy, ProductA_Sell, ProductA_Net...] の並び
        
        # 列名リストを作成（後でJSONのキーにするため）
        # 簡易的に "Col_1", "Col_2" とする（具体的な商品名は列位置で判断するか、そのまま保存）
        
        for i, row in df.iterrows():
            p_name = row[participant_col_idx]
            
            # 無効な行判定
            if pd.isna(p_name): continue
            p_name_str = str(p_name).strip()
            if p_name_str in ["", "-", "nan", "参加者", "Participant", "証券会社"]: continue
            
            # 合計行やヘッダー行っぽいものを除外
            if any(x in p_name_str for x in ["合計", "Total", "J-NET", "立会", "平均", "Turnover"]):
                continue
            
            # カテゴリ判定
            category = get_category(p_name_str)
            
            # 会社名として短すぎる、または数字だけのものはノイズとして除外
            if len(p_name_str) < 2 or p_name_str.replace(',','').isdigit():
                continue

            # 数値データの抽出
            products = {}
            for col in df.columns:
                if col == participant_col_idx: continue
                
                val = row[col]
                try:
                    if pd.isna(val): continue
                    val_str = str(val).strip()
                    if val_str in ["-", "", "nan"]: continue

                    # カンマ削除して数値化
                    val_clean = val_str.replace(',', '')
                    val_float = float(val_clean)
                    
                    if val_float != 0:
                        # JSONキーは「列インデックス」にする (Col_1, Col_2...)
                        # フロントエンド側で「1列目はラージ先物」のように解釈する必要があるが、
                        # とりあえずデータを確保することを優先
                        products[f"Col_{col}"] = int(val_float)
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
    print("=== Starting Daily Participant Analysis (Content Detection Mode) ===")
    
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    current_ym = get_current_month_str()
    json_url = get_json_url("participant_volume", current_ym)
    
    data_obj = fetch_json_data(json_url)
    
    if not data_obj:
        print("Trying previous month...")
        prev_date = datetime.now() - relativedelta(months=1)
        prev_ym = prev_date.strftime("%Y%m")
        json_url = get_json_url("participant_volume", prev_ym)
        data_obj = fetch_json_data(json_url)

    if not data_obj or "TableDatas" not in data_obj:
        print("Error: Could not retrieve any valid JSON data from JPX.")
        return

    table_datas = data_obj["TableDatas"]
    if not table_datas:
        print("Error: JSON 'TableDatas' is empty.")
        return
    
    latest_entry = table_datas[0]
    trade_date_str = latest_entry.get("TradeDate", "Unknown")
    
    formatted_date = f"{trade_date_str[:4]}/{trade_date_str[4:6]}/{trade_date_str[6:8]}"
    print(f"Latest Data Date: {formatted_date}")

    night_data = []
    day_data = []

    # キー名を修正 ("Night", "WholeDay")
    night_url = latest_entry.get("Night")
    if night_url and night_url != "-":
        print(f"Processing Night Session... (Path: {night_url})")
        night_data = fetch_and_parse_excel(night_url)
    else:
        print("Night session data not found.")

    day_url = latest_entry.get("WholeDay")
    if day_url and day_url != "-":
        print(f"Processing Day Session... (Path: {day_url})")
        day_data = fetch_and_parse_excel(day_url)
    else:
        print("Day session data not found.")

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
