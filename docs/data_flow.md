# Investment Dashboard - データフロー構成図

最終更新: 2026-03-16

---

## 全体アーキテクチャ概要

```
外部データソース → Pythonスクリプト → ストレージ → HTMLダッシュボード
```

---

## 1. データ取得・生成フロー

```
┌─────────────────────────────────────────────────────────────────────┐
│                     外部データソース                                  │
├─────────────────────────────────────────────────────────────────────┤
│  JPX公式サイト (jpx.co.jp)           Yahoo Finance (yfinance)        │
│  ├── 投資部門別売買状況 PDF            ├── ETFセクター株価（日次400日）  │
│  ├── デリバティブ建玉 XLSX            ├── ETFセクター株価（5分足5日）    │
│  └── 手口データ PDF                  └── GPIF関連資産株価（1500日）    │
└──────────────────────┬──────────────────────┬───────────────────────┘
                       │                      │
                       ▼                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Pythonスクリプト（GitHub Actions）                  │
├──────────────────┬──────────────────┬───────────────────────────────┤
│  scripts/jpx/    │  scripts/jpx/    │  scripts/jpx/                 │
│  fetch_option.py │ fetch_teguchi.py │  daily_participant_analyzer.py│
│  （建玉データ）   │  （手口データ）   │  （投資部門別売買データ）        │
├──────────────────┴──────────────────┴───────────────────────────────┤
│  scripts/market/               scripts/market/                       │
│  etf_data_manager.py           fetch_gpif_data.py                   │
│  （セクターETF株価）             （GPIF関連株価）                      │
├──────────────────────────────────────────────────────────────────────┤
│  sector_manager.py             main.py                               │
│  （セクター感応度分析）           （JPX PDFスクレイピング）              │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. ストレージ別データ一覧

### Firebase Firestore（リアルタイム型・履歴保持）

```
Firebase Project: nkf-option
│
├── option_data/
│   └── YYYYMMDD（日付キー）
│       ├── p1: デリバティブ建玉概要（日経225・TOPIX・mini等）
│       └── p2_225: 日経225オプション権利行使価格別詳細（Call/Put建玉）
│       ← 書き込み: fetch_option.py
│       ← 読み取り: option.html（メイン）
│
├── teguchi_data/
│   └── YYYYMMDD（日付キー）
│       ├── results: 証券会社別デルタ一覧（US/EU/JP/Net分類）
│       ├── matrix: 権利行使価格別C/P建玉マトリクス
│       └── strikes: 権利行使価格リスト
│       ← 書き込み: fetch_teguchi.py
│       ← 読み取り: teguchi.html（メイン・Firestoreのみ）
│
└── daily_participant/
    └── YYYYMMDD（日付キー）
        └── 投資部門別売買状況
        ← 書き込み: main.py（オプション）
        ← 読み取り: 現状未使用
```

### ローカルJSON（GitリポジトリへコミットしGitHub Pages経由で配信）

```
data/
│
├── etf_data.json          （80KB）
│   ├── benchmark: "1306.T"（TOPIX）
│   ├── sectors: { "1617.T": "食品", ... }（18セクターETF）
│   ├── dates: [ "2026-03-16", ... ]（400日分）
│   └── prices: { "1306.T": [...], ... }
│   ← 生成: etf_data_manager.py（毎日 16:00 JST）
│   ← 参照: etf.html（日次チャート表示）
│
├── etf_intraday_data.json （67KB）
│   └── セクターETF 5分足データ（直近5日分）
│   ← 生成: etf_data_manager.py（毎日 16:00 JST）
│   ← 参照: etf.html（イントラデイチャート表示）
│
├── sector_data.json       （118KB）
│   ├── 週次資金フロー（海外投資家 買越/売越）
│   ├── セクター別週次リターン
│   └── Mean DIFF = (買越週平均リターン) - (売越週平均リターン)
│   ← 生成: sector_manager.py（毎週木曜 18:00 JST）
│   ← 参照: analytics.html（感応度分析チャート）
│
├── option_history.json    （51KB）
│   └── デリバティブ建玉データ（複数日分）
│   ← 生成: fetch_option.py（毎日 20:05 JST）
│   ← 参照: option.html（Firebaseフォールバック用のみ）
│
├── gpif_data.json         （198KB）
│   ├── JP_EQ: 1306.T 日本株（1500日分）
│   ├── JP_BD: 2510.T 日本債券（1500日分）
│   ├── GL_EQ: 2559.T グローバル株（1500日分）
│   └── GL_BD: 2511.T グローバル債券（1500日分）
│   ← 生成: fetch_gpif_data.py（毎週木曜 18:00 JST）
│   ← 参照: GPIF/ React app
│
└── daily_participant.json （114KB）
    └── 投資部門別売買状況（JPX公式・最新1件）
    ← 生成: daily_participant_analyzer.py（毎日 20:05 JST）
    ← 参照: 現状未確認
