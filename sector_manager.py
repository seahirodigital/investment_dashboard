import pandas as pd
import yfinance as yf
import json
import os
from datetime import datetime, timedelta

# --- Config: 分析対象セクター定義 ---
SECTOR_CONFIG = [
    {"ticker": "1306.T", "name": "TOPIX (1306)", "category": "Benchmark"},
    {"ticker": "^N225", "name": "Nikkei 225", "category": "Benchmark"},
    {"ticker": "2644.T", "name": "Semicon (2644)", "category": "Growth"},
    {"ticker": "1615.T", "name": "Banks (1615)", "category": "Value"},
    {"ticker": "1618.T", "name": "Auto & Energy (1618)", "category": "Cyclical"},
    {"ticker": "1489.T", "name": "High Div Yield (1489)", "category": "Value"},
    {"ticker": "2516.T", "name": "Mothers/Growth (2516)", "category": "Small Cap"}
]

HISTORY_CSV = 'history.csv'
OUTPUT_JSON = 'sector_data.json'

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

def fetch_market_data(start_date, end_date):
    """Yahoo Financeから株価データを取得し、週次リターンを計算する"""
    tickers = [item['ticker'] for item in SECTOR_CONFIG]
    
    print(f"Fetching data for: {tickers}")
    
    try:
        # auto_adjust=Falseを指定して、Adj CloseとCloseを明確に分ける
        df = yf.download(tickers, start=start_date, end=end_date, interval='1wk', auto_adjust=False, progress=False)
        
        if df.empty:
            print("Warning: No data fetched from Yahoo Finance.")
            return pd.DataFrame()

        # カラム構造の確認とデータ抽出
        # yfinanceのバージョンや取得結果によって、MultiIndexかどうかが変わる場合がある
        target_col = 'Adj Close'
        
        # カラムがMultiIndexの場合 (Ticker数 > 1 または特定バージョン)
        if isinstance(df.columns, pd.MultiIndex):
            if target_col in df.columns.get_level_values(0):
                data = df[target_col]
            elif 'Close' in df.columns.get_level_values(0):
                print("Note: 'Adj Close' not found, using 'Close' instead.")
                data = df['Close']
            else:
                print(f"Error: Neither 'Adj Close' nor 'Close' found in columns: {df.columns}")
                return pd.DataFrame()
        else:
            # 単一階層の場合
            if target_col in df.columns:
                data = df[target_col]
            elif 'Close' in df.columns:
                print("Note: 'Adj Close' not found, using 'Close' instead.")
                data = df['Close']
            else:
                # カラム名がティッカーそのものの場合やその他のケース
                data = df

        # データ型をDataFrameに統一 (1銘柄の場合Seriesになるのを防ぐ)
        if isinstance(data, pd.Series):
            data = data.to_frame()
            # カラム名がティッカーになっていない場合は修正が必要だが、
            # yf.download(list) の場合は通常DataFrameで返る
            
        # 週次リターン(%)の計算
        returns = data.pct_change() * 100
        
        # インデックスを日付型に統一（タイムゾーン削除）
        returns.index = pd.to_datetime(returns.index).tz_localize(None)
        
        return returns

    except Exception as e:
        print(f"Error fetching market data: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()

def main():
    print("=== Starting Sector Analysis Data Processing ===")
    
    # 1. JPXデータの読み込み
    jpx_df = load_jpx_history()
    if jpx_df is None:
        return

    # 期間設定 (JPXデータの範囲 + バッファ)
    start_date = jpx_df.index.min() - timedelta(days=14) # 少し余裕を持たせる
    end_date = datetime.now() + timedelta(days=1)

    # 2. 株価データの取得
    market_returns = fetch_market_data(start_date, end_date)
    
    if market_returns.empty:
        print("Skipping analysis due to missing market data.")
        return
    
    # 3. データの結合 (Merge)
    output = {
        "metadata": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sectors": SECTOR_CONFIG
        },
        "data": []
    }

    # インデックスのリセット
    jpx_reset = jpx_df.reset_index()
    
    processed_count = 0
    for _, row in jpx_reset.iterrows():
        jpx_date = row['date']
        balance = row['balance']
        
        # JPX日付と同じ週の市場データを探す
        # nearestを使って最も近い日付のデータを取得
        try:
            idx_loc = market_returns.index.get_indexer([jpx_date], method='nearest')[0]
            
            # インデックスが範囲外の場合はスキップ
            if idx_loc == -1:
                continue
                
            market_date = market_returns.index[idx_loc]
            
            # 日付が離れすぎている場合は無視 (データの欠損対策: 7日以内)
            if abs((market_date - jpx_date).days) > 7:
                continue
                
            target_week_data = {}
            has_valid_return = False
            
            # 各セクターのリターンを取得
            for sector in SECTOR_CONFIG:
                ticker = sector['ticker']
                if ticker in market_returns.columns:
                    val = market_returns.iloc[idx_loc][ticker]
                    if pd.notna(val):
                        target_week_data[ticker] = round(val, 2)
                        has_valid_return = True
                    else:
                        target_week_data[ticker] = 0.0
                else:
                    target_week_data[ticker] = 0.0
            
            if has_valid_return:
                entry = {
                    "date": jpx_date.strftime("%Y-%m-%d"),
                    "flow": int(balance),
                    "returns": target_week_data
                }
                output["data"].append(entry)
                processed_count += 1
                
        except Exception as e:
            # 個別の行処理エラーはスキップして続行
            continue

    # 4. JSON出力
    if processed_count > 0:
        with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"Successfully generated {OUTPUT_JSON} with {processed_count} records.")
    else:
        print("No records processed. JSON not generated.")

if __name__ == "__main__":
    main()
