# 統合投資ダッシュボード

日本株・ETF・オプション等を一元管理する投資分析ダッシュボードです。

---

## GitHub Actions ワークフロー全体設計

### ワークフロー一覧

| ファイル | 名前 | 実行タイミング |
|---|---|---|
| `intraday_etf.yml` | イントラデイETF更新 | 市場時間中 **15分ごと**（JST 9:00〜15:45 平日） |
| `daily_etf.yml` | 日次ETFデータ取得 | **毎日 JST 16:00** |
| `daily_participant.yml` | 手口・オプション取得 | **毎日 JST 20:05** |
| `daily_task.yml` | JPX週次 + フルデプロイ | **毎週木曜 JST 18:00** + HTMLやワークフロー変更時のmainプッシュ |

---

### 各ワークフローの詳細

#### `intraday_etf.yml` — 市場時間中 15分ごと

```
トリガー: cron '0,15,30,45 0-6 * * 1-5'  (UTC 0:00〜6:45 = JST 9:00〜15:45)
         workflow_dispatch（手動）

処理:
  1. fetch_intraday.py を実行（5分足 14日分、yfinance取得、最大3回リトライ）
     → data/etf_intraday_data.json 生成（generated_at タイムスタンプ付き）

デプロイ方式: peaceirisを使わず、git コマンドで gh-pages に直接プッシュ
  git fetch origin gh-pages
  git checkout -B gh-pages origin/gh-pages
  # data/etf_intraday_data.json のみ上書きしてコミット・プッシュ
  git push --force-with-lease origin gh-pages
  # 失敗時はリフェッチ後に --force でリトライ

更新対象: gh-pages の data/etf_intraday_data.json のみ（サイト全体は触らない）
concurrency: intraday-etf-update グループで同時実行1つに制限（cancel-in-progress）
```

#### `daily_etf.yml` — 毎日 JST 16:00

```
トリガー: cron '0 7 * * *'  (UTC 07:00 = JST 16:00)
         workflow_dispatch（手動）

処理:
  1. etf_data_manager.py を実行
     → data/etf_data.json    （日次 400日分）生成
     → data/etf_intraday_data.json （5分足 14日分）生成
     ※ どちらも generated_at タイムスタンプ付き
  2. 変更があれば main ブランチにコミット・プッシュ

デプロイ方式: peaceiris/actions-gh-pages（keep_files: false → gh-pages 全面上書き）
  deploy/ に以下をコピーして全デプロイ:
    - HTML ファイル群
    - css/, js/, data/ フォルダ
    - gh-pages から GPIF/dist を取得して保持（ビルド済み静的ファイル）
```

#### `daily_participant.yml` — 毎日 JST 20:05

```
トリガー: cron '5 11 * * *'  (UTC 11:05 = JST 20:05)
         workflow_dispatch（手動）

処理:
  1. fetch_teguchi.py  → data/teguchi.json 生成（JPX スクレイピング）
  2. fetch_option.py   → data/option_history.json 生成（JPX スクレイピング）
  3. 変更があれば main ブランチにコミット・プッシュ

デプロイ方式: peaceiris/actions-gh-pages（keep_files: false → gh-pages 全面上書き）
  deploy/ に以下をコピーして全デプロイ:
    - HTML ファイル群
    - css/, js/, data/ フォルダ
    - gh-pages の最新 etf_intraday_data.json を取得して上書き保持
      （main ブランチの古いデータより gh-pages の直接プッシュ版を優先）
    - gh-pages から GPIF/dist を取得して保持
```

#### `daily_task.yml` — 週次JPX + フルデプロイ

```
トリガー: cron '0 9 * * 4'  (UTC 09:00 木曜 = JST 18:00)
         workflow_dispatch（手動）
         push to main（pathsフィルター付き）
           対象パス: *.html / css/** / js/** / .github/workflows/**
           ※ データファイルのみの更新コミットでは実行されない

処理:
  1. main.py           → history.csv 生成（JPX 履歴データ）
  2. sector_manager.py → sector_data.json 生成（セクター集計）
  3. fetch_gpif_data.py → data/gpif_data.json 生成
  4. 変更があれば main ブランチにコミット・プッシュ
  5. GPIF React アプリをビルド（cd GPIF && npm run build）
  6. [デプロイ直前] ETFデータを最新取得:
       fetch_intraday.py  → data/etf_intraday_data.json を最新化
       etf_data_manager.py → data/etf_data.json を最新化
       （失敗しても後続のデプロイは継続）

デプロイ方式: peaceiris/actions-gh-pages（keep_files: false → gh-pages 全面上書き）
  deploy/ に以下をコピーして全デプロイ:
    - HTML ファイル群
    - css/, js/, data/ フォルダ（上記6で最新化済みのETFデータ含む）
    - GPIF/dist（ビルド済み）
    - ビルド失敗時は gh-pages から GPIF/dist を取得してフォールバック
```

---

### gh-pages デプロイ設計

#### peaceiris の `keep_files: true` 方式

全ワークフローで `peaceiris/actions-gh-pages` に `keep_files: true` を設定。
これにより、deploy/ ディレクトリのファイルで gh-pages を**マージ更新**する（既存ファイルは削除されない）。

