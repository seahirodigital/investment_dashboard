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
        
        # 海外投資家の買いの行を探す
        foreign_investor_found = False
        purchases_found = False
        target_line_index = None
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            # 海外投資家の行を見つける
            if ('海外投資家' in line or 'foreigners' in line_lower) and not foreign_investor_found:
                foreign_investor_found = True
                print(f"海外投資家行を発見 (行{i}): {line[:100]}")
                
                # この行または次の数行で「買い」または「purchases」を探す
                for j in range(i, min(i + 10, len(lines))):
                    check_line = lines[j].lower()
                    if '買い' in check_line or 'purchases' in check_line:
                        target_line_index = j
                        purchases_found = True
                        print(f"買い行を発見 (行{j}): {lines[j][:100]}")
                        break
                
                if purchases_found:
                    break
        
        if not purchases_found:
            raise ValueError("海外投資家の買い行が見つかりませんでした")
        
        # ターゲット行から数値を抽出
        # 差引き（Balance）は通常、行の右側にある大きな数値
        target_line = lines[target_line_index]
        print(f"\n対象行の全文: {target_line}")
        
        # 数値を抽出（カンマ区切りの数値も含む）
        # パターン: 符号あり/なしの数値、カンマ区切り対応
        number_pattern = r'-?\d{1,3}(?:,\d{3})+|\d+'
        numbers = re.findall(number_pattern, target_line)
        
        print(f"行内の数値: {numbers}")
        
        # 最も大きな数値を差引きとみなす（通常、差引きは最大の金額）
        # カンマを除去して整数に変換
        values = []
        for num_str in numbers:
            try:
                clean_num = num_str.replace(',', '')
                value = int(clean_num)
                values.append(value)
            except ValueError:
                continue
        
        if not values:
            raise ValueError("数値を抽出できませんでした")
        
        # 絶対値が最大の数値を選択（差引きは通常最大）
        balance = max(values, key=abs)
        
        print(f"\n✓ 抽出成功: {balance:,}")
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
