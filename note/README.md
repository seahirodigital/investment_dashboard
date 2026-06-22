# note投稿連携

`C:\Users\mahha\OneDrive\開発\investment_dashboard\note\note_blog_publisher.py` は、Discord配信で使う市場材料をnoteブログ向けに再構成し、`C:\Users\mahha\OneDrive\開発\notion2note` の投稿エンジンへ渡します。

## Debug投稿

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
