# note投稿連携

`C:\Users\mahha\OneDrive\開発\investment_dashboard\note\note_blog_publisher.py` は、Discord配信で使う市場材料をnoteブログ向けに再構成し、`C:\Users\mahha\OneDrive\開発\notion2note` の投稿エンジンへ渡します。

## Debug下書き投稿（Gemini生成なし）

保存済みのGeminiレポートを使い、Gemini APIとDiscord投資サマリー配信を飛ばして、noteへの貼り付けテストだけを実行します。

```powershell
python C:\Users\mahha\OneDrive\開発\investment_dashboard\scripts\market\gemini_analysis.py --note-post-mode draft-note-only --note-date 20260619
```

GitHub Actionsでは `Daily Market Analysis (Gemini)` の `Run workflow` から `note_post_mode=draft-note-only` を選びます。初期値も `draft-note-only` です。

## Debug公開直前投稿

公開直前まで進め、最後の「投稿する」は押さない確認モードです。

```powershell
python C:\Users\mahha\OneDrive\開発\investment_dashboard\scripts\market\gemini_analysis.py --note-only --note-dry-run-publish --note-date 20260619
```

## 本投稿

```powershell
python C:\Users\mahha\OneDrive\開発\investment_dashboard\scripts\market\gemini_analysis.py --note-only --note-publish --note-date 20260619
```

## 生成物

Markdown、本文画像、noteサムネイル、投稿結果JSONは `C:\Users\mahha\OneDrive\開発\investment_dashboard\note\generated\<YYYYMMDD>` に保存されます。

## note設定

公開時のタグは `#投資初心者 #投資 #デイトレ #日本株 #日経平均 #米国株 #高配当 #FX #ドル円` と同じ内容を使います。

公開時のマガジンは `日本株の振り返りまとめ ` を選びます。
