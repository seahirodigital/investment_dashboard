import json
import logging
import os
import io
import requests
import pandas as pd
from datetime import datetime
import dateutil.relativedelta
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

def init_firestore():
    if not firebase_admin._apps:
        key_path = 'firebase-key.json'
        try:
            if os.path.exists(key_path):
                cred = credentials.Certificate(key_path)
            elif 'FIREBASE_KEY_JSON' in os.environ and os.environ['FIREBASE_KEY_JSON'].strip():
                try:
                    cred_dict = json.loads(os.environ['FIREBASE_KEY_JSON'])
                except:
                    import ast
                    cred_dict = ast.literal_eval(os.environ['FIREBASE_KEY_JSON'])
                cred = credentials.Certificate(cred_dict)
            else:
                logging.warning("Firebase credential missing. Skipping Firebase initialization.")
                return None
            firebase_admin.initialize_app(cred)
        except Exception as e:
            logging.error(f"Firebase initialization failed: {e}")
            return None
    try:
        return firestore.client()
    except Exception as e:
        logging.error(f"Firestore client init failed: {e}")
        return None

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Participant Mapping
broker_mapping = {
    "goldman": {"cat": "US", "rank": 10},
    "jpmorgan": {"cat": "US", "rank": 20},
    "bofa": {"cat": "US", "rank": 30},
    "citigroup": {"cat": "US", "rank": 40},
    "morgan": {"cat": "US", "rank": 50},
    "abn amro": {"cat": "EU", "rank": 10},
    "societe": {"cat": "EU", "rank": 20},
    "barclays": {"cat": "EU", "rank": 30},
    "bnp": {"cat": "EU", "rank": 40},
    "ubs": {"cat": "EU", "rank": 50},
    "deutsche": {"cat": "EU", "rank": 60},
    "nomura": {"cat": "JP", "rank": 10},
    "daiwa": {"cat": "JP", "rank": 20},
    "mizuho": {"cat": "JP", "rank": 30},
    "mitsubishi": {"cat": "JP", "rank": 40},
    "smbc": {"cat": "JP", "rank": 50},
    "sbi": {"cat": "Net", "rank": 10},
    "rakuten": {"cat": "Net", "rank": 20},
    "monex": {"cat": "Net", "rank": 30},
    "matsui": {"cat": "Net", "rank": 40},
}

cat_order = {"US": 1, "EU": 2, "JP": 3, "Net": 4, "Others": 5}

def get_broker_info(name_en: str):
    if not isinstance(name_en, str):
        return "Others", cat_order["Others"] * 1000 + 999
    name_lower = name_en.lower()
    for key, val in broker_mapping.items():
        if key in name_lower:
            return val["cat"], cat_order[val["cat"]] * 1000 + val["rank"]
    return "Others", cat_order["Others"] * 1000 + 999

def process_dataframe(df, nikkei_price=55000.0, topix_price=3700.0, delta_atm=0.5):
    # Setup data
    df = df[df['EN_Name'].astype(str).str.strip() != '']
    grouped = df.groupby(['EN_Name', 'JP_Name', 'Product_Class', 'Contract_Issue'], as_index=False)['Net'].sum()

    results = []
    op_matrix = []
    firm_info = {}

    firms = grouped['EN_Name'].unique()
    for firm in firms:
        firm_data = grouped[grouped['EN_Name'] == firm]
        jp_name = firm_data['JP_Name'].iloc[0]
        display_name = jp_name[:10] if isinstance(jp_name, str) else str(firm)[:10]
        category, rank = get_broker_info(firm)
        
        firm_info[firm] = {
            "display": display_name,
            "category": category,
            "rank": rank
        }
        
        nk_large = firm_data[firm_data['Product_Class'] == 'NK225F']['Net'].sum()
        nk_mini = firm_data[firm_data['Product_Class'] == 'NK225MF']['Net'].sum()
        topix_f = firm_data[(firm_data['Product_Class'] == 'TOPIXF') | (firm_data['Product_Class'] == 'TOPIX')]['Net'].sum()
        
        options = firm_data[firm_data['Contract_Issue'].str.contains(' OP | OOP ', na=False, case=False)]
        op_delta_amount = options['Net'].sum() * delta_atm * 1000
        
        for _, row in options.iterrows():
            issue = str(row['Contract_Issue'])
            cp = 'P' if ' P' in issue else ('C' if ' C' in issue else None)
            strike = 0
            import re
            match = re.search(r'-(\d+)', issue)
            if match:
                strike = int(match.group(1))
            if cp and strike:
                op_matrix.append({
                    "Firm": firm,
                    "Type": cp,
                    "Strike": strike,
                    "Net": row['Net']
                })
        
        delta_amount_yen = (nk_large * nikkei_price * 1000) + \
                           (nk_mini * nikkei_price * 100) + \
                           (topix_f * topix_price * 1000) + \
                           op_delta_amount
                           
        delta_amount_oku = delta_amount_yen / 100000000.0
        
        results.append({
            "Company": display_name,
            "Category": category,
            "NK225F": int(nk_large),
            "NK225M": int(nk_mini),
            "TOPIXF": int(topix_f),
            "DeltaOku": round(delta_amount_oku, 2),
            "Rank": rank
        })

    op_df = pd.DataFrame(op_matrix)
    matrix_data = []
    strikes = []
    if not op_df.empty:
        valid_strikes = [int(s) for s in op_df['Strike'].unique() if int(s) >= 10000]
        strikes = sorted(valid_strikes)
        
        for firm in op_df['Firm'].unique():
            firm_ops = op_df[op_df['Firm'] == firm]
            info = firm_info.get(firm, {"display": str(firm)[:10], "category": "Others", "rank": 9999})
            row_data = {
                "Company": info["display"],
                "Category": info["category"],
                "Rank": info["rank"]
            }
            for s in strikes:
                call_net = firm_ops[(firm_ops['Strike'] == s) & (firm_ops['Type'] == 'C')]['Net'].sum()
                put_net = firm_ops[(firm_ops['Strike'] == s) & (firm_ops['Type'] == 'P')]['Net'].sum()
                row_data[f"C_{s}"] = int(call_net)
                row_data[f"P_{s}"] = int(put_net)
            row_data["C_Total"] = int(firm_ops[firm_ops['Type'] == 'C']['Net'].sum())
            row_data["P_Total"] = int(firm_ops[firm_ops['Type'] == 'P']['Net'].sum())
            row_data["Net_Total"] = row_data["C_Total"] + row_data["P_Total"]
            matrix_data.append(row_data)

    results.sort(key=lambda x: x["Rank"])
    if matrix_data:
        matrix_data.sort(key=lambda x: x["Rank"])

    return {"status": "success", "results": results, "matrix": matrix_data, "strikes": strikes if not op_df.empty else []}

