# 統合投資ダッシュボード

日本株・ETF・オプション等を一元管理する投資分析ダッシュボードです。

---

## 📋 最新の大型アップデート (2026-03-25)

### 新規実装：TOPIX100分析 ＆ 売買フロー底打ち検知
**実績:** 
- **TOPIX100分析** (`topix100.html`): TOPIX Core30 + Large70 の全98銘柄のパフォーマンスを絶対値ベースで比較（日経指数等の参照ライン付き）する専用ダッシュボード構築。
- **売買フロー底打ち検知** (`short_selling.html`): 東証の日次「空売り集計」から、①売買代金の急膨張(パニック売り) ②空売り比率ピークアウト(ショートカバー)の2つのシグナルを検知し、相場の底打ち(Phase 3)を判定するアルゴリズムを実装。

---

## 📋 過去（2026-03-19）の実装履歴＆解決済み課題

### 最終達成：15分ごと確実なデータ更新＆CDN配信

**実績:** GitHub Actions cron不安定性（実行率21%）を完全克服
**方式:** ループ型ワークフロー（前場/後場セッション分割）
**結果:** 15分ごとに確実にデータ取得→main commit→CDNデプロイが自動実行

---

## 🔧 検討した対策オプション＆判定

| # | 対策案 | 信頼性 | GitHub完結 | 実装難度 | 結果 |
|---|------|--------|-----------|---------|------|
| **A** | 現状: 15分cronを28回/日で打つ | ❌ 21% | ✅ | - | **採用せず** — GitHub cronの21%発火率では市場中のリアルタイム性が失われる |
| **B** | **ループ型（前場/後場セッション分割）** | ✅ 99% | ✅ | 中 | **✨採用&実装** — 1日2回×バックアップ3本で起動確実性↑、内部sleep 900で100%正確な15分間隔 |
| **C** | 外部cronサービス→workflow_dispatch | ✅ 100% | ❌ | 中 | **却下** — ユーザーが「GitHubで完結させろ」と指示したため外部依存は不可 |
| **D** | 自己チェーン（workflow_dispatch連鎖） | ⚠️ 95% | △ | 中 | **却下** — GITHUB_TOKENでは自己トリガー不可、PAT必須（外部依存同然） |
| **E** | Pages sourceをmainに変更 | - | ✅ | 低 | **却下** — GPIF等のビルド成果物・gh-pages既存ファイル管理が破綻 |
| **F** | 頻度を下げる（30分/1時間） | ⚠️ 40-60% | ✅ | 低 | **却下** — 根本解決にならず、UX劣化 |

### 採用したB案（ループ型）の成功実績

```
2026-03-19 06:00 UTC ← cron起動（前場開始）
2026-03-19 06:15 UTC ← sleep完明け → データ取得→commit→CDNデプロイ
2026-03-19 06:31 UTC ← sleep完明け → データ取得→commit→CDNデプロイ
...（以降15分ごと）
2026-03-19 06:45 UTC ← 次のループサイクル
```

**実証:** git log に `Intraday update: 2026-03-19 06:00/06:15/06:31 UTC` が連続記録 → **ループが正常動作中**

---

## ⚠️ 過去トラブルから得た教訓（最重要）

### GitHub Pages CDN の困難と解決策

#### 1. **CDNは404をキャッシュする** ❌発生 → ✅解決

**問題:**
- `etf_intraday_data.json` が CDN から 404 を返し続けた
- ファイルが gh-pages に実際に存在しても CDN は 404 キャッシュを返す
- 数時間経っても自動解消されない

**原因の仮説（当初）:**
- ファイルがgh-pages ブランチに存在しない？
- peaceiris が deploy/ に含めていない？
- pages-build-deployment がトリガーされていない？

**実際の原因:**
GitHub CDN がパスに対して 404 を一度キャッシュすると、後続でファイルが追加されても キャッシュを優先して返す。新しいファイルパスに切り替えない限り解消不可。

**解決策:** ファイル名を `etf_intraday.json` に変更 → **即座に CDN がファイルを配信開始**

---

#### 2. **mainブランチのcommitが重要**（gh-pages直接pushは不安定）❌試行 → ✅確認

**問題の流れ:**
1. intraday_etf.yml が gh-pages ブランチへ直接 git push
2. gh-pages ブランチにはファイルが存在
3. しかし **CDN は 404 を返す** ← 予期しない動作

**原因分析:**
- peaceiris は「`keep_files: true`でgh-pagesの既存ファイルを保持する」ことしかできない
- gh-pages への直接 push は GitHub 内部の pages-build-deployment パイプラインを経由しない場合がある
- mainブランチにコミットされたファイルをpeaceirisが deploy/ に含める流れが最も確実

