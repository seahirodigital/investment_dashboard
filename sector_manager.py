import pandas as pd
import yfinance as yf
import json
import os
from datetime import datetime, timedelta

# ファイルパス定義
SECTORS_FILE = 'sectors.json'
HISTORY_CSV = 'history.csv'
OUTPUT_JSON = 'sector_data.json'

# デフォルト設定（sectors.jsonがない場合用）
DEFAULT_SECTORS = [
    {"ticker": "1306.T", "name": "TOPIX (1306)", "category": "Benchmark"},
    {"ticker": "^N225", "name": "Nikkei 225", "category": "Benchmark"},
    {"ticker": "2644.T", "name": "Semicon (2644)", "category": "Growth"},
    {"ticker": "1615.T", "name": "Banks (1615)", "category": "Value"}
]

def load_sectors():
    """sectors.jsonから設定を読み込む"""
    if os.path.exists(SECTORS_FILE):
        try:
            with open(SECTORS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {SECTORS_FILE}: {e}")
    
    # ファイルがない、またはエラーの場合はデフォルトを作成して使用
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
        
        # MultiIndex対応
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
            # 単一階層の場合
            if target_col in df.columns:
                data = df[target_col]
            elif 'Close' in df.columns:
                print("Note: 'Adj Close' not found, using 'Close' instead.")
                data = df['Close']
            else:
                data = df # フォールバック

        # データ型をDataFrameに統一
        if isinstance(data, pd.Series):
            data = data.to_frame()
            # カラム名がティッカーになっていない場合の対応（1銘柄時）
            if len(tickers) == 1 and data.columns[0] != tickers[0]:
                data.columns = tickers
            
        # 週次リターン(%)の計算
        returns = data.pct_change() * 100
        returns.index = pd.to_datetime(returns.index).tz_localize(None)
        
        return returns

    except Exception as e:
        print(f"Error fetching market data: {e}")
        return pd.DataFrame()

def main():
    print("=== Starting Sector Analysis Data Processing ===")
    
    # セクター設定読み込み
    sectors = load_sectors()
    
    jpx_df = load_jpx_history()
    if jpx_df is None:
        return

    # 期間設定 (JPXデータの範囲 + バッファ)
    start_date = jpx_df.index.min() - timedelta(days=14)
    end_date = datetime.now() + timedelta(days=1)

    # 株価データの取得
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
            jpx_date = row['date']
            balance = row['balance']
            
            # JPX日付に最も近い市場データを探す
            idx_loc = market_returns.index.get_indexer([jpx_date], method='nearest')[0]
            if idx_loc == -1: continue
                
            market_date = market_returns.index[idx_loc]
            # 日付乖離チェック（7日以内）
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
