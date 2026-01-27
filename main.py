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
    # Excelを読み込み。エンジンを指定し、全てのセルを文字列として扱う
    df = pd.read_excel(url, header=None).astype(str)
    
    # 1. 日付の取得（4行目 A列）
    date_label = df.iloc[3, 0].split(' ')[0].split('\n')[0]
    print(f"Target Date: {date_label}")

    # 2. 「海外投資家」を検索（空白や改行を無視）
    target_row_idx = None
    for idx, row in df.iterrows():
        cell_value = str(row[1]) # B列をチェック
        if "海外投資家" in cell_value:
            target_row_idx = idx
            print(f"Found 'Foreigners' at row: {idx + 1}")
            break
            
    if target_row_idx is None:
        # B列で見つからない場合、全列から探す
        mask = df.apply(lambda x: x.str.contains("海外投資家", na=False)).any(axis=1)
        target_row_idx = df[mask].index[0]
        print(f"Found 'Foreigners' in alternative search at row: {target_row_idx + 1}")

    # 3. 数値の抽出
    # 海外投資家行の1行下（買い Purchases）のL列（Index 11）を取得
    val_str = df.iloc[target_row_idx + 1, 11]
    
    # 数値化（カンマやゴミを除去）
    val_clean = val_str.replace(',', '').replace(' ', '').split('.')[0]
    val = int(val_clean)
    
    return date_label, val

def main():
    try:
        url = get_latest_excel_url()
        print(f"Downloading: {url}")
        date, val = extract_data(url)
        
        if os.path.exists(CSV_FILE):
            history = pd.read_csv(CSV_FILE)
        else:
            history = pd.DataFrame(columns=['Date', 'Value'])
        
        # 重複削除
        history = history[history['Date'] != date]
        
        new_row = pd.DataFrame({'Date': [date], 'Value': [val]})
        history = pd.concat([history, new_row], ignore_index=True)
        history.to_csv(CSV_FILE, index=False)
        
        # グラフ作成
        plt.figure(figsize=(10, 5))
        plt.plot(history['Date'], history['Value'], marker='o', color='blue', linewidth=2)
        plt.axhline(0, color='red', linestyle='--', alpha=0.5)
        plt.title('Foreign Investors Net Trading Volume (Weekly)')
        plt.grid(axis='y', linestyle=':', alpha=0.7)
        plt.tight_layout()
        plt.savefig('trend.png')
        print(f"Successfully updated: {date} = {val}")
        
    except Exception as e:
        print(f"Critical Error: {e}")
        exit(1)

if __name__ == "__main__":
    main()