**解決策:**
- intraday_etf.yml も main ブランチに commit
- gh-pages への直接 push は削除（peaceiris推奨に統一）
- ただし市場中の15分ごと更新のため、daily_* の次実行を待たずに済むよう **intraday_etf.yml 内で peaceiris も実行** に改修

---

#### 3. **GITHUB_TOKENと pages-build-deployment** ✅誤解を修正

**当初の外部AIの主張:**
「GITHUB_TOKEN では pages-build-deployment がトリガーされない」

**実装結果:**
daily_participant.yml / daily_task.yml が GITHUB_TOKEN + peaceiris で正常にCDN更新

**真実:**
- GitHub の「GITHUB_TOKEN で後続ワークフローが発火しない」制約は **ユーザー定義ワークフロー** に対するもの
- `pages-build-deployment` はGitHub内部のPages配信システムであり、gh-pagesブランチへのpushで通常どおり発火
- PATへの切り替えは不要

---

### GitHub Actions cron の21%発火率問題 ❌ → ✅完全克服

**実測データ:**
- 3.5時間で28回中6回のみ実行（実行率 21%）
- GitHub側に根本的な改善はなし（プラットフォーム仕様の制約）

**従来の対策試行:**
- バックアップcronを複数設定 → 発火率向上はわずか
- cron以外の手段を検討（外部サービス、自己チェーン）→ ユーザー要件「GitHub完結」に抵触

**最終解決:**
**ループ型ワークフロー** でcronの役割を「起動」のみに限定
- 起動後はOSレベルのsleep 900（15分）で次サイクルへ
- 1日2回×バックアップ3本のcron（6本）のうち1つでも発火すれば確実に市場時間中ずっと動作
- 実運用: 2026-03-19 06:00 UTC起動後、06:15, 06:31... と連続実行確認済み

---

### タイムゾーン二重加算の誤解 ✅ 正しい実装を確認

**外部AIの誤分析:**
「yfinanceはJSTタイムスタンプを出力済みだから toJST() の +9h は二重加算バグ」

**実装確認:**
- yfinance は複数市場データをマージ時に **UTC に統一**
- `tz_localize(None)` はラベルだけ除去、数値はUTC のまま
- 実データログ: 最後: 2026-03-19 05:40 = JST 14:40（市場中）← **UTC であることの証拠**
- `toJST()` の +9h 変換は **正しい** ← これを除去すると全5分足データが rangebreaks で非表示に

**措置:**
一時的に +9h を除去してしまい全チャート消滅 → すぐに復元 → チャート正常表示確認

---

### 上場廃止・データ取得不可の11銘柄削除 ✅

データ取得時のYahoo Finance エラー（期間14日、delisted/no price data）により以下を削除：

| セクター | 削除銘柄 | 実装 |
|---------|--------|------|
| 証券業 | 8702.T(岡三証券) | etf_data_manager.py + sector_category.html から削除 |
| ゴム製品 | 5104.T(TOYO TIRE) | 同上 |
| 空運業 | 9205.T(スカイマーク) | 同上 |
| 倉庫・運輸 | 9062.T(日本通運) | 同上 |
| パルプ・紙 | 3871.T(高度紙工業) | 同上 |
| 鉄鋼 | 5429.T(東京製鐵), 5481.T(山陽特殊製鋼) | 同上 |
| 電線 | 5809.T(タツタ電線), 5807.T(東京特殊電線) | 同上 |
| 海運業 | 9112.T(乾汽船) | 同上 |
| ETFセクター | 1613.T(情報通信業) | SECTORS/カテゴリリストから完全除外 |

**結果:** チャート・ランキング・バスケット説明が一貫

---

## GitHub Actions ワークフロー設計（現行版 2026-03-19）

### ワークフロー一覧

| ファイル | 名前 | 実行タイミング | デプロイ方式 |
|---|---|---|---|
| `intraday_etf.yml` | イントラデイETF更新 | 市場時間中 **15分ごとループ** | mainにcommit + gh-pages直接push |
| `daily_etf.yml` | 日次ETFデータ取得 | **毎日 JST 16:00** | peaceiris（keep_files: true） |
| `daily_short_selling.yml`| 空売り集計・株式相場状況 | **毎営業日 JST 17:05** | peaceiris（keep_files: true） |
| `daily_participant.yml` | 手口・オプション取得 | **毎日 JST 17:45** | peaceiris（keep_files: true） |
| `daily_task.yml` | JPX週次 + フルデプロイ | **毎週木曜 JST 18:00** + HTML/yml変更時 | peaceiris（keep_files: true） |
| `daily_market_analysis.yml` | **Gemini自動市場分析** | **平日 JST 18:15** | mainにcommit + Gist直接更新 |

### `daily_market_analysis.yml` — Gemini API 自動市場分析（2026-03-25 実装）

**概要:** 全データ取得→Gemini 3.1 Flash Lite Preview APIで分析→レポート生成→投資カレンダー「情報」タブに自動反映

