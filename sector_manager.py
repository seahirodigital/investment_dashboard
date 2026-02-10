import pandas as pd
import yfinance as yf
import json
import os
from datetime import datetime, timedelta

# --- Config: 分析対象セクター定義 (仕様書に基づき拡張可能に設計) ---
# 本来は yaml から読み込む仕様ですが、単独動作させるため辞書として定義します
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

    df = pd.read_csv(HISTORY_CSV)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    
    # 週次データへリサンプリング（金曜日基準）
    # JPXデータは通常木曜大引け後の公開で、データ自体は前週のものだが、
    # ここではシンプルに時系列インデックスとして扱う
    df.set_index('date', inplace=True)
    return df

def fetch_market_data(start_date, end_date):
    """Yahoo Financeから株価データを取得し、週次リターンを計算する"""
    tickers = [item['ticker'] for item in SECTOR_CONFIG]
    
    print(f"Fetching data for: {tickers}")
    # yfinanceのダウンロード (調整後終値)
    data = yf.download(tickers, start=start_date, end=end_date, interval='1wk')['Adj Close']
    
    # データが1銘柄の場合のSeries対応
    if len(tickers) == 1:
        data = data.to_frame(name=tickers[0])

    # 週次リターン(%)の計算
    returns = data.pct_change() * 100
    
    # インデックスを日付型に統一（タイムゾーン削除）
    returns.index = pd.to_datetime(returns.index).tz_localize(None)
    
    return returns

def main():
    print("=== Starting Sector Analysis Data Processing ===")
    
    # 1. JPXデータの読み込み
    jpx_df = load_jpx_history()
    if jpx_df is None:
        return

    if jpx_df.empty:
        print("JPX data is empty.")
        return

    # 期間設定 (JPXデータの範囲 + バッファ)
    start_date = jpx_df.index.min() - timedelta(days=7)
    end_date = datetime.now()

    # 2. 株価データの取得
    market_returns = fetch_market_data(start_date, end_date)
    
    # 3. データの結合 (Merge)
    # JPXの日付(金曜)に近い市場データの日付をマージする
    # sort=Trueで日付順を保証
    merged_data = []
    
    # JPXの各レコードに対して、最も近い過去〜同日の株価リターンを紐付ける
    # 完全一致しない場合があるため、asofのようなロジックあるいは週単位での結合を行う
    
    # データ出力用構造体
    output = {
        "metadata": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sectors": SECTOR_CONFIG
        },
        "data": []
    }

    # インデックスのリセット
    jpx_reset = jpx_df.reset_index()
    
    for _, row in jpx_reset.iterrows():
        jpx_date = row['date']
        balance = row['balance']
        
        # JPX日付と同じ週の市場データを探す (同じ週の金曜、あるいは直近)
        # 簡易的に、JPX日付から過去7日以内のデータを検索
        target_week_data = {}
        
        # マーケットデータの中で、このJPX日付に最も近い（かつ未来でない）日付を探す
        # 週次データなので、インデックスの差分が少ないものを採用
        idx_loc = market_returns.index.get_indexer([jpx_date], method='nearest')[0]
        market_date = market_returns.index[idx_loc]
        
        # 日付が離れすぎている場合は無視 (データの欠損対策)
        if abs((market_date - jpx_date).days) > 7:
            continue
            
        # 各セクターのリターンを取得
        for sector in SECTOR_CONFIG:
            ticker = sector['ticker']
            if ticker in market_returns.columns:
                val = market_returns.iloc[idx_loc][ticker]
                # NaNチェック
                if pd.notna(val):
                    target_week_data[ticker] = round(val, 2)
                else:
                    target_week_data[ticker] = 0.0
        
        entry = {
            "date": jpx_date.strftime("%Y-%m-%d"),
            "flow": int(balance), # 海外投資家収支
            "returns": target_week_data
        }
        output["data"].append(entry)

    # 4. JSON出力
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"Successfully generated {OUTPUT_JSON} with {len(output['data'])} records.")

if __name__ == "__main__":
    main()
