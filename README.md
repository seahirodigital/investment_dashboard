# 統合投資ダッシュボード

日本株・ETF・オプション等を一元管理する投資分析ダッシュボードです。

---

## 📊 セクター分類分析 (`sector_category.html`) 仕様

### ページ概要

`sector_category.html` は全セクターを7つのカテゴリに分類し、それぞれ **左：パフォーマンスチャート / 右：ランキング** の2カラム構成で表示する分析ページです。
市場時間中（前場 9:00〜11:30、後場 12:30〜15:30）は **15分ごとにイントラデイデータを自動更新** します。

---

### 画面構成（上から順）

| ブロック | 説明 |
|---|---|
| **① 規模別指数（絶対値）** | TOPIX割り返しなし・期間開始基準の絶対値リターン表示。参考ライン付き |
| **② 全セクター相対パフォーマンス** | 全セクターを1チャートに表示。上位7／下位7ボタン・サマリーコピー機能あり |
| **③ TOP 7 アウトパフォーマー** | TOPIX超過リターン上位7セクターのランキングチャート |
| **④ ワースト 7** | TOPIX超過リターン下位7セクターのランキングチャート |
| **⑤ 非鉄金属・半導体・機械・建設・資材・中小型** | 資本財・素材系カテゴリ（金融の上に配置） |
| **⑥ 金融・内需系** | 不動産・銀行・保険・証券・その他金融 |
| **⑦ エネルギー・資源・素材（バリュー系）** | 電力・ガス含む。卸売業は消費へ |
| **⑧ 消費・サービス・生活** | 卸売業（商社系）含む。電力・ガスはエネルギーへ |
| **⑨ ハイテク・製造・精密** | |
| **⑩ 市場環境（絶対値）** | 日経指数・半導体ETF等 |

---

### データ種別

| 記号 | 種別 | 説明 |
|:---:|---|---|
| 📈 | **ETF** | NEXT FUNDS 等の業種別 ETF 価格を直接利用 |
| 🧺 | **バスケット** | 同一 ETF に複数業種が混在するため、時価総額上位銘柄の**等加重平均**で合成した仮想指数 |
| 📉 | **指数** | Yahoo Finance 経由の市場参照指数（^N225、先物等） |

---

## セクター分類分析（sector_category.html）カテゴリ構成

| カテゴリ | 含まれるセクター |
|---------|----------------|
| 規模別指数（絶対値） | TOPIX Core30(1311.T) / JPX400(1591.T) / グロース250(2516.T) ＋参考ライン: TOPIX・日経指数・NASDAQ先物・SP500先物・半導体ETF |
| 非鉄金属・半導体・機械・建設・資材・中小型 | 化学 / 機械 / 非鉄金属 / 半導体ETF / 金属製品 / 電線（バスケット） |
| 金融・内需系 | 保険業 / 証券業 / その他金融 / 銀行業 / 銀行 |
| 不動産・建設・インフラ | 不動産(1633.T) / 建設・資材(1619.T) / 日経指数 / 倉庫・運輸 |
| エネルギー・資源・素材（バリュー系） | 鉱業 / 電力・ガス / 石油・石炭 / 水産・農林 / その他製品 |
| 製造・精密・ハイテク | 繊維製品 / 情報通信・サービスその他 / ガラス・土石 / 電機・精密 / 輸送用機器 / ゴム製品 / 鉄鋼 |
| 消費・サービス・生活 | 小売 / 空運業 / 陸運業 / 食料品 / 医薬品 / 卸売業 / 情報・通信業 / 海運業 / GX日本成長(200A.T) / サービス業 / パルプ・紙 |

---


### バスケット計算方式

```
basket_price[t] = mean( stock_price[t] / stock_price[t0] ) × 100
```

- **正規化基準**: データ取得開始時点 (t0) の価格 = 100
- **加重方式**: 等加重平均（Equal Weight）
- **欠損処理**: 初値が NaN/0 の銘柄は自動除外
- **チャート表示（通常）**: 期間開始点を基準に再正規化し、TOPIX 超過リターンとして描画
- **チャート表示（規模別指数）**: TOPIXで割り返さず、期間開始点を0%基準とした絶対値リターンで描画

---

## 🕐 データ更新スケジュール

### 更新タイミング一覧

