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
        
        # yfinanceのバージョンやデータ数によってカラム構造が変わるための対応
        data = None
        if isinstance(df.columns, pd.MultiIndex):
            # MultiIndexの場合 (Price, Ticker) または (Ticker, Price)
            if target_col in df.columns.get_level_values(0):
                data = df[target_col]
            elif 'Close' in df.columns.get_level_values(0):
                print("Note: 'Adj Close' not found, using 'Close' instead.")
                data = df['Close']
            else:
                # カラムレベルの入替や探索
                print(f"Note: Complex MultiIndex columns detected. Levels: {df.columns.levels}")
                try:
                    # 試行: tickerがlevel 0にある場合
                    data = df.xs(target_col, level=1, axis=1)
                except:
                    print(f"Error: Neither 'Adj Close' nor 'Close' found properly. Columns: {df.columns}")
                    return pd.DataFrame()
        else:
            # Single Indexの場合
            if target_col in df.columns:
                data = df[target_col]
            elif 'Close' in df.columns:
                print("Note: 'Adj Close' not found, using 'Close' instead.")
                data = df['Close']
            else:
                # 1銘柄だけでカラム名がTickerになっている場合などのフォールバック
                data = df 

        if data is None or data.empty:
            return pd.DataFrame()

        if isinstance(data, pd.Series):
            data = data.to_frame()
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
    
    sectors = load_sectors()
    jpx_df = load_jpx_history()
    
    if jpx_df is None:
        print("JPX history data is missing. Exiting.")
        return

    # 期間設定
    start_date = jpx_df.index.min() - timedelta(days=14)
    end_date = datetime.now() + timedelta(days=1)

    print(f"Analysis period: {start_date.date()} to {end_date.date()}")
    market_returns = fetch_market_data(sectors, start_date, end_date)
    
    # マーケットデータが空でも、空のJSONを出力するために処理は続行させる
    if market_returns.empty:
        print("Warning: Market data is empty. Generating empty dataset.")
    
    output = {
        "metadata": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sectors": sectors
        },
        "data": []
    }

    if not market_returns.empty:
        jpx_reset = jpx_df.reset_index()
        processed_count = 0
        
        for _, row in jpx_reset.iterrows():
            try:
                jpx_date = row['date']
                balance = row['balance']
                
                # CSVのDD部分(day)を週番号として扱う (01=1週目, 02=2週目...)
                target_year = jpx_date.year
                target_month = jpx_date.month
                target_week_idx = jpx_date.day - 1  # 01->0, 02->1
                
                # Yahooデータから該当する年月のデータを抽出
                mask = (market_returns.index.year == target_year) & (market_returns.index.month == target_month)
                monthly_data = market_returns[mask].sort_index()
                
                # 該当する週のデータが存在するか確認
                if target_week_idx < 0 or target_week_idx >= len(monthly_data):
                    continue
                
                # 対象週の日付を特定し、その日のデータを取得
                market_date = monthly_data.index[target_week_idx]
                
                # 週の開始日と終了日を計算（Yahoo Financeの週次データから）
                week_start = market_date - timedelta(days=market_date.weekday())  # 月曜日
                week_end = week_start + timedelta(days=6)  # 日曜日
                
                # 値の取得
                target_week_data = {}
                has_valid = False
                
                for sector in sectors:
                    ticker = sector['ticker']
                    if ticker in market_returns.columns:
                        val = market_returns.loc[market_date, ticker]
                        if pd.notna(val):
                            target_week_data[ticker] = round(val, 2)
                            has_valid = True
                        else:
                            target_week_data[ticker] = 0.0
                    else:
                        target_week_data[ticker] = 0.0
                
                if has_valid:
                    entry = {
                        "date": jpx_date.strftime("%Y-%m-%d"), # JSONには元の擬似日付(YYYY-MM-Week)を出力
                        "week_start": week_start.strftime("%Y-%m-%d"),  # 週の開始日
                        "week_end": week_end.strftime("%Y-%m-%d"),      # 週の終了日
                        "flow": int(balance),
                        "returns": target_week_data
                    }
                    output["data"].append(entry)
                    processed_count += 1
                    
            except Exception as e:
                # 個別の行エラーはスキップして続行
                continue
    else:
        processed_count = 0

    # 【重要修正】データ件数が0でも必ずJSONファイルを生成する
    # これによりHTML側で404エラーになるのを防ぐ
    try:
        with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        
        if processed_count > 0:
            print(f"Successfully generated {OUTPUT_JSON} with {processed_count} records.")
        else:
            print(f"Warning: Generated {OUTPUT_JSON} with 0 records (No matched data).")
            
    except Exception as e:
        print(f"Error saving JSON: {e}")

if __name__ == "__main__":
    main()
