# note投稿連携

`C:\Users\mahha\OneDrive\開発\investment_dashboard\note\note_blog_publisher.py` は、Discord配信で使う市場材料をnoteブログ向けに再構成し、`C:\Users\mahha\OneDrive\開発\notion2note` の投稿エンジンへ渡します。

## Debug下書き投稿（Gemini生成なし）

保存済みのGeminiレポートを使い、Gemini APIとDiscord投資サマリー配信を飛ばして、noteへの貼り付けテストだけを実行します。

```powershell
python C:\Users\mahha\OneDrive\開発\investment_dashboard\scripts\market\gemini_analysis.py --note-post-mode draft-note-only --note-date 20260619
```

GitHub Actionsでは `Daily Market Analysis (Gemini)` の `Run workflow` から `note_post_mode=draft-note-only` を選ぶと下書きDebugできます。初期値は `publish` のため、通常の手動実行はデータ取得、Gemini分析、note本投稿まで最初から実行します。

## Debug公開直前投稿

公開直前まで進め、最後の「投稿する」は押さない確認モードです。

```powershell
python C:\Users\mahha\OneDrive\開発\investment_dashboard\scripts\market\gemini_analysis.py --note-only --note-dry-run-publish --note-date 20260619
```

## 本投稿

GitHub Actionsでは `Daily Market Analysis (Gemini)` の `Run workflow` から `note_post_mode=publish` を選びます。スマホから初期値のまま実行しても同じ本投稿フローになります。

保存済みレポートだけを使って再投稿するローカル確認用コマンドは以下です。

```powershell
python C:\Users\mahha\OneDrive\開発\investment_dashboard\scripts\market\gemini_analysis.py --note-only --note-publish --note-date 20260619
```

## 生成物

Markdown、本文画像、noteサムネイル、投稿結果JSONは `C:\Users\mahha\OneDrive\開発\investment_dashboard\note\generated\<YYYYMMDD>` に保存されます。

## note設定

公開時のタグは `#投資初心者 #投資 #デイトレ #日本株 #日経平均 #米国株 #高配当 #FX #ドル円` と同じ内容を使います。

公開時のマガジンは `日本株の振り返りまとめ ` を選びます。

## 米国株セクター朝記事

`C:\Users\mahha\OneDrive\開発\investment_dashboard\note\us_sector_note_publisher.py` は、朝の市況Discord通知で作成した4画像（米株ヒートマップ、Fear & Greed Index、SOX指数、日経VIX）と、米国セクター資金流入ランキング上位7件・下位7件の画像を組み合わせてnote記事を投稿します。

GitHub Actionsでは `朝の市況Discord通知` の `Run workflow` から `note_post_mode=draft-note-only` を選ぶと、公開せず下書きでDebugできます。スケジュール実行では4画像をDiscordへ送信したあと、米国ETFデータを更新し、note投稿後にnoteリンクをDiscordへ再通知します。

```powershell
python C:\Users\mahha\OneDrive\開発\investment_dashboard\note\us_sector_note_publisher.py --mode draft-note-only --date 20260623 --market-assets-dir C:\Users\mahha\OneDrive\開発\investment_dashboard\artifacts\morning_market_notification
```

米国株セクター朝記事のMarkdown、本文画像、noteサムネイル、投稿結果JSONは `C:\Users\mahha\OneDrive\開発\investment_dashboard\note\generated\us_sector\<YYYYMMDD>` に保存されます。

米国株セクター朝記事の公開時マガジンは `米国株のニュース・動向まとめ` を選びます。タグとアフィリエイトは既存の日本株note投稿と同じく、`C:\Users\mahha\OneDrive\開発\notion2note\tag.md` と `C:\Users\mahha\OneDrive\開発\notion2note\affiliate_links.txt` を参照します。