**処理フロー:**
```
1. データ取得（5スクリプト順次実行）
   fetch_intraday.py → etf_data_manager.py → fetch_short_selling.py → fetch_teguchi.py → fetch_option.py

2. Gemini分析（scripts/market/gemini_analysis.py）
   - data/ 配下の5つのJSONを読み込み
   - Python側でサマリーに集約（6.3MB → 約150KB、トークン節約）
   - Gemini 3.1 Flash Lite Preview API に送信（入力 ~96,000 tokens）
   - レポートを market_analysis/reports/YYYYMMDD_daily_report.md に保存

3. 投資カレンダー連携（Gist API）
   - raw_url方式でGistの完全なデータを取得（truncation回避）
   - history[日付].info フィールドのみ更新（他フィールドは一切変更しない）
   - ブラウザリロードで「情報」タブにレポートが反映

4. コミット＆プッシュ（data/*.json + レポート）
```

**必要な GitHub Secrets:**
| Secret名 | 用途 |
|---|---|
| `GEMINI_API_KEY` | Gemini API認証キー |
| `FIREBASE_KEY_JSON` | 手口・オプションデータ取得（既存） |
| `GIST_TOKEN` | 投資カレンダーGist読み書き用GitHub PAT |
| `GIST_ID` | 投資カレンダーデータのGist ID |

**ローカル実行:**
```bash
GEMINI_API_KEY="..." GIST_TOKEN="..." GIST_ID="..." python scripts/market/gemini_analysis.py
```

**データ軽量化の仕組み:**
| データ | 元サイズ | 送信サイズ | 手法 |
|---|---|---|---|
| etf_intraday.json | 6.3MB | ~10KB | 銘柄ごとの始値・終値・騰落率のみ抽出 |
| etf_data.json | 788KB | ~5KB | 前日比・週比・月比のサマリーのみ |
| option_history.json | 153KB | ~30KB | 直近2日分のみ |
| teguchi.json | 28KB | 28KB | そのまま |
| short_selling.json | 58KB | 58KB | そのまま |

---

### `intraday_etf.yml` — ループ型15分間隔（決定版）

```
セッション起動型ループ（GitHub cronの21%不安定さを完全回避）

前場セッション:
  cron起動: UTC 0:00 / 0:15 / 0:30（JST 9:00 / 9:15 / 9:30）
  実行: JST 9:00 → 11:30 まで 15分ごとループ

後場セッション:
  cron起動: UTC 3:30 / 3:45 / 4:00（JST 12:30 / 12:45 / 13:00）
  実行: JST 12:30 → 15:45 まで 15分ごとループ

concurrency: cancel-in-progress: false
  → バックアップcronが複数発火しても キューで待機して順序保持
  → データ損失なし

1サイクル（15分）の流れ:
  1. fetch_intraday.py（yfinance で 5分足14日分）
  2. mainブランチに git commit & push
  3. gh-pagesブランチに直接 git push → CDN即時更新
  4. sleep 900（15分待機）
  5. 市場時間内なら繰り返し、15:45以降は終了
```

---

## データファイル一覧

| ファイル | 生成スクリプト | 参照HTML | 更新頻度 |
|---|---|---|---|
| `data/etf_data.json` | `etf_data_manager.py` | `etf.html`, `sector_category.html`, `topix100.html` | 毎日 JST 16:00 |
| `data/etf_intraday.json` | `fetch_intraday.py` / `etf_data_manager.py` | `sector_category.html`, `topix100.html` | **市場中15分ごと** + 毎日 JST 16:00 |
| `data/sector_data.json` | `sector_manager.py` | `analytics.html` | 週1回（木曜） |
| `data/short_selling.json` | `fetch_short_selling.py` | `short_selling.html` | 毎営業日 JST 17:05 |
| `data/teguchi.json` | `fetch_teguchi.py` | `teguchi.html` | 毎営業日 JST 17:45 |
| `data/option_history.json` | `fetch_option.py` | `option.html` | 毎営業日 JST 17:45 |
| `data/gpif_data.json` | `fetch_gpif_data.py` | `GPIF/dist/index.html` | 週1回（木曜） |

---

## セクター分類分析 (`sector_category.html`) 仕様（2026-03-23 最新版）

### ページ概要

全セクターを7カテゴリに分類し、**左：パフォーマンスチャート / 右：ランキング** の2カラム構成で表示。
市場時間中（前場 9:00〜11:30、後場 12:30〜15:30）は **5分ごとにブラウザ側でデータ取得・自動更新**する。
タブ復帰時にも即時更新（デバウンス500ms付き）。

---

### チャート構成と表示コンポーネント一覧

