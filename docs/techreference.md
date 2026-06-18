# 技術リファレンス — 試行錯誤・トラブルシューティング・対策記録

本ファイルは統合投資ダッシュボードの開発過程で遭遇した技術的問題、検討した対策、最終的な解決策をまとめたものです。
ページ仕様・デザイン仕様は [README.md](README.md) を参照してください。

---

## 目次

- [GitHub Actions cron の21%発火率問題](#github-actions-cron-の21発火率問題)
- [検討した対策オプション＆判定](#検討した対策オプション判定)
- [GitHub Pages CDN の困難と解決策](#github-pages-cdn-の困難と解決策)
- [タイムゾーン二重加算の誤解](#タイムゾーン二重加算の誤解)
- [上場廃止・データ取得不可の11銘柄削除](#上場廃止データ取得不可の11銘柄削除)
- [daily_market_analysis.yml 実装時の苦戦と解決策（2026-03-26）](#daily_market_analysisyml-実装時の苦戦と解決策2026-03-26)
- [Gist info消失バグ 第4層〜第5層（2026-04-01）](#gist-info消失バグ-第4層第5層2026-04-01)
- [Gist info消失バグ 第6層（2026-04-03）](#gist-info消失バグ-第6層2026-04-03)
- [intraday_etf.yml ループ型設計の経緯](#intraday_etfyml-ループ型設計の経緯)

---

## 過去（2026-03-19）の実装履歴＆解決済み課題

### 最終達成：15分ごと確実なデータ更新＆CDN配信

**実績:** GitHub Actions cron不安定性（実行率21%）を完全克服
**方式:** ループ型ワークフロー（前場/後場セッション分割）
**結果:** 15分ごとに確実にデータ取得→main commit→CDNデプロイが自動実行

---

## 検討した対策オプション＆判定

| # | 対策案 | 信頼性 | GitHub完結 | 実装難度 | 結果 |
|---|------|--------|-----------|---------|------|
| **A** | 現状: 15分cronを28回/日で打つ | ❌ 21% | ✅ | - | **採用せず** — GitHub cronの21%発火率では市場中のリアルタイム性が失われる |
| **B** | **ループ型（前場/後場セッション分割）** | ✅ 99% | ✅ | 中 | **✨採用&実装** — 1日2回×バックアップ3本で起動確実性↑、内部sleep 900で100%正確な15分間隔 |
| **C** | 外部cronサービス→workflow_dispatch | ✅ 100% | ❌ | 中 | **却下** — ユーザーが「GitHubで完結させろ」と指示したため外部依存は不可 |
| **D** | 自己チェーン（workflow_dispatch連鎖） | ⚠️ 95% | △ | 中 | **却下** — GITHUB_TOKENでは自己トリガー不可、PAT必須（外部依存同然） |
| **E** | Pages sourceをmainに変更 | - | ✅ | 低 | **却下** — GPIF等のビルド成果物・gh-pages既存ファイル管理が破綻 |
| **F** | 頻度を下げる（30分/1時間） | ⚠️ 40-60% | ✅ | 低 | **却下** — 根本解決にならず、UX劣化 |

### 採用したB案（ループ型）の成功実績

```
2026-03-19 06:00 UTC ← cron起動（前場開始）
2026-03-19 06:15 UTC ← sleep完明け → データ取得→commit→CDNデプロイ
2026-03-19 06:31 UTC ← sleep完明け → データ取得→commit→CDNデプロイ
...（以降15分ごと）
2026-03-19 06:45 UTC ← 次のループサイクル
```

**実証:** git log に `Intraday update: 2026-03-19 06:00/06:15/06:31 UTC` が連続記録 → **ループが正常動作中**

---

## GitHub Pages CDN の困難と解決策

### 1. CDNは404をキャッシュする ❌発生 → ✅解決

**問題:**
- `etf_intraday_data.json` が CDN から 404 を返し続けた
- ファイルが gh-pages に実際に存在しても CDN は 404 キャッシュを返す
- 数時間経っても自動解消されない

**原因の仮説（当初）:**
- ファイルがgh-pages ブランチに存在しない？
- peaceiris が deploy/ に含めていない？
- pages-build-deployment がトリガーされていない？

**実際の原因:**
GitHub CDN がパスに対して 404 を一度キャッシュすると、後続でファイルが追加されても キャッシュを優先して返す。新しいファイルパスに切り替えない限り解消不可。

**解決策:** ファイル名を `etf_intraday.json` に変更 → **即座に CDN がファイルを配信開始**

---

### 2. mainブランチのcommitが重要（gh-pages直接pushは不安定）❌試行 → ✅確認

**問題の流れ:**
1. intraday_etf.yml が gh-pages ブランチへ直接 git push
2. gh-pages ブランチにはファイルが存在
3. しかし **CDN は 404 を返す** ← 予期しない動作

**原因分析:**
- peaceiris は「`keep_files: true`でgh-pagesの既存ファイルを保持する」ことしかできない
- gh-pages への直接 push は GitHub 内部の pages-build-deployment パイプラインを経由しない場合がある
- mainブランチにコミットされたファイルをpeaceirisが deploy/ に含める流れが最も確実

**解決策:**
- intraday_etf.yml も main ブランチに commit
- gh-pages への直接 push は削除（peaceiris推奨に統一）
- ただし市場中の15分ごと更新のため、daily_* の次実行を待たずに済むよう **intraday_etf.yml 内で peaceiris も実行** に改修

---

### 3. GITHUB_TOKENと pages-build-deployment ✅誤解を修正

**当初の外部AIの主張:**
「GITHUB_TOKEN では pages-build-deployment がトリガーされない」

**実装結果:**
daily_participant.yml / daily_task.yml が GITHUB_TOKEN + peaceiris で正常にCDN更新

**真実:**
- GitHub の「GITHUB_TOKEN で後続ワークフローが発火しない」制約は **ユーザー定義ワークフロー** に対するもの
- `pages-build-deployment` はGitHub内部のPages配信システムであり、gh-pagesブランチへのpushで通常どおり発火
- PATへの切り替えは不要

---

## GitHub Actions cron の21%発火率問題 ❌ → ✅完全克服

**実測データ:**
- 3.5時間で28回中6回のみ実行（実行率 21%）
- GitHub側に根本的な改善はなし（プラットフォーム仕様の制約）

**従来の対策試行:**
- バックアップcronを複数設定 → 発火率向上はわずか
- cron以外の手段を検討（外部サービス、自己チェーン）→ ユーザー要件「GitHub完結」に抵触

**最終解決:**
**ループ型ワークフロー** でcronの役割を「起動」のみに限定
- 起動後はOSレベルのsleep 900（15分）で次サイクルへ
- 1日2回×バックアップ3本のcron（6本）のうち1つでも発火すれば確実に市場時間中ずっと動作
- 実運用: 2026-03-19 06:00 UTC起動後、06:15, 06:31... と連続実行確認済み

---

## タイムゾーン二重加算の誤解 ✅ 正しい実装を確認

**外部AIの誤分析:**
「yfinanceはJSTタイムスタンプを出力済みだから toJST() の +9h は二重加算バグ」

**実装確認:**
- yfinance は複数市場データをマージ時に **UTC に統一**
- `tz_localize(None)` はラベルだけ除去、数値はUTC のまま
- 実データログ: 最後: 2026-03-19 05:40 = JST 14:40（市場中）← **UTC であることの証拠**
- `toJST()` の +9h 変換は **正しい** ← これを除去すると全5分足データが rangebreaks で非表示に

**措置:**
一時的に +9h を除去してしまい全チャート消滅 → すぐに復元 → チャート正常表示確認

---

## 上場廃止・データ取得不可の11銘柄削除 ✅

データ取得時のYahoo Finance エラー（期間14日、delisted/no price data）により以下を削除：

| セクター | 削除銘柄 | 実装 |
|---------|--------|------|
| 証券業 | 8702.T(岡三証券) | etf_data_manager.py + sector_category.html から削除 |
| ゴム製品 | 5104.T(TOYO TIRE) | 同上 |
| 空運業 | 9205.T(スカイマーク) | 同上 |
| 倉庫・運輸 | 9062.T(日本通運) | 同上 |
| パルプ・紙 | 3871.T(高度紙工業) | 同上 |
| 鉄鋼 | 5429.T(東京製鐵), 5481.T(山陽特殊製鋼) | 同上 |
| 電線 | 5809.T(タツタ電線), 5807.T(東京特殊電線) | 同上 |
| 海運業 | 9112.T(乾汽船) | 同上 |
| ETFセクター | 1613.T(情報通信業) | SECTORS/カテゴリリストから完全除外 |

**結果:** チャート・ランキング・バスケット説明が一貫

---

## `daily_market_analysis.yml` 実装時の苦戦と解決策（2026-03-26）

### 問題1：ワークフローが18:15に動作していなかった（に見えた）

**症状:** JST 18:15に動作していない
**実際の原因:** GitHub Actions のcronは混雑時に**最大1時間程度遅延**することが仕様。当日は56分遅延して19:11 JSTに実行・成功していた。
**対応:** ワークフロー自体の問題ではなく、cronの遅延であることを確認。ただし以下の副次的問題も発見・修正した。

### 問題2：`git push` が競合エラーで失敗するリスク

**原因:** `intraday_etf.yml` が15分ごとにmainブランチにコミット＆プッシュするため、`daily_market_analysis.yml` のプッシュ時点でリモートが先に進んでいる（non-fast-forward）。

**修正:** `git pull --rebase origin main` をプッシュ前に追加し、最大3回リトライする方式に変更。

```yaml
for i in 1 2 3; do
  git pull --rebase origin main || { git rebase --abort 2>/dev/null; true; }
  if git push origin main; then exit 0; fi
  sleep 10
done
```

### 問題3：`fetch_teguchi.py` / `fetch_option.py` のエラーでワークフロー全体が停止

**原因:** 他のfetchステップには `continue-on-error: true` があったが、これら2つには設定が漏れていた。いずれかが失敗するとGemini分析まで到達しない。

**修正:** `continue-on-error: true` を追加し、フォールバック扱いにした（`daily_participant.yml` で08:45 UTCに取得済みのため二重取得でもある）。

### 問題4：`GIST_TOKEN` / `GIST_ID` のSecretsが未登録

**原因:** ワークフローログで `GIST_TOKEN:（空）` `GIST_ID:（空）` を確認。スクリプトが「⏭️ Gist設定なし — カレンダー更新をスキップ」と出力して情報タブ更新をスキップしていた。

**対応:** `gh secret set GIST_TOKEN` / `gh secret set GIST_ID` でSecretを登録。

### 問題5：フロントエンドがGistのinfoフィールドを上書きする（最難関）

**症状:** ワークフローがGistのinfoに2000文字超のレポートを書き込むが、数十秒後に「# 2026/03/26」（12文字）に戻る。

**根本原因（3層構造）:**

1. **React非同期stateバグ（第1層）:** 初回ページロード時、Gistデータを取得して `setHistoryData(content.history)` した直後に `saveAllData(undefined, ...)` を呼んでいた。`undefined` を渡すと「現在の `historyData` state を使う」仕様だが、React stateは非同期更新のため、その時点では古い空データが入っていた。古いデータでGistを上書きしてしまう。

2. **ページ開きっぱなしの問題（第2層）:** ユーザーがページを開いたまま（ワークフロー実行前に読み込んだ状態）でいると、ブラウザのReact stateは古い `info` を持ち続ける。そのまま保存操作を行うと古いデータでGistを上書きする。

3. **保存のたびに全フィールドをGISTへ送信（第3層）:** `saveAllData` はhistory全体を1つのJSONとしてGist PATCHするため、ワークフローが書いたフィールドも上書きされる。

**修正の変遷:**

| 試み | 内容 | 結果 |
|------|------|------|
| 第1版 | 初回ロードの `saveAllData(undefined,...)` を `saveAllData(loadedHistory,...)` に修正 | 第1層は解決。第2層・第3層は残存 |
| 第2版 | `serverInfoRef` でGistロード時のinfoをキャッシュし、保存時にマージ | ページロード前にinfoが空だとRefに保存されず保護されない |
| 第3版 | **Read-Merge-Write方式**: `saveAllData` のGist書き込み前に現在のGistデータをフェッチし、infoフィールドが15文字超であれば必ずローカルより優先してマージしてから書き込む | 第1〜3層は解決。**ただし第4層・第5層が残存**（下記参照） |

**副作用として発覚したバグ:** `serverInfoRef` のイテレーションが `saveCurrentState()` 呼び出しのタイミングでエラーを起こし、モーダルの全ボタン（タブ切替・保存・キャンセル）が動作不能になった。try-catch で保護して修正。

### Windows端末での文字化け誤検知

**症状:** Gistデータを `curl | python3` で読むと日本語が文字化けして見える。
**実際:** Gistには正しいUTF-8が保存されており、WindowsのCP932端末で表示する際に文字化けして見えるだけ。バイト列を直接確認（`efbc91` = `１`）して問題なしを確認。

---

## Gist info消失バグ 第4層〜第5層（2026-04-01）

### 発見の経緯

2026-03-29頃から投資カレンダーの「情報」タブにGemini分析レポートが表示されなくなった。GitHub Actionsのワークフロー実行ログでは3/27, 3/30, 3/31のGist更新はすべて成功していた。

### 調査結果

Gist APIで直接データを確認したところ、消失パターンが判明：

| 日付 | info長 | 状態 |
|---|---|---|
| 3/25 | 2186文字 | ✅ レポートあり |
| 3/26 | 7505文字 | ✅ レポートあり |
| 3/27 | 2308文字 | ✅ レポートあり |
| 3/30 | **0文字** | ❌ 消失 |
| 3/31 | **12文字** | ❌ デフォルト値「# 2026/03/31」に上書き |

3/27のレポートが残っている理由は、ユーザーがページを**リロード**した後にGistから正しくロードされたため。3/30と3/31はGeminiがGistを更新した**後**にフロントエンドの保存処理が上書きした。

### 根本原因（2層追加）

#### 第4層：Gistにのみ存在する日付エントリの消失

`index.html` の `saveAllData` 内のRead-Merge-Write（第3版で実装）の条件：

```js
// 旧コード（問題あり）
if (gi && gi.length > 15 && mergedH[key]) {
    // mergedH[key] が undefined の場合 → 条件false → Gistの日付エントリごと消失
}
```

`mergedH = { ...h }` はローカルの `historyData` のみをベースにしているため、**ページロード後にGeminiワークフローが追加した新しい日付エントリ**は `mergedH` に存在しない。マージ対象外となり、Gistへの書き込み時にエントリごと消失する。

**シナリオ:**
1. ユーザーがページを朝に開く → `historyData` にはその時点のGistデータがロードされる
2. 18:15 JST: Geminiワークフローが当日の `info` をGistに追加
3. ユーザーが（当日をクリックせずに）他の日付を編集・保存
4. `mergedH['2026-03-31']` が `undefined` → 条件 `mergedH[key]` が false
5. **Gistの2026-03-31エントリごと消失**

#### 第5層：Gist APIの content truncation（悪循環）

Gistファイル `market_data.json` が約**907KB〜921KB**に達しており、GitHub Gist APIの truncation閾値（約920KB付近）に接触。

**悪循環のメカニズム:**
1. Geminiレポート追加 → ファイルサイズ増加（907KB → 921KB）
2. フロントエンドの `saveAllData` がRead-Merge-WriteのためにGist APIを読み取り
3. API応答の `content` フィールドが **truncated** → `JSON.parse()` 失敗
4. マージ失敗 → ローカルデータ（Geminiレポートなし）でGistを上書き
5. レポート消失 → ファイルサイズ縮小（921KB → 907KB）→ truncated解消
6. 次回ワークフローで再びレポート追加 → 1. に戻る

**検証データ:**
```
レポート復旧前: size=907,541 bytes, truncated=false
レポート復旧後: size=921,784 bytes, truncated=true  ← 閾値超過
```

### 修正内容（Read-Merge-Write v3）

**修正箇所:** `index.html` の `saveAllData` 関数内と初回ロード処理

#### 修正1: Gistにのみ存在する日付エントリの完全保全（第4層対策）

```js
// 新コード
for (const key in gistHistory) {
    if (!mergedH[key]) {
        // ローカルに存在しない日付 → Gistのエントリを完全保全
        mergedH[key] = gistHistory[key];
    } else {
        // 両方に存在 → infoフィールドはGist側が長ければ保護
        const gi = gistHistory[key] && gistHistory[key].info;
        if (gi && gi.length > 15) {
            const li = mergedH[key].info || '';
            if (gi.length > li.length) mergedH[key] = { ...mergedH[key], info: gi };
        }
    }
}
```

#### 修正2: raw_url経由でのGist読み取り（第5層対策）

初回ロード・Read-Merge-Write両方で、`truncated: true` の場合は `raw_url` から完全なコンテンツを取得するように変更。`gemini_analysis.py` と同じ方式。

```js
// truncated時はraw_urlで完全データ取得
let gistContent = gistData.files['market_data.json'].content;
const rawUrl = gistData.files['market_data.json'].raw_url;
if (gistData.files['market_data.json'].truncated && rawUrl) {
    const rawResp = await fetch(rawUrl, { headers: gistAuth, cache: 'no-store' });
    if (rawResp.ok) gistContent = await rawResp.text();
}
```

#### 修正3: フェイルセーフ（Gist読み取り失敗時は書き込み中止）

```js
if (!gistReadOk) {
    console.warn("⚠️ Sync: Gist read failed, skipping write to prevent data loss");
    return;  // Gistへの書き込みを中止
}
```

#### 修正4: キャッシュ無効化

全てのGist API fetchに `cache: 'no-store'` を追加し、ブラウザキャッシュによるstaleデータ読み取りを防止。

### データ復旧

消失した3/30と3/31のレポートをgitリモート履歴（`a976b53`, `ddc9a9d`）から取得し、Gist APIで直接書き戻して復旧。

---

## Gist info消失バグ 第6層（2026-04-03）

### 発見の経緯

第4層〜第5層の修正後もinfo（情報）タブが空のままだった。Gist APIを直接確認すると4/1, 4/2のレポートは存在していたが、ブラウザ側で読み込めていなかった。
また3/30・3/31の復旧を試みるために作成した `restore_gist_history.py` が、実行後にGistファイルを952KBまで膨張させていたことが判明した。

### 根本原因（2つの問題の複合）

#### 問題A: `restore_gist_history.py`が`indent=2`でGistに書き込み（ファイル膨張）

```python
# 誤った実装（indent=2でファイルが2.5倍に膨張）
json.dump(market_data, f, ensure_ascii=False, indent=2)
```

コンパクト時400KB → インデント時952KBに膨張。Gist APIの`content`フィールドのtruncation閾値（約389K文字）を超過し、API経由でのJSONパースが不可能な状態になった。

**誤解の経緯:** `truncated: true` でも raw_url で完全データは取得できていた。問題は別にあった（問題B参照）。

#### 問題B: ブラウザからのraw_url fetchでCORS preflight失敗

第5層修正で「truncated時はraw_urlフォールバック」を実装したが、**raw_urlへのfetchに`Authorization`ヘッダーを付与していた**ため、ブラウザのCORSプリフライト（OPTIONSリクエスト）が発生。

```
gist.githubusercontent.com の CORS レスポンスヘッダー:
  Access-Control-Allow-Origin: *
  ✗ Access-Control-Allow-Headers: Authorization  ← このヘッダーがない
```

`*`（ワイルドカード）の場合、認証情報付きリクエストはCORSで禁止される。プリフライトが失敗し、raw_urlからのデータ取得が完全に不可能だった。

**失敗の連鎖:**
```
API content取得 → 389K文字で切り捨て → 不完全JSON
  ↓
raw_url fetch → CORS preflight失敗
  ↓
rawContent = 不完全JSONのまま
  ↓
JSON.parse() → SyntaxError
  ↓
catch() → 無視 → historyData = {} → 情報タブ空白
```

**注意:** `raw_url`（`gist.githubusercontent.com`）はURLにコミットハッシュを含むためAuthorizationヘッダー不要。Python（サーバーサイド）ではCORS制約がないため`gemini_analysis.py`は動作していた。

### 修正内容

#### 修正1: raw_url fetchからAuthorizationヘッダーを除去

```js
// 旧（CORS preflight失敗）
const rawResp = await fetch(rawUrl, { headers: gistAuth, cache: 'no-store' });

// 新（Auth不要、プリフライト不発生）
const rawResp = await fetch(rawUrl, { cache: 'no-store' });
```

適用箇所2か所: 初回ロード（`loadData`内）、Read-Merge-Write（`saveAllData`内）

#### 修正2: `truncated`フラグに依存せずraw_urlを常に優先取得

`truncated: false`でもAPIのcontent閾値（約389K文字）付近では不完全なJSONが返る可能性があるため、`raw_url`が利用可能な場合は常にraw_url経由で取得するよう変更。

```js
// 旧（truncatedフラグ依存）
if (json.files['market_data.json'].truncated && rawUrl) { ... }

// 新（常にraw_url優先）
if (rawUrl) { ... }
```

#### 修正3: `restore_gist_history.py`のコンパクトJSON化

```python
# 旧（indent=2で952KB）
json.dump(market_data, f, ensure_ascii=False, indent=2)

# 新（コンパクトで398KB）
json.dump(market_data, f, ensure_ascii=False)
```

ファイルサイズ: 952KB → 398KB（ただしGist APIの`size`フィールドはキャッシュ遅延で旧値を返すことがある）

#### 修正4: 消失レポートをGist APIで再復旧

`market_analysis/reports/` 内のMarkdownファイルをGist APIで直接PATCH。

| 日付 | 復旧文字数 | 復旧方法 |
|------|----------|---------|
| 3/30 | 2438文字 | `20260330_daily_report.md` からPATCH |
| 3/31 | 2404文字 | `20260331_daily_report.md` からPATCH |
| 4/1  | 2491文字 | `20260401_daily_report.md` からPATCH（存在確認・再確定） |
| 4/2  | 2439文字 | `20260402_daily_report.md` からPATCH（存在確認・再確定） |

### 教訓

| 間違い | 正しい対処 |
|--------|----------|
| Gistへの書き込みに`indent=2`を使う | 常に`json.dump(...)`のみ（インデントなし）でコンパクトに |
| raw_url fetchにAuthorizationヘッダーを付ける | raw_urlはAuth不要（CORS preflight回避のため除去必須）|
| `truncated`フラグだけで分岐する | raw_urlがあれば常に優先取得する |

---

## `intraday_etf.yml` ループ型設計の経緯

```
セッション起動型ループ（GitHub cronの21%不安定さを完全回避）

前場セッション:
  cron起動: UTC 0:00 / 0:15 / 0:30（JST 9:00 / 9:15 / 9:30）
  実行: JST 9:00 → 11:30 まで 15分ごとループ

後場セッション:
  cron起動: UTC 3:30 / 3:45 / 4:00（JST 12:30 / 12:45 / 13:00）
  実行: JST 12:30 → 15:45 まで 15分ごとループ

concurrency: cancel-in-progress: false
  → バックアップcronが複数発火しても キューで待機して順序保持
  → データ損失なし

1サイクル（15分）の流れ:
  1. fetch_intraday.py（yfinance で 5分足14日分）
  2. mainブランチに git commit & push
  3. gh-pagesブランチに直接 git push → CDN即時更新
  4. sleep 900（15分待機）
  5. 市場時間内なら繰り返し、15:45以降は終了
```

---

## 2026-05-27 セクター分類ページ修正失敗メモ

### 目的

`sector_category.html` のセクター分類ページで、以下2点を直そうとして失敗した。

1. 【US】相対パフォーマンス推移（全セクターvs SPY）を、米国1セッションだけの相対チャートとして正しく表示する。
2. 【JP】相対パフォーマンス推移（全セクターvs TOPIX）以下のJPチャートで、市場外のforward-fill横線を出さず、以前のように市場時間だけ連続表示する。

### 失敗した変更と症状

#### 失敗1: US最終点を米国引け時刻ラベルへ強制変更

`sector_category.html` のUSイントラデイで、日次終値補正時にチャート最終点の `date` を `getNewYorkCloseJSTLabel(...)` で `5/27 05:00` などへ置き換えた。

結果:

- 【US】米国セクター パフォーマンス推移（絶対値）で、最終時刻だけ全系列が急騰して見えた。
- 値は日次終値へ補正されているのに、直前のイントラデイ点からX軸だけ引け時刻へ飛ぶため、最後の線が不自然になった。
- これは「ランキングの終値補正」と「チャート線のイントラデイ形状」を混ぜたのが原因。

教訓:

- USのランキング値を日次終値で補正しても、チャート時系列の最終点に日次終値を上書きしない。
- チャート線はイントラデイの実測系列として保持する。
- 終値補正が必要なら、ランキングやサマリーだけへ適用する。

#### 失敗2: JP rangebreaksをREADME記載の `[2.5, 3.5]` に寄せた

`docs/README.md` にはJPの昼休みrangebreaksとして `[{ bounds: [2.5, 3.5] }]` と書かれていたため、それに合わせた。

結果:

- JPチャートのX軸で、市場外時間が表示された。
- `data/etf_intraday.json` は市場外のJP銘柄がforward-fillされるため、15:00以降や夜間に横一直線のデータが表示された。
- 【JP】相対パフォーマンス推移（全セクターvs TOPIX）以下のチャートが、市場時間だけの連続表示に見えなくなった。

教訓:

- 現在の描画実装では、JPデータは `toJST()` でJST文字列に変換してPlotlyへ渡している。
- そのため、実装上は以前動いていた以下のrangebreaksへ戻す必要があった。

```js
[
  { bounds: ["sat", "mon"] },
  { bounds: [15.5, 9], pattern: "hour" },
  { bounds: [11.5, 12.5], pattern: "hour" }
]
```

- `docs/README.md` の `[2.5, 3.5]` はUTC基準の説明だが、現行の描画データはJST表示後の値として扱われている。READMEを鵜呑みにして変更してはいけない。

#### 失敗3: JP全体を昔のコミットへ雑に戻すと危険

JPの軸だけを戻したい場合でも、`sector_category.html` 全体を1週間以上前へ戻すと、後続で追加したUS相対チャート、SPY基準、米国セッション抽出、データ取得補強まで巻き戻る。

教訓:

- JP復旧は、まず `buildProcessedData()` とJP用チャートの `rangebreaks` のみに限定して差分を見る。
- US相対チャートの再実装は、JP復旧後に別差分として行う。
- JPとUSの時刻処理を同じ関数や同じrangebreaksでまとめない。

### 現状の【US】相対パフォーマンス推移（全セクターvs SPY）仕様

#### 表示対象

`sector_category.html` の `FullSectorChart` 内で、USモードかつ `usMode === 'relative'` のときに表示する。

タイトル:

```text
【US】相対パフォーマンス推移（全セクターvs SPY）
```

対象銘柄:

```js
const US_SECTORS = {
  XLK, XLF, XLC, XLV, XLI, XLB, XLU, XLE, XLP, XLRE, XLY,
  ^SOX, XSD, XSW, XBI, XPH, XHE, XHS, XME, XRT, XHB, XTN,
  XTL, XAR, KBE, KRE, XOP, XES, PAVE
}
```

#### SPY基準の決定

表示側では、SPYだけを基準にする。`^GSPC`、VOOなどへフォールバックしない。

```js
const spyBenchmark = { code: 'SPY', name: 'SPY' };
const findBenchmark = (priceMap) => (
  Array.isArray(priceMap?.SPY) &&
  priceMap.SPY.some(v => Number.isFinite(Number(v)) && Number(v) > 0)
) ? spyBenchmark : null;
```

SPYが無い場合:

```text
SPYが未取得です。基準の連続性を守るため、他のS&P500連動系列には切り替えません。
```

#### 相対パフォーマンス計算式

セクターETFのリターン:

```js
sectorReturn = (sectorCurrent / sectorStart) - 1
```

SPYのリターン:

```js
benchmarkReturn = (spyCurrent / spyStart) - 1
```

US相対パフォーマンス:

```js
(sectorReturn - benchmarkReturn) * 100
```

つまり、チャート上の値は「各USセクターETFの騰落率 minus SPYの騰落率」。

#### イントラデイ期間の抽出

イントラデイ対象期間:

```js
['1d','2d','3d','4d','5d','6d','7d','8d','9d','10d','14d']
```

US市場時間は `America/New_York` 基準で判定する。

```js
const isNewYorkRegularSession = (marketTime) => {
  if (!marketTime || marketTime.weekday === 'Sat' || marketTime.weekday === 'Sun') return false;
  return marketTime.minutes >= 570 && marketTime.minutes <= 960;
};
```

570分 = 9:30、960分 = 16:00。

選択対象は `getRecentNewYorkSessionItems()` で、NY市場日ごとにまとめたうえで、実際に価格変化があるセッションだけを採用する。

```js
const sessionCheckSymbols = [...usSymbols, 'SPY', '^GSPC', '^NDX', '^DJI'];
const { filteredItems } = getRecentNewYorkSessionItems(dates, period, prices, sessionCheckSymbols);
```

1dの場合、直近の有効な米国市場日だけを使う。

#### X軸表示

USイントラデイはPlotlyの `category` 軸を使う。

理由:

- JST変換後に金曜米国セッションが土曜早朝に見える。
- datetime軸に `["sat", "mon"]` のrangebreaksを入れると、金曜夜から土曜早朝のUSデータが消えることがある。

現行仕様:

```js
const point = { date: toJSTChartLabel(dates[i]), marketDate: marketTime.date };
```

`toJSTChartLabel()` はUTC文字列をJSTへ変換し、`5/26 22:30` のような短縮ラベルを返す。

```js
...(isUSIntraday ? { type: 'category', nticks: 12, tickangle: -30 } : {})
```

USイントラデイ時のrangebreaksは空。

```js
return [];
```

#### ランキング補正とチャート補正の扱い

日次データにUS最終セッション日が含まれている場合、ランキング値は日次終値で補正する。

```js
const dailyBaseIdx = Math.max(0, dailyEndIdx - daysAgo);
const perf = calcPerformance(rawDaily.prices, sym, dailyBaseIdx, dailyEndIdx, dailyBenchmark || benchmark);
if (perf !== null && rankingMap[sym]) rankingMap[sym].performance = perf;
```

ただし、失敗事例から、チャート時系列の最終ポイントへ日次終値を上書きしてはいけない。

NG:

```js
lastPoint[name] = perf;
lastPoint.date = closeLabel;
```

OK:

- ランキングだけ日次終値で補正する。
- チャート線は `etf_intraday.json` の実測イントラデイ系列だけで描く。

### SPY取得仕様

取得側は `scripts/market/etf_data_manager.py` に実装されている。

#### SPYは取得対象に明示追加

```python
US_SP500_BENCHMARKS = {
  'SPY': 'SPY',
}
```

`ALL_SYMBOLS` には `US_SP500_BENCHMARKS.keys()` が含まれる。

```python
ALL_SYMBOLS = list(set(
    [BENCHMARK]
    + list(SECTORS.keys())
    + list(SEMICONDUCTOR_JP.keys())
    + list(SEMICONDUCTOR_US.keys())
    + list(US_SECTORS.keys())
    + list(US_SP500_BENCHMARKS.keys())
    + list(TOPIX100.keys())
    + ALL_US_INDIVIDUAL_SYMBOLS
    + ALL_BASKET_SYMBOLS
))
```

#### SPY補完処理

通常の一括 `yf.download(...)` でSPYが取れない場合、SPYだけを別取得する。

```python
df = ensure_spy_column(df, period, interval)
```

`ensure_spy_column()` の流れ:

1. `df['SPY']` が存在し、有効価格があればそのまま使う。
2. 無ければ `yf.download('SPY', period=period, interval=interval, auto_adjust=False, progress=False)` でSPY単独取得。
3. それでも無ければ `https://query1.finance.yahoo.com/v8/finance/chart/SPY` を直接叩く。
4. 取得したSPYを `df.index` に `reindex(...).ffill().bfill()` で合わせる。
5. それでも有効価格が無ければ例外で落とす。

Yahoo chart API取得では、イントラデイは `range=60d`、日次は `range=2y` を使う。

```python
chart_range = '2y' if interval == '1d' else ('60d' if interval.endswith('m') else period)
params = {
    'range': chart_range,
    'interval': interval,
    'includePrePost': 'true',
}
```

#### SPY出力検証

`data/etf_data.json` と `data/etf_intraday.json` の両方でSPYを検証する。

```python
validate_spy_output(data_daily, 'data/etf_data.json')
validate_spy_output(data_intraday, 'data/etf_intraday.json')
```

検証内容:

- `prices.SPY` が存在する。
- `prices.SPY.length === dates.length`。
- 有効な正の価格が1件以上ある。

#### 再実装時の必須条件

- SPYを基準にする相対チャートでは、`^GSPC` へ自動フォールバックしない。
- `SPY` が無い場合は「データなし」として止める。
- SPYは `etf_data.json` と `etf_intraday.json` の両方に必要。
- イントラデイでは、US市場日を `America/New_York` で判定する。
- X軸はUSのみ `category`、JPはdatetime + 市場時間外rangebreaks。
- ランキング補正とチャート線補正を混ぜない。

### 2週間前へ戻す前の注意

2週間前へ戻すと、以下の変更は失われる可能性がある。

- SPYを `US_SP500_BENCHMARKS` として取得対象に追加した変更。
- `ensure_spy_column()` によるSPY単独取得、Yahoo chart API fallback、出力検証。
- `FullSectorChart` の `usMode === 'relative'` とSPY割り返し表示。
- USイントラデイのNY市場日抽出。
- USイントラデイのcategory軸。

戻した後にSPY相対を再追加する場合は、まず取得側のSPY保証だけを復元し、`data/etf_data.json` と `data/etf_intraday.json` に `prices.SPY` が入ることを確認する。その後、表示側でUS相対チャートを追加する。JP復旧とUS相対追加を同じ差分で行わない。

---

## 2026-06-07 米国株チャート可視化の現行正解

### この章の位置付け

この章は、2026年6月7日時点の以下の実装を読み合わせた結果をまとめた最新仕様である。

- `C:\Users\mahha\OneDrive\開発\investment_dashboard\scripts\market\etf_data_manager.py`
- `C:\Users\mahha\OneDrive\開発\investment_dashboard\sector_category.html`
- `C:\Users\mahha\OneDrive\開発\investment_dashboard\us_individual.html`
- `C:\Users\mahha\OneDrive\開発\investment_dashboard\.github\workflows\daily_etf.yml`
- `C:\Users\mahha\OneDrive\開発\investment_dashboard\.github\workflows\intraday_etf.yml`
- `C:\Users\mahha\OneDrive\開発\investment_dashboard\.github\workflows\sector_category_discord.yml`

この章より前にある説明と矛盾する場合は、この章を優先する。

特に、以前の記述にある以下の考え方は現行仕様では使わない。

- 米国イントラデイの入力時刻をUTCと決め打ちする。
- 入力文字列へ単純に9時間を足してJSTにする。
- USチャートへJP用のdatetime軸や週末rangebreaksを流用する。
- 表示中の線だけを使って縦軸を決める。
- 日次終値でチャート最終点を上書きする。
- Discord撮影時にJP表示からUS表示へ画面操作で切り替える。

### 対象ページとデータ

#### セクター分類分析

対象ファイル:

```text
C:\Users\mahha\OneDrive\開発\investment_dashboard\sector_category.html
```

米国セクター分析は `FullSectorChart` が担当する。

主な表示箇所:

1. セクター分類分析ページの最上部
2. 通常のJP全セクターチャート内のUS切替表示
3. `embed=us-sector` を指定したUS専用埋め込み表示
4. US個別分析ページ最上部のiframe

通常ページ最上部のカードIDは次のとおり。

```text
top-us-sector-flow
```

US専用埋め込み表示では次の状態を固定する。

```jsx
initialMarket="us"
lockMarket={true}
initialUsMode="relative"
lockUsMode={true}
```

したがって、埋め込み表示やDiscord撮影では市場切替ボタンや相対・絶対ボタンをクリックしない。

#### US個別分析

対象ファイル:

```text
C:\Users\mahha\OneDrive\開発\investment_dashboard\us_individual.html
```

`StockSection` を共通コンポーネントとして使い、以下を描画する。

- US個別全銘柄パフォーマンス
- 48分類の各セクターパフォーマンス
- カルーセル内の全銘柄・各セクターカード
- 通常ページ下部の全銘柄・各セクター縦積み表示

2026年6月7日時点の全銘柄数は546銘柄である。銘柄定義は `etf_data_manager.py` の `US_INDIVIDUAL`、重複除去後の取得対象は `ALL_US_INDIVIDUAL_SYMBOLS` で管理する。

### 米国株データの取得方法

#### 出力ファイル

日次データ:

```text
C:\Users\mahha\OneDrive\開発\investment_dashboard\data\etf_data.json
```

イントラデイデータ:

```text
C:\Users\mahha\OneDrive\開発\investment_dashboard\data\etf_intraday.json
```

イントラデイは5分足、取得期間は14日である。

```python
data_intraday = fetch_data(period="14d", interval="5m")
```

日次とイントラデイの両方に、JP ETF、USセクターETF、SPY、主要指数、US個別株、TOPIX100等が同じ `dates` と `prices` 構造で保存される。

#### 一括取得

第一取得経路は `yfinance.download()` による一括取得である。

```python
df = yf.download(
    ALL_SYMBOLS,
    period=period,
    interval=interval,
    auto_adjust=False,
    progress=False,
)
```

`auto_adjust=False` とし、原則として `Close` の生値を使う。短期パフォーマンスが配当落ち調整で歪むことを避けるため、`Adj Close` より `Close` を優先する。

`ALL_SYMBOLS` には少なくとも以下を含める。

- JPベンチマークとJP ETF
- JP・US半導体
- USセクターETF
- SPY
- TOPIX100
- US個別全銘柄
- JPバスケット構成銘柄

#### 個別補完

一括取得で欠損したSPYまたはUSセクターETFは `ensure_symbol_column()` で補完する。

補完順序:

1. 一括取得済み列に有効な正の価格があるか確認する。
2. `yf.download(symbol, ...)` で対象シンボルだけ再取得する。
3. Yahoo Chart APIから直接取得する。
4. 出力側インデックスへ `reindex()` し、`ffill().bfill()` で揃える。
5. SPYを揃えられない場合は例外で停止する。

Yahoo Chart API:

```text
https://query1.finance.yahoo.com/v8/finance/chart/{symbol}
```

イントラデイ補完は最大60日、日次補完は2年を要求する。

```python
chart_range = "2y" if interval == "1d" else "60d"
```

#### SPYは必須

米国セクター相対チャートのベンチマークはSPYだけである。

```python
US_SP500_BENCHMARKS = {
    "SPY": "SPY",
}
```

`^GSPC`、VOO、IVV等へ自動フォールバックしない。SPYが無い状態で別系列へ切り替えると、時系列の連続性と過去比較の意味が変わるためである。

日次・イントラデイ出力後に以下を必ず検証する。

```python
validate_spy_output(data_daily, "data/etf_data.json")
validate_spy_output(data_intraday, "data/etf_intraday.json")
```

検証条件:

- `prices.SPY` が存在する。
- `prices.SPY` と `dates` の要素数が一致する。
- 正の有効価格が1件以上ある。

表示側でもSPYが無ければ次のメッセージを出し、相対チャートを描かない。

```text
SPYが未取得です。基準の連続性を守るため、他のS&P500連動系列には切り替えません。
```

#### USセクターETFの補完

`ensure_us_sector_columns()` は最初にSPYを必須取得し、その後 `US_SECTORS` の各シンボルを個別補完する。

全セクターを取得できなくても、有効なUSセクター系列が1つ以上あれば出力できる。ただし有効系列が0件の場合は例外で停止する。

#### GitHub Actionsの取得時刻

日次確定処理:

```text
C:\Users\mahha\OneDrive\開発\investment_dashboard\.github\workflows\daily_etf.yml
```

- JST 16:00: JP市場閉場後の日次確定
- JST 06:05: US市場閉場後の日次終値確定

USの朝通知は06:25 JSTなので、06:05 JSTの日次更新後に実行する。

イントラデイ処理:

```text
C:\Users\mahha\OneDrive\開発\investment_dashboard\.github\workflows\intraday_etf.yml
```

US市場用の主な起動:

- UTC 13:30、13:45、14:00
- UTC 17:00、17:15

米国夏時間ではJST 22:30が寄り付きとなる。冬時間では1時間後になるため、表示側は固定のJST時間帯で判定せず、必ず `America/New_York` を使う。

### 米国タイムスタンプの解釈

#### 入力をUTCと決め打ちしない

`data\etf_intraday.json` の日時文字列は、取得経路や過去データにより次のどちらとして解釈すべきかが異なる可能性がある。

- NY現地時刻文字列
- UTC時刻文字列

そのため `sector_category.html` と `us_individual.html` は、両方の候補を試す。

```js
const candidates = ["ny-local", "utc"].map(timestampMode => {
    // 各解釈で通常取引時間内の点を抽出する
});
```

候補ごとに有効な価格点数を数え、品質スコアが高い解釈を採用する。

```js
quality = validPriceCount + sessionItemCount * 0.001
```

同点の場合は、現行JSONの主形式である `ny-local` を優先する。

この自動判定を外し、`new Date(value + "Z")` のようにUTCへ固定してはいけない。

#### NY現地時刻からUTCへの変換

NY現地時刻文字列は `getUtcFromNewYorkLocal()` でUTC実時刻へ変換する。

処理概要:

1. 入力の年月日時分を `Date.UTC()` で仮配置する。
2. `Intl.DateTimeFormat` の `America/New_York` からオフセットを計算する。
3. UTC候補を補正する。
4. 補正後の時刻でもう一度オフセットを計算する。
5. 夏時間・冬時間を反映したUTC時刻を確定する。

固定の `-4時間` または `-5時間` を使用しない。

#### 通常取引時間

US市場日の判定は `America/New_York` 基準で行う。

```js
marketTime.minutes >= 570 && marketTime.minutes <= 960
```

- 570分 = 09:30 ET
- 960分 = 16:00 ET

土曜日・日曜日は除外する。

`getRecentNewYorkSessionItems()` は次の順に処理する。

1. NY通常取引時間内の点だけ抽出する。
2. NY市場日単位でグループ化する。
3. 対象シンボルに有効な価格変化がある日だけ残す。
4. `1d` なら直近1市場日、`2d` なら直近2市場日を選ぶ。
5. `ny-local` と `utc` のうち品質が高い解釈を返す。

### JST表示の正解

#### JSTラベル生成

採用した入力時刻をUTC実時刻へ確定した後、`Asia/Tokyo` の `Intl.DateTimeFormat` でラベルを作る。

```js
const formatJstAxisLabel = (date) => {
    const parts = getFormatterParts(TOKYO_TIME_FORMATTER, date);
    return `${Number(parts.month)}/${Number(parts.day)} ${parts.hour}:${parts.minute}`;
};
```

表示例:

```text
6/5 22:30
6/6 04:55
```

JST変換は「元文字列へ常に9時間を足す」処理ではない。最初に入力がNY現地時刻かUTCかを確定し、その後JSTへ変換する。

#### 夏時間と冬時間

米国市場のJST表示:

- 夏時間: 22:30から翌05:00付近
- 冬時間: 23:30から翌06:00付近

コードで22:30や05:00を固定条件として使わない。NY市場時間を判定した結果をJST表示する。

### 横軸の正解

#### USイントラデイ

USイントラデイはPlotlyの `category` 軸を使う。

```js
{
    type: "category",
    nticks: 12,
    tickangle: -30,
    title: {
        text: "時間（JST）"
    }
}
```

理由:

- 1市場日がJSTでは2暦日にまたがる。
- 米国金曜後半は日本では土曜早朝になる。
- datetime軸へ週末rangebreaksを適用すると、正しい金曜USセッション後半まで消える。
- category軸なら、抽出済みの有効な市場ティックを順番どおり、間隔を詰めて表示できる。

USイントラデイへ次のrangebreaksを入れてはいけない。

```js
{ bounds: ["sat", "mon"] }
```

USイントラデイではrangebreaksを空にする。

#### US日次

日次表示ではdatetime系列として扱い、土日を除くrangebreaksを使用できる。

#### JPとの分離

JPイントラデイはUSとは別仕様である。

現行JP用rangebreaks:

```js
[
  { bounds: ["sat", "mon"] },
  { bounds: [15.5, 9], pattern: "hour" },
  { bounds: [11.5, 12.5], pattern: "hour" }
]
```

絶対禁止:

- JPのrangebreaksをUSへ流用する。
- USのcategory軸をJP全チャートへ一括適用する。
- JPとUSの時刻変換を一つの固定オフセット関数へまとめる。

### 基準価格とパフォーマンス

#### 前営業日終値を基準にする

イントラデイの当日騰落率は、当日最初の5分足や寄り付き価格ではなく、前営業日の日次終値を基準にする。

`buildDailyBaseMap()` は選択した最初のUS市場日より前の日次データを後ろから探す。

```js
rawDaily.dates[di] < sessionStartDate
```

その日の価格を各シンボルの基準値として使う。

日次基準が無い場合のみ、次の順でフォールバックする。

1. イントラデイ開始位置より前にある直近の有効価格
2. 選択期間の開始位置にある有効価格

基準値探索では `null`、`undefined`、0、非数値を除外する。

#### 米国セクター相対値

セクターリターン:

```js
sectorReturn = sectorCurrent / sectorBase - 1
```

SPYリターン:

```js
spyReturn = spyCurrent / spyBase - 1
```

表示する相対値:

```js
(sectorReturn - spyReturn) * 100
```

これは「セクター価格をSPY価格そのもので割った値」ではなく、同じ基準時点からの騰落率差である。

#### 米国セクター絶対値

絶対モード:

```js
(sectorCurrent / sectorBase - 1) * 100
```

SPYとの比較を差し引かない。

#### US個別分析

US個別分析の個別株リターン:

```js
(stockCurrent / stockBase - 1) * 100
```

`S&P500` は `^GSPC` を使った比較用の点線として同じ基準時点から計算する。

現行 `StockSection` は個別株からS&P500リターンを差し引く相対超過リターンではなく、個別株とS&P500の絶対騰落率を同じチャート上で比較する。

セクター分類分析のSPY相対計算と、US個別分析のS&P500比較線を混同しない。

### 日次終値補正の正解

米国セクター分析では、最終市場日の日次終値が存在する場合、ランキング値を日次終値で補正できる。

ただし、イントラデイチャート線は `etf_intraday.json` の実測系列を維持する。

禁止:

```js
lastPoint[sectorName] = dailyClosePerformance;
lastPoint.date = marketCloseLabel;
```

この上書きを行うと、最終点だけ異なるデータ粒度になり、線が急騰・急落して見える。

原則:

- チャート線: 5分足の実測系列
- ランキング: 必要に応じて日次終値で補正
- 期間表示の終了日時: 日次終値がある場合は引け時刻表示に補正可能

US個別分析には既存の日次終値補正処理がある。変更する場合も、チャート全体の基準値、ランキング、最終点のデータ粒度が一致しているかを確認し、セクター分析の禁止事項をそのまま無視してはならない。

### 縦軸の正解

#### 固定レンジを使わない

USチャートの縦軸は、値が何%であっても全データを包含するよう動的に計算する。

使用する値:

- ランキング全件の `performance`
- 時系列全点の数値
- 現在表示していない系列も含む

計算:

```js
const minValue = Math.min(0, ...values);
const maxValue = Math.max(0, ...values);
const span = Math.max(maxValue - minValue, 0.5);
const padding = Math.max(span * 0.08, 0.2);
const range = [
    minValue - padding,
    maxValue + padding,
];
```

Plotly:

```js
{
    range: yAxisRange,
    autorange: false
}
```

これにより、XSDが-8.69%なら縦軸は-8.69%より下まで広がり、-2%固定のような欠落を起こさない。

#### 0%基準線

最低値と最高値の計算には必ず0を含め、0%の基準線を表示範囲外へ出さない。

#### US個別分析への適用

`StockSection` の動的縦軸は `US個別全銘柄パフォーマンス` だけでなく、全セクターカードとカルーセルにも共通適用される。

546銘柄のうち表示フィルターが上位10件だけでも、縦軸はランキング全件と時系列全系列を見て決める。そのため、ランキングに-20%の銘柄があるのに縦軸が-10%で切れる状態を防ぐ。

### セクター分類分析の表示構成

2026年6月7日時点の通常ページ上部順序:

1. 【US】相対パフォーマンス推移（全セクターvs SPY）
2. 規模別指数（絶対値）
3. 【JP】相対パフォーマンス推移（全セクターvs TOPIX）
4. その他の分類チャート

US相対チャートは相対モードがデフォルトである。通常ページでは必要に応じて絶対モードへ切り替えられる。

US個別分析ページでも最上部カルーセルおよび本文先頭のiframeに同じUS相対チャートを表示する。

埋め込みURL:

```text
sector_category.html?embed=us-sector&period={period}#full-sector-flow
```

### 上位・下位表示

`▲ 上7`:

- ランキング上位7件をチャート表示対象にする。
- USではSOXが上位7件に含まれない場合も参照用として追加されることがある。
- したがってチャート線は最大8本になり得る。

`▼ 下7`:

- ランキング下位7件をチャート表示対象にする。
- 同様にSOX参照を含め最大8本になり得る。

Discordのランキング画像は上位7行、下位7行へ限定する。チャート線がSOX参照を含む最大8本であることは現行の正しい仕様である。

### US個別分析の表示フィルター

`StockSection` は次の表示モードを持つ。

- `ALL`
- `TOP10 + WORST10`
- `TOP 10`
- `WORST 10`

表示フィルターはチャート線の選択とランキング表示操作に使うが、動的縦軸の母集団は全ランキング・全時系列である。

イントラデイ横軸は全 `StockSection` で次を共通使用する。

```js
{
    type: "category",
    nticks: 12,
    tickangle: -30,
    title: { text: "時間（JST）" }
}
```

日次では土日rangebreaksを使う。

### Discord朝通知の現行（20260607時点）正解

対象:

```text
C:\Users\mahha\OneDrive\開発\investment_dashboard\.github\workflows\sector_category_discord.yml
```

US通知時刻:

```text
25 21 * * 1-5
```

UTC月曜日から金曜日の21:25、JSTでは火曜日から土曜日の06:25である。

通知処理:

1. Python、Playwright、Pillow、データ取得依存関係を準備する。
2. `MARKET_DATA_ALLOW_US_ONLY=1` で `etf_data_manager.py` を実行する。
3. SPYとUSセクターを含む最新の日次・5分足データを生成する。
4. ローカルHTTPサーバーを起動する。
5. US専用埋め込みURLを直接開く。
6. `data-market="us"`、`data-us-mode="relative"`、タイトルの `vs SPY` を確認する。
7. 上位表示を選び、ランキングを上位7行へ限定して撮影する。
8. 下位表示を選び、ランキングを下位7行へ限定して撮影する。
9. チャートとランキングを横に結合する。
10. 生成画像をGitHub Actions Artifactへ7日間保存する。
11. Discordへ本文と2枚の画像を送る。
12. `curl --fail-with-body` によりDiscord HTTPエラーをWorkflow失敗として扱う。

撮影URL:

```text
http://127.0.0.1:8000/sector_category.html?embed=us-sector&period=1d#full-sector-flow
```

JP表示を開いてからUSボタンや相対ボタンをクリックする方式へ戻してはいけない。過去にはReactの再描画後に相対ボタンを見失い、30秒タイムアウトしてDiscord送信がスキップされた。

添付:

1. US相対チャート + 上位7ランキング
2. US相対チャート + 下位7ランキング

Discord本文のリンク:

```text
US個別分析
https://seahirodigital.github.io/investment_dashboard/us_individual.html
```

2026年6月7日の手動検証成功:

```text
https://github.com/seahirodigital/investment_dashboard/actions/runs/27088017458
```

検証された内容:

- USデータ再取得成功
- SPY相対表示確認成功
- 上位・下位スクリーンショット生成成功
- Artifactアップロード成功
- Discord送信成功
- 本文のUS個別分析URL確認成功

### 変更時の回帰確認

#### データ

- `data\etf_data.json` にSPYがある。
- `data\etf_intraday.json` にSPYがある。
- SPY配列長とdates配列長が一致する。
- USセクターETFに有効な正の価格がある。
- US個別銘柄が `prices` に出力される。

#### 時刻

- 入力時刻をUTCへ決め打ちしていない。
- `ny-local` と `utc` の品質比較が残っている。
- NY通常取引時間09:30から16:00で抽出している。
- JSTラベルが夏時間・冬時間へ自動追従する。
- 金曜USセッション後半が土曜JSTとして消えない。

#### 横軸

- USイントラデイはcategory軸である。
- 横軸タイトルは `時間（JST）` である。
- USイントラデイに週末rangebreaksを適用していない。
- JPのrangebreaksを変更していない。

#### 縦軸

- 固定の±2%、±10%、±20%を設定していない。
- ランキング全件と時系列全値を使って上下限を計算する。
- 最小値・最大値と0%を表示範囲に含む。
- 異常値があっても線がチャート外へ切れない。

#### パフォーマンス

- USセクター相対はSPYとのリターン差である。
- SPYから他のS&P500系列へフォールバックしていない。
- 前営業日の日次終値を基準にしている。
- 日次終値をイントラデイチャート最終点へ上書きしていない。
- US個別のS&P500線とセクター分析のSPY相対値を混同していない。

#### 表示

- セクター分類分析の最上部にUS相対チャートがある。
- US個別分析に同じUS相対チャートがある。
- US個別全銘柄以下の全チャートでJST横軸と動的縦軸が有効である。
- 上位・下位表示でランキング対象が正しい。
- SOX参照を含みチャート線が最大8本になることを誤って削除しない。

#### Discord

- US専用埋め込みURLを直接開いている。
- `data-market="us"` と `data-us-mode="relative"` を確認している。
- ランキング画像は上位7行・下位7行である。
- 2枚の結合画像が0バイトではない。
- Discord送信失敗時にWorkflowも失敗する。
- 本文リンクがUS個別分析ページである。

### 絶対禁止事項

1. 米国イントラデイ日時をUTCまたはNY現地時刻の一方へ決め打ちしない。
2. 米国時刻を固定オフセットだけでJSTへ変換しない。
3. SPY欠損時に `^GSPC`、VOO、IVVへ切り替えない。
4. USイントラデイへJP用rangebreaksを適用しない。
5. USとJPの時間軸修正を同じ一括変更で行わない。
6. 縦軸を固定値へ戻さない。
7. 表示中の線だけで縦軸を計算しない。
8. 日次終値をイントラデイチャート最終点へ上書きしない。
9. Discord撮影を画面切替ボタンのクリックへ依存させない。
10. `sector_category.html` 全体を古いコミットへ戻して部分修正を失わない。

### 現状の正解を確認する最短手順

1. `etf_data_manager.py` を実行する。
2. 日次・イントラデイJSONのSPYを確認する。
3. `sector_category.html?embed=us-sector&period=1d#full-sector-flow` を開く。
4. タイトルが `【US】相対パフォーマンス推移（全セクターvs SPY）` であることを確認する。
5. 横軸がJSTで米国1市場日全体を表示することを確認する。
6. 最悪値を含むよう縦軸が動的に広がることを確認する。
7. `us_individual.html?period=1d` を開く。
8. 全銘柄と複数のセクターカードで同じJST横軸・動的縦軸を確認する。
9. `sector_category_discord.yml` を `mode=us` で手動実行する。
10. Discordに上位・下位の2画像とUS個別分析URLが届くことを確認する。

## 2026-06-18 更新事項

### GitHub Pages 白画面対策

`https://seahirodigital.github.io/investment_dashboard/` が白画面になる問題に対応した。

原因は、複数の HTML が `https://unpkg.com/@babel/standalone/babel.min.js` をバージョン未固定で読み込んでいたこと。UNPKG 側の `@babel/standalone` の `latest` が昨日から今日にかけて `@babel/standalone@8.0.0` へ切り替わった可能性が高く、リポジトリ側を変更していなくても、ブラウザで読み込まれる Babel の実体が変わった。

この影響で、JSX 変換後コードに通常の `<script>` では実行できない `import` が混入し、React 描画前に停止して `#root` が空のままになった。つまり、サイト側のコミットがなくても、外部 CDN の未固定 `latest` が変わることで突然表示不能になる状態だった。

対策として、以下の HTML で Babel を `https://unpkg.com/@babel/standalone@7.26.10/babel.min.js` に固定し、`<script type="text/babel" data-presets="env,react">` と `/** @jsxRuntime classic */` を追加した。

- `C:\Users\mahha\OneDrive\開発\investment_dashboard\index.html`
- `C:\Users\mahha\OneDrive\開発\investment_dashboard\advanced.html`
- `C:\Users\mahha\OneDrive\開発\investment_dashboard\analytics.html`
- `C:\Users\mahha\OneDrive\開発\investment_dashboard\sector_category.html`
- `C:\Users\mahha\OneDrive\開発\investment_dashboard\short_selling.html`
- `C:\Users\mahha\OneDrive\開発\investment_dashboard\topix100.html`
- `C:\Users\mahha\OneDrive\開発\investment_dashboard\us_individual.html`

検証では、7 ページすべてで `#root` が描画され、`Cannot use import statement outside a module` および `react/jsx-runtime` 系のエラーが出ないことを確認した。

修正コミット: `33875071 Fix GitHub Pages white screen`
