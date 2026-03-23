import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta, timezone

BENCHMARK = '1306.T'

# ── ETFベースセクター（既存を維持、etf.htmlと互換）──────────────────────
SECTORS = {
  '1617.T': '食品',                        # WT/FD 複合ETF（バスケットで分離）
  '1619.T': '建設・資材',                  # CON 単独
  '1620.T': '素材・化学',                  # PAP/TXA/GAC/CAF 複合ETF（バスケットで分離）
  '1621.T': '医薬品',                      # PHR 単独
  '1622.T': '自動車・輸送機',              # RBP/TPXE 複合ETF（バスケットで分離）
  '1623.T': '鉄鋼・非鉄',                  # IAS/NM 複合ETF（バスケットで分離）
  '1624.T': '機械',                        # MIN/MC 複合ETF（バスケットで分離）
  '1625.T': '電機・精密',                  # ELC 単独
  '1626.T': '情報通信・サービスその他',    # MP/SVS 複合ETF
  '1627.T': '電力・ガス',                  # EPG 単独
  '1628.T': '運輸・物流',                  # AT/LT/WHT/SHP 複合ETF（バスケットで分離）
  '1629.T': '商社・卸売',                  # COM/OAC/SVS 複合ETF（バスケットで分離）
  '1630.T': '小売',                        # RT 単独
  '1631.T': '銀行',                        # BNK 旧コード
  '1632.T': '金融（除く銀行）',            # INS/SEC/OFB 複合ETF（バスケットで分離）
  '1633.T': '不動産',                      # RE 単独
  '213A.T': '半導体',                      # 半導体 旧コード
  '^N225':  '日経指数',                    # NI225 旧コード

  # ── 新規追加 ETFセクター ──────────────────────────────────────
  # 1613.T (情報・通信業 TPXI) は上場廃止のため除外
  '1615.T': '銀行業',                     # BNK 新コード
  '1321.T': '日経225ETF',                 # NI225 ETF
  '^TNX':   '米国債10年',                  # 10501 米国債10年利回り(CBOE)（市場環境参照用）
  '2644.T': '半導体ETF',                  # Global X 日本半導体ETF
  '200A.T': 'GX日本成長',                 # GX日本成長投資ETF

  # ── 規模別指数（絶対値チャート用、TOPIX割り返しなし）──────────────────
  '1311.T': 'TOPIX Core30',              # NEXT FUNDS TOPIX Core 30（超大型株30銘柄）
  '1591.T': 'JPX400',                    # NEXT FUNDS JPX日経インデックス400（中大型400銘柄）
  '2516.T': 'グロース250',               # 東証グロース市場250指数ETF（中小型・新興株）

  # ── グローバル先物 2026年6月限（規模別チャート参照用）──────────────────
  # JP市場時間中もリアルタイムで動くため、日経等との比較に有用
  # 限月切替時（2026年9月限→ NQU26.CME 等）にシンボル更新が必要
  'NQM26.CME': 'NQmain(2606)',            # NASDAQ 100先物 2026年6月限（CME）
  'ESM26.CME': 'ESmain(2606)',            # S&P 500先物 2026年6月限（CME）
  'YMM26.CBT': 'YMmain(2606)',            # Dow Jones先物 2026年6月限（CBOT）

  # ── グローバル指数（規模別チャート絶対値基準用）────────────────────────
  # 先物は契約ロールで日次終値がずれるため、指数を前日終値基準として使用
  '^NDX':   'NASDAQ100',                  # NASDAQ-100 Index
  '^GSPC':  'S&P500',                     # S&P 500 Index
  '^DJI':   'NYダウ',                     # Dow Jones Industrial Average
}

# ── 半導体銘柄（日本・米国、個別株式）─────────────────────────────────────
SEMICONDUCTOR_JP = {
  '2644.T': 'GX半導体ETF',
  '5801.T': '古河電工',
  '285A.T': 'キオクシア',
  '5802.T': '住友電工',
  '5803.T': 'フジクラ',
  '6146.T': 'ディスコ',
  '7729.T': '東京精密',
  '7735.T': 'SCREEN',
  '6857.T': 'アドバンテスト',
  '6315.T': 'TOWA',
  '6920.T': 'レーザーテック',
  '6723.T': 'ルネサス',
  '8035.T': '東京エレクトロン',
  '6525.T': 'KOKUSAI',
  '6526.T': 'ソシオネクスト',
  '9984.T': 'ソフトバンクG',
}