| コンポーネント | 表示内容 | JP/US切替 | チャート種別 | ランキング |
|---|---|---|---|---|
| **FullSectorChart** | 全セクター相対パフォーマンス (vs TOPIX) | JP/US切替あり | Plotly折れ線 | 横にTOP7/BOTTOM7 |
| **CategorySection ×7** | カテゴリ別チャート＋ランキング | JPのみ（US指数は参照線） | Plotly折れ線 | 横にランキングバー |
| **SemiconductorSection** | 半導体個別株パフォーマンス | JP/US切替あり | Plotly折れ線 | 横にランキングバー |

---

### パフォーマンス計算基準（重要）

```
イントラデイ（1d〜14d）: 前日終値基準（baseIndex = startIndex - 1）
  → 金融標準に準拠。ffillされたデータの前日最終ティックが前日終値となる
  → 例: 日経 -3.96% は前日終値からの変動（当日寄付からではない）

日次（1mo〜1y）: 期間開始日基準（baseIndex = startIndex）
  → 選択した期間の初日を100%として変動率を計算
```

**対象箇所（全て統一済み）:**
- JP市場 processedData（全セクター・全カテゴリ共通）
- US市場 usData（FullSectorChart用）
- SemiconductorSection JP/US（独自計算）
- SOX指数参照ライン

---

### 規模別指数（絶対値）カード — チャート＋ランキング仕様

**チャート表示ライン:**

| ライン | シンボル | 線種 | 色 | 備考 |
|---|---|---|---|---|
| TOPIX | 1306.T | 実線 | グレー | ベンチマーク |
| 日経指数 | ^N225 | 点線 | 黒 | JP主要指数 |
| NQmain(2606) | NQM26.CME | **破線** | 濃い青 | NASDAQ100先物 2026年6月限 |
| ESmain(2606) | ESM26.CME | **破線** | 濃い赤 | S&P500先物 2026年6月限 |
| YMmain(2606) | YMM26.CBT | **破線** | 濃い緑 | Dow Jones先物 2026年6月限 |
| NASDAQ100 | ^NDX | 実線 | 青 | 現物指数（前日終値ベース） |
| S&P500 | ^GSPC | 実線 | 赤 | 現物指数（前日終値ベース） |
| NYダウ | ^DJI | 実線 | 緑 | 現物指数（前日終値ベース） |
| 半導体ETF | 2644.T | 破線 | 橙 | GX半導体ETF |
| SOX指数 | ^SOX | 実線 | 紫 | フィラデルフィア半導体指数 |
| TOPIX Core30 | 1311.T | - | - | ランキングのみ |
| JPX400 | 1591.T | - | - | ランキングのみ |
| グロース250 | 2516.T | - | - | ランキングのみ |

**先物 vs 指数の使い分け:**
- **先物（破線）**: JP市場時間中もリアルタイムで変動するため、日経等との日中比較に有用
- **指数（実線）**: 前日の米国市場の確定結果。契約ロールの影響なし
- 両方表示することで「米国の前日結果」と「今の先物の動き」を同時に把握可能

**ランキング:** チャートの全ライン + TOPIX Core30/JPX400/グロース250 を含む全銘柄をパフォーマンス順で表示

---

### 先物シンボルの限月管理（運用上の注意）

```
現在: 2026年6月限（M = June）
  NQM26.CME  /  ESM26.CME  /  YMM26.CBT

次回更新: 2026年9月限（U = September）に切替時
  NQU26.CME  /  ESU26.CME  /  YMU26.CBT

変更箇所:
  1. scripts/market/etf_data_manager.py — SECTORS dict のシンボルと名前
  2. sector_category.html — EXCLUDE_FROM_SECTOR_RANKING, FULL_RANKING_HIDDEN,
     ABS_REF_LINES, US_REF_SYMBOLS（2箇所）の全シンボル・名前

CME先物限月コード: F=1月, G=2月, H=3月, J=4月, K=5月, M=6月,
                   N=7月, Q=8月, U=9月, V=10月, X=11月, Z=12月
```

---

### JP市場チャート仕様

**データソース:** `etf_intraday.json`（5分足14日分）/ `etf_data.json`（日次）
**X軸:** UTC → JST変換（toJST関数で+9h）、datetimeモード
**rangebreaks:** 土日非表示 `[{ bounds: ["sat", "mon"] }]`、昼休み非表示 `[{ bounds: [2.5, 3.5] }]`（UTC）

**全セクターチャート（FullSectorChart）:**
- 相対パフォーマンス = (セクター変動率 - TOPIX変動率) × 100
- TOPIXを0%基準線として各セクターの超過リターンを表示

**カテゴリ別チャート（CategorySection ×7）:**
- 相対モード: 上記と同じTOPIX割り返し
- 絶対値モード（規模別指数のみ）: TOPIX割り返しなし、各銘柄の純変動率を表示

---

### US市場チャート仕様

