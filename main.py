import pandas as pd
import requests
from bs4 import BeautifulSoup
import os
import matplotlib.pyplot as plt

CSV_FILE = 'history.csv'
BASE_URL = "https://www.jpx.co.jp"
TARGET_URL = "https://www.jpx.co.jp/markets/statistics-equities/investor-type/00-00-archives-00.html"

def get_latest_excel_url():
    res = requests.get(TARGET_URL)
    soup = BeautifulSoup(res.text, 'html.parser')
    link = soup.find('a', href=lambda x: x and x.endswith('.xls'))
    return BASE_URL + link['href']

def extract_data(url):
    df = pd.read_excel(url, header=None)
    
    # 1. 日付の取得
    date_label = str(df.iloc[3, 0]).split(' ')[0].split('\n')[0]
    
    # 2. 「海外投資家」の行を探す
    target_row_idx = None
    for idx, row in df.iterrows():
        if "海外投資家" in str(row[1]): # B列を優先
            target_row_idx = idx
            break
    
    if target_row_idx is None:
        mask = df.apply(lambda x: x.astype(str).str.contains("海外投資家")).any(axis=1)
        target_row_idx = df[mask].index[0]

    # 3. 数値の抽出（ここを強化）
    # 海外投資家行の「1行下(買い)」の中で、数値が入っている列を後ろから探す
    # 通常、一番右側の数値が「差引き（Balance）」になる
    target_row = df.iloc[target_row_idx + 1]
    val = None
    for item in reversed(target_row):
        try:
            temp_val = float(str(item).replace(',', ''))
            if not pd.isna(temp_val):
                val = int(temp_val)
                break
        except:
            continue
            
    if val is None:
        raise Exception("数値が見つかりませんでした")
        
    return date_label, val

def main():
    try:
        url = get_latest_excel_url()
        date, val = extract_data(url)
        print(f"Captured: {date} = {val}")
        
        if os.path.exists(CSV_FILE):
            history = pd.read_csv(CSV_FILE)
        else:
            history = pd.DataFrame(columns=['Date', 'Value'])
        
        history = history[history['Date'] != date]
        new_row = pd.DataFrame({'Date': [date], 'Value': [val]})
        history = pd.concat([history, new_row], ignore_index=True)
        history.to_csv(CSV_FILE, index=False)
        
        # グラフ作成
        plt.figure(figsize=(10, 5))
        plt.plot(history['Date'], history['Value'], marker='o', color='#1f77b4', linewidth=2)
        plt.axhline(0, color='red', linestyle='--', alpha=0.5)
        plt.title('Foreign Investors Net Trading Volume (Weekly)')
        plt.grid(True, linestyle=':', alpha=0.7)
        plt.tight_layout()
        plt.savefig('trend.png')
        
    except Exception as e:
        print(f"Error: {e}")
        exit(1)

if __name__ == "__main__":
    main()