SEMICONDUCTOR_US = {
  '^SOX':   'SOX指数',
  'SNDK':   'サンディスク',
  'WDC':    'ウエスタンデジタル',
  'MU':     'マイクロン',
  'AMAT':   'アプライドマテリアルズ',
  'LRCX':   'ラムリサーチ',
  'ASML':   'ASML',
  'KLAC':   'KLA',
  'INTC':   'インテル',
  'ARM':    'アーム',
  'TSM':    'TSMC',
  'NVDA':   'エヌビディア',
  'AVGO':   'ブロードコム',
  'AMD':    'AMD',
  'ORCL':   'オラクル',
}

# ── 米国セクターETF（SPDRセレクト・セクター等）─────────────────────────────
US_SECTORS = {
  'XLK':  '情報技術',
  'XLF':  '金融',
  'XLC':  '通信サービス',
  'XLV':  'ヘルスケア',
  'XLI':  '資本財',
  'XLB':  '素材',
  'XLU':  '公共事業',
  'XLE':  'エネルギー',
  'XLP':  '生活必需品',
  'XLRE': '不動産',
  'XLY':  '一般消費財',
  'XSD':  '半導体',
  'XSW':  'ソフトウェア',
  # 'XWEB': 'インターネット',  # 上場廃止（yfinance取得不可）
  # 'XTH':  'ハードウェア',    # 上場廃止（yfinance取得不可）
  'XBI':  'バイオテクノロジー',
  'XPH':  '製薬',
  'XHE':  '医療機器',
  'XHS':  '医療サービス',
  'XME':  '金属・採掘',
  'XRT':  '小売',
  'XHB':  '住宅建設',
  'XTN':  '輸送',
  'XTL':  '通信機器',
  'XAR':  '防衛',
  'KBE':  '銀行',
  'KRE':  '地方銀行',
  'XOP':  '石油探索・生産',
  'XES':  'エネルギー設備',
  'PAVE': 'インフラ',
}

