# X コンテンツ生成システム（保存版 ＋ 決算実況）

実装依頼書v3に基づく「リプライで配るための弾を安定供給する仕組み」。
**自動投稿はしない**。生成 → 人間が確認して投稿、が唯一のフロー。

## 全体像

```
data/
  evergreen_topics.yml   保存版のネタストック（20本＋AI提案分）
  watchlist.yml          決算実況の対象銘柄と指数ウェイト概算
  earnings_calendar.yml  決算・マクロイベント日程（手動＋Finnhub自動追記）
  holdings.yml           保有と比率（data.json から自動生成）
  cache/etf_constituents.yml  ETF上位10銘柄キャッシュ
src/
  common/    render.py(ASSET LOGデザイン共通化) / textcheck / notify / postlog
  evergreen/ 機能A: 保存版生成
  earnings/  機能B: 決算実況テンプレ
  report/    週次レポート
scripts/
  log_metrics.py         View等の対話式入力（週1回・5分以内）
  sync_holdings_yml.py   data.json → data/holdings.yml
output/
  evergreen/YYYY-MM-DD/          post.txt / reply.txt / table.png / ammo.md
  earnings/YYYY-MM-DD_TICKER/    pre.txt / post.txt / morning.txt
logs/posts.csv           全生成物の記録（views以降は手入力）
reports/weekly_YYYY-WW.md 週次のformat別・type別平均View
```

## 機能A: 保存版コンテンツ（週1本・日曜21:00 JST）

```bash
python -m src.evergreen.generate              # 未使用ネタから1本生成
python -m src.evergreen.generate --topic ev003
python -m src.evergreen.generate --dry-run    # フラグ・ログを書かない
```

- post.txt は画像なしで成立・**全角280字以内**（超過は生成時に警告）
- 1枚目はテキスト、画像(table.png)は返信欄に置く運用
- ammo.md に「どのリプライで使うか」と雛形3案が必ず付く
- 使用済みネタは90日後に再利用可能（数値を更新して再投稿）
- ETF構成の取得失敗時は前回キャッシュを使い、画像に stale 表記
- `ANTHROPIC_API_KEY` があれば新ネタをAI提案して追記
  （`needs_review: true` 付き。人間がデータを埋めるまで自動選択されない）

## 機能B: 決算実況テンプレ（平日毎時、カレンダー連動）

```bash
python -m src.earnings.generate --ticker MSFT --date 2026-07-28 --phase pre
python -m src.earnings.scheduler   # cronから呼ばれる判定役
```

| phase | タイミング | 必須要素 |
|---|---|---|
| pre | 発表90〜0分前 | 予想EPS・売上、注目点、**分岐条件**、実効保有比率 |
| post | 発表後6時間以内 | 実績vs予想、初動は**「時間外」と明記**、ガイダンス |
| morning | 翌朝7:00 JST | **指数寄与＝構成比×騰落率**、資産への影響、翌日の論点 |

- 予想EPS等は Finnhub 無料枠（`FINNHUB_API_KEY`）。取れない項目は
  **「要手動入力」と表示され、推測値では絶対に埋めない**
- 生成済み判定は出力ファイルの有無（再実行しても二重生成しない）
- T-60分の通知は失敗時リトライ3回＋失敗通知（`SLACK_WEBHOOK_URL`）

## 計測と自動調整

```bash
python scripts/log_metrics.py   # 週1回、Xアナリティクスから手入力
python -m src.report.weekly     # 週次レポート＋format_weights.yml 更新
```

4週分たまると、平均Viewが全体の50%未満の型（format）は
`data/format_weights.yml` に `reduced` と記録され、
保存版のネタ選択がその型を自動的に後回しにする。

## GitHub Actions

| workflow | cron (UTC) | 内容 |
|---|---|---|
| evergreen.yml | 日曜 12:00（予備14:00） | 保存版生成＋ネタ提案 |
| earnings.yml | 平日 毎時 | カレンダー判定→実況テンプレ生成 |
| weekly_report.yml | 日曜 13:00 | 週次レポート |

**注意: schedule はmainブランチのworkflowだけが動く**（過去の教訓）。
ブランチで検証したら必ずmainへマージすること。
cron遅延（数時間）は既知の仕様。同日二重生成はガード済み。

Secrets（すべて任意。無くても動く＝欄が「要手動入力」になるだけ）:
`FINNHUB_API_KEY` / `SLACK_WEBHOOK_URL` / `ANTHROPIC_API_KEY`

## テスト

```bash
python -m pytest tests/ -q   # 47件
```

指数寄与の検算・280字チェック・重複ネタ検出・90日再利用・
スケジューラの時刻窓・「要手動入力」表示を含む。

## 運用フロー（1日1時間）

| 時間 | 作業 |
|---|---|
| 30分 | リプライ15〜25本（ammo.md の雛形＋table.png を持って大型アカウントへ） |
| 20分 | 保存版の確認と投稿（output/evergreen/ の最新を見る） |
| 10分 | 決算実況の「要手動入力」を埋めて投稿 |
| 週1回15分 | `python scripts/log_metrics.py` でView入力 |

## 免責

本システムは記録・情報共有目的のコンテンツ生成支援であり、投資助言では
ない。生成物は投稿前に必ず人間が内容を確認する（特に「要手動入力」欄と
概算数値）。