**データソース:** 同じ `etf_intraday.json` / `etf_data.json`（US銘柄も含む）
**X軸:** **categoryモード**（datetimeモードではない）
  - 理由: JST変換で金曜深夜→土曜早朝になり、datetimeモードの `["sat","mon"]` rangebreakで非表示になる問題を回避
  - ラベル: toJSTShort関数で `"3/20 22:00"` 形式

**US取引時間フィルタ:** UTC 13〜20時のデータのみ抽出（ET 9:00〜16:00）
**表示時間帯（JST）:** 22:00〜翌05:00（金曜の米国セッションは土曜早朝まで表示）

**FullSectorChart US:**
- US_SECTORS（XLK, XLF, XLE等 15セクターETF）の絶対パフォーマンス
- 参照線: NASDAQ100, S&P500, NYダウ

**SemiconductorSection US:**
- SEMICONDUCTOR_US（NVDA, AMD, AVGO等）の個別株パフォーマンス
- 参照線: SOX指数（^SOX）

---

### モバイルレイアウト仕様

**スワイプUI（SwipeContainer）:**
- 各カードは `w-[85%] max-w-[85%]` で幅を固定、CSS scroll-snap で横スワイプ
- ドットインジケーター（2つ）でページ位置を表示
- デスクトップでは `md:contents` で透過（通常の2カラム表示）

**Plotlyタッチ対応:**
- モバイル（`window.innerWidth < 768`）で `staticPlot: true` を適用
- `dragmode: false`、`touch-action: pan-x` でブラウザの横スワイプを優先
- これによりPlotlyがタッチイベントを横取りせず、カード間スワイプが機能

**ヘッダー:**
- モバイル: 2行に折り返し（`flex-wrap`）。ボタンテキスト短縮（「▲ 上7」「▼ 下7」）
- デスクトップ: 1行（`md:flex-nowrap`）。ボタンは右端配置

---

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
const intradayAvailable = rawIntraday?.dates?.length > 1
    && rawIntraday.dates[0].includes(' ');
```

5分足データが未取得の場合、日次データで代替表示し、ヘッダーに「[日次のみ]」を表示する。

### データのフレッシュネス表示

ヘッダーにデータ生成時刻と経過分数を表示。
市場時間中で20分以上古い場合はアンバー色で警告。

---

## 更新スケジュール（まとめ）

| タイミング | 実行内容 | 結果 |
|---|---|---|
| **市場中 毎15分（JST 9:00〜15:45）** | ループ型: `fetch_intraday.py` | mainコミット + gh-pages直接push → **CDN即時更新** |
| 毎日 JST 16:00 | `etf_data_manager.py` | 日次+イントラデイ両方再生成 → peaceirisでCDNデプロイ |
| 毎営業日 JST 17:05 | `fetch_short_selling.py` | 空売り集計・株式相場状況 → peaceirisでCDNデプロイ |
| 毎営業日 JST 17:45 | `fetch_teguchi.py` + `fetch_option.py` | 手口・建玉 → peaceirisでCDNデプロイ |
| 毎週木曜 JST 18:00 | JPX週次 + GPIF + フルデプロイ | → peaceirisでCDNデプロイ |
| HTML/yml変更プッシュ時 | daily_task.yml | → peaceirisでCDNデプロイ |

### ⚠️ 手口データの「古く見える」理由

JPXは**当日分の手口データを翌営業日 10:30頃に公開**するため、毎日 JST 17:45 に取得できる最新データは「前営業日分」になる。

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
investment_dashboard/
│
├── index.html                          # メインダッシュボード（サイドバーナビ）
├── topix100.html                       # TOPIX100銘柄分析（絶対値パフォーマンス）
├── etf.html                            # セクター分析（全セクター単一チャート）
├── sector_category.html                # セクター分類分析（7カテゴリ × チャート+ランキング）
├── short_selling.html                  # 売買フロー底打ち検知・空売り集計
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
│   ├── etf_intraday.json               # ETF・バスケット 5分足（intraday_etf.yml / daily_etf.yml）
│   ├── sector_data.json                # セクター集計（daily_task.yml）
│   ├── short_selling.json              # 空売り・売買フロー集計（daily_short_selling.yml）
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
│       ├── fetch_short_selling.py      # 空売り集計・株式相場状況（JPX スクレイピング）
│       ├── fetch_option.py             # オプション建玉（JPX スクレイピング）
│       └── fetch_teguchi.py            # 手口データ（JPX API）
│
├── GPIF/                               # GPIF 分析 React サブアプリ
│   ├── package.json
│   └── dist/                           # npm run build 生成物（gh-pages に保持）
│
└── .github/workflows/
    ├── intraday_etf.yml                # ループ型15分間隔更新（mainコミット + gh-pages直接push）
    ├── daily_etf.yml                   # 毎日 JST 16:00 ETFデータ
    ├── daily_short_selling.yml         # 毎営業日 JST 17:05 空売り集計取得
    ├── daily_participant.yml           # 毎営業日 JST 17:45 手口・オプション
    └── daily_task.yml                  # 週次 + HTML変更時フルデプロイ
```

