# JPX 海外投資家動向トラッカー

日本取引所グループ（JPX）の投資部門別売買状況から、海外投資家の差引（買い - 売り）を自動取得・可視化するアプリケーションです。

## 🌟 特徴

- **自動データ取得**: 毎週木曜日18時（JST）に自動実行
- **動的可視化**: リアルタイムで更新されるインタラクティブなグラフ
- **モダンUI**: Tailwind CSS + Reactによる洗練されたデザイン
- **複数の表示形式**: ライン、バー、エリアチャートを切り替え可能
- **期間フィルター**: 全期間/1年/6ヶ月/3ヶ月で絞り込み表示

## 📊 デモ

GitHub Pagesでホストされたライブデモを見る:
`https://[your-username].github.io/[repository-name]/`

## 🚀 セットアップ

### 1. リポジトリのフォーク/クローン

```bash
git clone https://github.com/[your-username]/[repository-name].git
cd [repository-name]
```

### 2. GitHub Pagesの有効化

1. リポジトリの **Settings** → **Pages** に移動
2. **Source** を `gh-pages` ブランチに設定
3. **Save** をクリック

### 3. GitHub Actionsの権限設定

1. **Settings** → **Actions** → **General** に移動
2. **Workflow permissions** で以下を選択:
   - ✅ Read and write permissions
   - ✅ Allow GitHub Actions to create and approve pull requests

### 4. 初回実行

**Actions** タブから `JPX Automation` を選択し、**Run workflow** をクリック

オプション:
- **Debug mode**: `true` を選択すると5件のみ取得（高速テスト用）

## 📁 ファイル構成

```
├── main.py                 # データ取得スクリプト（変更なし）
├── index.html             # Webアプリケーション（新規追加）
├── history.csv            # 取得データ（自動生成）
├── trend.png              # トレンドグラフ（自動生成）
├── requirements.txt       # Python依存関係
└── .github/
    └── workflows/
        └── daily_task.yml # 自動実行設定（更新済み）
```

## 🎨 UI/UX仕様

本アプリは以下の仕様書に基づいて実装されています:

- **カラーパレット**: Slate系（青みがかったグレー）
- **フレームワーク**: React 18 + Tailwind CSS
- **チャートライブラリ**: Recharts
- **デザインコンセプト**: 「Excelのような高密度な情報」を「モダンWebの柔らかさ」で包む

### 主要な特徴

1. **3ペイン同期スクロール**: 左軸・メイン・下軸が同期
2. **カスタムツールチップ**: 詳細情報を見やすく表示
3. **アニメーション**: フェードイン/アップ効果
4. **レスポンシブ**: モバイル・タブレット・デスクトップ対応

## 📈 データ仕様

### 取得データ
- **ソース**: JPX 投資部門別売買状況（金額版）
- **期間**: 2023年〜現在
- **更新頻度**: 毎週木曜日

### CSV形式
```csv
date,balance
2023-12-04,1234567890
2023-12-11,-987654321
...
```

- `date`: YYYY-MM-DD形式
- `balance`: 差引金額（円）
  - 正の値: 買い越し
  - 負の値: 売り越し

## 🔧 カスタマイズ

### 実行スケジュールの変更

`.github/workflows/daily_task.yml` の `cron` を編集:

```yaml
schedule:
  - cron: '0 9 * * 4'  # 毎週木曜日 9:00 UTC
```

### グラフの色変更

`index.html` の以下の部分を編集:

```javascript
// 買い越し色
fill="#4A86E8"  // 青系

// 売り越し色
text-red-500    // 赤系
```

## 🛠️ 技術スタック

### バックエンド（データ取得）
- Python 3.10
- pandas
- requests
- beautifulsoup4
- pdfplumber
- matplotlib

### フロントエンド（可視化）
- React 18
- Recharts
- Tailwind CSS
- PapaParse（CSV解析）

### インフラ
- GitHub Actions（自動実行）
- GitHub Pages（ホスティング）

## 📝 更新履歴

### v2.0.0 - 動的可視化対応
- ✨ Webアプリケーション追加
- 📊 インタラクティブなグラフ表示
- 🎨 モダンなUI/UX
- 📱 レスポンシブデザイン

### v1.0.0 - 初期リリース
- 🤖 自動データ取得
- 📈 静的グラフ生成
- 💾 CSV保存

## 🤝 コントリビューション

1. このリポジトリをフォーク
2. 新しいブランチを作成 (`git checkout -b feature/amazing-feature`)
3. 変更をコミット (`git commit -m 'Add amazing feature'`)
4. ブランチにプッシュ (`git push origin feature/amazing-feature`)
5. プルリクエストを作成

## 📄 ライセンス

MIT License

## ⚠️ 免責事項

- このツールは情報提供を目的としており、投資判断の根拠とするものではありません
- データの正確性については保証しません
- 投資は自己責任で行ってください

## 🔗 関連リンク

- [JPX 投資部門別売買状況](https://www.jpx.co.jp/markets/statistics-equities/investor-type/)
- [Recharts ドキュメント](https://recharts.org/)
- [Tailwind CSS](https://tailwindcss.com/)

---

Made with ❤️ by GitHub Actions
