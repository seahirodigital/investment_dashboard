import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import pdfplumber
import re

def get_latest_pdf_url():
    """JPXのページから最新のPDFファイルのURLを取得"""
    base_url = "https://www.jpx.co.jp"
    page_url = "https://www.jpx.co.jp/markets/statistics-equities/investor-type/00-00-archives-00.html"
    
    try:
        response = requests.get(page_url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # PDFファイルのリンクを探す（最新のものを取得）
        pdf_links = soup.find_all('a', href=lambda x: x and '.pdf' in x.lower())
        
        if not pdf_links:
            raise ValueError("PDFファイルが見つかりませんでした")
        
        # 最初のリンクを最新とみなす
        latest_link = pdf_links[0]['href']
        
        # 相対URLを絶対URLに変換
        if latest_link.startswith('/'):
            pdf_url = base_url + latest_link
        elif latest_link.startswith('http'):
            pdf_url = latest_link
        else:
            pdf_url = base_url + '/' + latest_link
            
        print(f"取得URL: {pdf_url}")
        return pdf_url
        
    except Exception as e:
        print(f"URL取得エラー: {e}")
        raise

def download_pdf(url, filename='temp.pdf'):
    """PDFをダウンロード"""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        with open(filename, 'wb') as f:
            f.write(response.content)
        
        print(f"PDFをダウンロードしました: {filename}")
        return filename
    except Exception as e:
        print(f"PDFダウンロードエラー: {e}")
        raise

def extract_from_pdf(pdf_path):
    """PDFから海外投資家の差引き金額を抽出"""
    
    try:
        print("PDFからテーブルを抽出中...")
        
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                print(f"\n=== ページ {page_num + 1} ===")
                
                # テーブルを抽出
                tables = page.extract_tables()
                
                if not tables:
                    print("このページにテーブルが見つかりません")
                    continue
                
                for table_num, table in enumerate(tables):
                    print(f"\nテーブル {table_num + 1}:")
                    
                    # 各行を検索
                    for row_idx, row in enumerate(table):
                        if not row:
                            continue
                        
                        # 行の内容を文字列として結合
                        row_text = ' '.join([str(cell) if cell else '' for cell in row])
                        
                        # 海外投資家の売り行を探す
                        if ('海外投資家' in row_text or 'Foreigners' in row_text) and ('売り' in row_text or 'Sales' in row_text):
                            print(f"\n海外投資家(売り)行を発見 (行{row_idx}):")
                            print(f"  内容: {row}")
                            
                            # この行の最後の数値（差引き）を取得
                            sell_balance = None
                            for cell in reversed(row):
                                if cell:
                                    # 数値を抽出
                                    match = re.search(r'-?\d{1,3}(?:,\d{3})+|-?\d+', str(cell))
                                    if match:
                                        try:
                                            sell_balance = int(match.group().replace(',', ''))
                                            if abs(sell_balance) >= 100000:  # 十分大きい数値
                                                break
                                        except ValueError:
                                            continue
                            
                            print(f"  売りの差引き: {sell_balance:,}" if sell_balance else "  売りの差引き: 見つかりませんでした")
                        
                        # 海外投資家の買い行を探す
                        if ('海外投資家' in row_text or 'Foreigners' in row_text) and ('買い' in row_text or 'Purchases' in row_text):
                            print(f"\n海外投資家(買い)行を発見 (行{row_idx}):")
                            print(f"  内容: {row}")
                            
                            # この行の最後の数値（差引き）を取得
                            buy_balance = None
                            for cell in reversed(row):
                                if cell:
                                    # 数値を抽出
                                    match = re.search(r'-?\d{1,3}(?:,\d{3})+|-?\d+', str(cell))
                                    if match:
                                        try:
                                            buy_balance = int(match.group().replace(',', ''))
                                            if abs(buy_balance) >= 100000:  # 十分大きい数値
                                                break
                                        except ValueError:
                                            continue
                            
                            print(f"  買いの差引き: {buy_balance:,}" if buy_balance else "  買いの差引き: 見つかりませんでした")
                            
                            # 売りと買いの両方が見つかった場合、絶対値が大きい方を返す
                            if buy_balance is not None and sell_balance is not None:
                                if abs(buy_balance) >= abs(sell_balance):
                                    print(f"\n✓ 買い超を採用: {buy_balance:,}")
                                    return buy_balance
                                else:
                                    print(f"\n✓ 売り超を採用: {sell_balance:,}")
                                    return sell_balance
                            elif buy_balance is not None:
                                print(f"\n✓ 買いのみ採用: {buy_balance:,}")
                                return buy_balance
                            elif sell_balance is not None:
                                print(f"\n✓ 売りのみ採用: {sell_balance:,}")
                                return sell_balance
        
        raise ValueError("海外投資家の差引き金額が見つかりませんでした")
        
    except Exception as e:
        print(f"PDF抽出エラー: {e}")
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
    
    # 日付を文字列として扱う
    df['date'] = df['date'].astype(str)
    
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
    pdf_path = None
    try:
        print("=== JPX海外投資家データ抽出開始 ===\n")
        
        # 最新のPDF URLを取得
        pdf_url = get_latest_pdf_url()
        
        # PDFをダウンロード
        pdf_path = download_pdf(pdf_url)
        
        # PDFからデータ抽出
        balance = extract_from_pdf(pdf_path)
        
        # CSV保存
        save_to_csv(balance)
        
        # グラフ作成
        create_trend_chart()
        
        print("\n=== 処理完了 ===")
        
    except Exception as e:
        print(f"\nエラーが発生しました: {e}")
        raise
    finally:
        # 一時ファイルを削除
        if pdf_path and os.path.exists(pdf_path):
            os.remove(pdf_path)
            print("一時ファイルを削除しました")

if __name__ == "__main__":
    main()