---

## セットアップ

```bash
pip install yfinance pandas pytz
python scripts/market/etf_data_manager.py
```

## デザイン仕様 (Design Reference)

本プロジェクトのUI/UXプロトコル。新規画面追加・既存画面改修時はこの仕様に従うこと。

### 技術スタック
- **UIライブラリ**: React 18 (Babel Standalone)
- **スタイリング**: Tailwind CSS (CDN)
- **アイコン**: Lucide Icons
- **チャート**: Recharts
- **その他**: html2canvas, Marked.js

### カラースキーム

| 用途 | カラーコード | Tailwind |
|------|------------|----------|
| **背景 (Body)** | `#f8fafc` | slate-50 |
| **カード背景** | `#ffffff` | white |
| **境界線** | `#e2e8f0` | slate-200 |
| **メインテキスト** | `#334155` | slate-700 |
| **見出し** | `#1e293b` | slate-800 |
| **ラベル** | `#64748b` | slate-500 |
| **注釈** | `#94a3b8` | slate-400 |
| **Primary** | `#7C4DFF` | - |
| **Primary Hover** | `#651FFF` | - |
| **ポジティブ/上昇** | `#10B981` | emerald-500 |
| **ネガティブ/下落** | `#F43F5E` | rose-500 |
| **ベンチマーク** | `#475569` | slate-600 |

### 売買フロー専用カラー（統一）

| 項目 | カラー | 用途 |
|------|--------|------|
| **現物買い** | `#60a5fa` (blue-400) | チャート棒・テーブルハイライト・凡例 |
| **現物売り** | `#a78bfa` (violet-400) | チャート棒・凡例 |
| **空売り** | `#F43F5E` (rose-500) | チャート棒・テーブル警告・凡例 |
| **ネット買い** | `#10B981` (emerald-500) | チャート線・ポジティブ表示 |

### UIコンポーネント
- **カード**: `bg-white rounded-xl shadow-sm border border-slate-200 p-6`
- **サイドバー**: `bg-white border-r border-slate-200`
  - アクティブ: `bg-[#7C4DFF] text-white shadow`
  - 非アクティブ: `text-[#64748B] hover:bg-slate-100`
- **ボタン**: `bg-[#7C4DFF] text-white hover:bg-[#651FFF] font-bold rounded-lg`
- **テーブルヘッダー**: `bg-slate-50 text-xs uppercase font-bold text-slate-500`
- **モーダル**: `bg-white p-6 rounded-xl shadow-xl max-w-lg w-[90%]`
- **アニメーション**: `.animate-fade-in` (fadeIn 0.5s ease-out)

---

## ⚠️ 免責事項

- このツールは情報提供を目的としており、投資判断の根拠とするものではありません
- データの正確性については保証しません
- 投資は自己責任で行ってください

---

## 売買フロー分析・空売り集計 (`short_selling.html`) 仕様（最新版）

東証の空売り集計データと日次売買代金を組み合わせ、市場のセンチメントや底打ちの兆候を分析する専用ダッシュボードです。

### 全体レイアウトとUI構成
*   **2カラムレイアウト (レスポンシブ)**: 
    *   PC画面では「売買フロー推移」チャートと「空売り内訳推移」チャートが横2列で並列表示される (`grid-cols-1 lg:grid-cols-2`)。
    *   スマートフォンなどのモバイル環境では縦並びとなる。
*   **チャートの高さと整列**:
    *   両方のチャート高さを `420px` に固定。
    *   X軸・Y軸が左右のチャートでミリ単位で揃うよう、`margin={{top:15, right:25, left:-15, bottom:0}}` 等の余白設定を完全に統一している。
*   **デフォルト表示期間**:
    *   ページを開いた際のデフォルトズーム（Brush）は「直近20日間」に設定している。
*   **モジュール化されたヘルプUI**:
    *   画面をテキストで埋めるのを避け、各タイトルの横にある `?` アイコンから、そのチャートやロジック単体の説明モーダル（ポップアップ）を開くクリーンな設計を採用。

### 専用カラースキームと独自強調ルール
このページ独自の視覚的ルールとして、以下の色と透過率の制御を厳格に適用している。

*   **売買フロー推移の最大値強調 (Max Total)**:
    *   売買代金のバー(`total`)は通常、薄紫（`#a78bfa` / 不透明度 0.5）で描画される。
    *   ただし、期間内で「最大売買代金を記録した日（`mx_t_d`）」のバーだけは、不透明度を 1.0 に上げ、**濃い紫(`COLORS.total`: `#7C4DFF`)**へと変色させて最も目立たせる設計。
