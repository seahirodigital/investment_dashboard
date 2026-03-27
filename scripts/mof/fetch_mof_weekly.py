"""
財務省「対外及び対内証券売買契約等の状況」週次データ取得スクリプト

データソース:
  https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/week.csv

取得対象:
  対内証券投資 → 株式・投資ファンド持分 → ネット（Column O, index 14）
  単位: 億円

出力: data/mof_weekly.json
"""

import os
import sys
import json
import csv
import io
import requests
from datetime import datetime, timedelta, timezone

# プロジェクトルートを基準にパスを解決
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..'))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
OUTPUT_FILE = os.path.join(DATA_DIR, 'mof_weekly.json')

CSV_URL = "https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/week.csv"

# 対内証券投資 → 株式・投資ファンド持分 → ネット（O列 = index 14）
TARGET_COLUMN_INDEX = 14


def fetch_csv():
    """財務省CSVをダウンロード（CP932エンコーディング）"""
    print(f"CSVダウンロード中: {CSV_URL}")
    response = requests.get(CSV_URL, timeout=30)
    response.raise_for_status()
    # CP932（Shift-JIS）でデコード
    text = response.content.decode('cp932')
    print(f"  ダウンロード完了: {len(text)} 文字")
    return text


def parse_period(period_str):
    """期間文字列からISO日付（週末日）を抽出
    形式例:
      '2026．3．15～3．21'        （年省略パターン）
      '2005．1．2～ 1．8'         （年省略パターン）
      '2026．3．15～2026．3．21'   （年あり）
    区切り: 全角ドット(．)、半角ドット(.)、スラッシュ(/)
    """
    import re
    period_str = period_str.strip().replace(' ', '')
    # ～ または ~ で分割
    sep = '～' if '～' in period_str else '~' if '~' in period_str else None
    if not sep:
        return None

    start_part, end_part = period_str.split(sep, 1)

    # 全角ドット → 半角ドットに統一
    start_part = start_part.replace('．', '.').replace('/', '.')
    end_part = end_part.replace('．', '.').replace('/', '.')

    # 開始部分から年を取得
    start_nums = [x for x in start_part.split('.') if x]
    if len(start_nums) < 3:
        return None
    year = start_nums[0]

    # 終了部分をパース
    end_nums = [x for x in end_part.split('.') if x]
    if len(end_nums) == 3:
        # 年あり: YYYY.M.D
        y, m, d = end_nums
    elif len(end_nums) == 2:
        # 年省略: M.D → 開始部分の年を使用
        y = year
        m, d = end_nums
    else:
        return None

    try:
        dt = datetime(int(y), int(m), int(d))
        return dt.strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        return None


def parse_value(val_str):
    """数値文字列をintに変換（カンマ、スペース除去）
    例: '-25,097' → -25097, '264,738' → 264738
    """
    if not val_str:
        return None
    cleaned = val_str.strip().replace(',', '').replace(' ', '')
    if not cleaned or cleaned == '-':
        return None
    try:
        return int(cleaned)
    except ValueError:
        try:
            return int(float(cleaned))
        except ValueError:
            return None


def extract_data(csv_text):
    """CSVテキストからデータ行を抽出し、期間とO列の値を返す"""
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)

    data_entries = []

    for row in rows:
        if len(row) <= TARGET_COLUMN_INDEX:
            continue

        # 期間列（A列）に日付パターンがあるかチェック
        period = row[0].strip()
        # 全角ドット(．)、半角ドット(.)、スラッシュ(/) のいずれかを含み、～ or ~ を含む行がデータ行
        has_separator = '．' in period or '.' in period or '/' in period
        has_range = '～' in period or '~' in period
        if not has_separator or not has_range:
            continue

        date_str = parse_period(period)
        if not date_str:
            continue

        value = parse_value(row[TARGET_COLUMN_INDEX])
        if value is None:
            continue

        data_entries.append({
            'date': date_str,
            'value': value,
            'period': period.strip()
        })

    # 日付順にソート
    data_entries.sort(key=lambda x: x['date'])
    print(f"  データ行数: {len(data_entries)}")

    if data_entries:
        latest = data_entries[-1]
        print(f"  最新データ: {latest['date']} → {latest['value']:,}億円")

    return data_entries


def load_existing_data():
    """既存のJSONデータを読み込む"""
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return None


def save_data(data_entries):
    """データをJSONに保存（Read-Merge-Write方式）"""
    os.makedirs(DATA_DIR, exist_ok=True)

    existing = load_existing_data()
    existing_map = {}
    if existing and 'data' in existing:
        for entry in existing['data']:
            existing_map[entry['date']] = entry

    # 新データでマージ（新しいデータが優先）
    for entry in data_entries:
        existing_map[entry['date']] = entry

    merged = sorted(existing_map.values(), key=lambda x: x['date'])

    JST = timezone(timedelta(hours=9))
    now_jst = datetime.now(JST)

    output = {
        'generated_at': now_jst.strftime('%Y-%m-%dT%H:%M:%S+09:00'),
        'source': 'https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/week.csv',
        'unit': '億円',
        'description': '対内証券投資 株式・投資ファンド持分 ネット（非居住者による日本株売買ネット）',
        'total_records': len(merged),
        'data': merged
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"保存完了: {OUTPUT_FILE} ({len(merged)}件)")
    return output


def main():
    try:
        csv_text = fetch_csv()
        data_entries = extract_data(csv_text)

        if not data_entries:
            print("エラー: データが抽出できませんでした")
            sys.exit(1)

        save_data(data_entries)
        print("[OK] 財務省週次データの取得・保存が完了しました")

    except requests.RequestException as e:
        print(f"エラー: CSVダウンロード失敗 - {e}")
        sys.exit(1)
    except Exception as e:
        print(f"エラー: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
