# OCI MooViewスクリーンショットのGitHub Actions連携

## 目的と完了後の状態

GitHubホステッドランナーを一時的にTailscaleへ参加させ、公開インターネットへMooViewを開放せずに、OCI上の株価データ取得と画面撮影を行います。

撮影処理は、OCIのOpenD接続、日本・米国の代表銘柄、4チャート用の5分足を順に検証します。右側の「更新」ボタンを押して10秒待ち、直線ではない十分な時系列変動を確認できた画像だけを成功成果物として保存します。一部銘柄の取得失敗は許容します。

この段階では、note記事やDiscordへの画像添付処理は変更しません。

ローカルTailscaleからの確認にはChrome操作、Tailscale Workload Identity Federation、GitHub Actions Secretは不要です。

## 実装ファイル

- Workflow: `C:\Users\mahha\OneDrive\開発\investment_dashboard\.github\workflows\oci_mooview_screenshot_debug.yml`
- 撮影スクリプト: `C:\Users\mahha\OneDrive\開発\investment_dashboard\scripts\market\oci_mooview_screenshot.py`
- 米国株記事用画像: `C:\Users\mahha\AppData\Local\Temp\investment_dashboard_oci_mooview_capture_20260705_08\us_market_top_charts.png`
- 日本株記事用JPセクター画像: `C:\Users\mahha\AppData\Local\Temp\investment_dashboard_oci_mooview_capture_20260705_08\jp_market_sector_chart.png`
- 日本株記事用半導体画像: `C:\Users\mahha\AppData\Local\Temp\investment_dashboard_oci_mooview_capture_20260705_08\jp_market_semiconductor_charts.png`
- ローカル診断結果: `C:\Users\mahha\AppData\Local\Temp\investment_dashboard_oci_mooview_capture_20260705_08\oci_mooview_capture_result.json`
- Actions成果物: `/home/runner/work/investment_dashboard/investment_dashboard/artifacts/oci_mooview_capture`

## 採用する固定チャート幅

画像ピクセルを圧縮して横幅を変える処理は使用しません。ブラウザー上の左右のチャート列境界を移動し、ResizeObserverでSVG、軸、凡例、折れ線を新しい幅へ再描画してから撮影します。

- 左列 of 固定幅: 483ピクセル
- 右列 of 固定幅: 417ピクセル
- 上段左右 of 固定高: 442ピクセル

この値は、初回確認時の列幅を約2/3へ縮めた採用値です。以後は現在幅や高さへ比率を掛ける計算を行わず、毎回この固定値へ戻します。そのため、実行のたびにチャートが小さくなることはありません。上段左右の高さを揃えることで、下段2チャートの開始位置も一致させます。

生成する画像:

1. 米国株記事用: 上段の `JPセクター/TPX` と `半導体個別/TPX`
2. 日本株記事用: `JPセクター/TPX` 単体
3. 日本株記事用: 下段の `半導体・非鉄金属` と `半導体B/TPX`

## Tailscale接続方式

長期Auth KeyやOAuth Client Secretは使用せず、Tailscale Workload Identity Federationを使用します。GitHub Actionsが発行するOIDCトークンをTailscaleが検証し、Workflow実行中だけ `tag:ci` を持つ一時ノードを作成します。

Workflow終了後、一時ノードは自動的に削除されます。

## Tailscale管理画面の設定

1. Tailscale管理画面の「Trust credentials」を開きます。
2. 「Credential」から「OpenID Connect」を選択します。
3. Issuerは「GitHub Actions」を選択します。
4. Subjectは `repo:seahirodigital/investment_dashboard:*` に限定します。
5. Scopeは `auth_keys` だけを許可します。
6. Tagは `tag:ci` を指定します。
7. 作成後に表示されるClient IDとAudienceを控えます。どちらも秘密値ではありませんが、WorkflowではGitHub Actions Secret経由で参照します。

`tag:ci` がまだ存在しない場合は、既存のTailnet Policyへ次の定義を統合します。既存ポリシー全体を置き換えてはいけません。

```json
{
  "tagOwners": {
    "tag:ci": []
  },
  "hosts": {
    "mooview-oci-ci-target": "100.91.52.116"
  },
  "grants": [
    {
      "src": ["tag:ci"],
      "dst": ["mooview-oci-ci-target"],
      "ip": ["tcp:443"]
    }
  ]
}
```

既存ポリシーに全端末間通信を許可する広いGrantがある場合も、上記の限定Grantを追加しておくと、将来ポリシーを狭めた際の意図が明確になります。

## GitHub Actions Secret

GitHubリポジトリ `seahirodigital/investment_dashboard` の「Settings」→「Secrets and variables」→「Actions」へ、次の2件を登録します。

| Secret名 | 設定する値 | 取得場所 |
|---|---|---|
| `TS_OAUTH_CLIENT_ID` | Workload Identity FederationのClient ID | TailscaleのTrust credentials |
| `TS_AUDIENCE` | Workload Identity FederationのAudience | TailscaleのTrust credentials |

秘密値をコマンド履歴やチャットへ貼り付ける必要はありません。

## 撮影処理

1. Tailscale GitHub ActionがOCIへPingし、Tailnet内の疎通を確認します。
2. `https://mooview-oci.taild87712.ts.net/api/moomoo/status` でOpenD接続を確認します。
3. `JP.1306` と `US.VOO` の実価格と日足を確認します。
4. OCI共有設定から4チャートとバスケットの構成銘柄を読み取ります。
5. 各構成銘柄の5分足150本を先行取得します。
6. 取得できた時系列をPlaywrightのIndexedDBへ投入します。
7. MooViewを再読込し、右側の「更新」ボタンを必ず押します。
8. 10秒待機します。
9. 4チャートそれぞれの70%以上の系列で、10点以上かつ実際の上下動があることを検証します。
10. 左右 of チャート列境界を採用済みの固定幅へ移動し、チャートを再描画します。
11. 米国株記事用1枚と日本株記事用2枚を撮影します。
12. 条件を満たしたPNGと診断JSONだけを保存します。