*   **空売り内訳推移の Peak! ドット**:
    *   直近20日間で空売り比率がピーク（上限）に達した日にのみ、折れ線上に強いピンク色（`#EC4899`）のドットアイコンと「Peak!」の文字を描画する。
    *   （※ もう一方の売買フローチャートにはPeakドットを表示しないルール）
*   **基本色の逆転**:
    *   現物売り(`genbutsu_uri`)はグレー(`COLORS.totalBar`: `#94a3b8`)。
    *   空売り合計・機関空売り はローズレッド表示(`COLORS.short / kikan`: `#F43F5E`)。

### センチメント転換（底打ち）判定ロジック
ダッシュボード上部で「フェーズ」として表示される市場判定は、直近20日間の以下の2つの先行指標を用いて算出される。

1.  **売買代金膨張シグナル (S1)**: 
    *   判定式: `当日の売買代金 / 20日MA >= 1.3 (+30%)`
    *   理由: パニック売りやセリングクライマックスに伴う「出来高の急増」を検知する。
2.  **空売り比率ピークアウト (S2)**: 
    *   判定式: `当日の空売り比率 / 直近20日内最大ピークの空売り比率 <= 0.80 (相対値で20%低下)`
    *   理由: レバレッジをかけたショートカバー（買い戻し）による底入れの兆しを検知する。

両方が点灯した場合にのみ「Phase 3: 反転上昇（底打ちシグナル全点灯）」とみなす。

### GitHub Actions との連携
*   空売り集計データは、東証公式サイトから前営業日分のデータが発表される夕方時刻を狙い、**毎営業日 JST 17:05** に `daily_short_selling.yml` (`fetch_short_selling.py`) によって新規取得・生成が行われ、GitHub Pages（CDN）へ自動配信されるアーキテクチャとなっている。

---

## TOPIX100分析ページ (`topix100.html`)

### 概要
TOPIX100（TOPIX Core30 + TOPIX Large70）構成銘柄98銘柄の相対パフォーマンスを、絶対値ベースでチャート＋ランキング表示するページ。セクター分類分析ページの半導体銘柄セクション (`SemiconductorSection`) のロジック・デザインを流用して構築。

### サイドバー配置
「個別分析」カテゴリ（「ETFセクター分析」と「売買フロー」の間）に配置。

### 構成銘柄一覧（98銘柄）

| コード | 銘柄名 | コード | 銘柄名 |
|--------|--------|--------|--------|
| 1925.T | 大和ハウス工業 | 6594.T | ニデック |
| 1928.T | 積水ハウス | 6645.T | オムロン |
| 2413.T | エムスリー | 6702.T | 富士通 |
| 2502.T | アサヒグループHD | 6752.T | パナソニックHD |
| 2503.T | キリンHD | 6758.T | ソニーG |
| 2802.T | 味の素 | 6861.T | キーエンス |
| 2914.T | JT | 6869.T | シスメックス |
| 3382.T | セブン&アイ | 6902.T | デンソー |
| 3402.T | 東レ | 6920.T | レーザーテック |
| 3407.T | 旭化成 | 6954.T | ファナック |
| 4063.T | 信越化学工業 | 6971.T | 京セラ |
| 4188.T | 三菱ケミカルG | 6981.T | 村田製作所 |
| 4452.T | 花王 | 7011.T | 三菱重工業 |
| 4502.T | 武田薬品工業 | 7201.T | 日産自動車 |
| 4503.T | アステラス製薬 | 7203.T | トヨタ自動車 |
| 4507.T | 塩野義製薬 | 7267.T | 本田技研工業 |
| 4519.T | 中外製薬 | 7269.T | スズキ |
| 4523.T | エーザイ | 7270.T | SUBARU |
| 4528.T | 小野薬品工業 | 7309.T | シマノ |
| 4543.T | テルモ | 7733.T | オリンパス |
| 4568.T | 第一三共 | 7741.T | HOYA |
| 4578.T | 大塚HD | 7751.T | キヤノン |
| 4661.T | オリエンタルランド | 7832.T | バンダイナムコHD |
| 4689.T | LINEヤフー | 7974.T | 任天堂 |
| 4901.T | 富士フイルムHD | 8001.T | 伊藤忠商事 |
| 4911.T | 資生堂 | 8002.T | 丸紅 |
| 5020.T | ENEOS HD | 8031.T | 三井物産 |
| 5108.T | ブリヂストン | 8035.T | 東京エレクトロン |
| 5401.T | 日本製鉄 | 8053.T | 住友商事 |
| 5713.T | 住友金属鉱山 | 8058.T | 三菱商事 |
| 5802.T | 住友電気工業 | 8113.T | ユニ・チャーム |
| 6098.T | リクルートHD | 8267.T | イオン |
| 6178.T | 日本郵政 | 8306.T | 三菱UFJFG |
| 6273.T | SMC | 8308.T | りそなHD |
| 6301.T | 小松製作所 | 8309.T | 三井住友トラストHD |
| 6326.T | クボタ | 8316.T | 三井住友FG |
| 6367.T | ダイキン工業 | 8411.T | みずほFG |
| 6501.T | 日立製作所 | 8591.T | オリックス |
| 6503.T | 三菱電機 | 8604.T | 野村HD |
| 6586.T | マキタ | 8630.T | SOMPO HD |
| — | — | 8697.T | JPX |
| — | — | 8725.T | MS&AD |
| — | — | 8750.T | 第一生命HD |
| — | — | 8766.T | 東京海上HD |
| — | — | 8801.T | 三井不動産 |
| — | — | 8802.T | 三菱地所 |
| — | — | 8830.T | 住友不動産 |
| — | — | 9020.T | JR東日本 |
| — | — | 9021.T | JR西日本 |
| — | — | 9022.T | JR東海 |
| — | — | 9101.T | 日本郵船 |
| — | — | 9202.T | ANA HD |
| — | — | 9432.T | NTT |
| — | — | 9433.T | KDDI |
| — | — | 9434.T | ソフトバンク |
| — | — | 9735.T | セコム |
| — | — | 9843.T | ニトリHD |
| — | — | 9983.T | ファーストリテイリング |
| — | — | 9984.T | ソフトバンクG |

