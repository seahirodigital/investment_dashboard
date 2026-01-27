import pandas as pd
import requests
from bs4 import BeautifulSoup
import os
import matplotlib.pyplot as plt

CSV_FILE = 'history.csv'
BASE_URL = "https://www.jpx.co.jp"
TARGET_URL = "https://www.jpx.co.jp/markets/statistics-equities/investor-type/00-00-archives-00.html"

def extract_data(url):
    # エンジンにxlrdを指定し、全ての型を維持して読み込み
    df = pd.read_excel(url, header=None)
    
    # 1. 日付の取得（4行目 A列）
    date_label = str(df.iloc[3, 0]).split(' ')[0]
    
    # 2. ピンポイントで「L31」のセルを狙う
    # Excelの L31セル = pandasでは [行Index 30, 列Index 11]
    # ここに「750,493,712」が入っていることを画像で確認済み
    raw_val = df.iloc[30, 11] 
    
    # 数値化処理
    try:
        val = int(float(str(raw_val).replace(',', '')))
    except:
        # もしズレていた場合のバックアップ検索（海外投資家の行の右端）
        mask = df.astype(str).apply(lambda x: x.str.contains("海外投資家")).any(axis=1)
        row_idx = df[mask].index[0]
        val = int(df.iloc[row_idx + 1, 11]) # 買い行のL列
        
    return date_label, val

def main():
    try:
        res = requests.get(TARGET_URL)
        soup = BeautifulSoup(res.text, 'html.parser')
        link = soup.find('a', href=lambda x: x and x.endswith('.xls'))
        url = BASE_URL + link['href']
        
        date, val = extract_data(url)
        print(f"Target Captured: {date} = {val}") # ログで確認用

        # 履歴更新
        if os.path.exists(CSV_FILE):
            history = pd.read_csv(CSV_FILE)
        else:
            history = pd.DataFrame(columns=['Date', 'Value'])
        
        # 間違ったデータ(192634)を削除して更新
        history = history[history['Date'] != date]
        new_row = pd.DataFrame({'Date': [date], 'Value': [val]})
        history = pd.concat([history, new_row], ignore_index=True)
        history.to_csv(CSV_FILE, index=False)
        
        # グラフ作成
        plt.figure(figsize=(10, 5))
        plt.plot(history['Date'], history['Value'], marker='o', color='green', linewidth=2)
        plt.axhline(0, color='black', linewidth=1)
        plt.title('Foreign Investors Net Trading Volume')
        plt.grid(True, alpha=0.3)
        plt.savefig('trend.png')
        
    except Exception as e:
        print(f"Error: {e}")
        exit(1)

if __name__ == "__main__":
    main()