| ページ | データファイル | GitHub Actions 実行（JST） | 更新頻度 | ワークフロー |
|---|---|---|---|---|
| 手口データ分析（`teguchi.html`） | `data/teguchi.json` | **毎日 20:05** | 毎営業日 ※1 | `daily_participant.yml` |
| 日経225建玉・オプション（`option.html`） | `data/option_history.json` | **毎日 20:05** | 毎営業日 ※2 | `daily_participant.yml` |
| セクター分析・分類分析（`etf.html`, `sector_category.html`） | `data/etf_data.json`<br>`data/etf_intraday_data.json` | **毎日 16:00** | 毎日 | `daily_etf.yml` |
| セクター感応度（`analytics.html`） | `data/sector_data.json` | **毎週木曜 18:00** | 週1回 | `daily_task.yml` |
| GPIF分析 | `data/gpif_data.json` | **毎週木曜 18:00** | 週1回 | `daily_task.yml` |

### ⚠️ 重要：「古いデータ」に見える理由と JPX の公開タイミング

#### ※1 手口データ（`teguchi.html`）— **JPXは翌営業日の10:30頃に公開**

| 確認タイミング | 画面に表示される最新日付 | 理由 |
|---|---|---|
| 月曜〜金曜 20:05以降 | **前営業日**分 | JPXは当日分を翌営業日10:30頃に公開するため |
| 土曜・日曜・祝日 | 直前の金曜分 | 週末・祝日はJPXがデータを公開しない |

> **例（実際に発生した状況）**: 3/16（月）22:33 に確認 → 表示は 3/13（金）分
> - 3/16（月）のワークフローは 20:05 に実行済み
> - この時点でJPXから取得できる最新は「3/13（金）分」のみ（3/16分はJPXが3/17に公開予定）
> - → **正常動作。バグではない。**
> - 次の更新（3/16分）は 3/17（火）の 20:05 頃。

#### ※2 オプション建玉（`option.html`）— **JPXは当日取引終了後（16:30〜17:30頃）に公開**

| 確認タイミング | 画面に表示される最新日付 |
|---|---|
| 平日 20:05 以降 | **当日**分（ワークフロー実行時に取得済み） |
| 土曜・日曜・祝日 | 直前の金曜分 |

### セクター分析の自動リフレッシュ

`sector_category.html`（セクター分類分析）は、**市場時間中に15分ごと自動更新**されます。

| セッション | 時間帯 | 動作 |
|---|---|---|
| 前場 | 09:00〜11:30 | 15分ごとにデータ自動取得・描画更新 |
| 後場 | 12:30〜15:30 | 15分ごとにデータ自動取得・描画更新 |
| 時間外 | 上記以外 | 自動取得なし（手動リロードのみ） |

---

## 🔄 データフロー

### 全体フロー図

```
[Yahoo Finance / JPX]
        │
        ├─ yfinance API ──────────────────────────────────────────────────┐
        │   (ETF価格・バスケット銘柄・GPIF構成資産)                        │
        │                                                                  ▼
        │                                               scripts/market/etf_data_manager.py
        │                                               scripts/market/fetch_gpif_data.py
        │                                                        │
        │                                               data/etf_data.json
        │                                               data/etf_intraday_data.json
        │                                               data/gpif_data.json
        │
        └─ JPX スクレイピング ────────────────────────────────────────────┐
            (手口データ・オプション建玉・JPX 履歴)                         │
                                                                          ▼
                                                       scripts/jpx/fetch_teguchi.py
                                                       scripts/jpx/fetch_option.py
                                                       main.py + sector_manager.py
                                                                │
                                                       data/teguchi.json
                                                       data/option_history.json
                                                       data/sector_data.json
                                                       history.csv
```

### GitHub Actions → GitHub Pages デプロイフロー

```
[GitHub Actions]
        │
        ├─ daily_etf.yml (毎日 JST 16:00)
        │   └─ etf_data_manager.py 実行
        │       → data/etf_data.json, data/etf_intraday_data.json 更新
        │       → main ブランチにコミット・プッシュ
        │       → gh-pages にデプロイ（HTML + data フォルダ）
        │
        ├─ daily_participant.yml (毎日 JST 20:05)
        │   └─ fetch_teguchi.py, fetch_option.py 実行
        │       → data/teguchi.json, data/option_history.json 更新
        │       → main ブランチにコミット・プッシュ
        │       → gh-pages にデプロイ（HTML + data フォルダ）
        │
        ├─ daily_task.yml (毎週木曜 JST 18:00 + main push 時)
        │   └─ main.py, sector_manager.py, fetch_gpif_data.py 実行
        │       → data/sector_data.json, data/gpif_data.json 更新
        │       → GPIF React アプリをビルド (npm run build)
        │       → main ブランチにコミット・プッシュ
        │       → gh-pages にデプロイ（HTML + data + GPIF/dist フォルダ）
        │
        └─ intraday_etf.yml (市場時間中 15分ごと)
            └─ ETF イントラデイデータ取得
                → data/etf_intraday_data.json 更新
                → gh-pages ブランチに直接プッシュ（main をバイパス）
```

