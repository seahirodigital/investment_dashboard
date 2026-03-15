import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta

BENCHMARK = '1306.T'
SECTORS = {
  '1617.T': '食品',
  '1618.T': 'エネルギー資源',
  '1619.T': '建設・資材',
  '1620.T': '素材・化学',
  '1621.T': '医薬品',
  '1622.T': '自動車・輸送機',
  '1623.T': '鉄鋼・非鉄',
  '1624.T': '機械',
  '1625.T': '電機・精密',
  '1626.T': '情報通信・サービスその他',
  '1627.T': '電力・ガス',
  '1628.T': '運輸・物流',
  '1629.T': '商社・卸売',
  '1630.T': '小売',
  '1631.T': '銀行',
  '1632.T': '金融（除く銀行）',
  '1633.T': '不動産',
  '213A.T': '半導体',
  '^N225': '日経指数'
}
ALL_SYMBOLS = [BENCHMARK] + list(SECTORS.keys())
FETCH_DAYS = 400

def fetch_data():
    start_date = (datetime.now() - timedelta(days=FETCH_DAYS)).strftime('%Y-%m-%d')
    end_date = datetime.now().strftime('%Y-%m-%d')
    output = {
        "benchmark": BENCHMARK,
        "sectors": SECTORS,
        "dates": [],
        "prices": {}
    }
    
    print(f"Fetching data from {start_date} to {end_date}...")
    
    # Download data
    df = yf.download(ALL_SYMBOLS, start=start_date, end=end_date, auto_adjust=False, progress=False)
    
    if df.empty:
        print("Warning: No data fetched from Yahoo Finance.")
        return output
    
    if isinstance(df.columns, pd.MultiIndex):
        if 'Adj Close' in df.columns.get_level_values(0):
            df = df['Adj Close']
        elif 'Close' in df.columns.get_level_values(0):
            df = df['Close']
    
    # Remove timezone info 
    df.index = pd.to_datetime(df.index).tz_localize(None)
    
    # Check what symbols we actually got
    valid_symbols = [col for col in ALL_SYMBOLS if col in df.columns]
    
    # Clean up dates and interpolate missing ones
    df = df.ffill().bfill() # Forward fill then backward fill missing
    
    # Keep only rows where BENCHMARK is not NaN
    if BENCHMARK in df.columns:
        df = df[df[BENCHMARK].notna()]
        
    for symbol in valid_symbols:
        output["prices"][symbol] = [round(x, 2) if pd.notna(x) else None for x in df[symbol].tolist()]
        
    output["dates"] = [d.strftime('%Y-%m-%d') for d in df.index]

    return output

def main():
    os.makedirs('data', exist_ok=True)
    data = fetch_data()
    
    with open('data/etf_data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
        
    print(f"Successfully saved {len(data['dates'])} days of ETF data.")

if __name__ == "__main__":
    main()
