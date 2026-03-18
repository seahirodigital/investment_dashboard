"""
イントラデイETFデータ取得スクリプト
GitHub Actions intraday_etf.yml から呼び出される（15分ごと）。
5分足 14日分のデータを取得し data/etf_intraday_data.json に書き出す。
"""
import sys
import os
import json
import traceback

# プロジェクトルートを基準にパスを解決
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, script_dir)

os.makedirs(os.path.join(project_root, 'data'), exist_ok=True)
output_path = os.path.join(project_root, 'data', 'etf_intraday_data.json')

from etf_data_manager import fetch_data

print("=== イントラデイデータ取得開始 ===")
try:
    data = fetch_data(period='14d', interval='5m')
    dates = data.get('dates', [])
    if not dates:
        print("WARNING: データが空です。yfinance の取得に問題がある可能性があります。")
        sys.exit(1)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)

    print(f"完了: {len(dates)} ticks")
    print(f"最初: {dates[0]}")
    print(f"最後: {dates[-1]}")
    print(f"出力先: {output_path}")

except Exception as e:
    print(f"ERROR: データ取得中にエラーが発生しました: {e}")
    traceback.print_exc()
    sys.exit(1)
