import os
import re
import csv

HTML_PATH = r"c:\Users\mahha\OneDrive\開発\investment_dashboard\sector_category.html"
OUTPUT_DIR = r"C:\Users\mahha\Downloads\CSVリスト"

def parse_html_content(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. US_SECTORS
    us_sectors_dict = {}
    us_sectors_match = re.search(r"const\s+US_SECTORS\s*=\s*\{([^}]+)\}", content)
    if us_sectors_match:
        block = us_sectors_match.group(1)
        for line in block.split('\n'):
            m = re.search(r"'([^']+)':\s*'([^']+)'", line)
            if m:
                us_sectors_dict[m.group(1)] = m.group(2)

    # 2. SEMICONDUCTOR_JP
    semi_jp_dict = {}
    semi_jp_match = re.search(r"const\s+SEMICONDUCTOR_JP\s*=\s*\{([^}]+)\}", content)
    if semi_jp_match:
        block = semi_jp_match.group(1)
        for line in block.split('\n'):
            m = re.search(r"'([^']+)':\s*'([^']+)'", line)
            if m:
                semi_jp_dict[m.group(1)] = m.group(2)

    # 3. SEMICONDUCTOR_US
    semi_us_dict = {}
    semi_us_match = re.search(r"const\s+SEMICONDUCTOR_US\s*=\s*\{([^}]+)\}", content)
    if semi_us_match:
        block = semi_us_match.group(1)
        for line in block.split('\n'):
            m = re.search(r"'([^']+)':\s*'([^']+)'", line)
            if m:
                semi_us_dict[m.group(1)] = m.group(2)

    # 4. CATEGORY_DETAILS
    category_details = {}
    details_match = re.search(r"const\s+CATEGORY_DETAILS\s*=\s*\{(.+?)\}\s*;\s*\n", content, re.DOTALL)
    if not details_match:
        details_match = re.search(r"const\s+CATEGORY_DETAILS\s*=\s*\{(.+?)\}\s*;", content, re.DOTALL)

    if details_match:
        details_block = details_match.group(1)
        key_blocks = re.findall(r"([a-zA-Z0-9_]+):\s*\[(.*?)\s*\]\s*(?:,|\n|$)", details_block, re.DOTALL)
        for key, list_str in key_blocks:
            items = []
            obj_matches = re.findall(r"\{([^}]+)\}", list_str, re.DOTALL)
            for obj_str in obj_matches:
                item = {}
                name_m = re.search(r"name:\s*'([^']+)'", obj_str)
                type_m = re.search(r"type:\s*'([^']+)'", obj_str)
                code_m = re.search(r"code:\s*'([^']+)'", obj_str)
                stocks_m = re.search(r"stocks:\s*'([^']+)'", obj_str)
                
                if name_m:
                    item['name'] = name_m.group(1)
                if type_m:
                    item['type'] = type_m.group(1)
                if code_m:
                    item['code'] = code_m.group(1)
                if stocks_m:
                    item['stocks'] = stocks_m.group(1)
                items.append(item)
            category_details[key] = items

    return us_sectors_dict, semi_jp_dict, semi_us_dict, category_details

def extract_codes_from_string(s):
    """コード文字列から証券コード/ティッカーを抽出する。
    対応形式:
      - 'CODE.T (名前)'  → CODE を抽出
      - '^DJI (名前)'   → ^DJI を抽出
      - '名前(CODE.T)'  → CODE を抽出（参考ラインなど）
    """
    codes = []
    
    # 先頭がコードで括弧内が名前の形式: 'CODE.T (...)' or '^CODE (...)'
    # 文字列の最初のトークンがコードかどうかチェック
    first_token = s.split()[0].replace('.T', '').strip().rstrip(',') if s.strip() else ''
    if re.match(r'^(\^[A-Z0-9]+|[0-9]{4}|[0-9A-Z]{3,6})$', first_token):
        codes.append(first_token)
        return sorted(list(set(codes)))
    
    # 「名前(コード)」形式: 参考ラインなど
    paren_matches = re.findall(r'\(([^)]+)\)', s)
    for pm in paren_matches:
        pm_clean = pm.replace('.T', '').strip()
        # コードらしい文字列のみ取得（スペースなし、証券コード/ティッカー形式）
        if re.match(r'^(\^[A-Z0-9]+|[0-9]{4}|[0-9A-Z]{2,6})$', pm_clean):
            codes.append(pm_clean)
    
    return sorted(list(set(codes)))

def get_codes_for_detail_item(item):
    codes = []
    t = item.get('type')
    if t in ('ETF', '指数'):
        if 'code' in item:
            c = item['code']
            c_clean = c.split()[0].replace('.T', '').strip()
            codes.append(c_clean)
    elif t == 'バスケット':
        if 'stocks' in item:
            s = item['stocks']
            matches = re.findall(r"\(([^)]+)\)", s)
            for m in matches:
                codes.append(m.replace('.T', '').strip())
    return codes

def build_code_to_name_map(us_sectors_dict, semi_jp_dict, semi_us_dict, category_details):
    code_to_name = {}
    code_to_name['1306'] = 'TOPIX'
    code_to_name['SPY'] = 'SPY'

    for ticker, name in us_sectors_dict.items():
        code_to_name[ticker] = name

    for ticker, name in semi_jp_dict.items():
        code_to_name[ticker.replace('.T', '')] = name

    for ticker, name in semi_us_dict.items():
        code_to_name[ticker] = name

    for cat_key, items in category_details.items():
        for item in items:
            t = item.get('type')
            if t in ('ETF', '指数') and 'code' in item:
                c = item['code']
                first_token = c.split()[0].replace('.T', '').strip()
                item_name = item.get('name', '')
                
                # 先頭がコード形式（数字4桁 or ^TICKER）の場合: 「CODE (名前)」形式
                if re.match(r'^(\^[A-Z0-9]+|[0-9]{4}|[0-9A-Z]{2,6})$', first_token):
                    # item['name'] が正式な銘柄名として使用する
                    code_to_name[first_token] = item_name
                else:
                    # 「名前(CODE) / 名前(CODE)」形式（参考ライン等）
                    matches = re.findall(r'([^・()/\s][^(/)]*?)\(([^)]+)\)', c)
                    for seg_name, seg_code in matches:
                        clean_code = seg_code.replace('.T', '').strip()
                        clean_name = seg_name.strip()
                        if re.match(r'^(\^[A-Z0-9]+|[0-9]{4}|[0-9A-Z]{2,6})$', clean_code):
                            code_to_name[clean_code] = clean_name
            elif t == 'バスケット' and 'stocks' in item:
                # stocks フィールドは「名前(CODE.T)」形式
                matches = re.findall(r'([^・()/]+)\(([^)]+)\)', item['stocks'])
                for seg_name, seg_code in matches:
                    code_to_name[seg_code.replace('.T', '').strip()] = seg_name.strip()
                    
    return code_to_name

def main():
    print("セクター分類分析 HTMLからのCSV抽出（2列構成：コード/銘柄）を開始します...")
    
    if not os.path.exists(HTML_PATH):
        print(f"エラー: {HTML_PATH} が存在しません。")
        return

    us_sectors_dict, semi_jp_dict, semi_us_dict, category_details = parse_html_content(HTML_PATH)
    code_to_name = build_code_to_name_map(us_sectors_dict, semi_jp_dict, semi_us_dict, category_details)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"出力先フォルダ: {OUTPUT_DIR}")

    # CSV書き出しヘルパー
    def write_csv(filename, codes):
        filepath = os.path.join(OUTPUT_DIR, filename)
        # 重複排除とソート
        unique_codes = sorted(list(set(codes)))
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['コード', '銘柄'])
            for code in unique_codes:
                numerator = code.split('/')[0]
                name = code_to_name.get(numerator, numerator)
                writer.writerow([code, name])
        print(f"  作成完了: {filename} ({len(unique_codes)}件)")

    # 1. 【US】相対パフォーマンス推移（全セクターvs SPY）.csv
    us_sectors = list(us_sectors_dict.keys())
    us_rel = [f"{ticker}/SPY" for ticker in us_sectors]
    write_csv("【US】相対パフォーマンス推移（全セクターvs SPY）.csv", us_rel)

    # 2. 【US】米国セクター パフォーマンス推移（絶対値）.csv
    write_csv("【US】米国セクター パフォーマンス推移（絶対値）.csv", us_sectors)

    # 3. 規模別指数（絶対値）.csv
    scale_codes = []
    if 'scale' in category_details:
        for item in category_details['scale']:
            if 'code' in item:
                scale_codes.extend(extract_codes_from_string(item['code']))
    write_csv("規模別指数（絶対値）.csv", scale_codes)

    # 4. 【JP】相対パフォーマンス推移（全セクターvs TOPIX）.csv
    jp_all_codes = []
    for cat_key, items in category_details.items():
        if cat_key == 'scale':
            continue
        for item in items:
            codes = get_codes_for_detail_item(item)
            for c in codes:
                if c != '1306': # TOPIX自身は除外
                    jp_all_codes.append(f"{c}/1306")
    write_csv("【JP】相対パフォーマンス推移（全セクターvs TOPIX）.csv", jp_all_codes)

    # 5. 非鉄金属・半導体・機械・建設・資材・中小型.csv
    smallcap_codes = []
    if 'smallcap' in category_details:
        for item in category_details['smallcap']:
            for c in get_codes_for_detail_item(item):
                smallcap_codes.append(f"{c}/1306")
    write_csv("非鉄金属・半導体・機械・建設・資材・中小型.csv", smallcap_codes)

    # 6. 【JP】半導体銘柄（絶対値）.csv
    semi_jp = list(semi_jp_dict.keys())
    semi_jp_clean = [t.replace('.T', '') for t in semi_jp]
    write_csv("【JP】半導体銘柄（絶対値）.csv", semi_jp_clean)

    # 7. 【US】半導体銘柄（絶対値）.csv
    semi_us = list(semi_us_dict.keys())
    write_csv("【US】半導体銘柄（絶対値）.csv", semi_us)

    # 8. 金融・内需系.csv
    finance_codes = []
    if 'finance' in category_details:
        for item in category_details['finance']:
            for c in get_codes_for_detail_item(item):
                finance_codes.append(f"{c}/1306")
    write_csv("金融・内需系.csv", finance_codes)

    # 9. 不動産・建設・インフラ.csv
    re_codes = []
    if 'realestate' in category_details:
        for item in category_details['realestate']:
            for c in get_codes_for_detail_item(item):
                re_codes.append(f"{c}/1306")
    write_csv("不動産・建設・インフラ.csv", re_codes)

    # 10. エネルギー・資源・素材（バリュー系）.csv
    energy_codes = []
    if 'energy' in category_details:
        for item in category_details['energy']:
            for c in get_codes_for_detail_item(item):
                energy_codes.append(f"{c}/1306")
    write_csv("エネルギー・資源・素材（バリュー系）.csv", energy_codes)

    # 11. 製造・精密・ハイテク.csv
    tech_codes = []
    if 'tech' in category_details:
        for item in category_details['tech']:
            for c in get_codes_for_detail_item(item):
                tech_codes.append(f"{c}/1306")
    write_csv("製造・精密・ハイテク.csv", tech_codes)

    # 12. 消費・サービス・生活.csv
    consumer_codes = []
    if 'consumer' in category_details:
        for item in category_details['consumer']:
            for c in get_codes_for_detail_item(item):
                consumer_codes.append(f"{c}/1306")
    write_csv("消費・サービス・生活.csv", consumer_codes)

    print("すべてのCSV出力が完了しました。")

if __name__ == "__main__":
    main()
