# Discord通知一覧

作成日: 2026-05-21  
対象リポジトリ: `C:\Users\mahha\OneDrive\開発\investment_dashboard`  
共通Webhook Secret: `DISCORD_OPTION_WEBHOOK_URL`

## 現在の通知一覧

| 通知名 | Workflow | 実行タイミング | 手動実行 | 送信条件 | 通知内容 | 添付ファイル | 直近状況 |
|---|---|---:|---|---|---|---|---|
| 朝の市況Discord通知 | `C:\Users\mahha\OneDrive\開発\investment_dashboard\.github\workflows\morning_market_discord.yml` | 平日 06:33 JST（月〜金） / `33 21 * * 0-4` UTC | あり | 常に送信 | Fear & Greed Indexの数値とURL、日経VIXの数値とURL、FinvizヒートマップURL、指定ハッシュタグ | 1. Finvizヒートマップ<br>2. Fear & Greed Index<br>3. 日経VIX 1wチャート | 成功。直近手動実行: 2026-05-20 23:54 JST / `https://github.com/seahirodigital/investment_dashboard/actions/runs/26170687841` |
| 米国株セクター資金流入通知 | `C:\Users\mahha\OneDrive\開発\investment_dashboard\.github\workflows\sector_category_discord.yml` | 06:25 JST（UTC月〜金の21:25なのでJST火〜土相当） / `25 21 * * 1-5` UTC | あり。`mode=us` | 常に送信 | 当日の日付、米国株各セクター資金流入、上位7件、下位7件、ハッシュタグ、セクター分析ページURL | 1. 米国株セクター上位7件チャート＋ランキング<br>2. 米国株セクター下位7件チャート＋ランキング | 成功。直近の該当Workflow実行: 2026-05-20 19:03 JST / `https://github.com/seahirodigital/investment_dashboard/actions/runs/26155557923` |
| 日本株セクター資金流入通知 | `C:\Users\mahha\OneDrive\開発\investment_dashboard\.github\workflows\sector_category_discord.yml` | 平日 15:40 JST（月〜金） / `40 6 * * 1-5` UTC | あり。`mode=jp` | 常に送信 | 当日の日付、セクター資金流入割合分析、上位5件、下位5件、ハッシュタグ、セクター分析ページURL | 1. 日本株セクター上位7件チャート＋ランキング<br>2. 日本株セクター下位7件チャート＋ランキング<br>3. 日本株セクター全ランキング | 成功。直近の該当Workflow実行: 2026-05-20 19:03 JST / `https://github.com/seahirodigital/investment_dashboard/actions/runs/26155557923` |
| 日経225オプション分析通知 | `C:\Users\mahha\OneDrive\開発\investment_dashboard\.github\workflows\daily_participant.yml` | 毎日 17:45 JST / `45 8 * * *` UTC | あり | JPX手口データとオプション履歴を取得後に送信 | `YYYYMMDDの日経225 オプション分析`、ハッシュタグ、オプションページURL、トップページURL | 1. 主要投資家差分チャート<br>2. 主要投資家合計チャート<br>3. 主要投資家トレンドチャート<br>4. 日経225建玉ストライク別チャート<br>5. 日経225差分ストライク別チャート | 成功。直近定期実行: 2026-05-20 20:33 JST / `https://github.com/seahirodigital/investment_dashboard/actions/runs/26159830471` |
| ダッシュボード更新通知 | `C:\Users\mahha\OneDrive\開発\investment_dashboard\.github\workflows\daily_task.yml` | 毎週木曜 18:00 JST / `0 9 * * 4` UTC | あり | 定期実行ではデータ差分がある場合のみ送信。手動実行では送信。push実行では送信しない | 海外投資家動向（JPX・財務省）とセクター別感応度ページの更新通知、各ページURL | 1. 海外投資家動向（JPX・財務省）スクリーンショット<br>2. セクター別感応度スクリーンショット | Workflow自体は成功。直近実行: 2026-05-21 00:05 JST のpush実行（Discord送信条件外） / `https://github.com/seahirodigital/investment_dashboard/actions/runs/26171311985` |

## 送信本文テンプレート

### 朝の市況Discord通知

```text
Feaar % Greed Index：{fear_greed_value}
https://edition.cnn.com/markets/fear-and-greed

日経VIX:{nikkei_vi_value}
https://indexes.nikkei.co.jp/nkave/index/profile?cid=1&idx=nk225vi#section-gist

米株ヒートマップ
https://finviz.com/map

#デイトレ #米国株 #日本株 #日経平均 #FX  #CFD 
```

### 米国株セクター資金流入通知

```text
{YYYYMMDD}の米国株各セクター資金流入

▼上位7件
{セクター名}: {騰落率}

▼下位7件
{セクター名}: {騰落率}

#米国株 #株式投資 #デイトレ #オプション #FX

https://seahirodigital.github.io/investment_dashboard/sector_category.html#full-sector-flow
```

### 日本株セクター資金流入通知

```text
{YYYYMMDD} セクター資金流入割合分析

▼上位5件
{セクター名}: {騰落率}

▼下位5件
{セクター名}: {騰落率}

#日経平均 #株式投資 #デイトレ #TOPIX #N225 #オプション #CFD

https://seahirodigital.github.io/investment_dashboard/sector_category.html#full-sector-flow
https://seahirodigital.github.io/investment_dashboard/
```

### 日経225オプション分析通知

```text
{YYYYMMDD}の日経225 オプション分析


#日経平均 #株式投資 #デイトレ #N225 #オプション #CFD


https://seahirodigital.github.io/investment_dashboard/option.html
https://seahirodigital.github.io/investment_dashboard/
```

### ダッシュボード更新通知

```text
海外投資家動向（JPX・財務省） / セクター別感応度ページを更新しました。現状の最新データでスクリーンショットを送信します。

海外投資家動向（JPX・財務省）
https://seahirodigital.github.io/investment_dashboard/index.html?view=jpx
https://seahirodigital.github.io/investment_dashboard/

セクター別感応度ページ
https://seahirodigital.github.io/investment_dashboard/analytics.html
https://seahirodigital.github.io/investment_dashboard/
```

## 運用メモ

| 項目 | 現状 |
|---|---|
| Webhook Secret | 全通知で `DISCORD_OPTION_WEBHOOK_URL` を使用 |
| 朝の市況通知の一時スクショ | Discord送信成功後、`C:\Users\mahha\OneDrive\開発\investment_dashboard\artifacts\morning_market_notification` を削除 |
| ローカル練習スクショ | `C:\Users\mahha\OneDrive\開発\investment_dashboard\artifacts\` は `.gitignore` で除外 |
| GitHub Actions Artifact | 朝の市況通知ではアップロードしない設定 |
| push時のDiscord送信 | `C:\Users\mahha\OneDrive\開発\investment_dashboard\.github\workflows\daily_task.yml` はpushで起動するが、Discord送信ステップはpushでは実行されない |
