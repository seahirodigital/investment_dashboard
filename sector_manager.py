import pandas as pd
import yfinance as yf
import json
import os
from datetime import datetime, timedelta

# ファイルパス定義
SECTORS_FILE = 'sectors.json'
HISTORY_CSV = 'history.csv'
OUTPUT_JSON = 'sector_data.json'

# デフォルト設定
DEFAULT_SECTORS = [
  { "ticker": "^N225", "name": "日経平均", "category": "Benchmark" },
  { "ticker": "1306.T", "name": "TOPIX", "category": "Benchmark" },
  { "ticker": "^GSPC", "name": "S&P 500", "category": "Benchmark" },
  { "ticker": "^NDX", "name": "NASDAQ 100", "category": "Benchmark" },
  { "ticker": "213A.T", "name": "半導体(国内) 213A", "category": "Semicon" },
  { "ticker": "2243.T", "name": "半導体(米国SOX)", "category": "Semicon" },
  { "ticker": "346A.T", "name": "半導体(米国S&P)", "category": "Semicon" },
  { "ticker": "1617.T", "name": "食品", "category": "Defensive" },
  { "ticker": "1618.T", "name": "エネルギー資源", "category": "Cyclical" },
  { "ticker": "1619.T", "name": "建設・資材", "category": "Cyclical" },
  { "ticker": "1620.T", "name": "素材・化学", "category": "Cyclical" },
  { "ticker": "1621.T", "name": "医薬品", "category": "Defensive" },
  { "ticker": "1622.T", "name": "自動車・輸送機", "category": "Cyclical" },
  { "ticker": "1623.T", "name": "鉄鋼・非鉄", "category": "Cyclical" },
  { "ticker": "1624.T", "name": "機械", "category": "Cyclical" },
  { "ticker": "1625.T", "name": "電機・精密", "category": "Tech" },
  { "ticker": "1626.T", "name": "情報通信・サービス", "category": "Tech" },
  { "ticker": "1627.T", "name": "電力・ガス", "category": "Defensive" },
  { "ticker": "1628.T", "name": "運輸・物流", "category": "Cyclical" },
  { "ticker": "1629.T", "name": "商社・卸売", "category": "Value" },
  { "ticker": "1630.T", "name": "小売", "category": "Consumer" },
  { "ticker": "1631.T", "name": "銀行", "category": "Financial" },
  { "ticker": "1632.T", "name": "金融(除く銀行)", "category": "Financial" },
  { "ticker": "1633.T", "name": "不動産", "category": "Financial" }
]

def load_sectors():
    """sectors.jsonから設定を読み込む"""
    if os.path.exists(SECTORS_FILE):
        try:
            with open(SECTORS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {SECTORS_FILE}: {e}")
    
    print(f"Using default sectors and creating {SECTORS_FILE}")
    with open(SECTORS_FILE, 'w', encoding='utf-8') as f:
        json.dump(DEFAULT_SECTORS, f, ensure_ascii=False, indent=2)
    return DEFAULT_SECTORS

def load_jpx_history():
    """既存のhistory.csvを読み込み、週次データとして整形する"""
    if not os.path.exists(HISTORY_CSV):
        print(f"Error: {HISTORY_CSV} not found. Run main.py first.")
        return None

    try:
        df = pd.read_csv(HISTORY_CSV)
        if df.empty:
            print("Warning: history.csv is empty.")
            return None
            
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        df.set_index('date', inplace=True)
        return df
    except Exception as e:
        print(f"Error loading history.csv: {e}")
        return None

def fetch_market_data(sectors, start_date, end_date):
    """Yahoo Financeから株価データを取得し、週次リターンを計算する"""
    tickers = [item['ticker'] for item in sectors]
    
    print(f"Fetching data for: {tickers}")
    
    try:
        # auto_adjust=Falseを指定して、Adj CloseとCloseを明確に分ける
        df = yf.download(tickers, start=start_date, end=end_date, interval='1wk', auto_adjust=False, progress=False)
        
        if df.empty:
            print("Warning: No data fetched from Yahoo Finance.")
            return pd.DataFrame()

        # カラム構造の確認とデータ抽出
        target_col = 'Adj Close'
        
        if isinstance(df.columns, pd.MultiIndex):
            if target_col in df.columns.get_level_values(0):
                data = df[target_col]
            elif 'Close' in df.columns.get_level_values(0):
                print("Note: 'Adj Close' not found, using 'Close' instead.")
                data = df['Close']
            else:
                print(f"Error: Neither 'Adj Close' nor 'Close' found. Columns: {df.columns}")
                return pd.DataFrame()
        else:
            if target_col in df.columns:
                data = df[target_col]
            elif 'Close' in df.columns:
                print("Note: 'Adj Close' not found, using 'Close' instead.")
                data = df['Close']
            else:
                data = df 

        if isinstance(data, pd.Series):
            data = data.to_frame()
            if len(tickers) == 1 and data.columns[0] != tickers[0]:
                data.columns = tickers
            
        # 週次リターン(%)の計算
        # pct_change() は (今週の終値 - 前週の終値) / 前週の終値
        # これは「その週の保有リターン」を意味する
        returns = data.pct_change() * 100
        returns.index = pd.to_datetime(returns.index).tz_localize(None)
        
        return returns

    except Exception as e:
        print(f"Error fetching market data: {e}")
        return pd.DataFrame()

def main():
    print("=== Starting Sector Analysis Data Processing ===")
    
    sectors = load_sectors()
    jpx_df = load_jpx_history()
    if jpx_df is None:
        return

    # 期間設定
    start_date = jpx_df.index.min() - timedelta(days=14)
    end_date = datetime.now() + timedelta(days=1)

    market_returns = fetch_market_data(sectors, start_date, end_date)
    
    if market_returns.empty:
        print("Skipping analysis due to missing market data.")
        return
    
    output = {
        "metadata": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sectors": sectors
        },
        "data": []
    }

    jpx_reset = jpx_df.reset_index()
    processed_count = 0
    
    for _, row in jpx_reset.iterrows():
        try:
            jpx_date = row['date'] # 通常は金曜日
            balance = row['balance']
            
            # 【重要修正】
            # JPXの日付(金曜)に対して、直近の過去(method='pad')のYahoo日付(月曜)を探す。
            # これにより「同じ週」のデータを確実にマッチングさせる。
            # 以前の method='nearest' では、金曜→翌月曜(3日差)となり、翌週のデータを見てしまっていた。
            idx_loc = market_returns.index.get_indexer([jpx_date], method='pad')[0]
            
            if idx_loc == -1: continue
                
            market_date = market_returns.index[idx_loc]
            
            # 日付乖離チェック（念のため7日以内、通常は4日以内になるはず）
            if abs((market_date - jpx_date).days) > 7: continue
                
            target_week_data = {}
            has_valid = False
            
            for sector in sectors:
                ticker = sector['ticker']
                if ticker in market_returns.columns:
                    val = market_returns.iloc[idx_loc][ticker]
                    if pd.notna(val):
                        target_week_data[ticker] = round(val, 2)
                        has_valid = True
                    else:
                        target_week_data[ticker] = 0.0
                else:
                    target_week_data[ticker] = 0.0
            
            if has_valid:
                entry = {
                    "date": jpx_date.strftime("%Y-%m-%d"),
                    "flow": int(balance),
                    "returns": target_week_data
                }
                output["data"].append(entry)
                processed_count += 1
        except Exception as e:
            continue

    if processed_count > 0:
        with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"Successfully generated {OUTPUT_JSON} with {processed_count} records.")
    else:
        print("No records processed.")

if __name__ == "__main__":
    main()
