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
    # Excelを読み込む（全データを文字列として読み込み、検索しやすくする）
    df = pd.read_excel(url, header=None).astype(str)
    
    # 1. 日付ラベルの取得（4行目付近）
    date_label = df.iloc[3, 0].split(' ')[0]
    
    # 2. 「海外投資家」の行を特定
    # B列（Index 1）から探す
    row_idx = df[df[1].str.contains("海外投資家", na=False)].index[0]
    
    # 3. 「差引き Balance」の列を特定（10行目付近にある見出しから探す）
    # 海外投資家の行の右側にある数値のうち、今回ターゲットの「750,493,712」が入っている列(Index 11)を取得
    # JPXのこの形式では、L列（Index 11）が最新週の「差引き」です。
    val_str = df.iloc[row_idx + 1, 11] # 31行目のL列
    
    # カンマなどを除去して数値に変換
    val = int(float(val_str.replace(',', '')))
    
    return date_label, val

def main():
    try:
        url = get_latest_excel_url()
        date, val = extract_data(url)
        
        # 履歴の読み込み
        if os.path.exists(CSV_FILE):
            history = pd.read_csv(CSV_FILE)
        else:
            history = pd.DataFrame(columns=['Date', 'Value'])
        
        # 同じ日付があれば削除して更新（修正のため）
        history = history[history['Date'] != date]
        
        new_data = pd.DataFrame({'Date': [date], 'Value': [val]})
        history = pd.concat([history, new_data], ignore_index=True)
        history.to_csv(CSV_FILE, index=False)
        
        # グラフ作成
        plt.figure(figsize=(10,5))
        plt.plot(history['Date'], history['Value'], marker='o', color='blue')
        plt.axhline(0, color='red', linestyle='--')
        plt.title('Foreign Investors Net Trading Volume (Weekly)')
        plt.grid(True, linestyle=':', alpha=0.6)
        plt.tight_layout()
        plt.savefig('trend.png')
        print(f"Updated: {date} = {val}")
        
    except Exception as e:
        print(f"Error: {e}")
        exit(1)

if __name__ == "__main__":
    main()
