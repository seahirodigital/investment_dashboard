# RSS NEWS Discord配信 仕様書

作成日: 2026-05-21  
対象リポジトリ: `C:\Users\mahha\OneDrive\開発\investment_dashboard`  
実装スクリプト: `C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\rss_discord_news.py`  
状態管理ファイル: `C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\news_state.json`  
GitHub Actions workflow: `C:\Users\mahha\OneDrive\開発\investment_dashboard\.github\workflows\rss_news_discord.yml`

## 目的

ブルームバーグとロイターのRSSを定期監視し、新着NEWSをDiscordへ自動配信する。

RSS提供元に「クローラーによる各サイトページへのアクセスは1時間に1回以内」と記載があるため、記事ページ本文のクロールは行わず、指定されたRSSだけを監視対象にする。

## 対象RSS

| 媒体 | RSS URL |
|---|---|
| ブルームバーグ | `https://assets.wor.jp/rss/rdf/bloomberg/markets.rdf` |
| ロイター | `https://assets.wor.jp/rss/rdf/reuters/top.rdf` |

## Discord通知先

GitHub Actionsでは、Discord Webhook URLをコードへ直書きしない。

使用Secret:

`DISCORD_NEWS_WEBHOOK_URL`

GitHubリポジトリのActions Secretに、通知先Webhook URLを登録する。

ローカルテスト時のみ、ユーザーが提示したWebhook URLをPowerShellの一時変数として使った。Webhook URLは `C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\rss_discord_news.py` と `C:\Users\mahha\OneDrive\開発\investment_dashboard\.github\workflows\rss_news_discord.yml` には保存していない。

## 監視方式

### GitHub Actionsの起動

`C:\Users\mahha\OneDrive\開発\investment_dashboard\.github\workflows\rss_news_discord.yml` は、以下のcronで起動する。

```yaml
cron: '55 2,8,14,20 * * *'
```

これはUTC基準であり、日本時間では以下に相当する。

| UTC | JST |
|---:|---:|
| 02:55 | 11:55 |
| 08:55 | 17:55 |
| 14:55 | 23:55 |
| 20:55 | 05:55 |

GitHub Actionsのcron混雑を避けるため、毎時00分ぴったりではなく5分前倒しで起動する。

### 1回の起動内での監視

毎時cronで単発実行する方式ではなく、1回のActions起動内で監視を継続する。

標準設定:

| 項目 | 値 |
|---|---:|
| 監視間隔 | 10分 |
| 1回の起動で監視する時間 | 360分 |
| workflow timeout | 365分 |

これにより、1日4回のActions起動で、ほぼ連続的に10分おきのRSS監視を行う。

GitHub Actionsは完全な永久常駐には向かないため、約6時間の長時間ジョブを1日4回つなぐ構成にしている。

## 配信時間帯

Discord配信は日本時間 `06:00` から `23:59` まで行う。

日本時間 `00:00` から `05:59` に取得したNEWSは、Discordへ送信せず `C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\news_state.json` に保留する。

日本時間 `06:00` 以降の最初の監視タイミングで、夜間に保留したNEWSと新着NEWSを合わせてDiscordへ配信する。

## RSS取得間隔

実装上の最小取得間隔:

```python
MIN_FETCH_INTERVAL_SECONDS = 10 * 60
```

対象ファイル:

`C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\rss_discord_news.py`

同一RSS URLについて、前回取得から10分未満の場合は取得をスキップする。

## 重複排除

NEWSごとに以下を元にIDを作成する。

優先順:

1. RSS itemの `guid` または `id`
2. RSS itemの `rdf:about`
3. RSS itemの `link`
4. 媒体名とタイトル

生成したIDは `C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\news_state.json` の `seen_ids` に保存する。

同じNEWS IDが `seen_ids` または `pending_items` に存在する場合、再配信しない。

保持する既読ID数:

```python
MAX_SEEN_IDS = 800
```

## 状態管理

状態管理ファイル:

`C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\news_state.json`

主な項目:

| 項目 | 内容 |
|---|---|
| `version` | 状態ファイルのバージョン |
| `feeds` | RSS URLごとの最終取得時刻とエラー |
| `seen_ids` | 配信済みまたは保留済みNEWSのID |
| `pending_items` | 夜間保留中、または送信失敗で未配信のNEWS |

GitHub Actionsでは、監視ループの各回ごとに `C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\news_state.json` をコミットし、pushする。

これにより、Actionsの次回起動でも既読・保留状態を引き継ぐ。

## Discord配信フォーマット

各NEWSは以下の3行構成にする。

```text
YYYY/MM/DD/HH:mm
タイトル
URL
```

例:

```text
2026/05/21/00:00
独自インド中銀、ルピー安阻止へ利上げ検討－海外からドル調達策も選択肢
https://www.bloomberg.com/jp/news/articles/2026-05-21/TFDBJZT9NJLT00?srnd=jp-markets
```

Discord投稿の先頭には、以下のヘッダーを付ける。

```text
NEWS配信
YYYY-MM-DD HH:mm JST
```

Discordの1投稿あたりの文字数上限を避けるため、本文は約1900文字以内で分割する。

