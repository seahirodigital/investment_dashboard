import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from google import genai
from google.genai import types
import time

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

def extract_with_gemini(pdf_path):
    """Gemini APIを使ってPDFから海外投資家の差引き金額を抽出"""
    
    # 環境変数からAPIキーを取得
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY環境変数が設定されていません")
    
    # Gemini APIクライアントを初期化
    client = genai.Client(api_key=api_key)
    
    try:
        # PDFファイルを読み込み
        print("PDFを読み込み中...")
        with open(pdf_path, 'rb') as f:
            pdf_data = f.read()
        
        # プロンプトを作成
        prompt = """
このPDFファイルは日本取引所グループ(JPX)の「投資部門別売買状況」のデータです。

以下の情報を抽出してください:
- 「海外投資家」(Foreigners)の行を見つける
- その行の「買い」(Purchases)に対応する「差引き」(Balance)の金額を見つける
- 金額は数値のみを返してください（カンマなし、符号あり）

例: 750493712 または -123456789

重要:
- 必ず「海外投資家」の「買い」の行を見てください
- 「比率」や他の列の数値と間違えないでください
- 数値のみを返してください（説明や単位は不要）
"""
        
        print("Geminiで解析中...")
        
        # PDFをアップロードしてコンテンツ生成
        response = client.models.generate_content(
            model='gemini-2.0-flash-exp',
            contents=[
                types.Part.from_bytes(
                    data=pdf_data,
                    mime_type='application/pdf'
                ),
                prompt
            ]
        )
        
        # 結果を取得
        result_text = response.text.strip()
        print(f"Gemini応答: {result_text}")
        
        # 数値に変換
        # レスポンスから数値部分のみを抽出
        import re
        numbers = re.findall(r'-?\d+', result_text.replace(',', '').replace(' ', ''))
        
        if not numbers:
            raise ValueError("Geminiのレスポンスから数値を抽出できませんでした")
        
        # 最初の数値を使用（通常は最も関連性の高い数値）
        value = int(numbers[0])
        
        print(f"抽出された値: {value:,}")
        
        return value
        
    except Exception as e:
        print(f"Gemini抽出エラー: {e}")
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
        print("=== JPX海外投資家データ抽出開始 (Gemini使用) ===\n")
        
        # 最新のPDF URLを取得
        pdf_url = get_latest_pdf_url()
        
        # PDFをダウンロード
        pdf_path = download_pdf(pdf_url)
        
        # Geminiでデータ抽出
        balance = extract_with_gemini(pdf_path)
        
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