# ── バスケットセクター（時価総額上位銘柄で構成）─────────────────────────
# 同一ETFコードに複数業種が混在しているため、代表銘柄の等加重平均で分離
BASKET_SECTORS = {

    # ── 金融・内需系: 1632.T(保険+証券+その他金融) を分離 ──
    '保険業': [
        '8766.T',  # 東京海上ホールディングス
        '8725.T',  # MS&ADインシュアランスグループHD
        '8630.T',  # SOMPOホールディングス
        '8750.T',  # 第一生命ホールディングス
        '8795.T',  # T&Dホールディングス
        '7181.T',  # かんぽ生命保険
        '6178.T',  # 日本郵政
    ],
    '証券業': [
        '8604.T',  # 野村ホールディングス
        '8601.T',  # 大和証券グループ本社
        '8473.T',  # SBIホールディングス
        '8697.T',  # 日本取引所グループ(JPX)
        '8628.T',  # 松井証券
        '8698.T',  # マネックスグループ
        '8616.T',  # 東海東京フィナンシャルHD
        '8613.T',  # 丸三証券
        '8622.T',  # 水戸証券
        '8595.T',  # ジャフコグループ
        '8706.T',  # 極東証券
    ],
    'その他金融': [
        '8591.T',  # オリックス
        '8572.T',  # アコム(三菱UFJ系)
        '8253.T',  # クレディセゾン
        '8515.T',  # アイフル
        '8439.T',  # 東京センチュリー
        '8424.T',  # 芙蓉総合リース
        '8570.T',  # イオンフィナンシャルサービス
        '8566.T',  # リコーリース
        '8584.T',  # ジャックス
        '8593.T',  # 三菱HCキャピタル
        '8425.T',  # みずほリース
    ],

    # ── エネルギー・資源・素材: 1618(鉱業+石油石炭), 1617(水産+食料品) ──
    '鉱業': [
        '1605.T',  # INPEX
        '1662.T',  # 石油資源開発
        '1515.T',  # 日鉄鉱業
        '1518.T',  # 三井松島ホールディングス
        '5541.T',  # 大平洋金属
        '1663.T',  # K&Oエナジーグループ
        '1514.T',  # 住石ホールディングス
    ],
    '石油・石炭': [
        '5020.T',  # ENEOSホールディングス
        '5019.T',  # 出光興産
        '5021.T',  # コスモエネルギーホールディングス
    ],
    '水産・農林': [
        '1332.T',  # 日本水産
        '1333.T',  # マルハニチロ
        '1301.T',  # 極洋
    ],
    'ゴム製品': [
        '5108.T',  # ブリヂストン
        '5105.T',  # 横浜ゴム
        '5110.T',  # 住友ゴム工業
    ],
    '卸売業': [
        '8058.T',  # 三菱商事
        '8031.T',  # 三井物産
        '8001.T',  # 伊藤忠商事
        '8053.T',  # 住友商事
        '8002.T',  # 丸紅
        '8015.T',  # 豊田通商
        '2768.T',  # 双日
        '3132.T',  # マクニカホールディングス
        '8020.T',  # 兼松
    ],
    'その他製品': [
        '7974.T',  # 任天堂
        '9766.T',  # コナミグループ
        '9697.T',  # カプコン
        '7832.T',  # バンダイナムコHD
        '9684.T',  # スクウェア・エニックスHD
        '7951.T',  # ヤマハ
        '7936.T',  # アシックス
        '3659.T',  # ネクソン
        '7911.T',  # TOPPAN
        '7912.T',  # 大日本印刷(DNP)
    ],

    # ── 消費・サービス・生活: 1617(食料品), 1628(空運/陸運), 1622(輸送用機器) ──
    '食料品': [
        '2502.T',  # アサヒグループHD
        '2503.T',  # キリンHD
        '2802.T',  # 味の素
        '2801.T',  # キッコーマン
        '2897.T',  # 日清食品HD
        '2914.T',  # JT(日本たばこ産業)
        '2282.T',  # 日本ハム
        '2871.T',  # ニチレイ
        '2269.T',  # 明治HD
        '2270.T',  # 雪印メグミルク
        '2267.T',  # ヤクルト本社
        '2587.T',  # サントリー食品インターナショナル
    ],
    '空運業': [
        '9202.T',  # ANAホールディングス
        '9201.T',  # 日本航空(JAL)
    ],
    '陸運業': [
        '9022.T',  # 東海旅客鉄道(JR東海)
        '9020.T',  # 東日本旅客鉄道(JR東)
        '9021.T',  # 西日本旅客鉄道(JR西)
        '9064.T',  # ヤマトホールディングス
        '9005.T',  # 東急
        '9008.T',  # 小田急電鉄
        '9048.T',  # 名古屋鉄道
        '9001.T',  # 東武鉄道
        '9007.T',  # 京王電鉄
        '9006.T',  # 京浜急行電鉄
        '9143.T',  # SGホールディングス
        '9042.T',  # 阪急阪神ホールディングス
        '9009.T',  # 京成電鉄
    ],
    '輸送用機器': [
        '7203.T',  # トヨタ自動車
        '7267.T',  # 本田技研工業
        '7269.T',  # スズキ
        '7270.T',  # SUBARU
        '7201.T',  # 日産自動車
        '7261.T',  # マツダ
        '7272.T',  # ヤマハ発動機
        '7282.T',  # 豊田合成
        '7211.T',  # 三菱自動車工業
        '7205.T',  # 日野自動車
        '7259.T',  # アイシン
        '7309.T',  # シマノ
    ],

    # ── ハイテク・製造・精密: 1628(倉庫・運輸), 1629(サービス業), 1620(パルプ/繊維/ガラス) ──
    '倉庫・運輸': [
        '9302.T',  # 三菱倉庫
        '9303.T',  # 住友倉庫
        '9065.T',  # 山九
        '9305.T',  # 安田倉庫
        '9304.T',  # 渋沢倉庫
        '9307.T',  # 杉村倉庫
    ],
    'サービス業': [
        '6098.T',  # リクルートHD
        '4324.T',  # 電通グループ
        '2413.T',  # エムスリー
        '9602.T',  # 東宝
        '9735.T',  # セコム
        '4751.T',  # サイバーエージェント
        '2432.T',  # DeNA
        '4385.T',  # メルカリ
        '4661.T',  # オリエンタルランド
        '2181.T',  # パーソルホールディングス
    ],
    'パルプ・紙': [
        '3861.T',  # 王子ホールディングス
        '3863.T',  # 日本製紙
        '3880.T',  # 大王製紙
        '3865.T',  # 北越コーポレーション
        '3877.T',  # 中越パルプ工業
    ],
    '繊維製品': [
        '3402.T',  # 東レ
        '3401.T',  # 帝人
        '3105.T',  # 日清紡ホールディングス
        '3107.T',  # ダイワボウホールディングス
        '3103.T',  # ユニチカ
        '3201.T',  # 日本毛織(ニッケ)
        '3302.T',  # 帝国繊維
    ],
    'ガラス・土石': [
        '5201.T',  # AGC(旭硝子)
        '5214.T',  # 日本電気硝子
        '5233.T',  # 太平洋セメント
        '5232.T',  # 住友大阪セメント
        '5301.T',  # 東海カーボン
        '5202.T',  # 日本板硝子
        '5334.T',  # 日本特殊陶業
        '5310.T',  # 東洋炭素
    ],

    # ── 新興・中小型・資本財: 1620(化学), 1624(機械), 1623(非鉄金属), 1624(金属製品), 1628(海運) ──
    '化学': [
        '4063.T',  # 信越化学工業
        '4183.T',  # 三井化学
        '4188.T',  # 三菱ケミカルグループ
        '4901.T',  # 富士フイルムHD
        '4631.T',  # DIC
        '4004.T',  # レゾナック・ホールディングス
        '4182.T',  # 三菱ガス化学
        '4208.T',  # UBE
        '4452.T',  # 花王
        '3407.T',  # 旭化成
        '4911.T',  # 資生堂
        '8113.T',  # ユニ・チャーム
        '6988.T',  # 日東電工
    ],
    '機械': [
        '6367.T',  # ダイキン工業
        '6301.T',  # コマツ(小松製作所)
        '6273.T',  # SMC
        '7011.T',  # 三菱重工業
        '6326.T',  # クボタ
        '6302.T',  # 住友重機械工業
        '7012.T',  # 川崎重工業
        '7013.T',  # IHI
        '6305.T',  # 日立建機
        '6201.T',  # 豊田自動織機
        '6954.T',  # ファナック
        '6383.T',  # ダイフク
        '6361.T',  # 荏原製作所
    ],
    '金属製品': [
        '5938.T',  # LIXILグループ
        '5901.T',  # 東洋製罐グループHD
        '5803.T',  # フジクラ
        '5805.T',  # 昭和電線ホールディングス
        '5949.T',  # ユニプレス
        '5991.T',  # ニッパツ(日本発条)
        '5970.T',  # GS ユアサ コーポレーション
        '5929.T',  # 三和ホールディングス
        '5947.T',  # リンナイ
    ],
    '鉄鋼': [
        '5401.T',  # 日本製鉄
        '5411.T',  # JFEホールディングス
        '5406.T',  # 神戸製鋼所
        '5440.T',  # 共英製鋼
        '5463.T',  # 丸一鋼管
        '5451.T',  # 淀川製鋼所
        '5423.T',  # 東京鐵鋼
        '5471.T',  # 大同特殊鋼
        '5482.T',  # 愛知製鋼
    ],
    '非鉄金属': [
        '5713.T',  # 住友金属鉱山
        '5711.T',  # 三菱マテリアル
        '5714.T',  # DOWAホールディングス
        '5706.T',  # 三井金属鉱業
        '3436.T',  # SUMCO
        '5703.T',  # 日本軽金属HD
        '5707.T',  # 東邦亜鉛
        '5727.T',  # 東邦チタニウム
        '5016.T',  # JX金属(JX Advanced Metals) ※2024年上場
        '5802.T',  # 住友電気工業
    ],
    '電線': [
        '5802.T',  # 住友電工
        '5801.T',  # 古河電工
        '5803.T',  # フジクラ
        '5805.T',  # SWCC
        '5821.T',  # 平河ヒューテック
        '5820.T',  # 三ッ星
    ],
    '海運業': [
        '9101.T',  # 日本郵船
        '9104.T',  # 商船三井
        '9107.T',  # 川崎汽船
        '9119.T',  # 飯野海運
        '9130.T',  # 共栄タンカー
    ],
}

