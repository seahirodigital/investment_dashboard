import requests
import re
import pandas as pd
import json
import os
from bs4 import BeautifulSoup
from datetime import datetime
import io
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

def init_firestore():
    if not firebase_admin._apps:
        key_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'firebase-key.json')
        try:
            if os.path.exists(key_path):
                cred = credentials.Certificate(key_path)
            elif 'FIREBASE_KEY_JSON' in os.environ and os.environ['FIREBASE_KEY_JSON'].strip():
                try:
                    cred_dict = json.loads(os.environ['FIREBASE_KEY_JSON'])
                except:
                    # Allow fallback to parsing it as a string formatted json (some environments escape quotes)
                    import ast
                    cred_dict = ast.literal_eval(os.environ['FIREBASE_KEY_JSON'])
                cred = credentials.Certificate(cred_dict)
            else:
                print("Firebase credential missing. Skipping Firebase initialization.")
                return None
            firebase_admin.initialize_app(cred)
        except Exception as e:
            print(f"Firebase initialization failed: {e}")
            return None
    try:
        return firestore.client()
    except Exception as e:
        print(f"Firestore client init failed: {e}")
        return None

def fetch_option_data():
    import sys
    target_date = None
    if len(sys.argv) > 1:
        target_date = sys.argv[1] # Expected format YYYYMMDD
        
    index_url = 'https://www.jpx.co.jp/markets/derivatives/trading-volume/index.html'
    html = requests.get(index_url, timeout=10).text
    soup = BeautifulSoup(html, 'html.parser')
    
    xlsx_path = None
    
    # If a specific date is given, try to find a link that matches it exactly
    if target_date:
        for a in soup.find_all('a'):
            href = a.get('href')
            if href and f'{target_date}open_interest.xlsx' in href:
                xlsx_path = href.strip()
                break
    
    # Otherwise, fallback to the latest one
    if not xlsx_path:
        for a in soup.find_all('a'):
            href = a.get('href')
            if href and 'open_interest.xlsx' in href:
                xlsx_path = href.strip()
                break
            
    if not xlsx_path:
        print(f"open_interest.xlsx not found for target {target_date or 'latest'}")
        return
        
    if not xlsx_path.startswith('http'):
        if xlsx_path.startswith('/'):
            xlsx_path = 'https://www.jpx.co.jp' + xlsx_path
        else:
            xlsx_path = 'https://www.jpx.co.jp/' + xlsx_path
            
    match = re.search(r'(\d{8})open_interest\.xlsx', xlsx_path)
    if match:
        data_date = match.group(1)
    else:
        data_date = target_date if target_date else datetime.now().strftime('%Y%m%d')
        
    print(f"Downloading {xlsx_path} for date {data_date}")
    try:
        content = requests.get(xlsx_path, timeout=10).content
    except Exception as e:
        print(f"Failed to fetch {xlsx_path}: {e}")
        return
    
    xls = pd.ExcelFile(io.BytesIO(content), engine='openpyxl')
    
    p1_sheet = None
    for sheet in xls.sheet_names:
        if "デリバティブ建玉" in sheet or "残高" in sheet:
            p1_sheet = sheet
            break
            
    p1_data = {'labels': [], 'totals': [], 'differences': []}
    if p1_sheet:
        df1 = pd.read_excel(xls, sheet_name=p1_sheet, header=None)
        targets = ["日経225", "TOPIX", "日経225mini", "日経225マイクロ"]
        for target in targets:
            found = False
            for r in range(len(df1)):
                if found: break
                for c in range(len(df1.columns)):
                    val = str(df1.iat[r, c]).replace(' ', '').replace('\u3000', '')
                    if val == target:
                        for r2 in range(r, len(df1)):
                            if c+1 < len(df1.columns):
                                val2 = str(df1.iat[r2, c+1]).replace(' ', '').replace('\u3000', '')
                                if "合計" in val2:
                                    try:
                                        total = float(str(df1.iat[r2, c+3]).replace(',', ''))
                                        diff = float(str(df1.iat[r2, c+4]).replace(',', ''))
                                        p1_data['labels'].append(target)
                                        p1_data['totals'].append(total)
                                        p1_data['differences'].append(diff)
                                        found = True
                                        break
                                    except:
                                        pass

    p2_sheet = None
    for sheet in xls.sheet_names:
        if "別紙1" in sheet:
            p2_sheet = sheet
            break
            
    p2_data = {'strikes': [], 'c_oi': [], 'c_diff': [], 'p_oi': [], 'p_diff': []}
    if p2_sheet:
        df2 = pd.read_excel(xls, sheet_name=p2_sheet, header=None)
        strike_map = {}
        for r in range(len(df2)):
            for c in range(len(df2.columns)):
                cell_val = str(df2.iat[r, c])
                match = re.search(r'([PC])\d{4}-(\d+)', cell_val, re.IGNORECASE)
                if match:
                    t = match.group(1).upper()
                    strike = int(match.group(2))
                    if strike not in strike_map:
                        strike_map[strike] = {'p': 0, 'p_diff': 0, 'c': 0, 'c_diff': 0}
                        
                    try:
                        oi = float(str(df2.iat[r, c+2]).replace(',', '')) if pd.notna(df2.iat[r, c+2]) else 0
                        diff = float(str(df2.iat[r, c+3]).replace(',', '')) if pd.notna(df2.iat[r, c+3]) else 0
                    except:
                        oi = 0
                        diff = 0
                        
                    if t == 'P':
                        strike_map[strike]['p'] += oi
                        strike_map[strike]['p_diff'] += diff
                    elif t == 'C':
                        strike_map[strike]['c'] += oi
                        strike_map[strike]['c_diff'] += diff
                        
        sorted_strikes = sorted(strike_map.keys())
        for s in sorted_strikes:
            o = strike_map[s]
            if o['p'] == 0 and o['c'] == 0 and o['p_diff'] == 0 and o['c_diff'] == 0:
                continue
            p2_data['strikes'].append(s)
            p2_data['c_oi'].append(o['c'])
            p2_data['c_diff'].append(o['c_diff'])
            p2_data['p_oi'].append(o['p'])
            p2_data['p_diff'].append(o['p_diff'])
            
    day_data = {
        'date': data_date,
        'p1': p1_data,
        'p2_225': p2_data
    }
    
    history_file = 'option_history.json'
    abs_history_file = os.path.join(os.path.dirname(__file__), '..', history_file)
    os.makedirs(os.path.dirname(abs_history_file), exist_ok=True)
    
    if os.path.exists(abs_history_file):
        with open(abs_history_file, 'r', encoding='utf-8') as f:
            try:
                history = json.load(f)
            except:
                history = {}
    else:
        history = {}
        
    history[data_date] = day_data
    
    with open(abs_history_file, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
        
    print(f"Saved {data_date} options data successfully format JSON.")

    db = init_firestore()
    if db:
        try:
            doc_ref = db.collection('option_data').document(data_date)
            # Remove any non-supported types like numpy primitives if applicable.
            # But here day_data comes from pd but converted correctly?
            # day_data contains floats and ints and arrays, it should be fine.
            # Let's save to firebase.
            doc_ref.set(day_data)
            print(f"Successfully saved {data_date} options data to Firebase.")
        except Exception as e:
            print(f"Error saving {data_date} options data to Firebase: {e}")

if __name__ == "__main__":
    fetch_option_data()
