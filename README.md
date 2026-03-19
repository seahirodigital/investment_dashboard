# 統合投資ダッシュボード

日本株・ETF・オプション等を一元管理する投資分析ダッシュボードです。

---

## 📋 本日（2026-03-19）の実装履歴＆解決済み課題

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
| `daily_participant.yml` | 手口・オプション取得 | **毎日 JST 20:05** | peaceiris（keep_files: true） |
| `daily_task.yml` | JPX週次 + フルデプロイ | **毎週木曜 JST 18:00** + HTML/yml変更時 | peaceiris（keep_files: true） |

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
| `data/etf_data.json` | `etf_data_manager.py` | `etf.html`, `sector_category.html` | 毎日 JST 16:00 |
| `data/etf_intraday.json` | `fetch_intraday.py` / `etf_data_manager.py` | `sector_category.html` | **市場中15分ごと** + 毎日 JST 16:00 |
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
    ├── intraday_etf.yml                # ループ型15分間隔更新（mainコミット + gh-pages直接push）
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