# 全シンボルリスト（ETF + バスケット構成銘柄 + 半導体個別株）
ALL_BASKET_SYMBOLS = list(set(s for stocks in BASKET_SECTORS.values() for s in stocks))
ALL_SYMBOLS = list(set(
    [BENCHMARK]
    + list(SECTORS.keys())
    + list(SEMICONDUCTOR_JP.keys())
    + list(SEMICONDUCTOR_US.keys())
    + list(US_SECTORS.keys())
    + ALL_BASKET_SYMBOLS
))
FETCH_DAYS = 400


def fetch_data(period="400d", interval="1d"):
    # sectors 定義はSECTORSのみ（半導体個別株は混入させない）
    sectors_def = dict(SECTORS)

    output = {
        "benchmark": BENCHMARK,
        "sectors": sectors_def,
        "semiconductor_jp": SEMICONDUCTOR_JP,
        "semiconductor_us": SEMICONDUCTOR_US,
        "us_sectors": US_SECTORS,
        "dates": [],
        "prices": {}
    }

    print(f"Fetching data (period={period}, interval={interval})...")
    print(f"  Total symbols: {len(ALL_SYMBOLS)} (ETF:{len(SECTORS)+1}, basket stocks:{len(ALL_BASKET_SYMBOLS)})")

    # 一括ダウンロード
    df = yf.download(ALL_SYMBOLS, period=period, interval=interval, auto_adjust=False, progress=False)

    if df.empty:
        print("Warning: No data fetched from Yahoo Finance.")
        return output

    if isinstance(df.columns, pd.MultiIndex):
        if 'Adj Close' in df.columns.get_level_values(0):
            df = df['Adj Close']
        elif 'Close' in df.columns.get_level_values(0):
            df = df['Close']

    # タイムゾーン除去
    df.index = pd.to_datetime(df.index).tz_localize(None)

    # 欠損値補完
    df = df.ffill().bfill()

    # ベンチマーク行のみ保持
    if BENCHMARK in df.columns:
        df = df[df[BENCHMARK].notna()]

    # ── ETFセクター・半導体銘柄価格の保存──
    etf_symbols = [BENCHMARK] + list(SECTORS.keys()) + list(SEMICONDUCTOR_JP.keys()) + list(SEMICONDUCTOR_US.keys()) + list(US_SECTORS.keys())
    for symbol in etf_symbols:
        if symbol in df.columns:
            output["prices"][symbol] = [
                round(float(x), 2) if pd.notna(x) else None for x in df[symbol].tolist()
            ]

    # ── バスケットセクター価格の計算（等加重平均）──
    print(f"  Computing {len(BASKET_SECTORS)} basket sector prices...")
    basket_ok = 0
    for basket_name, basket_symbols in BASKET_SECTORS.items():
        # 取得できた銘柄のみ抽出
        valid = [s for s in basket_symbols if s in df.columns]
        if not valid:
            print(f"    Skip '{basket_name}': no valid stocks found")
            continue

        subset = df[valid]
        first_row = subset.iloc[0]

        # 初値が0またはNaNの銘柄を除外
        valid = [s for s in valid if pd.notna(first_row[s]) and first_row[s] > 0]
        if not valid:
            print(f"    Skip '{basket_name}': all first prices are NaN/0")
            continue

        subset = df[valid]
        first_row = subset.iloc[0]

        # 各銘柄を初値=100に正規化して等加重平均
        normalized = subset.div(first_row) * 100
        basket_price = normalized.mean(axis=1)

        output["prices"][basket_name] = [
            round(float(x), 4) if pd.notna(x) else None for x in basket_price.tolist()
        ]
        output["sectors"][basket_name] = basket_name  # シンボルキー=表示名
        basket_ok += 1

    print(f"  Basket sectors computed: {basket_ok}/{len(BASKET_SECTORS)}")

    # 日付出力
    if interval == "1d":
        output["dates"] = [d.strftime('%Y-%m-%d') for d in df.index]
    else:
        output["dates"] = [d.strftime('%Y-%m-%d %H:%M') for d in df.index]

    return output


def main():
    os.makedirs('data', exist_ok=True)

    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    now_utc = datetime.now(timezone.utc)
    ts_utc = now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
    ts_jst = now_jst.strftime('%Y-%m-%d %H:%M JST')

    # 日次データ（400日）
    data_daily = fetch_data(period="400d", interval="1d")
    data_daily['generated_at'] = ts_utc
    data_daily['generated_at_jst'] = ts_jst
    with open('data/etf_data.json', 'w', encoding='utf-8') as f:
        json.dump(data_daily, f, ensure_ascii=False)

    # イントラデイ 5分足（14日）
    data_intraday = fetch_data(period="14d", interval="5m")
    data_intraday['generated_at'] = ts_utc
    data_intraday['generated_at_jst'] = ts_jst
    with open('data/etf_intraday.json', 'w', encoding='utf-8') as f:
        json.dump(data_intraday, f, ensure_ascii=False)

    print(f"Done: {len(data_daily['dates'])} days daily, {len(data_intraday['dates'])} ticks intraday.")
    print(f"Total sectors in output: {len(data_daily['sectors'])} (ETF:{len(SECTORS)}, basket:{len(BASKET_SECTORS)})")
    print(f"Generated at: {ts_jst}")


if __name__ == "__main__":
    main()