def run():
    import sys
    target_date = None
    if len(sys.argv) > 1:
        target_date = sys.argv[1].replace('-', '') # e.g. 20260310
        
    logging.info(f"Starting JPX Data Fetch for date {target_date or 'latest'}...")
    
    # Decide which months to check based on target_date
    if target_date:
        try:
            target_dt = datetime.strptime(target_date, '%Y%m%d')
            months_to_try = [target_dt]
        except ValueError:
            target_dt = datetime.now()
            months_to_try = [target_dt]
    else:
        now = datetime.now()
        months_to_try = [now, now - dateutil.relativedelta.relativedelta(months=1)]
    
    xlsx_path = None
    data_date = None
    for m in months_to_try:
        yyyymm = m.strftime('%Y%m')
        url = f"https://www.jpx.co.jp/automation/markets/derivatives/participant-volume/json/participant_volume_{yyyymm}.json"
        
        logging.info(f"Checking URL: {url}")
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            for row in data.get('TableDatas', []):
                path = row.get('WholeDay')
                trade_date = str(row.get('TradeDate'))
                if target_date and trade_date != target_date:
                    continue
                    
                if path and str(path).strip() != '-' and 'xlsx' in str(path):
                    xlsx_path = path
                    data_date = trade_date
                    break
        if xlsx_path:
            break
            
    if not xlsx_path:
        logging.error("Failed to find Excel file URL on JPX website.")
        return
        
    if not xlsx_path.startswith('http'):
        xlsx_path = "https://www.jpx.co.jp" + xlsx_path
        
    logging.info(f"Downloading Excel from: {xlsx_path}")
    resp = requests.get(xlsx_path, timeout=30)
    resp.raise_for_status()
    
    df = pd.read_excel(io.BytesIO(resp.content), sheet_name="手口上位一覧", header=5, engine='openpyxl')
    cols = df.columns.tolist()
    df = df.rename(columns={
        cols[0]: 'Product_Class',
        cols[2]: 'Contract_Issue',
        cols[5]: 'JP_Name',
        cols[6]: 'EN_Name',
        cols[7]: 'Volume'
    })
    df = df[['Product_Class', 'Contract_Issue', 'EN_Name', 'JP_Name', 'Volume']].dropna(subset=['Volume'])
    df['Net'] = pd.to_numeric(df['Volume'], errors='coerce').fillna(0) * 1
    
    df = df[df['Product_Class'].astype(str).str.strip() != '']
    df = df[df['EN_Name'].notna()]
    
    # Generate JSON data
    output_data = process_dataframe(df)
    # 取引日付をJSONに含める（HTMLフォールバック読み込み用）
    output_data['date'] = data_date

    # Write to data/teguchi.json
    os.makedirs('data', exist_ok=True)
    out_path = os.path.join('data', 'teguchi.json')

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
        
    logging.info(f"Successfully saved data to {out_path}")

    # Save to Firebase
    if data_date:
        db = init_firestore()
        if db:
            try:
                # Firestore will not accept int64, doing a quick round-trip stringification
                clean_data = json.loads(json.dumps(output_data))
                db.collection('teguchi_data').document(data_date).set(clean_data)
                logging.info(f"Successfully saved {data_date} teguchi data to Firebase.")
            except Exception as e:
                logging.error(f"Error saving {data_date} teguchi data to Firebase: {e}")
    else:
        logging.warning("No data_date found, cannot save to Firebase.")

if __name__ == "__main__":
    run()
