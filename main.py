import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import pdfplumber
import re

# デバッグモード: 環境変数 DEBUG_MODE=true で有効化
DEBUG_MODE = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
DEBUG_LIMIT = 5  # デバッグ時に取得するPDF数

def get_all_pdf_urls_by_year(year):
    """指定年度のページから全てのstock_val PDFのURLを取得"""
    base_url = "https://www.jpx.co.jp"
    
    # 年度に応じたアーカイブページのURL
    year_to_archive = {
        2026: "00-00-archives-00.html",
        2025: "00-00-archives-01.html",
        2024: "00-00-archives-02.html",
        2023: "00-00-archives-03.html"
    }
    
    if year not in year_to_archive:
        print(f"警告: {year}年度のアーカイブページは定義されていません")
        return []
    
    page_url = f"https://www.jpx.co.jp/markets/statistics-equities/investor-type/{year_to_archive[year]}"
    
    try:
        print(f"\n{year}年度のページを取得中: {page_url}")
        response = requests.get(page_url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # stock_val (金額版) のPDFリンクを全て取得
        pdf_links = soup.find_all('a', href=lambda x: x and 'stock_val' in x and '.pdf' in x.lower())
        
        urls = []
        for link in pdf_links:
            href = link['href']
            
            # 相対URLを絶対URLに変換
            if href.startswith('/'):
                pdf_url = base_url + href
            elif href.startswith('http'):
                pdf_url = href
            else:
                pdf_url = base_url + '/' + href
            
            urls.append(pdf_url)
        
        print(f"  {year}年度: {len(urls)}件のPDFを発見")
        return urls
        
    except Exception as e:
        print(f"{year}年度のURL取得エラー: {e}")
        return []

def get_latest_pdf_url():
    """JPXのページから最新の金額版PDFファイルのURLを取得"""
    base_url = "https://www.jpx.co.jp"
    page_url = "https://www.jpx.co.jp/markets/statistics-equities/investor-type/00-00-archives-00.html"
    
    try:
        response = requests.get(page_url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # stock_val (金額版) のPDFリンクを探す
        pdf_links = soup.find_all('a', href=lambda x: x and 'stock_val' in x and '.pdf' in x.lower())
        
        if not pdf_links:
            # フォールバック
            all_pdf_links = soup.find_all('a', href=lambda x: x and '.pdf' in x.lower())
            pdf_links = [link for link in all_pdf_links if 'stock_val' in link.get('href', '')]
        
        if not pdf_links:
            raise ValueError("金額版PDF (stock_val) ファイルが見つかりませんでした")
        
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
        
        if 'stock_val' not in pdf_url:
            raise ValueError(f"金額版PDFではありません: {pdf_url}")
        
        return pdf_url
        
    except Exception as e:
        print(f"URL取得エラー: {e}")
        raise

def extract_date_from_filename(url):
    """PDFのURLから日付を抽出"""
    try:
        # ファイル名から日付部分を抽出 (例: 231204)
        match = re.search(r'stock_val_\d+_(\d{6})\.pdf', url)
        if match:
            date_str = match.group(1)
            yy = int(date_str[0:2])
            month = int(date_str[2:4])
            day = int(date_str[4:6])
            
            # 23以上なら2023年、それ以下は除外
            if yy >= 23:
                year = 2000 + yy
            else:
                print(f"  警告: 2023年より前のデータをスキップ: 20{yy}-{month:02d}-{day:02d}")
                return None
            
            result_date = f"{year:04d}-{month:02d}-{day:02d}"
            print(f"  抽出日付: {result_date}")
            return result_date
            
    except Exception as e:
        print(f"日付抽出エラー: {e}")
        import traceback
        traceback.print_exc()
    return None

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
            page = pdf.pages[0]
            tables = page.extract_tables()
            
            if not tables:
                raise ValueError("テーブルが見つかりませんでした")
            
            for table_num, table in enumerate(tables):
                for row_idx, row in enumerate(table):
                    if not row:
                        continue
                    
                    row_text = ' '.join([str(cell) if cell else '' for cell in row])
                    
                    # 海外投資家の売り行
                    if ('海外投資家' in row_text or 'Foreigners' in row_text) and ('売り' in row_text or 'Sales' in row_text):
                        # 7列目（インデックス6）の金額を取得
                        sell_amount = None
                        if len(row) > 6 and row[6]:
                            cell_text = str(row[6]).strip()
                            match = re.search(r'\d{1,3}(?:,\d{3})+', cell_text)
                            if match:
                                try:
                                    sell_amount = int(match.group().replace(',', ''))
                                except ValueError:
                                    pass
                        
                        if sell_amount is None:
                            continue
                        
                        # 次の行を買い行として処理
                        buy_amount = None
                        if row_idx + 1 < len(table):
                            next_row = table[row_idx + 1]
                            next_row_text = ' '.join([str(cell) if cell else '' for cell in next_row])
                            
                            if '買い' in next_row_text or 'Purchases' in next_row_text or 'Foreigners' in next_row_text:
                                if len(next_row) > 6 and next_row[6]:
                                    cell_text = str(next_row[6]).strip()
                                    match = re.search(r'\d{1,3}(?:,\d{3})+', cell_text)
                                    if match:
                                        try:
                                            buy_amount = int(match.group().replace(',', ''))
                                        except ValueError:
                                            pass
                        
                        if buy_amount is None:
                            continue
                        
                        # 差引きを計算
                        balance = buy_amount - sell_amount
                        print(f"\n✓ 海外投資家収支: {balance:,}")
                        return balance
        
        raise ValueError("海外投資家行が見つかりませんでした")
    except Exception as e:
        print(f"PDF抽出エラー: {e}")
        raise

def save_to_csv(value, date_str=None):
    """CSVファイルにデータを保存"""
    csv_file = 'history.csv'
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')
    
    if os.path.exists(csv_file):
        df = pd.read_csv(csv_file)
    else:
        df = pd.DataFrame(columns=['date', 'balance'])
    
    new_row = pd.DataFrame({'date': [date_str], 'balance': [value]})
    df = pd.concat([df, new_row], ignore_index=True)
    df = df.drop_duplicates(subset=['date'], keep='last')
    
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    df['date'] = df['date'].dt.strftime('%Y-%m-%d')
    
    df.to_csv(csv_file, index=False)
    print(f"CSVに保存しました: {date_str} - {value:,}")

def create_trend_chart():
    """トレンドグラフを作成"""
    csv_file = 'history.csv'
    if not os.path.exists(csv_file):
        return
    
    df = pd.read_csv(csv_file)
    if len(df) == 0:
        return
    
    df['date'] = df['date'].astype(str)
    
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

def process_historical_data():
    """過去データを取得して保存"""
    if DEBUG_MODE:
        print("\n=== DEBUG MODE: 過去データを制限して取得 ===")
    else:
        print("\n=== 過去データの取得を開始 ===")
    
    csv_file = 'history.csv'
    if os.path.exists(csv_file):
        os.remove(csv_file)
    
    if DEBUG_MODE:
        urls_2023 = get_all_pdf_urls_by_year(2023)
        all_urls = urls_2023[:DEBUG_LIMIT]
    else:
        all_urls = []
        for year in [2023, 2024, 2025, 2026]:
            urls = get_all_pdf_urls_by_year(year)
            all_urls.extend(urls)
    
    for idx, url in enumerate(all_urls, 1):
        try:
            print(f"\n[{idx}/{len(all_urls)}] 処理中: {url}")
            date_str = extract_date_from_filename(url)
            if not date_str:
                continue
            
            pdf_path = download_pdf(url, f'temp_{idx}.pdf')
            balance = extract_from_pdf(pdf_path)
            save_to_csv(balance, date_str)
            
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
        except Exception as e:
            print(f"  エラー: {e}")
            temp_file = f'temp_{idx}.pdf'
            if os.path.exists(temp_file):
                os.remove(temp_file)
            continue

def main():
    pdf_path = None
    try:
        # 初回またはデータ不足時の過去データ取得判定
        csv_file = 'history.csv'
        should_get_historical = False
        
        if not os.path.exists(csv_file):
            should_get_historical = True
        else:
            try:
                df = pd.read_csv(csv_file)
                if len(df) < 10:
                    should_get_historical = True
            except:
                should_get_historical = True
        
        if should_get_historical:
            process_historical_data()
        
        # 最新データ取得
        print("\n=== 最新データの取得 ===")
        pdf_url = get_latest_pdf_url()
        date_str = extract_date_from_filename(pdf_url)
        
        if date_str:
            pdf_path = download_pdf(pdf_url)
            balance = extract_from_pdf(pdf_path)
            save_to_csv(balance, date_str)
            create_trend_chart()
        
        print("\n=== JPX処理完了 ===")
        
    except Exception as e:
        print(f"\nJPXエラーが発生しました: {e}")
        # JPX処理が失敗しても後続処理（Shutai）を実行したいため、
        # ここではエラーログを出して終了せず、例外を再送出する（Actionsを失敗扱いにしたい場合）
        # ただし、今回は要件通り「両方の処理」を実行するため、ここでraiseする
        raise
    finally:
        if pdf_path and os.path.exists(pdf_path):
            os.remove(pdf_path)

if __name__ == "__main__":
    # 1. JPX PDF Processing
    try:
        main()
    except Exception as e:
        print("Main execution failed, but continuing to scraping task if possible.")
        # Github Actionsでは一つでも失敗したら失敗とみなしたいため、フラグ管理してもよいが
        # ここでは後続を実行してから終了ステータスを考慮する
        # （簡易的に、まずは順次実行する）
        pass

    # 2. Investor Trading Status Scraping (Shutai)
    print("\n" + "-" * 30)
    print("Starting Investor Trading Status Scraping...")
    try:
        import shutai_scraper
        shutai_scraper.scrape_shutai_data()
    except ImportError as e:
        print(f"Failed to import shutai_scraper: {e}")
    except Exception as e:
        print(f"Failed to run shutai_scraper: {e}")
    print("-" * 30 + "\n")
