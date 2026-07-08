# Oracleサーバー 日本株セクターDiscord通知

## 目的と完了後の状態

GitHub Actionsのcron遅延に左右されないように、`C:\Users\mahha\OneDrive\開発\investment_dashboard\scripts\market\jp_sector_discord_oracle.py` をOracleサーバー上の `systemd timer` で直接起動します。

完了後は、Oracle側で平日11:35 JSTに `jp_sector_discord_oracle.py --slot midday`、平日15:35 JSTに `jp_sector_discord_oracle.py --slot close` を起動します。安定確認期間中は既存Actionsとの重複通知が発生しますが、Oracle側では `C:\Users\mahha\OneDrive\開発\investment_dashboard\scripts\market\jp_sector_discord_oracle.py` が日付・時間帯ごとの成功マーカーを保存し、Oracle側の同一時間帯内では再送を防ぎます。

## 追加ファイル

| 用途 | ファイル |
|---|---|
| Oracle実行本体 | `C:\Users\mahha\OneDrive\開発\investment_dashboard\scripts\market\jp_sector_discord_oracle.py` |
| systemd service | `C:\Users\mahha\OneDrive\開発\investment_dashboard\deploy\systemd\investment-dashboard-jp-sector-discord@.service` |
| 前場timer | `C:\Users\mahha\OneDrive\開発\investment_dashboard\deploy\systemd\investment-dashboard-jp-sector-discord-midday.timer` |
| 大引けtimer | `C:\Users\mahha\OneDrive\開発\investment_dashboard\deploy\systemd\investment-dashboard-jp-sector-discord-close.timer` |

## Oracle側の前提パス

この手順ではOracleサーバー上のリポジトリを `/home/ubuntu/investment_dashboard` に置きます。別の場所に置く場合は、以下のファイル内にある `/home/ubuntu/investment_dashboard` を実際の完全フルパスへ置き換えます。

- `/home/ubuntu/investment_dashboard/deploy/systemd/investment-dashboard-jp-sector-discord@.service`
- `/home/ubuntu/investment_dashboard/deploy/systemd/investment-dashboard-jp-sector-discord-midday.timer`
- `/home/ubuntu/investment_dashboard/deploy/systemd/investment-dashboard-jp-sector-discord-close.timer`

Oracleの実行ユーザーを `ubuntu` 以外にする場合は、`/home/ubuntu/investment_dashboard/deploy/systemd/investment-dashboard-jp-sector-discord@.service` の `User=ubuntu`、`Group=ubuntu`、`/home/ubuntu/investment_dashboard`、`/home/ubuntu/.cache/ms-playwright` も実際の完全フルパスへ置き換えます。

## 初回セットアップ

### 1. リポジトリ配置

```bash
git clone https://github.com/seahirodigital/investment_dashboard.git /home/ubuntu/investment_dashboard
cd /home/ubuntu/investment_dashboard
```

すでに配置済みの場合は、次のコマンドで最新化します。

```bash
cd /home/ubuntu/investment_dashboard
git pull --ff-only origin main
```

### 2. Python環境

```bash
cd /home/ubuntu/investment_dashboard
python3 -m venv /home/ubuntu/investment_dashboard/.venv
/home/ubuntu/investment_dashboard/.venv/bin/pip install --upgrade pip
/home/ubuntu/investment_dashboard/.venv/bin/pip install -r /home/ubuntu/investment_dashboard/requirements.txt
/home/ubuntu/investment_dashboard/.venv/bin/python -m playwright install chromium
```

Oracle Linux系でChromiumの依存ライブラリが不足する場合は、次を実行します。

```bash
sudo dnf install -y nss atk at-spi2-atk cups-libs libdrm libxkbcommon libXcomposite libXdamage libXrandr mesa-libgbm alsa-lib pango cairo liberation-fonts google-noto-cjk-fonts
```

Ubuntu系の場合は、次を実行します。

```bash
sudo apt-get update
sudo apt-get install -y fonts-noto-cjk
/home/ubuntu/investment_dashboard/.venv/bin/python -m playwright install-deps chromium
```

### 3. Discord Webhook

Discord Webhook URLはGit管理しません。Oracleサーバー上に `/home/ubuntu/investment_dashboard/.secrets/discord.env` を作成します。

