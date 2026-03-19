# 統合投資ダッシュボード

日本株・ETF・オプション等を一元管理する投資分析ダッシュボードです。

---

## ⚠️ 過去トラブルから得た教訓（最重要）

### GitHub Pages CDN の仕様と落とし穴

1. **CDNはgh-pagesブランチから直接配信しない**
   - peaceirisがgh-pagesにpush → `pages-build-deployment`が内部でビルド → CDNに反映
   - gh-pagesブランチにファイルが存在しても、CDNが配信するとは限らない
   - `keep_files: true`でgh-pagesコミットに含まれていても、CDNが404を返すケースがある

2. **CDNは404をキャッシュする**
   - 一度404になったパスは、ファイルが追加されてもしばらく404を返し続ける
   - ファイル名を変更すれば即座にキャッシュをバイパスできる
   - 例: `etf_intraday_data.json` → `etf_intraday.json` で解決

3. **CDNに確実にファイルを配信させる方法**
   - **mainブランチにファイルをコミットし、peaceirisのdeploy/に含める**のが最も確実
   - gh-pagesへの直接git pushは信頼性が低い（CDNに反映されない場合がある）
   - `keep_files: true`でのファイル保持も信頼性が低い

4. **GITHUB_TOKEN と pages-build-deployment の関係**
   - 「GITHUB_TOKENではpages-build-deploymentがトリガーされない」という情報は**誤り**
   - GitHubの「GITHUB_TOKENで後続ワークフローが発火しない」制約は**ユーザー定義ワークフロー**に対するもの
   - `pages-build-deployment`はGitHub内部のPages配信プロセスであり、GITHUB_TOKENのpushで**正常に発火する**
   - 実証: このリポジトリの daily_participant.yml / daily_task.yml はGITHUB_TOKEN + peaceirisで正常にCDN更新している

### peaceiris/actions-gh-pages の注意点

1. **`keep_files: true` は万能ではない**
   - deploy/に含まれないファイルはgh-pagesブランチのコミットには残る
   - しかしCDN（pages-build-deployment）がそのファイルを配信する保証がない
   - **結論: deploy/に含めないファイルはCDNで404になるリスクがある**

2. **peaceirisデプロイがイントラデイデータを上書きする問題**
   - mainブランチに古いデータがコミットされていると、peaceirisがそれをdeploy/に含めてデプロイ
   - gh-pagesにある新しいデータが古いデータで上書きされる
   - **解決策: intraday_etf.ymlがmainに直接commit&pushし、他ワークフローはそれを引き継ぐ**

### GitHub Actions cron の信頼性問題と解決策

- 15分間隔のcronスケジュールは**全ての実行が保証されない**
- 実測: 3.5時間で28回中6回しか実行されなかった（実行率 約21%）
- **根本解決: ループ型ワークフローを採用**（後述）
  - cronは「セッション起動」のみに使用（1日2回 × バックアップ3本 = 6回）
  - 起動後はワークフロー内部で `sleep 900`（15分）のループ → 100%確実に実行
  - GitHub cronの不安定さに一切依存しない設計

### フロントエンド toJST の仕様（重要：変更するな）

- yfinanceは複数市場のデータをマージする際に**UTCに統一**し、`tz_localize(None)`でラベルだけ除去
- したがってデータのタイムスタンプは**UTC**（例: 05:40 = JST 14:40）
- `toJST()`の+9h変換は**正しい**。これを除去するとrangebreaksで全データが非表示になる
- **「データがJSTだから二重加算」という分析は誤り** — 実データのログ（最後: 05:40 = 市場中14:40 JST）がUTCであることを証明

### intraday_etf.yml でのブランチ切り替えエラー

- `fetch_intraday.py`が`data/etf_intraday.json`を生成 → `git checkout gh-pages`で未コミット変更エラー
- 原因: 作業ディレクトリに生成されたファイルがcheckoutを阻害
- 解決策: gh-pagesへの直接pushをやめ、mainにcommit&pushする方式に変更

### フロントエンド Script Error