### データソース
*   `data/etf_data.json` — 日次終値データ（400日分）
*   `data/etf_intraday.json` — イントラデイ5分足データ（14日分）
*   データ取得元: Yahoo Finance (`yfinance`)、`scripts/market/etf_data_manager.py` の `TOPIX100` 定数で定義

### パフォーマンス計算ロジック

1.  **絶対値ベース**: TOPIX等のベンチマークで割り返しせず、各銘柄の価格変動率をそのまま表示
2.  **計算式**: `((当日価格 / 基準価格) - 1) × 100 [%]`
3.  **基準価格の決定**:
    *   イントラデイモード（1日〜14日）: 前日最終データポイント（`startIndex - 1`）を基準
    *   日次モード（1ヶ月〜1年）: 期間開始日を基準
4.  **終値補正**: イントラデイ表示時、日次データが存在すれば**常に**ランキング値を日次終値で上書き。イントラデイ5分足の最終tickは実際の終値と乖離するため、ランキング数値の精度を日次データで担保する。
5.  **日経指数参考ライン**: `^N225`（日経225指数）を黒点線で同時表示し、市場全体との比較が可能

### フィルタボタン（チャート制御）

| ボタン | チャート表示 | ランキング表示 | デフォルトスクロール位置 |
|--------|-------------|---------------|----------------------|
| **ALL** | 全銘柄 | 全銘柄（上から） | 上端 |
| **TOP10 + WORST10**（デフォルト） | 上位10 + 下位10 | 全銘柄（上から） | 上端 |
| **TOP 10** | 上位10銘柄 | 全銘柄（上から） | 上端 |
| **WORST 10** | 下位10銘柄 | 全銘柄（下から） | 下端 |

*   ランキングは常に全銘柄を1位から最下位まで表示
*   チャートに表示中の銘柄はハイライト表示、非対象銘柄は薄く（`opacity-40`）表示
*   WORST 10 モード選択時のみ、ランキングが自動的に下端（最下位）へスクロール

### UIレイアウト
*   **左半面**: Plotly.js チャート（折れ線グラフ、Y軸: パフォーマンス%、X軸: 日付/時刻）
*   **右半面**: 横バーランキング（左右対称バー、緑=プラス/赤=マイナス、中央0%基準線）
*   **カード高さ**: 800px
*   **凡例**: カード下部にチャート表示中銘柄のみ表示。クリックでトレースの表示/非表示トグル
*   **日経指数凡例**: 凡例末尾に「日経指数(参考)」として独立表示

### 期間選択
1日 / 2日 / 3日 / 5日 / 7日 / 10日 / 14日 / 1ヶ月 / 2ヶ月 / 3ヶ月 / 6ヶ月 / 1年

### 自動更新
*   市場時間中（前場 8:55-11:35 / 後場 12:25-15:35）: **5分**毎に自動再取得
*   市場時間外: **30分**毎に自動再取得
*   ページ復帰時（タブ切替・スリープ復帰）: 500msデバウンス後に再取得

### GitHub Actions との連携
*   TOPIX100銘柄データは `etf_data_manager.py` の `TOPIX100` 定数に定義され、既存のETF・半導体銘柄と一括でダウンロード
*   `daily_etf.yml` / `intraday_etf.yml` の既存ワークフローでデータ更新・GitHub Pages配信される（追加のワークフロー不要）