```bash
mkdir -p /home/ubuntu/investment_dashboard/.secrets
chmod 700 /home/ubuntu/investment_dashboard/.secrets
vi /home/ubuntu/investment_dashboard/.secrets/discord.env
chmod 600 /home/ubuntu/investment_dashboard/.secrets/discord.env
```

`/home/ubuntu/investment_dashboard/.secrets/discord.env` の内容:

```bash
DISCORD_OPTION_WEBHOOK_URL=https://discord.com/api/webhooks/xxxxxxxx/yyyyyyyy
```

## 手動検証

Discordへ送らずにスクリーンショット生成まで確認します。

```bash
cd /home/ubuntu/investment_dashboard
/home/ubuntu/investment_dashboard/.venv/bin/python /home/ubuntu/investment_dashboard/scripts/market/jp_sector_discord_oracle.py --slot midday --dry-run --allow-weekend --skip-fund-flow --retry-count 1
```

MooView資金フロー撮影も含めて確認します。

```bash
cd /home/ubuntu/investment_dashboard
/home/ubuntu/investment_dashboard/.venv/bin/python /home/ubuntu/investment_dashboard/scripts/market/jp_sector_discord_oracle.py --slot midday --dry-run --allow-weekend --retry-count 1 --mooview-base-url https://mooview-oci.taild87712.ts.net
```

本番Webhookへ実送信する前場テストは、重複防止マーカーを無視するため `--force` を付けます。

```bash
cd /home/ubuntu/investment_dashboard
/home/ubuntu/investment_dashboard/.venv/bin/python /home/ubuntu/investment_dashboard/scripts/market/jp_sector_discord_oracle.py --slot midday --allow-weekend --force --retry-count 1 --mooview-base-url https://mooview-oci.taild87712.ts.net
```

## 自動実行設定

`systemd` へ配置します。`sudo` を使うため、既存の同名unitを置き換える場合は実行中サービスがないことを確認してください。

```bash
sudo cp /home/ubuntu/investment_dashboard/deploy/systemd/investment-dashboard-jp-sector-discord@.service /etc/systemd/system/investment-dashboard-jp-sector-discord@.service
sudo cp /home/ubuntu/investment_dashboard/deploy/systemd/investment-dashboard-jp-sector-discord-midday.timer /etc/systemd/system/investment-dashboard-jp-sector-discord-midday.timer
sudo cp /home/ubuntu/investment_dashboard/deploy/systemd/investment-dashboard-jp-sector-discord-close.timer /etc/systemd/system/investment-dashboard-jp-sector-discord-close.timer
sudo systemctl daemon-reload
sudo systemctl enable --now investment-dashboard-jp-sector-discord-midday.timer
sudo systemctl enable --now investment-dashboard-jp-sector-discord-close.timer
```

次回起動予定を確認します。

```bash
systemctl list-timers --all investment-dashboard-jp-sector-discord-midday.timer investment-dashboard-jp-sector-discord-close.timer
```

ログ確認:

```bash
journalctl -u investment-dashboard-jp-sector-discord@midday.service -n 200 --no-pager
journalctl -u investment-dashboard-jp-sector-discord@close.service -n 200 --no-pager
```

## 実行仕様

| 項目 | 内容 |
|---|---|
| 前場 | 平日 11:35 JST に `investment-dashboard-jp-sector-discord@midday.service` を起動 |
| 大引け | 平日 15:35 JST に `investment-dashboard-jp-sector-discord@close.service` を起動 |
| 再試行 | 失敗時は10分間隔で最大4回 |
| 成功マーカー | `/home/ubuntu/investment_dashboard/artifacts/sector_category_delivery/sector-category-delivery-jp-midday-YYYYMMDD.json` または `/home/ubuntu/investment_dashboard/artifacts/sector_category_delivery/sector-category-delivery-jp-close-YYYYMMDD.json` |
| 出力画像 | `/home/ubuntu/investment_dashboard/artifacts/oracle_sector_category_discord/` |
| Actionsとの関係 | 既存Actionsは変更しない。安定確認中はActions側とOracle側の重複通知を許容する |

## 停止と無効化

Oracle側通知を止める場合:

```bash
sudo systemctl disable --now investment-dashboard-jp-sector-discord-midday.timer
sudo systemctl disable --now investment-dashboard-jp-sector-discord-close.timer
```

一時的に当日分を再送したい場合は、対象マーカーを削除せず、手動実行に `--force` を付けます。これにより履歴を残したまま再送できます。
