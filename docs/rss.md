# RSS NEWS Discord配信 仕様書

作成日: 2026-05-21

対象リポジトリ: `C:\Users\mahha\OneDrive\開発\investment_dashboard`

実装ファイル:

- `C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\rss_discord_news.py`
- `C:\Users\mahha\OneDrive\開発\investment_dashboard\.github\workflows\rss_news_discord.yml`
- `C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\news_state.json`
- `C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\news_delivery_log.jsonl`

## 目的

BloombergとReutersのRSSを定期監視し、新着NEWSがある場合だけDiscordへ配信する。

記事本文ページのクロールは行わない。RSS提供元に「各サイトページへのアクセスは1時間に1回以内」といった制限があるため、監視対象はRSS XMLだけに限定する。

## 対象RSS

| 媒体 | RSS URL |
|---|---|
| Bloomberg | `https://assets.wor.jp/rss/rdf/bloomberg/markets.rdf` |
| Reuters | `https://assets.wor.jp/rss/rdf/reuters/top.rdf` |

## GitHub Actions起動仕様

`C:\Users\mahha\OneDrive\開発\investment_dashboard\.github\workflows\rss_news_discord.yml` は以下のcronで起動する。

```yaml
cron: '55 2,8,14,20 * * *'
```

GitHub ActionsのcronはUTC基準。日本時間では以下になる。

| UTC | JST |
|---:|---:|
| 02:55 | 11:55 |
| 08:55 | 17:55 |
| 14:55 | 23:55 |
| 20:55 | 05:55 |

毎時00分ぴったりはGitHub Actions側の混雑に当たりやすいため、5分前倒しにしている。

## 監視ループ仕様

1回のActions起動内で、RSS監視を継続する。

| 項目 | 値 |
|---|---:|
| RSS確認間隔 | 10分 |
| 1回の起動で監視する時間 | 360分 |
| workflow timeout | 365分 |
| concurrency group | `rss-news-discord` |
| cancel-in-progress | `false` |

`cancel-in-progress: false` により、前回ジョブが残っている場合でも新しいジョブで強制キャンセルしない。状態ファイルのpush競合が起きた場合は、workflow内の `git pull --rebase --autostash` で取り込みを試みる。

## GitHub Actions未起動リスク

GitHub Actionsのscheduleは100%発火保証ではない。現在の設計は「1回起動したら6時間監視する」方式なので、起動失敗が起きた場合は次の起動予定まで空白が出る可能性がある。

ただし、起動時刻をJST `05:55 / 11:55 / 17:55 / 23:55` に分散し、00分ぴったりを避けることで、混雑による遅延や未起動のリスクを下げている。

より堅くする場合は、30分おき起動か、バックアップcronを追加する必要がある。

## Discord配信時間帯

Discordへ送信する時間帯は日本時間 `06:00` から `23:59` まで。

日本時間 `00:00` から `05:59` に取得したNEWSはDiscordへ送信せず、`C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\news_state.json` の `pending_items` に保留する。

日本時間 `06:00` 以降の最初の監視タイミングで、夜間に保留したNEWSと新着NEWSをまとめてDiscordへ送信する。

## RSS取得間隔

実装上の最小取得間隔は10分。

```python
MIN_FETCH_INTERVAL_SECONDS = 10 * 60
```

同一RSS URLについて、前回取得から10分未満の場合は取得をスキップする。

## 日時取得仕様

各RSS itemについて、以下の子要素を日時候補として読む。

- `pubDate`
- `date`
- `updated`
- `published`
- `dc:date` はXML namespaceを除いたローカル名 `date` として読む

日時文字列は以下の順でパースする。

1. RFC 2822形式などを `email.utils.parsedate_to_datetime` で読む
2. ISO 8601形式を `datetime.fromisoformat` で読む
3. タイムゾーンが無い場合はUTCとして扱う
4. 内部保存時はUTC ISO形式へ変換する
5. Discord表示時はJSTへ変換する

## Bloomberg RSSの日時注意点

BloombergのRSSでは、channel全体の更新時刻には実時刻が入る場合がある。

例:

```xml
<dc:date>2026-05-21T20:15:13+09:00</dc:date>
```

一方で、各itemの `dc:date` は日付だけを表す目的で `00:00:00+09:00` になっている場合がある。

例:

```xml
<dc:date>2026-05-21T00:00:00+09:00</dc:date>
```

この場合、Discordに `2026/05/21/00:00` と表示すると「深夜0時に公開された記事」と誤解しやすい。そのため、JST変換後の時刻が `00:00:00` の場合は、時刻を信用せず日付だけ表示する。

表示例:

```text
2026/05/21
独自シタデル・セキュリティーズ、アジアで約60人増員－半数近くが香港
https://www.bloomberg.com/jp/news/articles/2026-05-21/-60-mpew008z?srnd=jp-markets
```

時刻が `00:00:00` 以外の場合は、従来どおり分まで表示する。

```text
2026/05/21/20:15
タイトル
URL
```

## 重複排除仕様

NEWSごとにIDを作り、同じNEWSを再送しない。

ID生成に使う値の優先順:

1. RSS itemの `guid` または `id`
2. RSS itemの `rdf:about`
3. RSS itemの `link`
4. 媒体名とタイトル

最終的なIDはSHA-256でハッシュ化し、媒体名と先頭32文字のdigestを組み合わせる。

保持する既読ID数:

```python
MAX_SEEN_IDS = 800
```

同じIDが `seen_ids` または `pending_items` に存在する場合、そのNEWSは追加しない。

## 状態管理仕様

状態管理ファイル:

`C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\news_state.json`

主な項目:

| 項目 | 内容 |
|---|---|
| `version` | 状態ファイルのバージョン |
| `feeds` | RSS URLごとの最終取得時刻と直近エラー |
| `seen_ids` | 配信済みまたは保留済みNEWSのID |
| `pending_items` | 夜間保留中、または送信失敗で未配信のNEWS |

GitHub Actionsでは、監視ループの各回ごとに `C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\news_state.json` をコミットしてpushする。これにより、次回Actions起動時にも既読・保留状態を引き継ぐ。

## 配信ログ保存仕様

Discordへ実際に送信できたNEWSだけを、分類仕様作成用の素材として永続保存する。

保存先:

`C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\news_delivery_log.jsonl`

形式はJSONL。1行が1NEWSを表す。CSVではなくJSONLにする理由は、後から分類結果、判定理由、複数候補、関連キーワードなどを追加しやすいため。

保存タイミング:

- Discord送信成功後に追記する
- 夜間保留中のNEWSはまだ保存しない
- Discord送信失敗時のNEWSは保存しない
- 同じNEWSが後続の再送で成功した場合、その成功時点で保存する

保存する主な項目:

| 項目 | 内容 |
|---|---|
| `id` | NEWSの重複排除ID |
| `delivered_at` | Discord送信成功時刻。UTC ISO形式 |
| `delivered_at_jst` | Discord送信成功時刻。JST表示 |
| `source` | RSS媒体名 |
| `title` | NEWSタイトル |
| `link` | NEWS URL |
| `published_at` | RSS itemから読んだ公開日時。UTC ISO形式または `null` |
| `published_display` | Discordに表示した日付または日時 |
| `fetched_at` | RSS取得時刻。UTC ISO形式 |
| `classification` | 後で分類するための初期フィールド |

`classification` の初期値:

```json
{
  "status": "unclassified",
  "primary": null,
  "candidates": ["米国株", "日本株", "海外市況", "日本市況"],
  "reason": ""
}
```

分類予定カテゴリ:

| カテゴリ | 想定内容 |
|---|---|
| `米国株` | 米国個別株、米国株セクター、米国企業決算、米国株式市場に直接関係するNEWS |
| `日本株` | 日本個別株、日本株セクター、日本企業決算、日本株式市場に直接関係するNEWS |
| `海外市況` | 米国以外も含む海外マクロ、為替、金利、商品、地政学、海外中央銀行など |
| `日本市況` | 日本の金利、為替、日銀、財政、国内マクロ、日本市場全体に関係するNEWS |

この時点では自動分類は行わない。分類ルールを作る前に、実際に通知されたNEWSを蓄積して、人間が分類仕様を検討しやすい状態を作る。

## Discord通知先

Discord Webhook URLはコードへ直書きしない。

GitHub Actions Secret:

```text
DISCORD_NEWS_WEBHOOK_URL
```

送信時に `https://discordapp.com/api/webhooks/` が指定されていた場合は、`https://discord.com/api/webhooks/` へ正規化する。

## Discord投稿仕様

Discord投稿の先頭にはヘッダーを付ける。

```text
NEWS配信
YYYY-MM-DD HH:mm JST
```

各NEWSは以下の形式で投稿する。

時刻が信頼できる場合:

```text
YYYY/MM/DD/HH:mm
タイトル
URL
```

RSS itemの時刻がJST `00:00:00` の場合:

```text
YYYY/MM/DD
タイトル
URL
```

Discordの1投稿あたりの文字数上限を避けるため、本文は約1900文字以内で分割する。

```python
DISCORD_CONTENT_LIMIT = 1900
```

タイトルは220文字で切り詰める。

## 文字化け対策

Windows実行時は標準出力と標準エラーをUTF-8へ設定する。

```python
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
```

日本語を含むファイルはUTF-8として保存する。Windows Bashの `echo`、`printf`、heredocでは日本語ファイルを作成・更新しない。

## 手動実行

ドライラン:

```powershell
python -B C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\rss_discord_news.py
```

Discord送信あり:

```powershell
$env:DISCORD_NEWS_WEBHOOK_URL = "<Discord Webhook URL>"
python -B C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\rss_discord_news.py --send
$env:DISCORD_NEWS_WEBHOOK_URL = ""
```

テストメッセージ送信:

```powershell
$env:DISCORD_NEWS_WEBHOOK_URL = "<Discord Webhook URL>"
python -B C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\rss_discord_news.py --test-message --send
$env:DISCORD_NEWS_WEBHOOK_URL = ""
```

一時状態ファイルを使ったテスト:

```powershell
python -B C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\rss_discord_news.py --state-path C:\Users\mahha\OneDrive\開発\investment_dashboard\artifacts\rss_news_test_state.json
```

## GitHub Actions手動実行

`RSS NEWS Discord配信` workflowは `workflow_dispatch` に対応している。

入力:

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

## テスト観点

変更時は以下を確認する。

- Python構文チェックが通ること
- `2026-05-21T00:00:00+09:00` が `2026/05/21` と表示されること
- `2026-05-21T20:15:13+09:00` が `2026/05/21/20:15` と表示されること
- `05:59 JST` は配信せず保留すること
- `06:00 JST` は配信対象になること
- `C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\news_state.json` がUTF-8 JSONとして保存されること

## 注意事項

この仕組みは「毎時間必ず通知」ではない。10分おきにRSSを確認し、新着NEWSがある場合だけDiscordへ通知する。新着NEWSがない場合は通知しない。

Reuters RSSは、取得できても `<item>` が0件の場合がある。その場合、取得成功でも配信対象NEWSは0件になる。

GitHub Actions scheduleは遅延または未起動の可能性がある。通知が来ない場合は、GitHub Actionsの `RSS NEWS Discord配信` workflow実行履歴、`C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\news_state.json` の `feeds`、`pending_items`、`seen_ids` を確認する。