- タブ復帰時（visibilitychange）にCDN由来のReact/Babelスクリプトでクロスオリジンエラー発生
- `window.onerror`で `message === 'Script error.'` をフィルタリングして対処
- fetchの重複呼び出し防止に`fetchingRef`フラグを使用

---

## GitHub Actions ワークフロー設計（現行版 2026-03-19）

### ワークフロー一覧

| ファイル | 名前 | 実行タイミング | デプロイ方式 |
|---|---|---|---|
| `intraday_etf.yml` | イントラデイETF更新 | 市場時間中 **15分ごとループ** | mainにcommit + gh-pagesに直接push |
| `daily_etf.yml` | 日次ETFデータ取得 | **毎日 JST 16:00** | peaceiris（keep_files: true） |
| `daily_participant.yml` | 手口・オプション取得 | **毎日 JST 20:05** | peaceiris（keep_files: true） |
| `daily_task.yml` | JPX週次 + フルデプロイ | **毎週木曜 JST 18:00** + HTML/yml変更時 | peaceiris（keep_files: true） |

### 各ワークフロー詳細

#### `intraday_etf.yml` — ループ型15分間隔更新

```
方式: セッション起動型ループ（GitHub cronの不安定さを完全回避）

cron起動（1日6本、うち発火すればOK）:
  前場: UTC 0:00 / 0:15 / 0:30（JST 9:00 / 9:15 / 9:30）
  後場: UTC 3:30 / 3:45 / 4:00（JST 12:30 / 12:45 / 13:00）
  手動: workflow_dispatch

concurrency: intraday-etf-update（cancel-in-progress: false）
  → バックアップcronが発火してもキューに入り重複しない
  → 先行ジョブ終了後に開始し、市場時間外なら即終了

ワークフロー内部ループ（起動後）:
  while 市場時間内:
    1. fetch_intraday.py（5分足 14日分、yfinance、リトライ付き）
    2. mainブランチにコミット&プッシュ
    3. gh-pagesブランチに直接git push（CDN即時更新）
    4. sleep 900（15分）

  市場時間判定:
    前場: JST 9:00〜11:30
    昼休み: JST 11:30〜12:30（5分ごとにチェック、スキップ）
    後場: JST 12:30〜15:45
    15:45以降: ループ終了

  6時間制限の回避:
    前場セッション = 最大2.5時間（余裕）
    後場セッション = 最大3.25時間（余裕）
    GitHub-hosted runnerの6時間ハードリミットに抵触しない

信頼性:
  - cronは「起動」のみ → 各セッション3本のうち1本でも発火すればOK
  - ループ内のsleep 900はOSレベル → 100%正確に15分後に再開
  - 1日あたり約27回のデータ更新＋CDNデプロイを確実に実行
```

#### `daily_etf.yml` — 毎日 JST 16:00（市場閉場後）

```
トリガー: cron '0 7 * * *'  (UTC 07:00 = JST 16:00)
         workflow_dispatch（手動）

処理:
  1. etf_data_manager.py を実行
     → data/etf_data.json    （日次 400日分）
     → data/etf_intraday.json （5分足 14日分、当日全データ確定版）
  2. 変更があれば mainブランチにコミット&プッシュ

デプロイ: peaceiris（keep_files: true）
  deploy/ にHTML + css/ + js/ + data/ をコピーして全デプロイ
```

#### `daily_participant.yml` — 毎日 JST 20:05

```
トリガー: cron '5 11 * * *'  (UTC 11:05 = JST 20:05)
         workflow_dispatch（手動）

処理:
  1. fetch_teguchi.py  → data/teguchi.json
  2. fetch_option.py   → data/option_history.json
  3. 変更があれば mainブランチにコミット&プッシュ

デプロイ: peaceiris（keep_files: true）
  deploy/ にHTML + css/ + js/ + data/ をコピーして全デプロイ
```

#### `daily_task.yml` — 週次JPX + フルデプロイ

