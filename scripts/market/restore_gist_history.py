import os
import sys
import json
import subprocess
from datetime import datetime

def run_cmd(cmd):
    try:
        output_bytes = subprocess.check_output(cmd)
        return output_bytes.decode('utf-8').strip()
    except subprocess.CalledProcessError as e:
        print(f"❌ コマンド実行エラー: {' '.join(cmd)}")
        if e.output:
            print(e.output.decode('utf-8', errors='ignore'))
        sys.exit(1)

def get_gist_id():
    return "ad5bf7d5738f78b3c33aabffc92761ff"

def main():
    print("🚀 Gist への過去データ(3/30, 3/31)復旧ツールを起動しました。")
    gist_id = get_gist_id()
    
    # Download current market_data.json from Gist using gh
    print("📥 現在の market_data.json をGistから取得中...")
    raw_json = run_cmd(['gh', 'gist', 'view', gist_id, '--filename', 'market_data.json', '--raw'])
    
    try:
        market_data = json.loads(raw_json)
    except json.JSONDecodeError:
        print("❌ 取得したデータのJSONパースに失敗しました。")
        sys.exit(1)
        
    history = market_data.get('history', {})
    
    # Target dates to restore
    target_dates = ['2026-03-30', '2026-03-31']
    updated_count = 0
    
    for date_str in target_dates:
        # e.g., '20260330_daily_report.md'
        file_name = f"{date_str.replace('-', '')}_daily_report.md"
        file_path = os.path.join(os.path.dirname(__file__), '..', '..', 'market_analysis', 'reports', file_name)
        
        if not os.path.exists(file_path):
            print(f"⚠️ {file_path} が見つからないため、{date_str} の復旧をスキップします。")
            continue
            
        with open(file_path, 'r', encoding='utf-8') as f:
            info_text = f.read()
            
        if date_str not in history:
            history[date_str] = {}
            
        history[date_str]['info'] = info_text
        updated_count += 1
        print(f"✅ {date_str} のデータを適用しました ({len(info_text)} bytes)")
        
    if updated_count == 0:
        print("ℹ️ 更新するデータがありませんでした。処理を終了します。")
        return
        
    # Save the merged dictionary locally to a temp file (compact JSON to avoid truncation)
    temp_file = 'market_data.json'
    with open(temp_file, 'w', encoding='utf-8') as f:
        json.dump(market_data, f, ensure_ascii=False)

    file_size = os.path.getsize(temp_file)
    print(f"📊 ファイルサイズ: {file_size:,} bytes ({file_size/1024:.0f} KB)")
    if file_size > 900_000:
        print("⚠️ 警告: ファイルサイズが900KBを超えています。Gist APIのtruncation閾値に注意。")

    # Upload to Gist
    print("📤 Gistを更新中...")
    run_cmd(['gh', 'gist', 'edit', gist_id, temp_file])
    
    # Clean up
    if os.path.exists(temp_file):
        os.remove(temp_file)
        
    print("🎉 Gistへの復旧が完了しました！")
    print("⚠️ ブラウザで Investment Dashboard を開き、画面を「スーパーリロード (Ctrl+F5 または Shift+F5)」して確認してください。")

if __name__ == "__main__":
    main()
