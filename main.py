import pandas as pd
import requests
from bs4 import BeautifulSoup
import os
import matplotlib.pyplot as plt

CSV_FILE = 'history.csv'
BASE_URL = "https://www.jpx.co.jp"
TARGET_URL = "https://www.jpx.co.jp/markets/statistics-equities/investor-type/00-00-archives-00.html"

def extract_data(url):
    # すべてのセルを文字列として読み込む
    df = pd.read_excel(url, header=None).astype(str)
    
    # 1. 日付取得
    date_label = df.iloc[3, 0].split(' ')[0]

    # 2. 「海外投資家」の行(B列)と「差引き Balance」の列(11行目付近)を特定
    # 「差引き Balance」という文字が含まれる列のIndexをすべて探す
    balance_cols = []
    header_row = df.iloc[11] # 12行目をチェック
    for i, cell in enumerate(header_row):
        if "差引き" in cell or "Balance" in cell:
            balance_cols.append(i)
    
    # 最新週の「差引き」は通常、一番右側の「差引き」列（Indexが大きい方）
    target_col_idx = max(balance_cols) if balance_cols else 10

    # 3. 「海外投資家」の行を探す
    row_idx = df[df[1].str.contains("海外投資家", na=False)].index[0]
    
    # 4. 「海外投資家」の「買い(Purchases)」行（row_idx + 1）のターゲット列から数値抽出
    val_str = df.iloc[row_idx + 1, target_col_idx]
    
    # カンマや不要な文字を排除して整数化
    val = int(float(val_str.replace(',', '').replace(' ', '')))
    
    return date_label, val

def main():
    try:
        res = requests.get(TARGET_URL)
        soup = BeautifulSoup(res.text, 'html.parser')
        link = soup.find('a', href=lambda x: x and x.endswith('.xls'))
        url = BASE_URL + link['href']
        
        date, val = extract_data(url)
        print(f"Captured: {date} = {val}")

        if os.path.exists(CSV_FILE):
            history = pd.read_csv(CSV_FILE)
        else:
            history = pd.DataFrame(columns=['Date', 'Value'])
        
        # 既存の誤ったデータを上書き
        history = history[history['Date'] != date]
        new_row = pd.DataFrame({'Date': [date], 'Value': [val]})
        history = pd.concat([history, new_row], ignore_index=True)
        history.to_csv(CSV_FILE, index=False)
        
        # グラフ作成
        plt.figure(figsize=(10, 5))
        plt.plot(history['Date'], history['Value'], marker='o', color='blue')
        plt.axhline(0, color='red', linestyle='--')
        plt.title('Foreign Investors Net Trading Volume')
        plt.grid(True, alpha=0.3)
        plt.savefig('trend.png')
        
    except Exception as e:
        print(f"Error: {e}")
        exit(1)

if __name__ == "__main__":
    main()
