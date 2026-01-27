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
        
        # 「株式週間売買状況」セクションを探す
        # stock_val (金額版) のPDFリンクを探す
        pdf_links = soup.find_all('a', href=lambda x: x and 'stock_val' in x and '.pdf' in x.lower())
        
        if not pdf_links:
            # フォールバック: すべてのPDFリンクを取得して金額版を探す
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
        
        # URLが正しく金額版(stock_val)であることを確認
        if 'stock_val' not in pdf_url:
            raise ValueError(f"金額版PDFではありません: {pdf_url}")
        
        return pdf_url
        
    except Exception as e:
        print(f"URL取得エラー: {e}")
        raise

def extract_date_from_filename(url):
    """
    PDFのURLから日付を抽出
    
    ファイル名の日付をそのまま使用（例: stock_val_1_231204.pdf → 2023-12-04）
    2022年のデータは除外する
    """
    try:
        # ファイル名から日付部分を抽出 (例: 231204)
        match = re.search(r'stock_val_\d+_(\d{6})\.pdf', url)
        if match:
            date_str = match.group(1)
            
            # YYMMDDを解析
            yy = int(date_str[0:2])
            month = int(date_str[2:4])
            day = int(date_str[4:6])
            
            # 年を判定: 23以上なら2023年、それ以下は除外
            if yy >= 23:
                year = 2000 + yy
            else:
                print(f"  警告: 2023年より前のデータをスキップ: 20{yy}-{month:02d}-{day:02d}")
                return None
            
            # YYYY-MM-DD形式で返す
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
    """PDFから海外投資家の差引き金額を抽出（買い金額 - 売り金額で計算）"""
    
    try:
        print("PDFからテーブルを抽出中...")
        
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[0]
            print(f"\n=== ページ 1 を処理 ===")
            
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
                        print(f"\n海外投資家(売り)行を発見:")
                        print(f"  行データ: {row}")
                        
                        # 売り金額を取得（最初の大きな数値）
                        sell_amount = None
                        for cell in row:
                            if cell and str(cell).strip():
                                # カンマ区切りの大きな数値を探す
                                match = re.search(r'\d{1,3}(?:,\d{3})+', str(cell))
                                if match:
                                    try:
                                        value = int(match.group().replace(',', ''))
                                        # 100億以上の数値（売買金額レベル）
                                        if value >= 1000000000:
                                            sell_amount = value
                                            print(f"  売り金額: {sell_amount:,}")
                                            break
                                    except ValueError:
                                        continue
                        
                        if sell_amount is None:
                            print("  警告: 売り金額が見つかりませんでした")
                            continue
                        
                        # 次の行を買い行として処理
                        buy_amount = None
                        if row_idx + 1 < len(table):
                            next_row = table[row_idx + 1]
                            next_row_text = ' '.join([str(cell) if cell else '' for cell in next_row])
                            
                            print(f"\n次の行（買い行と推定）:")
                            print(f"  行データ: {next_row}")
                            
                            if '買い' in next_row_text or 'Purchases' in next_row_text or 'Foreigners' in next_row_text:
                                # 買い金額を取得（最初の大きな数値）
                                for cell in next_row:
                                    if cell and str(cell).strip():
                                        # カンマ区切りの大きな数値を探す
                                        match = re.search(r'\d{1,3}(?:,\d{3})+', str(cell))
                                        if match:
                                            try:
                                                value = int(match.group().replace(',', ''))
                                                # 100億以上の数値（売買金額レベル）
                                                if value >= 1000000000:
                                                    buy_amount = value
                                                    print(f"  買い金額: {buy_amount:,}")
                                                    break
                                            except ValueError:
                                                continue
                        
                        if buy_amount is None:
                            print("  警告: 買い金額が見つかりませんでした")
                            continue
                        
                        # 差引きを計算: 買い - 売り
                        balance = buy_amount - sell_amount
                        
                        if balance > 0:
                            print(f"\n✓ 買い超: {balance:,} (買い {buy_amount:,} - 売り {sell_amount:,})")
                        elif balance < 0:
                            print(f"\n✓ 売り超: {balance:,} (買い {buy_amount:,} - 売り {sell_amount:,})")
                        else:
                            print(f"\n✓ 均衡: 0")
                        
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
    
    # 既存のCSVを読み込むか、新規作成
    if os.path.exists(csv_file):
        df = pd.read_csv(csv_file)
    else:
        df = pd.DataFrame(columns=['date', 'balance'])
    
    # 新しいデータを追加
    new_row = pd.DataFrame({'date': [date_str], 'balance': [value]})
    df = pd.concat([df, new_row], ignore_index=True)
    
    # 重複削除（同じ日付の場合は最新を保持）
    df = df.drop_duplicates(subset=['date'], keep='last')
    
    # 日付でソート
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    df['date'] = df['date'].dt.strftime('%Y-%m-%d')
    
    df.to_csv(csv_file, index=False)
    print(f"CSVに保存しました: {date_str} - {value:,}")

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