実装上の上限:

```python
DISCORD_CONTENT_LIMIT = 1900
```

## 文字化け対策

Windows環境で日本語を扱うため、以下の対策を行う。

`C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\rss_discord_news.py` では、Windows実行時に標準出力と標準エラーをUTF-8へ設定する。

```python
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
```

PowerShellでRSS取得テストを行う場合は、`Invoke-WebRequest` の `.Content` をそのまま使うと文字化けする場合がある。

テスト時はRSSをバイト列として取得し、明示的にUTF-8として復元した。

```powershell
[byte[]]$bytes = $client.DownloadData($feed.Url)
$content = [System.Text.Encoding]::UTF8.GetString($bytes)
```

Discord送信時も、JSON本文をUTF-8バイト列にしてPOSTした。

```powershell
$bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
Invoke-RestMethod -Method Post -Uri $webhookUrl -ContentType 'application/json; charset=utf-8' -Body $bodyBytes
```

## Discord Webhook URLの正規化

ユーザー提示URLが `https://discordapp.com/api/webhooks/` の場合でも、送信時に `https://discord.com/api/webhooks/` へ正規化する。

対象関数:

`C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\rss_discord_news.py` の `_normalize_webhook_url`

## テスト結果

2026-05-21に以下を確認した。

| テスト | 結果 |
|---|---|
| PowerShellからのWebhook疎通確認 | 成功 |
| RSS取得テスト通知 | 成功 |
| 文字化け修正版RSS取得テスト通知 | 成功 |
| 3行フォーマットRSS取得テスト通知 | 成功 |
| ブルームバーグRSS実取得 | 10件パース成功 |
| ロイターRSS実取得 | RSS自体は取得成功。ただし取得時点では `<item>` が0件 |
| Python構文チェック | 成功 |
| UTF-8確認 | 成功 |
| 05:59 JSTの配信判定 | 配信しない |
| 06:00 JSTの配信判定 | 配信する |

ローカルPythonでは、Discord送信とRSS取得のHTTPS通信時にSSL証明書検証エラーが発生した。

エラー内容:

```text
SSLCertVerificationError
```

PowerShellのHTTPS通信では同じWebhookとRSS URLにアクセスできたため、ローカルPython環境の証明書設定に起因する問題と判断した。

GitHub Actionsの `ubuntu-latest` では標準CA証明書が利用できるため、Python実行での成功を想定している。

## 手動実行

RSS監視スクリプトを手動でドライランする。

```powershell
python -B C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\rss_discord_news.py
```

Discordへ送信する。

```powershell
$env:DISCORD_NEWS_WEBHOOK_URL = "<Discord Webhook URL>"
python -B C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\rss_discord_news.py --send
$env:DISCORD_NEWS_WEBHOOK_URL = ""
```

テストメッセージだけを送る。

```powershell
$env:DISCORD_NEWS_WEBHOOK_URL = "<Discord Webhook URL>"
python -B C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\rss_discord_news.py --test-message --send
$env:DISCORD_NEWS_WEBHOOK_URL = ""
```

一時状態ファイルでテストする。

```powershell
python -B C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\rss_discord_news.py --state-path C:\Users\mahha\OneDrive\開発\investment_dashboard\artifacts\rss_news_test_state.json
```

## GitHub Actions手動実行

GitHub Actionsの `RSS NEWS Discord配信` workflowは、`workflow_dispatch` に対応している。

手動実行時に指定できる入力:

| 入力 | 既定値 | 内容 |
|---|---:|---|
| `interval_minutes` | `10` | RSS監視間隔 |
| `duration_minutes` | `360` | 1回の起動で監視し続ける時間 |

短時間テスト例:

| 入力 | 値 |
|---|---:|
| `interval_minutes` | `1` |
| `duration_minutes` | `3` |

この設定では、約3分間だけRSS監視を行う。

## 注意事項

### 「毎時間通知」ではない

この仕組みは、毎時間必ず通知するものではない。

10分おきにRSSを確認し、新着NEWSがある場合だけDiscordへ通知する。

新着NEWSがない場合は通知しない。

夜間の日本時間 `00:00` から `05:59` は、取得しても通知せず保留する。

### ロイターRSSが空の場合

2026-05-21のテスト時点では、`https://assets.wor.jp/rss/rdf/reuters/top.rdf` のRSS内に `<item>` が存在しなかった。

この場合、取得自体は成功しても配信対象NEWSは0件になる。

### Git push不可の現状

2026-05-21時点で、`C:\Users\mahha\OneDrive\開発\investment_dashboard\.git` は以下を指している。

```text
gitdir: /Users/user/LocalGit/investment_dashboard.git
```

これはMac側の絶対パスであり、Windows上の現在環境では通常の `git status`、`git remote -v`、`git branch --show-current` が失敗する。

実際のエラー:

```text
fatal: not a git repository: /Users/user/LocalGit/investment_dashboard.git
```

そのため、現時点のWindows環境からは通常の `git push` を実行できない。

pushするには、Windows上で有効なGitメタデータへ接続し直すか、Mac側の `/Users/user/LocalGit/investment_dashboard.git` が見える環境でpushする必要がある。