```
[動作イメージ]
gh-pages（既存）:
  data/etf_intraday_data.json  ← intraday_etf.yml が直接プッシュ済み
  GPIF/dist/index.html          ← daily_task.yml でビルド済み

peaceiris（keep_files: true）で deploy/ をマージ:
  data/etf_data.json            ← 更新
  data/teguchi.json             ← 更新
  sector_category.html          ← 更新
  data/etf_intraday_data.json   ← 既存のまま保持（deploy/ に含まなければ上書きされない）
  GPIF/dist/index.html          ← 既存のまま保持
```

#### 共存ルール

| ワークフロー | デプロイ方式 | 競合リスク |
|---|---|---|
| `intraday_etf.yml` | gh-pages に直接 git push（1ファイルのみ） | なし（keep_files: true で保持される） |
| `daily_etf.yml` | peaceiris（keep_files: true） | なし（data/ を上書き更新、他は保持） |
| `daily_participant.yml` | peaceiris（keep_files: true） | なし（data/ を上書き更新、他は保持） |
| `daily_task.yml` | peaceiris（keep_files: true） | なし（全ファイル更新、ETFも最新取得済み） |

---

### データフロー全体図

```
[Yahoo Finance / JPX]
        │
        ├─ yfinance API（ETF・バスケット銘柄・市場指数）
        │      │
        │      ├─ etf_data_manager.py  →  data/etf_data.json（日次 400日）
        │      │                           data/etf_intraday_data.json（5分足 14日）
        │      │
        │      └─ fetch_gpif_data.py   →  data/gpif_data.json
        │
        └─ JPX スクレイピング（手口・オプション・週次履歴）
               │
               ├─ fetch_teguchi.py     →  data/teguchi.json
               ├─ fetch_option.py      →  data/option_history.json
               └─ main.py + sector_manager.py → history.csv, sector_data.json

[GitHub Actions]
        │
        ├─ intraday_etf.yml  （15分ごと）
        │    └─ fetch_intraday.py → etf_intraday_data.json → gh-pages に直接プッシュ
        │
        ├─ daily_etf.yml    （毎日 JST 16:00）
        │    └─ etf_data_manager.py → etf_data.json + etf_intraday_data.json
        │         → main コミット → peaceiris で gh-pages 全面デプロイ
        │
        ├─ daily_participant.yml  （毎日 JST 20:05）
        │    └─ fetch_teguchi.py + fetch_option.py
        │         → main コミット → peaceiris で gh-pages 全面デプロイ
        │           （デプロイ時に gh-pages 最新 intraday を取得・保持）
        │
        └─ daily_task.yml  （毎週木曜 JST 18:00 + HTML/yml 変更時）
             └─ main.py + sector_manager.py + fetch_gpif_data.py
                  → main コミット → GPIF npm build
                  → fetch_intraday.py + etf_data_manager.py（ETF最新化）
                  → peaceiris で gh-pages 全面デプロイ

[GitHub Pages]
        └─ gh-pages ブランチ → seahirodigital.github.io/investment_dashboard/
```

---

## データファイル一覧

| ファイル | 生成スクリプト | 参照HTML | 更新頻度 |
|---|---|---|---|
| `data/etf_data.json` | `etf_data_manager.py` | `etf.html`, `sector_category.html` | 毎日 JST 16:00 |
| `data/etf_intraday_data.json` | `fetch_intraday.py` / `etf_data_manager.py` | `sector_category.html` | 市場中15分ごと + 毎日 JST 16:00 |
| `data/sector_data.json` | `sector_manager.py` | `analytics.html` | 週1回（木曜） |
| `data/teguchi.json` | `fetch_teguchi.py` | `teguchi.html` | 毎営業日 JST 20:05 |
| `data/option_history.json` | `fetch_option.py` | `option.html` | 毎営業日 JST 20:05 |
| `data/gpif_data.json` | `fetch_gpif_data.py` | `GPIF/dist/index.html` | 週1回（木曜） |

---

## セクター分類分析 (`sector_category.html`) 仕様

### ページ概要

全セクターを7カテゴリに分類し、**左：パフォーマンスチャート / 右：ランキング** の2カラム構成で表示。
市場時間中（前場 9:00〜11:30、後場 12:30〜15:30）は **5分ごとにブラウザ側でデータ取得・自動更新**する。
タブ復帰時にも即時更新（デバウンス500ms付き）。

### フロントエンドのデータ取得ロジック

```
初回ロード          → fetchRawData() 実行
5分ごと（市場中）   → 自動 fetchRawData()
30分ごと（市場外）  → 自動 fetchRawData()（先物・海外データ更新確認用）
タブ復帰時          → fetchRawData()（500msデバウンス付き）
「更新」ボタン      → fetchRawData() 即時実行

fetchRawData():
  - Cache-Control: no-cache + クエリ文字列タイムスタンプでキャッシュ回避
  - etf_data.json と etf_intraday_data.json を並列取得
  - 重複呼び出し防止（fetchingRef フラグ）
  - intraday 取得失敗時は日次データにフォールバック（チャートは継続表示）
  - 既存データがある場合、更新失敗時もエラー表示せず前回データを維持
```

