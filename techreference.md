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

第4層〜第5層の修正後もinfo（情報）タブが空のままだった。Gist APIでは4/1, 4/2のレポートが正常に保存されていることを確認。

### 根本原因（2つの問題の複合）

#### 問題A: `restore_gist_history.py`が`indent=2`でGistに書き込み（ファイル膨張）

`json.dump(market_data, f, ensure_ascii=False, indent=2)` により、コンパクト時400KB → インデント時952KBに膨張。Gist APIのcontent truncation閾値（約389K文字）を超過。

#### 問題B: ブラウザからのraw_url fetchでCORS preflight失敗

`gist.githubusercontent.com`へのfetchに`Authorization`ヘッダーを付与していたため、CORSプリフライト（OPTIONSリクエスト）が発生。`gist.githubusercontent.com`は`Access-Control-Allow-Headers: Authorization`を返さないため、プリフライトが失敗し、raw_urlからのデータ取得ができなかった。

**結果:** API contentは切り詰め → raw_urlフォールバックもCORSで失敗 → `JSON.parse()` → エラー → catchで無視 → 空のhistoryDataが表示される

### 修正内容

#### 修正1: raw_url fetchからAuthorizationヘッダーを除去

`raw_url`（`gist.githubusercontent.com`）はURL自体にコミットハッシュを含むため認証不要。Authヘッダーを除去しCORSプリフライトを回避。

```js
// 旧: const rawResp = await fetch(rawUrl, { headers: gistAuth, cache: 'no-store' });
// 新: const rawResp = await fetch(rawUrl, { cache: 'no-store' });
```

#### 修正2: raw_urlを常に優先取得

`truncated`フラグに関係なく、`raw_url`が利用可能な場合は常にraw_url経由で完全データを取得。API contentは400KB付近で切り詰められるため、サイズが閾値付近のファイルでは`truncated: false`でも不完全なJSONが返る場合がある。

#### 修正3: `restore_gist_history.py`のコンパクトJSON化

`json.dump(market_data, f, ensure_ascii=False, indent=2)` → `json.dump(market_data, f, ensure_ascii=False)` に変更。ファイルサイズを952KB → 398KBに圧縮。

#### 修正4: 3/30, 3/31のレポート再復旧

Gist APIで直接コンパクトJSONに書き戻し。

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
