# 日米仕訳skill

## 目的

RSSニュース通知のタイトルを見て、米国系ニュースは `★`、日本系ニュースは `●` で仕分ける。印の数は重要度を表す。通貨・為替系ニュースは、国別印とは別に `【FX】` を付ける。

## 重要度

- 重要度3: 要人発言、トランプ、パウエル、FRB、FOMC、連銀、金利政策、金利、債券、国債、利回り、関税、中東・イランなど。米国は `★★★`、日本は `●●●`。
- 重要度2: 着工件数、失業保険、雇用統計、CPI、PCE、GDP、ISM、PMI、ADP、短観、機械受注などの経済指標。米国は `★★`、日本は `●●`。
- 重要度1: 個別株、企業、株価指数、市場一般。米国は `★`、日本は `●`。
- FXタグ: 為替、外為、ドル円、円高、円安、ドル高、ドル安、対ドル、ユーロ、ポンド、人民元、ウォンなどは `【FX】`。

## 使うタイミング

- `C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\news_delivery_log.jsonl` の過去ログを分析して、仕訳単語を増やすとき。
- `C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\rss_discord_news.py` のDiscord通知文へ、重要度印と `【FX】` タグを入れるとき。
- 「政策・金利ニュースだけ先に読む」「指標系だけ拾う」「個別株は低優先で見る」という通知改善をするとき。

## ファイル

- ルール: `C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\shiwake_skill\rules.json`
- 仕訳関数: `C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\shiwake_skill\classifier.py`
- テスト生成: `C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\shiwake_skill\generate_test_report.py`
- 軽量テスト結果: `C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\shiwake_skill\testfile.md`
- 全件テスト結果: `C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\shiwake_skill\testfile_full.md`

## 判定仕様

- 同じ国の複数レベルに一致した場合は、最も高いレベルだけを表示する。
- 米国と日本の両方に一致した場合は、両方の印を表示する。例: `★★★●`。
- 通貨系は国別印とは別に `【FX】` を追加する。例: `★★★【FX】`、`●●●【FX】`。
- `米` は強力だが誤検知しやすいため、`備蓄米`、`米価`、`米穀`、`新米`、`古米`、`輸入米`、`コメ`、`ライス` は米国判定から除外する。

## テスト方法

```powershell
python C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\shiwake_skill\generate_test_report.py --log-path C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\news_delivery_log.jsonl --output C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\shiwake_skill\testfile.md --full-output C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\shiwake_skill\testfile_full.md
```

## 本番実装時の呼び出し

`C:\Users\mahha\OneDrive\開発\investment_dashboard\RSS\shiwake_skill\classifier.py` から `classify_news_text` または `format_discord_date_line` を呼び出す。

```python
from shiwake_skill.classifier import format_discord_date_line

date_line = format_discord_date_line(published, item.title)
```

Discord通知では、日時行 `2026/06/04/11:16` を `2026/06/04/11:16　★★★【FX】` のように変換する。