### イントラデイデータ判定条件

```javascript
// dates 配列の先頭に時刻（スペース）が含まれる = 5分足データ
const intradayAvailable = rawIntraday?.dates?.length > 1
    && rawIntraday.dates[0].includes(' ');
```

5分足データが未取得の場合、日次データで代替表示し、ヘッダーに「[日次のみ]」を表示する。

### データのフレッシュネス表示

ヘッダーにデータ生成時刻と経過分数を表示。
市場時間中で20分以上古い場合はアンバー色で警告。

### 画面構成（上から順）

| ブロック | 説明 |
|---|---|
| **① 規模別指数（絶対値）** | TOPIX割り返しなし・期間開始基準の絶対値リターン |
| **② 全セクター相対パフォーマンス** | 全セクターを1チャートに表示。上位7／下位7・サマリーコピー機能 |
| **③ TOP 7 アウトパフォーマー** | TOPIX超過リターン上位7セクター |
| **④ ワースト 7** | TOPIX超過リターン下位7セクター |
| **⑤〜⑩** | カテゴリ別チャート（非鉄・半導体・機械 / 金融・内需 / 不動産・建設 / エネルギー・資源 / 製造・精密 / 消費・サービス） |

---

## 更新スケジュール（まとめ）

| タイミング | 実行内容 | 結果 |
|---|---|---|
| 市場中 毎15分（JST 9:00〜15:45） | `fetch_intraday.py` | gh-pages の etf_intraday_data.json のみ直接更新 |
| 毎日 JST 16:00 | `etf_data_manager.py` | 日次+イントラデイ両方再生成 → gh-pages 全面デプロイ |
| 毎日 JST 20:05 | `fetch_teguchi.py` + `fetch_option.py` | 手口・建玉 → gh-pages 全面デプロイ |
| 毎週木曜 JST 18:00 | JPX週次 + GPIF + ETF最新化 | → gh-pages 全面デプロイ |
| HTML/yml変更プッシュ時 | 同上（daily_task.yml） | → gh-pages 全面デプロイ（ETFデータも最新化） |

### ⚠️ 手口データの「古く見える」理由

JPXは**当日分の手口データを翌営業日 10:30頃に公開**するため、毎日 JST 20:05 に取得できる最新データは「前営業日分」になる。

---

## バスケット計算方式

```
basket_price[t] = mean( stock_price[t] / stock_price[t0] ) × 100
```

- 正規化基準: データ取得開始時点 (t0) の価格 = 100
- 加重方式: 等加重平均（Equal Weight）
- 欠損処理: 初値が NaN/0 の銘柄は自動除外

---

## ファイル構成

```
investment_dasboard/
│
├── index.html                          # メインダッシュボード（サイドバーナビ）
├── etf.html                            # セクター分析（全セクター単一チャート）
├── sector_category.html                # セクター分類分析（7カテゴリ × チャート+ランキング）
├── analytics.html                      # セクター別感応度分析
├── option.html                         # オプション建玉監視
├── teguchi.html                        # 手口データ分析
├── advanced.html                       # 詳細分析
│
├── main.py                             # JPX 履歴取得
├── sector_manager.py                   # セクター集計
├── requirements.txt
│
├── data/
│   ├── etf_data.json                   # ETF・バスケット 日次（daily_etf.yml）
│   ├── etf_intraday_data.json          # ETF・バスケット 5分足（intraday_etf.yml / daily_etf.yml）
│   ├── sector_data.json                # セクター集計（daily_task.yml）
│   ├── option_history.json             # オプション建玉（daily_participant.yml）
│   ├── teguchi.json                    # 手口データ（daily_participant.yml）
│   ├── daily_participant.json          # 日次参加者データ
│   └── gpif_data.json                  # GPIF 運用資産（daily_task.yml）
│
├── scripts/
│   ├── market/
│   │   ├── etf_data_manager.py         # ETF・バスケット データ取得
│   │   ├── fetch_intraday.py           # イントラデイ専用取得（リトライ付き）
│   │   └── fetch_gpif_data.py          # GPIF データ取得
│   └── jpx/
│       ├── fetch_option.py             # オプション建玉（JPX スクレイピング）
│       └── fetch_teguchi.py            # 手口データ（JPX API）
│
├── GPIF/                               # GPIF 分析 React サブアプリ
│   ├── package.json
│   └── dist/                           # npm run build 生成物（gh-pages に保持）
│
└── .github/workflows/
    ├── intraday_etf.yml                # 15分ごとイントラデイ更新
    ├── daily_etf.yml                   # 毎日 JST 16:00 ETFデータ
    ├── daily_participant.yml           # 毎日 JST 20:05 手口・オプション
    └── daily_task.yml                  # 週次 + HTML変更時フルデプロイ
```

---

## セットアップ

```bash
pip install yfinance pandas pytz
python scripts/market/etf_data_manager.py
```

## ⚠️ 免責事項

- このツールは情報提供を目的としており、投資判断の根拠とするものではありません
- データの正確性については保証しません
- 投資は自己責任で行ってください