### データファイルと参照元の対応

| データファイル | 生成スクリプト | 参照 HTML | 更新頻度 |
|---|---|---|---|
| `data/etf_data.json` | `etf_data_manager.py` | `etf.html`, `sector_category.html` | 毎日 |
| `data/etf_intraday_data.json` | `etf_data_manager.py` | `sector_category.html` | 毎日 + イントラデイ |
| `data/sector_data.json` | `sector_manager.py` | `analytics.html` | 週1回 |
| `data/teguchi.json` | `fetch_teguchi.py` | `teguchi.html` | 毎営業日 |
| `data/option_history.json` | `fetch_option.py` | `option.html` | 毎営業日 |
| `data/gpif_data.json` | `fetch_gpif_data.py` | `GPIF/dist/index.html` | 週1回 |

---

## 📁 ファイル構成

```
investment_dasboard/
│
├── index.html                          # メインダッシュボード（サイドバー統合ナビ）
├── etf.html                            # セクター分析（全セクター単一チャート）
├── sector_category.html                # セクター分類分析（7カテゴリ × チャート+ランキング）
├── analytics.html                      # セクター別感応度分析
├── option.html                         # オプション建玉監視（日経225・TOPIX）
├── teguchi.html                        # 手口データ分析（売買参加者別）
├── advanced.html                       # 詳細分析
├── history.csv                         # JPX 履歴データ（main.py 生成）
├── sector_data.json                    # セクター集計データ（ルート直置き・旧形式）
├── sectors.json                        # セクター定義（旧形式）
├── requirements.txt                    # Python 依存パッケージ
├── design_reference.md                 # UIデザイン参考資料
├── trend.png                           # トレンド画像
│
├── main.py                             # エントリーポイント（旧スクリプト）
├── sector_manager.py                   # セクター管理（旧スクリプト）
│
├── data/                               # 自動生成データ（GitHub Actions）
│   ├── etf_data.json                   # ETF・バスケット 日次データ（daily_etf.yml）
│   ├── etf_intraday_data.json          # ETF・バスケット 5分足イントラデイ（daily_etf.yml）
│   ├── sector_data.json                # セクター集計データ（daily_task.yml）
│   ├── option_history.json             # オプション建玉履歴（daily_participant.yml）
│   ├── teguchi.json                    # 手口データ（売買参加者別）（daily_participant.yml）
│   ├── daily_participant.json          # 日次参加者データ
│   └── gpif_data.json                  # GPIF 運用資産データ（daily_task.yml）
│
├── scripts/
│   ├── market/
│   │   ├── etf_data_manager.py         # ETF・バスケット データ取得（本ドキュメント対応）
│   │   └── fetch_gpif_data.py          # GPIF データ取得
│   └── jpx/
│       ├── fetch_option.py             # オプション建玉データ取得（JPX スクレイピング）
│       └── fetch_teguchi.py            # 手口データ取得（JPX API + Excel 解析）
│
├── docs/                               # ドキュメント類（gitignore済み・ローカル参照用）
│
├── GPIF/                               # GPIF 分析サブアプリ（Node.js）
│   ├── index.html                      # GPIF ダッシュボード
│   ├── package.json
│   └── metadata.json
│
├── JPEG/                               # スクリーンショット等の画像
│
└── .github/
    └── workflows/
        ├── daily_task.yml              # 週次総合タスク（毎週木曜 JST 18:00）※セクター・GPIF
        ├── daily_etf.yml               # 日次 ETF・バスケットデータ取得（毎日 JST 16:00）
        ├── intraday_etf.yml            # イントラデイ ETF データ取得（市場時間中 15分ごと）
        └── daily_participant.yml       # 日次 手口・建玉データ取得（毎日 JST 20:05）
```

---

## 🔧 セットアップ

```bash
pip install yfinance pandas
python scripts/market/etf_data_manager.py
```

## ⚠️ 免責事項

- このツールは情報提供を目的としており、投資判断の根拠とするものではありません
- データの正確性については保証しません
- 投資は自己責任で行ってください