```
トリガー: cron '0 9 * * 4'  (毎週木曜 JST 18:00)
         workflow_dispatch（手動）
         push to main（pathsフィルター付き）
           対象: *.html / css/** / js/** / .github/workflows/**
           ※ data/ のみの変更コミットでは実行されない

処理:
  1. main.py           → history.csv（JPX 履歴データ）
  2. sector_manager.py → sector_data.json
  3. fetch_gpif_data.py → data/gpif_data.json
  4. 変更があれば mainブランチにコミット&プッシュ
  5. GPIF React アプリをビルド（npm run build）

デプロイ: peaceiris（keep_files: true）
  deploy/ にHTML + css/ + js/ + data/ + GPIF/dist をコピーして全デプロイ
```

---

### データ更新の流れ（イントラデイ）

```
[市場時間中の更新フロー — ループ型]

  cron起動（前場/後場の開始時に1回）
       │
       ▼
  ワークフロー内部ループ開始
       │
       ├──→ fetch_intraday.py
       │    （yfinance → 5分足14日分取得 → data/etf_intraday.json生成）
       │         │
       │         ▼
       │    mainブランチにcommit & push
       │         │
       │         ▼
       │    gh-pagesブランチに直接git push → CDN即時更新
       │         │
       │         ▼
       │    sleep 900（15分待機）
       │         │
       └─────────┘（ループ）

  15:45 JST → ループ終了

[フロントエンド側]
  5分ごとに自動fetch → CDNから最新データ取得 → チャート更新
```

**重要:** ループ型ではgh-pagesへの直接git pushでCDN更新するため、
peaceirisやdaily_*ワークフローの実行を待つ必要がない。
市場時間中は15分ごとに確実にCDNが更新される。

---

## データファイル一覧

| ファイル | 生成スクリプト | 参照HTML | 更新頻度 |
|---|---|---|---|
| `data/etf_data.json` | `etf_data_manager.py` | `etf.html`, `sector_category.html` | 毎日 JST 16:00 |
| `data/etf_intraday.json` | `fetch_intraday.py` / `etf_data_manager.py` | `sector_category.html` | 市場中15分ごと + 毎日 JST 16:00 |
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
タブ復帰時          → fetchRawData()（500msデバウンス付き）
「更新」ボタン      → fetchRawData() 即時実行

fetchRawData():
  - Cache-Control: no-cache + クエリ文字列タイムスタンプでキャッシュ回避
  - etf_data.json と etf_intraday.json を並列取得
  - 重複呼び出し防止（fetchingRef フラグ）
  - intraday 取得失敗時は日次データにフォールバック（チャートは継続表示）
  - 既存データがある場合、更新失敗時もエラー表示せず前回データを維持
```

### タイムスタンプの扱い（重要：変更するな）

```
yfinance → 複数市場マージ時にUTC統一 → tz_localize(None) → UTCタイムスタンプ（ラベルなし）
  例: "2026-03-19 05:40" = UTC 05:40 = JST 14:40

フロントエンド toJST():
  ✅ 正しい実装: UTC文字列として解析し +9h → JST表示
  ❌ 誤った「修正」: +9h除去 → UTC時刻のままrangebreaksで全消滅
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
| 市場中 毎15分（JST 9:00〜15:45） | `fetch_intraday.py`（ループ型） | mainコミット + gh-pages直接push → CDN即時更新 |
| 毎日 JST 16:00 | `etf_data_manager.py` | 日次+イントラデイ両方再生成 → peaceirisでCDNデプロイ |
| 毎日 JST 20:05 | `fetch_teguchi.py` + `fetch_option.py` | 手口・建玉 → peaceirisでCDNデプロイ |
| 毎週木曜 JST 18:00 | JPX週次 + GPIF + フルデプロイ | → peaceirisでCDNデプロイ |
| HTML/yml変更プッシュ時 | daily_task.yml | → peaceirisでCDNデプロイ |

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
│   ├── etf_intraday.json              # ETF・バスケット 5分足（intraday_etf.yml / daily_etf.yml）
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
    ├── intraday_etf.yml                # ループ型15分間隔更新（main + gh-pages直接push）
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
