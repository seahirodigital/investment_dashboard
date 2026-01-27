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
    if not link:
        raise Exception("Excelが見つかりませんでした")
    return BASE_URL + link['href']

def extract_data(url):
    # JPXのxls読み込み
    df = pd.read_excel(url, header=None)
    # 日付ラベルの取得
    date_label = str(df.iloc[3, 0]).split(' ')[0]
    # 「海外投資家」の文字がある行を探す
    target_idx = df[df[0].str.contains("海外投資家", na=False)].index[0]
    # その1行下(Purchases)のK列(Index 10)を取得
    val = df.iloc[target_idx + 1, 10]
    return date_label, val

def main():
    try:
        url = get_latest_excel_url()
        date, val = extract_data(url)
        
        if os.path.exists(CSV_FILE):
            history = pd.read_csv(CSV_FILE)
        else:
            history = pd.DataFrame(columns=['Date', 'Value'])
        
        if date not in history['Date'].values:
            new_data = pd.DataFrame({'Date': [date], 'Value': [val]})
            history = pd.concat([history, new_data], ignore_index=True)
            history.to_csv(CSV_FILE, index=False)
            
            # グラフ作成
            plt.figure(figsize=(10,5))
            plt.plot(history['Date'], history['Value'], marker='o')
            plt.axhline(0, color='red', linestyle='--')
            plt.title('Foreign Investors Net Trading Volume')
            plt.tight_layout()
            plt.savefig('trend.png')
            print(f"Success: {date} - {val}")
        else:
            print("No new data to update.")
    except Exception as e:
        print(f"Error: {e}")
        exit(1)

if __name__ == "__main__":
    main()
