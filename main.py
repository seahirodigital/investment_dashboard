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
        print("PDFからテキストを抽出中...")
        
        with pdfplumber.open(pdf_path) as pdf:
            # すべてのページからテキストを抽出
            all_text = ""
            for page in pdf.pages:
                all_text += page.extract_text() + "\n"
        
        print(f"抽出したテキスト長: {len(all_text)} 文字")
        
        # テキストを行に分割
        lines = all_text.split('\n')
        
        # 海外投資家のセクションを探す
        foreign_section_start = None
        
        for i, line in enumerate(lines):
            # 「海外投資家」の行を見つける
            if '海外投資家' in line or 'Foreigners' in line:
                # この行に「売り」「買い」が含まれていないことを確認（ヘッダー行）
                if '売り' not in line and '買い' not in line:
                    foreign_section_start = i
                    print(f"\n海外投資家セクション開始 (行{i}): {line}")
                    break
        
        if foreign_section_start is None:
            raise ValueError("海外投資家セクションが見つかりませんでした")
        
        # 海外投資家セクションの次の数行を解析
        sell_line = None
        buy_line = None
        
        for i in range(foreign_section_start + 1, min(foreign_section_start + 5, len(lines))):
            line = lines[i]
            
            if '売り' in line or 'Sales' in line:
                sell_line = line
                sell_line_index = i
                print(f"売り行 (行{i}): {line}")
            
            if '買い' in line or 'Purchases' in line:
                buy_line = line
                buy_line_index = i
                print(f"買い行 (行{i}): {line}")
        
        if not sell_line or not buy_line:
            raise ValueError("海外投資家の売り/買い行が見つかりませんでした")
        
        # 各行から数値を抽出
        number_pattern = r'-?\d{1,3}(?:,\d{3})+|-?\d+'
        
        def extract_numbers_from_line(line):
            """行から数値を抽出し、整数リストとして返す"""
            matches = re.findall(number_pattern, line)
            numbers = []
            for match in matches:
                try:
                    clean = match.replace(',', '')
                    val = int(clean)
                    # 小さすぎる数値（比率など）は除外
                    if abs(val) >= 1000:
                        numbers.append(val)
                except ValueError:
                    continue
            return numbers
        
        sell_numbers = extract_numbers_from_line(sell_line)
        buy_numbers = extract_numbers_from_line(buy_line)
        
        print(f"\n売り行の数値: {[f'{n:,}' for n in sell_numbers]}")
        print(f"買い行の数値: {[f'{n:,}' for n in buy_numbers]}")
        
        # 差引きを計算
        # 売り行の最後の数値が売りの差引き
        # 買い行の最後の数値が買いの差引き
        sell_balance = sell_numbers[-1] if sell_numbers else 0
        buy_balance = buy_numbers[-1] if buy_numbers else 0
        
        print(f"\n売りの差引き: {sell_balance:,}")
        print(f"買いの差引き: {buy_balance:,}")
        
        # 絶対値が大きい方（買い超 or 売り超）を返す
        if abs(buy_balance) >= abs(sell_balance):
            balance = buy_balance
            print(f"\n✓ 買い超を採用: {balance:,}")
        else:
            balance = sell_balance
            print(f"\n✓ 売り超を採用: {balance:,}")
        
        return balance
        
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
