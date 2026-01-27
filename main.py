import pandas as pd
import requests
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
from datetime import datetime
import os

def get_latest_excel_url():
    """JPXのページから最新のExcelファイルのURLを取得"""
    base_url = "https://www.jpx.co.jp"
    page_url = "https://www.jpx.co.jp/markets/statistics-equities/investor-type/00-00-archives-00.html"
    
    try:
        response = requests.get(page_url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # .xlsファイルのリンクを探す（最新のものを取得）
        xls_links = soup.find_all('a', href=lambda x: x and '.xls' in x.lower())
        
        if not xls_links:
            raise ValueError("Excel(.xls)ファイルが見つかりませんでした")
        
        # 最初のリンクを最新とみなす
        latest_link = xls_links[0]['href']
        
        # 相対URLを絶対URLに変換
        if latest_link.startswith('/'):
            excel_url = base_url + latest_link
        elif latest_link.startswith('http'):
            excel_url = latest_link
        else:
            excel_url = base_url + '/' + latest_link
            
        print(f"取得URL: {excel_url}")
        return excel_url
        
    except Exception as e:
        print(f"URL取得エラー: {e}")
        raise

def extract_foreign_investor_balance(excel_url):
    """
    Excelファイルから海外投資家の差引き金額を抽出
    
    戦略:
    1. Excelを読み込み、すべてのセルを文字列として扱う
    2. 「海外投資家」または「Foreigners」を含む行を検索
    3. その行の「買い」に対応する差引き列を特定
    4. 列ヘッダーから「差引き」「Balance」を探して列位置を特定
    """
    try:
        # Excelを読み込む（複数シートの可能性を考慮）
        # header=Noneで列名を自動判定させず、すべて数値インデックスで扱う
        all_sheets = pd.read_excel(excel_url, sheet_name=None, header=None)
        
        for sheet_name, df in all_sheets.items():
            print(f"\n=== シート: {sheet_name} ===")
            
            # すべてのセルを文字列に変換（NaNは空文字列に）
            df = df.fillna('').astype(str)
            
            # ステップ1: ヘッダー行を探す（「差引き」「Balance」を含む行）
            balance_col = None
            header_row = None
            
            for idx, row in df.iterrows():
                row_text = ' '.join(row.values).lower()
                if 'balance' in row_text or '差引き' in row_text:
                    header_row = idx
                    # この行から「差引き」「Balance」の列を特定
                    for col_idx, cell in enumerate(row.values):
                        cell_lower = str(cell).lower().strip()
                        if 'balance' in cell_lower or '差引' in cell_lower:
                            balance_col = col_idx
                            print(f"差引き列を発見: 列{balance_col} (ヘッダー行{header_row})")
                            break
                    break
            
            if balance_col is None:
                print(f"このシートには差引き列が見つかりませんでした")
                continue
            
            # ステップ2: 「海外投資家」の「買い」行を探す
            foreign_investor_row = None
            
            for idx, row in df.iterrows():
                # 行の最初の数列を結合してチェック
                row_text = ' '.join(row.values[:5]).lower()
                
                # 「海外投資家」または「foreigners」を含み、かつ「買い」または「purchases」を含む
                if ('海外投資家' in row_text or 'foreigners' in row_text) and \
                   ('買い' in row_text or 'purchases' in row_text):
                    foreign_investor_row = idx
                    print(f"海外投資家(買い)行を発見: 行{idx}")
                    print(f"  内容: {row.values[:5]}")
                    break
            
            if foreign_investor_row is None:
                # 買い売りが分かれていない可能性もあるため、海外投資家行だけを探す
                for idx, row in df.iterrows():
                    row_text = ' '.join(row.values[:5]).lower()
                    if '海外投資家' in row_text or 'foreigners' in row_text:
                        # この行の数行後に「買い」があるかチェック
                        for offset in range(1, 5):
                            if idx + offset >= len(df):
                                break
                            next_row_text = ' '.join(df.iloc[idx + offset].values[:5]).lower()
                            if '買い' in next_row_text or 'purchases' in next_row_text:
                                foreign_investor_row = idx + offset
                                print(f"海外投資家(買い)行を発見: 行{foreign_investor_row}")
                                print(f"  内容: {df.iloc[foreign_investor_row].values[:5]}")
                                break
                        if foreign_investor_row:
                            break
            
            if foreign_investor_row is None:
                print(f"このシートには海外投資家の買い行が見つかりませんでした")
                continue
            
            # ステップ3: 該当セルから数値を取得
            target_cell = df.iloc[foreign_investor_row, balance_col]
            print(f"ターゲットセル: 行{foreign_investor_row}, 列{balance_col} = {target_cell}")
            
            # 数値に変換（カンマを除去）
            try:
                # 文字列から数値部分のみを抽出
                cleaned_value = target_cell.replace(',', '').replace(' ', '').strip()
                # マイナス記号が含まれる可能性も考慮
                value = float(cleaned_value)
                
                print(f"\n✓ 抽出成功: {value:,.0f}")
                return value
                
            except ValueError:
                print(f"数値変換エラー: '{target_cell}' は数値ではありません")
                continue
        
        raise ValueError("すべてのシートで海外投資家の差引き金額が見つかりませんでした")
        
    except Exception as e:
        print(f"データ抽出エラー: {e}")
        raise

def save_to_csv(value):
    """CSVファイルにデータを保存"""
    csv_file = 'history.csv'
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 既存のCSVを読み込むか、新規作成
    if os.path.exists(csv_file):
        df = pd.read_csv(csv_file)
    else:
        df = pd.DataFrame(columns=['date', 'balance'])
    
    # 新しいデータを追加
    new_row = pd.DataFrame({'date': [today], 'balance': [value]})
    df = pd.concat([df, new_row], ignore_index=True)
    
    # 重複削除（同じ日付の場合は最新を保持）
    df = df.drop_duplicates(subset=['date'], keep='last')
    
    df.to_csv(csv_file, index=False)
    print(f"CSVに保存しました: {csv_file}")

def create_trend_chart():
    """トレンドグラフを作成"""
    csv_file = 'history.csv'
    
    if not os.path.exists(csv_file):
        print("CSVファイルが存在しないため、グラフを作成できません")
        return
    
    df = pd.read_csv(csv_file)
    
    if len(df) == 0:
        print("データが空のため、グラフを作成できません")
        return
    
    # グラフ作成
    plt.figure(figsize=(12, 6))
    plt.plot(df['date'], df['balance'], marker='o', linewidth=2, markersize=8)
    plt.xlabel('Date', fontsize=12)
    plt.ylabel('Balance (JPY)', fontsize=12)
    plt.title('Foreign Investors Balance Trend', fontsize=14, fontweight='bold')
    plt.xticks(rotation=45, ha='right')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    plt.savefig('trend.png', dpi=150)
    print("グラフを保存しました: trend.png")

def main():
    try:
        print("=== JPX海外投資家データ抽出開始 ===\n")
        
        # 最新のExcel URLを取得
        excel_url = get_latest_excel_url()
        
        # データ抽出
        balance = extract_foreign_investor_balance(excel_url)
        
        # CSV保存
        save_to_csv(balance)
        
        # グラフ作成
        create_trend_chart()
        
        print("\n=== 処理完了 ===")
        
    except Exception as e:
        print(f"\nエラーが発生しました: {e}")
        raise

if __name__ == "__main__":
    main()