一部銘柄の502やデータ欠損は許容します。2点だけの放射状直線や、値動きのない系列しか表示されていない場合は失敗として扱います。

## 手動実行

WorkflowがGitHubの既定ブランチへ反映された後、次のコマンドで実行できます。

```powershell
gh workflow run "OCI MooViewスクリーンショットデバッグ" --repo seahirodigital/investment_dashboard -f timeout_seconds=600 -f refresh_wait_seconds=10 -f viewport_width=1800 -f viewport_height=1000
```

実行状況の確認:

```powershell
gh run list --repo seahirodigital/investment_dashboard --workflow "OCI MooViewスクリーンショットデバッグ" --limit 5
```

成功後はGitHub Actions画面の `oci-mooview-screenshot-実行ID` Artifactから、PNGと診断JSONを確認します。

## セキュリティ上の禁止事項

- Tailscale Funnelを有効にしない。
- OCIのTCP `3000`、`8787`、`11111` を公開インターネットへ開放しない。
- SSH秘密鍵、Moomoo認証情報、Tailscale認証情報をWorkflowへ直接記述しない。
- 直線状態の画像を取得成功としてnoteやDiscordへ渡さない。

## 関連GitHub Actionsの実行スケジュールと通知内容

本プロジェクトで自動実行されている GitHub Actions のスケジュール（日本時間 JST 換算）と、それぞれの Discord 通知・処理内容は以下の通りです。

| 実行時間 (JST) | ワークフロー名 (YAMLファイル名) | Discord通知 / 主な処理内容 |
|---|---|---|
| **平日 06:25** | [Sector Category Discord Screenshots](file:///c:/Users/mahha/OneDrive/開発/investment_dashboard/.github/workflows/sector_category_discord.yml)<br>`sector_category_discord.yml` | **【Discord通知】** 米国株セクター相対グラフおよびランキング（上位7件/下位7件）の画像を送信 |
| **平日 06:33** | [朝の市況Discord通知](file:///c:/Users/mahha/OneDrive/開発/investment_dashboard/.github/workflows/morning_market_discord.yml)<br>`morning_market_discord.yml` | **【Discord通知】** 米国株の資金フロー画像と朝の市況（要約）を送信。また、米国株セクターのnote記事も自動投稿 |
| **平日 11:35** | [Sector Category Discord Screenshots](file:///c:/Users/mahha/OneDrive/開発/investment_dashboard/.github/workflows/sector_category_discord.yml)<br>`sector_category_discord.yml` | **【Discord通知】** 日本株の前場振り返りとして、資金フロー画像（OCI経由撮影）、日本株セクターランキング画像、資金流入割合分析の要約を送信 |
| **平日 15:45** | [Sector Category Discord Screenshots](file:///c:/Users/mahha/OneDrive/開発/investment_dashboard/.github/workflows/sector_category_discord.yml)<br>`sector_category_discord.yml` | **【Discord通知】** 日本株の資金フロー画像（OCI経由撮影）、日本株セクターランキング画像、資金流入割合分析の要約を送信 |
| **平日 17:05** | [Daily Short Selling Data Fetch](file:///c:/Users/mahha/OneDrive/開発/investment_dashboard/.github/workflows/daily_short_selling.yml)<br>`daily_short_selling.yml` | **【通知なし】** 空売り比率データを取得・更新し、GitHub Pagesにデプロイ |
| **平日 17:45** | [Daily JPX Participant Analysis & NF Option Fetch](file:///c:/Users/mahha/OneDrive/開発/investment_dashboard/.github/workflows/daily_participant.yml)<br>`daily_participant.yml` | **【Discord通知】** 日経225オプション分析画像（差分、累計、トレンド、権利行使価格別OIなど）を送信 |
| **平日 18:15** | [Daily Market Analysis (Gemini)](file:///c:/Users/mahha/OneDrive/開発/investment_dashboard/.github/workflows/daily_market_analysis.yml)<br>`daily_market_analysis.yml` | **【Discord通知】** 日本株の振り返りレポートと資金フロー画像を送信。また、日本株振り返りのnote記事も自動投稿 |
| **毎日 16:00**<br>**平日 06:05** | [Daily ETF Sector Analysis](file:///c:/Users/mahha/OneDrive/開発/investment_dashboard/.github/workflows/daily_etf.yml)<br>`daily_etf.yml` | **【通知なし】** 日次ETFデータを取得・更新し、GitHub Pagesへデプロイ |
| **毎日 05:55 / 11:55**<br>**17:55 / 23:55** | [RSS NEWS Discord配信](file:///c:/Users/mahha/OneDrive/開発/investment_dashboard/.github/workflows/rss_news_discord.yml)<br>`rss_news_discord.yml` | **【Discord通知】** 起動から6時間ループし、10分おきにニュースRSS（みんかぶ等）を監視してDiscordに都度配信 |
| **平日日中 / 夜間**<br>（15分間隔） | [Intraday ETF Update](file:///c:/Users/mahha/OneDrive/開発/investment_dashboard/.github/workflows/intraday_etf.yml)<br>`intraday_etf.yml` | **【通知なし】** 日本株（09:00〜15:45 ※昼休み除く）および米国株（22:00〜翌05:30）の取引時間中、15分おきにETFデータを取得・更新しWebダッシュボードへデプロイ |
