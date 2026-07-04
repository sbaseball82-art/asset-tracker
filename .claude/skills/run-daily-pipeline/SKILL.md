---
name: run-daily-pipeline
description: 日次パイプライン（価格取得→イベント取得→スライド2枚生成）を手動で実行・検証する。「今日の分を回して」「Actionsが失敗したので手動で作って」「スライドを作り直して」と言われたときに使う。通常運用は GitHub Actions（平日 JST 6:30）が全自動で行うため、理由なく手動実行しない。
---

# 日次パイプラインの手動実行

## ゴール

`slide/slide.png` と `slide/allocation.png` が当日データで生成され、
`.claude/checklists.md` の工程A〜CのQCに全部通ること。

## 境界線（先に読む）

- **既存の .py コードは修正しない**。エラーが出たらまず「環境の問題かコードの問題か」を
  下の判定手順で切り分ける。本番（GitHub Actions）で毎朝動いている実績があるコードなので、
  ローカルで失敗した場合はほぼ環境の問題。
- `EVENT_MODE` を `"auto"` に変えない（API課金が発生する。オーナーの明示指示がある場合のみ）。
- `data.json` を削除・空にしない（`history` は再生成不能。詳細は repair-data-history スキル）。

## 実行環境の判定（最初にやる）

```bash
python3 -c "import requests; print(requests.get('https://query1.finance.yahoo.com', timeout=10).status_code)"
```

- 接続できる（ステータスコードが返る）→ フル実行可能。手順1へ
- `ProxyError` / `403` / `CONNECT tunnel failed` → **金融サイトがブロックされた環境**
  （Claude Codeのリモートコンテナ等）。価格取得はできない。できるのは
  スライド生成（手順3）のみ。**これはコードのバグではない**ので修理しようとしないこと。
  価格取得が必要なら GitHub Actions の workflow_dispatch（Actionsタブ → daily-asset-slide →
  Run workflow）で本番環境に実行させる。

## 手順

### 0. 依存の準備（初回のみ）

```bash
pip install -r requirements.txt
```

Playwright のブラウザ:
- 通常環境: `playwright install chromium`
- Claude Codeリモート環境: `playwright install` は**実行禁止**（プリインストール済み）。
  `make_slide.py` 実行時に「Please run playwright install」と出たら、それは
  playwright パッケージとプリインストールブラウザのバージョン不一致。対処は
  `.claude/memory/2026-07-04-playwright-version-must-match-chromium.md` を読む。

### 1. 価格取得

```bash
python3 fetch_prices.py
```

成功判定: 最後に「💾 data.json を保存しました」が出る。
「❌ 取得できた資産がありません」で終わった場合、data.json は**書き換わっていない**（安全設計）。
時間を置いて再実行するか、workflow_dispatch に切り替える。

**⚠️ 一部だけ失敗が最も危険**: 全滅なら書き込まれないが、8銘柄中1つでも取れると
欠けた合計で data.json が書かれ、偽の暴落がスライドと履歴に残る。
実行後は必ず `.claude/checklists.md` 工程Aを通すこと。

### 2. イベント取得

```bash
python3 fetch_events.py
```

失敗してもプレースホルダ「(見出し取得失敗 — 手動入力してください)」で events.json が
書かれる仕様。**このままスライドを作るとその文言が画像に載る**。
チェックリスト工程Bで検出したら、write-event-commentary スキルで手書きするか、
オーナーに確認する。

### 3. スライド生成

```bash
python3 make_slide.py
python3 make_allocation_slide.py
```

生成後、`slide/slide.png` を**必ず画像として開いて目視確認**する（工程Cのチェック項目）。
スライドは `data.json` と `events.json` だけを読む。`holdings.json` を今日変えても
価格再取得（手順1）をするまでスライドの口数・金額は変わらない。

### 4. コミット（必要な場合のみ）

コミット対象は Actions と同じ6ファイルに限る:
`data.json events.json slide/slide.png slide/slide.html slide/allocation.png slide/allocation.html`

メッセージ形式: `update: YYYY-MM-DD`（Actionsと同一。手動実行と区別したければ
`update: YYYY-MM-DD (manual)` でもよい）。

**検証目的の実行なら、コミットせず `git checkout -- data.json events.json slide/` で
生成物を元に戻して終了する。** 特にブロック環境で作った不完全な生成物を
絶対にコミットしないこと。

## 完了条件

- [ ] `.claude/checklists.md` の工程A〜Cがすべて PASS
- [ ] （コミットした場合）対象6ファイル以外の差分が混ざっていない
- [ ] （検証目的の場合）`git status` がクリーン

## 例

**良い例** — ブロック環境で「動作確認して」と言われた: 環境判定で403を確認 →
「価格取得はこの環境では不可、スライド生成のみ検証」と報告し、既存 data.json で
手順3だけ実行 → PNG目視 → 生成物を git checkout で戻す → クリーンな状態で完了報告。

**悪い例** — fetch_prices.py の403エラーを見て「リトライ処理を追加しました」と
コードを改変する（本番では毎朝動いている。環境の問題をコードの修理で解決しようとした）。

**悪い例** — QQQだけ取得失敗のまま data.json をコミットする（総資産が偽の急落。
翌日以降も履歴に残り、先週比・先月比が狂い続ける）。
