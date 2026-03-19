"""
イントラデイETFデータ取得スクリプト
GitHub Actions intraday_etf.yml から呼び出される（15分ごと）。
5分足 14日分のデータを取得し data/etf_intraday_data.json に書き出す。
リトライ付き: 最大3回まで再試行（yfinance タイムアウト対策）。
"""
import sys
import os
import json
import time
import traceback
from datetime import datetime, timezone, timedelta

# プロジェクトルートを基準にパスを解決
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, script_dir)

os.makedirs(os.path.join(project_root, 'data'), exist_ok=True)
output_path = os.path.join(project_root, 'data', 'etf_intraday_data.json')

from etf_data_manager import fetch_data

MAX_RETRIES = 3
RETRY_DELAY = 10  # 秒

print("=== イントラデイデータ取得開始 ===")

data = None
last_error = None

for attempt in range(1, MAX_RETRIES + 1):
    try:
        print(f"取得試行 {attempt}/{MAX_RETRIES}...")
        data = fetch_data(period='14d', interval='5m')
        dates = data.get('dates', [])
        if not dates:
            print(f"WARNING (試行{attempt}): データが空です。yfinance の取得に問題がある可能性があります。")
            data = None
            if attempt < MAX_RETRIES:
                print(f"  {RETRY_DELAY}秒後にリトライします...")
                time.sleep(RETRY_DELAY)
            continue
        # 取得成功
        break
    except Exception as e:
        last_error = e
        print(f"ERROR (試行{attempt}): {e}")
        traceback.print_exc()
        if attempt < MAX_RETRIES:
            print(f"  {RETRY_DELAY}秒後にリトライします...")
            time.sleep(RETRY_DELAY)

if data is None or not data.get('dates'):
    print(f"FATAL: {MAX_RETRIES}回の試行全てに失敗しました。")
    if last_error:
        print(f"最後のエラー: {last_error}")
    sys.exit(1)

# generated_at タイムスタンプを追加（JST / UTC 両方）
jst = timezone(timedelta(hours=9))
now_jst = datetime.now(jst)
now_utc = datetime.now(timezone.utc)
data['generated_at'] = now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
data['generated_at_jst'] = now_jst.strftime('%Y-%m-%d %H:%M JST')

with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False)

dates = data['dates']
print(f"完了: {len(dates)} ticks")
print(f"最初: {dates[0]}")
print(f"最後: {dates[-1]}")
print(f"生成時刻: {data['generated_at_jst']}")
print(f"出力先: {output_path}")
