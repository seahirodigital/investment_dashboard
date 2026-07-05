# OCI MooViewスクリーンショットのGitHub Actions連携

## 目的と完了後の状態

GitHubホステッドランナーを一時的にTailscaleへ参加させ、公開インターネットへMooViewを開放せずに、OCI上の株価データ取得と画面撮影を行います。

撮影処理は、OCIのOpenD接続、日本・米国の代表銘柄、上段2チャート用の5分足を順に検証します。右側の「更新」ボタンを押して10秒待ち、直線ではない十分な時系列変動を確認できた画像だけを成功成果物として保存します。一部銘柄の取得失敗は許容します。

この段階では、note記事やDiscordへの画像添付処理は変更しません。

## 実装ファイル

- Workflow: `C:\Users\mahha\OneDrive\開発\investment_dashboard\.github\workflows\oci_mooview_screenshot_debug.yml`
- 撮影スクリプト: `C:\Users\mahha\OneDrive\開発\investment_dashboard\scripts\market\oci_mooview_screenshot.py`
- ローカル検証画像: `C:\Users\mahha\AppData\Local\Temp\investment_dashboard_oci_mooview_capture_20260705_04\oci_mooview_top_charts.png`
- ローカル診断結果: `C:\Users\mahha\AppData\Local\Temp\investment_dashboard_oci_mooview_capture_20260705_04\oci_mooview_capture_result.json`
- Actions成果物: `/home/runner/work/investment_dashboard/investment_dashboard/artifacts/oci_mooview_capture`

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
4. OCI共有設定から上段2チャートの銘柄を読み取ります。
5. 各構成銘柄の5分足150本を先行取得します。
6. 取得できた時系列をPlaywrightのIndexedDBへ投入します。
7. MooViewを再読込し、右側の「更新」ボタンを必ず押します。
8. 10秒待機します。
9. 上段2チャートの70%以上の系列で、10点以上かつ実際の上下動があることを検証します。
10. 条件を満たした場合だけPNGと診断JSONをGitHub Artifactへ保存します。

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
