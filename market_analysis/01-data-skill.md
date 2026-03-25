# 01. データ取得スキル (Data Fetch)

このスキルは、市場分析に必要な全データを欠損なく取得するためのプロセスです。
以下の表に記載されたPythonスクリプトを、**「必ず1行ずつ別々に」独立して実行**し、すべてのデータを最新状態に更新してください。
※ `run_command` を使用し、実行ディレクトリはダッシュボード直下（`investment_dashboard/`）とすること。

| 実行順 | 実行コマンド | 取得データ・役割 |
|---|---|---|
| 1 | `python scripts/market/fetch_intraday.py` | 主に**個別株（TOPIX100等）のランキング分析**に用いるための、最新リアルタイムパフォーマンスを取得 |
| 2 | `python scripts/market/etf_data_manager.py` | 主に**セクター分析・US指数動向**に用いるための、各種ETFと指数の日次（Daily）データを取得 |
| 3 | `python scripts/jpx/fetch_short_selling.py` | 売買フロー、機関/個人の空売り比率、売買代金データを取得 |
| 4 | `python scripts/jpx/fetch_teguchi.py` | 日経225先物・オプションの手口データ、米系外資の建玉動向を取得 |
| 5 | `python scripts/jpx/fetch_option.py` | 日経225オプションの全限月建玉データを取得 |

**終了条件**:
上記スクリプトすべてがエラーなく完了し、`data/` フォルダ内のJSONファイル群が更新されたことを確認できたら、次の分析ステップ（02）へ進んでください。