def process_historical_data():
    """過去データ（2023-2026年度）を全て取得して保存"""
    
    if DEBUG_MODE:
        print("\n" + "="*60)
        print("⚠️  DEBUG MODE ACTIVE - 2023年ページの上から5件のみ取得")
        print("="*60 + "\n")
    else:
        print("\n=== 過去データの取得を開始 ===")
    
    # 既存のCSVファイルを削除（クリーンスタート）
    csv_file = 'history.csv'
    if os.path.exists(csv_file):
        os.remove(csv_file)
        print("既存のCSVファイルを削除しました")
    
    if DEBUG_MODE:
        # デバッグモード: 2023年ページの上から5件のみ取得（ソートなし）
        urls_2023 = get_all_pdf_urls_by_year(2023)
        all_urls = urls_2023[:DEBUG_LIMIT]  # 上から5件
        print(f"デバッグモード: 2023年ページの上から {len(all_urls)} 件のPDFを処理します")
        print(f"URL例: {all_urls[0] if all_urls else 'なし'}")
    else:
        # 本番モード: 全年度のデータを取得
        all_urls = []
        for year in [2023, 2024, 2025, 2026]:
            urls = get_all_pdf_urls_by_year(year)
            all_urls.extend(urls)
        print(f"\n合計 {len(all_urls)} 件のPDFを処理します")
    
    success_count = 0
    error_count = 0
    skip_count = 0
    
    for idx, url in enumerate(all_urls, 1):
        try:
            print(f"\n[{idx}/{len(all_urls)}] 処理中: {url}")
            
            # 日付を抽出
            date_str = extract_date_from_filename(url)
            if not date_str:
                print(f"  スキップ: 日付が無効またはフィルタリングされました")
                skip_count += 1
                continue
            
            # PDFをダウンロード
            pdf_path = download_pdf(url, f'temp_{idx}.pdf')
            
            # データを抽出
            balance = extract_from_pdf(pdf_path)
            
            # CSVに保存
            save_to_csv(balance, date_str)
            
            # 一時ファイルを削除
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            
            success_count += 1
            
        except Exception as e:
            print(f"  エラー: {e}")
            error_count += 1
            # エラー時も一時ファイルを削除
            temp_file = f'temp_{idx}.pdf'
            if os.path.exists(temp_file):
                os.remove(temp_file)
            continue
    
    print(f"\n=== 過去データ取得完了 ===")
    print(f"成功: {success_count}件, スキップ: {skip_count}件, エラー: {error_count}件")

def main():
    pdf_path = None
    try:
        if DEBUG_MODE:
            print("\n" + "🐛 "*20)
            print("   DEBUG MODE: 高速デバッグモードで実行中")
            print("   2023年ページの上から5件のPDFのみ処理します")
            print("🐛 "*20 + "\n")
        
        csv_file = 'history.csv'
        
        # 初回実行判定: CSVファイルが存在しないか、データが少ない場合
        should_get_historical = False
        
        if not os.path.exists(csv_file):
            should_get_historical = True
            print("=== 初回実行: CSVファイルが存在しません ===\n")
        else:
            try:
                df = pd.read_csv(csv_file)
                if len(df) < 10:  # データが10件未満なら過去データを再取得
                    should_get_historical = True
                    print("=== データが少ないため、過去データを取得します ===\n")
                else:
                    print("=== 通常実行: 最新データのみ取得します ===\n")
            except (pd.errors.EmptyDataError, pd.errors.ParserError):
                should_get_historical = True
                print("=== CSVファイルが破損しているため、再取得します ===\n")
        
        if should_get_historical:
            process_historical_data()
        
        # 最新データを取得
        print("\n=== 最新データの取得 ===")
        
        # 最新のPDF URLを取得
        pdf_url = get_latest_pdf_url()
        
        # 日付を抽出
        date_str = extract_date_from_filename(pdf_url)
        
        if not date_str:
            print("警告: 日付が抽出できませんでした")
            return
        
        # PDFをダウンロード
        pdf_path = download_pdf(pdf_url)
        
        # データ抽出
        balance = extract_from_pdf(pdf_path)
        
        # CSV保存
        save_to_csv(balance, date_str)
        
        # グラフ作成
        create_trend_chart()
        
        print("\n=== 処理完了 ===")
        
    except Exception as e:
        print(f"\nエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        # 一時ファイルを削除
        if pdf_path and os.path.exists(pdf_path):
            os.remove(pdf_path)
            print("一時ファイルを削除しました")

if __name__ == "__main__":
    main()