```

### GitHub Gist（ユーザー管理データ）

```
GitHub Gist（認証: localStorage['gist_token']）
│
└── market_data.json（Gist ID: localStorage['gist_id']）
    ├── マーケットカレンダー（祝日・イベント等）
    └── 投資格言（quotes）
    ← 読み書き: index.html（PATCH/GET https://api.github.com/gists/{gistId}）
```

---

## 3. HTMLページ別データ参照マップ

| ページ | Firebase | ローカルJSON | Gist | 備考 |
|-------|---------|------------|------|-----|
| `index.html` | ─ | ─ | ✅ market_data.json | カレンダー・格言 |
| `option.html` | ✅ option_data | ✅ option_history.json（FB失敗時） | ─ | フォールバックあり |
| `teguchi.html` | ✅ teguchi_data | ─ | ─ | Firebaseのみ |
| `etf.html` | ─ | ✅ etf_data.json / etf_intraday_data.json | ─ | |
| `analytics.html` | ─ | ✅ sector_data.json | ─ | |
| `advanced.html` | ─ | ─（history.csv） | ─ | ローカルCSV（未push） |
| GPIF React app | ─ | ✅ gpif_data.json | ─ | |

---

## 4. GitHub Actions スケジュール

| ワークフロー | ファイル | 実行タイミング | 処理内容 |
|------------|---------|-------------|--------|
| JPX Automation | `daily_task.yml` | 毎週木曜 18:00 JST | JPX PDF取得 → sector_data.json生成 → GPIF data取得 → Deploy |
| Daily ETF Analysis | `daily_etf.yml` | 毎日 16:00 JST | ETF株価取得 → etf_data.json / etf_intraday_data.json → Deploy |
| Daily Participant & Option | `daily_participant.yml` | 毎日 20:05 JST | JPX建玉XLSX + 手口PDF取得 → Firebase書き込み + JSONバックアップ → Deploy |

---

## 5. Firebase移行検討メモ

### 移行適切（将来的に検討）
- `option_history.json` → Firebaseに既に書き込み済み。JSONはフォールバックとして冗長なので削除可能

### 移行不要・非推奨
- `etf_data.json` / `etf_intraday_data.json` / `gpif_data.json` → 80〜200KBの大規模時系列データ。Firestoreの1MBドキュメント制限・コスト観点から静的JSONが最適
- `sector_data.json` → 週次計算結果。静的JSONで十分
- GitHub Gist（カレンダー・格言）→ ユーザーが手動管理するメモ的データ。Gistの方が編集しやすい

---

## 6. 補助ファイル

| ファイル | 用途 |
|--------|-----|
| `sectors.json` | セクターETFのティッカー・カテゴリ定義（sector_manager.pyが参照） |
| `firebase-key.json` | Firebase Admin SDK 認証キー（gitignore対象・要注意） |
| `history.csv` | JPX投資部門別売買データ（自動生成・gitignore対象） |
| `trend.png` | 分析グラフ画像（自動生成・gitignore対象） |
