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
        
        # ヘッダー行を探して「差引き」の位置を特定
        balance_keyword_positions = []
        for i, line in enumerate(lines):
            if '差引き' in line or 'balance' in line.lower():
                print(f"差引きヘッダー行 (行{i}): {line}")
                # この行での「差引き」の出現位置を記録
                words = line.split()
                for j, word in enumerate(words):
                    if '差引き' in word.lower() or 'balance' in word.lower():
                        balance_keyword_positions.append(j)
        
        # 海外投資家の買いの行を探す
        foreign_investor_found = False
        purchases_found = False
        target_line = None
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            # 海外投資家の行を見つける
            if ('海外投資家' in line or 'foreigners' in line_lower) and not foreign_investor_found:
                foreign_investor_found = True
                print(f"\n海外投資家行を発見 (行{i}): {line}")
                
                # この行または次の数行で「買い」または「purchases」を探す
                for j in range(i, min(i + 3, len(lines))):
                    check_line = lines[j].lower()
                    if '買い' in check_line or 'purchases' in check_line:
                        target_line = lines[j]
                        purchases_found = True
                        print(f"買い行を発見 (行{j}): {lines[j]}")
                        break
                
                if purchases_found:
                    break
        
        if not purchases_found:
            raise ValueError("海外投資家の買い行が見つかりませんでした")
        
        print(f"\n対象行の全文: {target_line}")
        
        # 行を単語に分割
        words = target_line.split()
        
        # 数値を抽出（カンマ区切りの数値も含む）
        number_pattern = r'-?\d{1,3}(?:,\d{3})+|-?\d+'
        numbers_with_positions = []
        
        for i, word in enumerate(words):
            matches = re.findall(number_pattern, word)
            for match in matches:
                try:
                    clean_num = match.replace(',', '')
                    value = int(clean_num)
                    # 小さすぎる数値（比率など）は除外
                    if abs(value) >= 1000:
                        numbers_with_positions.append((i, value, match))
                except ValueError:
                    continue
        
        print(f"\n数値とその位置:")
        for pos, val, orig in numbers_with_positions:
            print(f"  位置{pos}: {orig} = {val:,}")
        
        # 差引きの値を特定
        # 戦略: 行の中で3番目以降の大きな数値（最初の2つは通常、売りと買いの金額）
        if len(numbers_with_positions) >= 3:
            # 位置でソートして、3番目の大きな数値を取得
            # または、「差引き」の直後の数値を探す
            balance = numbers_with_positions[2][1]  # 3番目の数値
            print(f"\n✓ 抽出成功 (3番目の数値): {balance:,}")
        elif len(numbers_with_positions) >= 1:
            # フォールバック: 最小の絶対値を持つ数値（差引きは通常、売買金額より小さい）
            balance = min(numbers_with_positions, key=lambda x: abs(x[1]))[1]
            print(f"\n✓ 抽出成功 (最小絶対値): {balance:,}")
        else:
            raise ValueError("適切な数値を抽出できませんでした")
        
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
