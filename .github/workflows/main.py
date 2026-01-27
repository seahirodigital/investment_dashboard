import pandas as pd
import requests
from bs4 import BeautifulSoup
import os
import matplotlib.pyplot as plt

# 設定
CSV_FILE = 'history.csv'
BASE_URL = "https://www.jpx.co.jp"
CURRENT_YEAR_URL = "https://www.jpx.co.jp/markets/statistics-equities/investor-type/00-00-archives-00.html"

def get_latest_excel_url():
    """最新のExcelURLを取得"""
    res = requests.get(CURRENT_YEAR_URL)
    soup = BeautifulSoup(res.text, 'html.parser')
    # 「金額」列のExcelアイコン（.xls）を探す
    link = soup.find('a', href=lambda x: x and x.endswith('.xls'))
    return BASE_URL + link['href']

def extract_foreign_balance(url):
    """Excelから海外投資家の差引き額を抽出"""
    df = pd.read_excel(url, sheet_name=0, header=None)
    # 「海外投資家」という文字列がある行を探す（推測に基づく柔軟な抽出）
    target_row_idx = df[df[0].str.contains("海外投資家", na=False)].index[0]
    # 海外投資家ブロックの「買い」行のK列(10番目)が「差引き」
    balance_value = df.iloc[target_row_idx + 1, 10] 
    
    # 日付の抽出（4行目付近にあることが多い）
    date_label = df.iloc[3, 0] 
    return date_label, balance_value

def update_data():
    latest_url = get_latest_excel_url()
    date_label, value = extract_foreign_balance(latest_url)
    
    # 履歴の読み込み/作成
    if os.path.exists(CSV_FILE):
        history_df = pd.read_csv(CSV_FILE)
    else:
        history_df = pd.DataFrame(columns=['Date', 'ForeignBalance'])
    
    # 重複チェック（同じ日付があれば更新しない）
    if date_label not in history_df['Date'].values:
        new_row = pd.DataFrame({'Date': [date_label], 'ForeignBalance': [value]})
        history_df = pd.concat([history_df, new_row], ignore_index=True)
        history_df.to_csv(CSV_FILE, index=False)
        print(f"Added: {date_label}")
        generate_graph(history_df)
    else:
        print("No new data found.")

def generate_graph(df):
    """グラフの生成"""
    plt.figure(figsize=(10, 6))
    plt.plot(df['Date'], df['ForeignBalance'], marker='o', linestyle='-', color='blue')
    plt.axhline(0, color='black', linewidth=1)
    plt.title('Foreign Investors Net Trading Volume (Weekly)')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig('trend.png')

if __name__ == "__main__":
    update_data()
