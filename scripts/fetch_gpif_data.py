import yfinance as yf
import json
import os
from datetime import datetime, timedelta

def main():
    print("Fetching GPIF market data...")
    tickers = {
        'JP_EQ': '1306.T',
        'JP_BD': '2510.T',
        'GL_EQ': '2559.T',
        'GL_BD': '2511.T'
    }

    # API uses up to 3 years (1095 days). We fetch 4 years to have safety margins
    start_date = (datetime.now() - timedelta(days=1500)).strftime('%Y-%m-%d')
    results = {}

    for key, symbol in tickers.items():
        print(f"Fetching {symbol} for {key}...")
        try:
            df = yf.download(symbol, start=start_date, interval="1d")
            # Flatten multi-index columns if necessary
            if isinstance(df.columns, pd.MultiIndex):
                # For newer yfinance, df['Close'] might have the ticker as multi-index
                try:
                    close_series = df['Close'][symbol]
                except KeyError:
                    close_series = df['Close']
            else:
                close_series = df['Close']
                
            close_series = close_series.dropna()
            
            data_list = []
            for date, close_val in close_series.items():
                data_list.append({
                    "date": date.strftime('%Y-%m-%d'),
                    "close": float(close_val)
                })
            results[key] = data_list
        except Exception as e:
            print(f"Failed to fetch {symbol}: {e}")
            results[key] = []

    # Save to data/gpif_data.json
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, 'gpif_data.json')
    
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False)
        
    print(f"Saved data to {out_path}")

if __name__ == '__main__':
    import pandas as pd
    main()
