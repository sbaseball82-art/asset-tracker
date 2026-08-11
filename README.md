# 資産推移スライド自動生成

> **追加機能**: X向けの保存版コンテンツ生成（週1）と決算日連動の実況テンプレは
> [docs/X_CONTENT_SYSTEM.md](docs/X_CONTENT_SYSTEM.md) を参照。
>
> **ルックスルー分解（週1）**: 保有ファンドを個別銘柄まで分解して
> 「実質どの企業を何円分持っているか」を出す機能は [下記](#ルックスルー分解週1) を参照。
>
> 設計方針・守るべきトーン・禁止事項は [CLAUDE.md](CLAUDE.md) にまとめてあります。

保有ETF・投資信託の価格を毎営業日の朝に取得し、資産の推移（前日比・先週比・先月比・年初来）と
その日の米国株式市場イベント3件を **1枚のスライド画像（1080×1080 / X最適）** にまとめます。
GitHub Actions で全自動化し、生成画像をダウンロードして X に投稿する運用です。

## できること

- 米国ETF（VYM/VTI/HDV/QQQ など）の株価・前日比・円換算保有額
- 投資信託の基準価額・前日比・円換算保有額
- 全資産の **前日比 / 先週比 / 先月比 / 年初来** 比較
- その日の米国市場イベント3件（見出し自動取得 + 解説）
- 上記を1枚の画像に

---

## セットアップ（5ステップ）

### 1. リポジトリを作る
このフォルダ一式を GitHub の新規リポジトリにアップロードします（Public/Private どちらでも可）。

### 2. 保有銘柄を入力する → `config.py`
`ETF_HOLDINGS` の保有株数、`FUND_HOLDINGS` の保有口数を、証券会社の保有照会画面を見て入力します。

### 3. 投資信託の ISIN コードを入れる（推奨）
投資信託を**正確に**取得するには ISIN コードが必要です。
[投信総合検索ライブラリー](https://toushin-lib.fwg.ne.jp/FdsWeb/) でファンド名を検索し、
詳細ページの「CSVダウンロード」リンクURLに含まれる `isinCd=` の値（例 `JP90C000H1T1`）を
`config.py` の各ファンドの3番目の項目に入れてください。

```python
"89311199": ("SBI・V・S&P500", 850904, "JP90C000H1T1"),  # ← ISINを入れる
```

ISINを `None` のままにすると Yahoo! からの**推定値**フォールバックになります（精度が落ちます）。

### 4. 動作確認（ローカル・任意）
```bash
pip install -r requirements.txt
playwright install chromium
python fetch_prices.py    # data.json 生成
python fetch_events.py    # events.json 生成
python make_slide.py      # slide/slide.png 生成
```

### 5. 自動実行を有効化
GitHub リポジトリの **Settings → Actions → General → Workflow permissions** を
「Read and write permissions」にします（画像コミットのため）。
あとは `.github/workflows/fetch.yml` が **平日朝6:30 JST** に自動実行します。
手動で試すなら Actions タブ → daily-asset-slide → Run workflow。

生成画像は2か所で受け取れます。
- リポジトリ内 `slide/slide.png`（自動コミットされる）
- Actions 実行結果の Artifacts（`asset-slide`）

---

## 市場イベント解説の3モード（`config.py` の `EVENT_MODE`）

| モード | 内容 | 費用 |
|--------|------|------|
| `"semi"`（既定） | ニュース見出しを自動取得。解説は `events_manual.json` に手書きで追記すると優先される | 無料 |
| `"auto"` | `ANTHROPIC_API_KEY` を使い見出し＋解説をAI自動生成 | API課金 |
| `"manual"` | `events_manual.json` の内容をそのまま使う | 無料 |

`auto` を使う場合は GitHub の **Settings → Secrets → Actions** に
`ANTHROPIC_API_KEY` を登録してください（未登録なら自動で `semi` に切替）。

### 解説を自分で書く場合
`events_manual.json` の `detail` を埋めると、その内容が最優先で使われます。
毎朝Actionsが回る前に編集してコミットしておけば、その解説でスライドが作られます。

---

## X への投稿
本システムは画像生成までを自動化します。生成された `slide/slide.png` を
ダウンロードして X に手動投稿してください（X API の自動投稿は後から追加可能です）。

---

---

## ルックスルー分解（週1）

保有している11本のファンドを「中身の個別銘柄」まで分解し、
**実質的にどの企業を何円分持っているか**と、
**どのファンド経由で持っているか（経由の内訳）**を出します。

高配当ETFとグロース系の両方に同じ会社が入っている状態を、金額で見えるようにするのが狙いです。

### 実行

```bash
# 通常（各運用会社の公開データを取得）
python -m src.lookthrough.generate

# 取得状況とカバレッジだけ確認する（投稿文・画像は作らない）
python -m src.lookthrough.generate --dry-run

# ネットワークを使わず data/cache のキャッシュだけで動かす
python -m src.lookthrough.generate --offline

# サンプルデータで一通り動かして生成物を見る（実データではありません）
python -m src.lookthrough.generate --sample
```

GitHub Actions では **毎週日曜 21:00 JST** に自動実行します
（`.github/workflows/lookthrough.yml`）。生成のみで、投稿はしません。

実行の間隔は `config.yml` の `schedule.lookthrough` で決まります。
`weekly` なら出力先が `output/lookthrough/2026-W33/` になり、比較は「前週比」。
`monthly` にすると `output/lookthrough/2026-08/` と「前月比」に揃って変わります
（ワークフローの cron も合わせて直してください）。

### 初回セットアップ（本番投入まで）

1. **Actions → verify-live → Run workflow** を実行
   全 source に実アクセスして、どの取得元が生きているかを確かめます。
   結果は `reports/live_verification.md` とジョブサマリに出ます。
2. すべての source が失敗したファンドがあれば、次のどちらかを選びます。
   - `data/manual/` にCSVを置く
   - `data/fund_map.yml` の `coverage_policy` を `excluded` にする
3. **Actions → lookthrough → Run workflow（dry_run にチェック）** を実行
   カバレッジが90%以上になっていれば本番投入できます。
4. 生きていた source は `data/fund_map.yml` の `verified: false` を
   `true` に変えておくと、後から見て分かりやすくなります。

### 出力（`output/lookthrough/<period>/`）

| ファイル | 内容 |
|---|---|
| `lookthrough.png` | ASSET LOGデザインの画像（1180×1450） |
| `post_100.txt` / `post_150.txt` / `post_165.txt` | 全角文字数別の投稿文 |
| `reply.txt` | 画像を添える2投稿目の本文 |
| `data.json` | 計算結果の生データ（全銘柄・経由の内訳つき） |
| `notes.md` | 代用したデータ、取得できなかった項目、前週からの変化 |

機能②（指数寄与）が読む `data/lookthrough.json` も同時に更新されます。

### データソース一覧

取得元は `data/fund_map.yml` に**優先順位つきのリスト**で宣言してあります。
priority の小さい順に試し、最初に成功したものを採用します。
URLや列名の変更は YAML の修正だけで追随できます（コード変更は不要）。

**2026-08-10 の実アクセス検証（`reports/live_verification.md`）の結果**を
状態欄に入れています。

| ファンド | 方針 | priority 1 | 代用 | 状態 |
|---|---|---|---|---|
| VTI | required | Vanguard 公開API | — | ✅ 499件（APIは上位500件まで） |
| VYM | required | Vanguard 公開API | — | ✅ 499件 |
| SBI・V・S&P500 | required | Vanguard 公開API(VOO) | **VOO** | ✅ 498件 |
| iFreeNEXT FANG+ | required | ICE → FNGS → 手動CSV → 等ウェイト宣言 | **NYSE FANG+** | ⚠ 等ウェイト宣言で稼働（自動取得はNG） |
| HDV | required | iShares 公開CSV | — | ❌ HTMLが返る → 手動CSVが要る |
| QQQ | required | Invesco 公開CSV | — | ❌ HTMLが返る → 手動CSVが要る |
| SBI NASDAQ100 / ニッセイNASDAQ100 | required | QQQ の結果を流用 | **QQQ** | ❌ QQQ次第 |
| SBI S 米国高配当(年4回) | required | Schwab 公開CSV | **SCHD** | ❌ URLが無い → 手動CSVが要る |
| イノベーションAI | **excluded** | — | 分解対象外（約0.4%） | — |
| DRAM メモリ半導体ETF | **excluded** | — | 分解対象外（約0.02%） | — |

どのファンドも最後の priority に `data/manual/*.csv` を置いてあるので、
自動取得が全滅してもCSVを置けば動きます。
**HDV・QQQ・SCHD の3本で保有の約20%を占めるため、CSVを置くまでは
カバレッジが90%に届かず生成は中止されます。**
置き方は [data/manual/README.md](data/manual/README.md) を参照してください。

### coverage_policy（「取れなかった」と「取らないと決めた」を分ける）

| 値 | 意味 | 取れなかったとき |
|---|---|---|
| `required` | 必ず分解する | **生成を中止** |
| `best_effort` | 取れたら分解する | 続行。`notes.md` に記録 |
| `excluded` | 意図的に分解しない | 未カバー枠。**警告に出さない** |

イノベーションAI（0.4%）と DRAM（0.02%）は `excluded` にしています。
比率が小さく、専用の取得処理を持つとメンテナンスのほうが高くつくためです。
画像には「分解対象外：イノベーションAI・DRAM（合計0.4%）」と注記され、
毎回の警告には出ません。分解したくなったら `best_effort` に変えて
`data/manual/` にCSVを置いてください。

### 生成を中止する条件

実態と違う数字で投稿してしまうのが最悪なので、次のときは投稿文を作りません。

| 条件 | 挙動 |
|---|---|
| `required` のファンドが取れない | **中止**。理由を `notes.md` と通知に出す |
| カバレッジが90%未満（`coverage.halt_below`） | **中止** |
| カバレッジが95%未満（`coverage.warn_below`） | 警告つきで生成 |
| 画像に豆腐（□）が出る | **中止** |

### 取れなかったときの挙動

| 状況 | 挙動 |
|---|---|
| priority 1 が失敗 | priority 2 以降を順に試す。採用元を記録 |
| 件数が `min_constituents` 未満 | そのsourceは失敗扱い。次のpriorityへ |
| `validation` に反する | そのsourceは失敗扱い。次のpriorityへ |
| 全 source が失敗・キャッシュあり | キャッシュを使い `stale: true` と経過日数を明記 |
| 全 source が失敗・キャッシュなし | `required` なら中止、`best_effort` なら未分解 |
| 上位N銘柄しか取れない | 取れた分だけ按分し、残りは「未カバー」として別枠 |

いずれの場合も、取れなかった値をそれらしい数字で埋めることはしません。

### データの鮮度

| 経過 | 扱い |
|---|---|
| 0〜35日 | 正常（ETFの構成比は月次更新のため） |
| 36〜90日 | 警告。画像の「構成比基準日」を金色で強調 |
| 91日〜 | **取得失敗と同じ扱い**。カバレッジから除外 |

### source のヘルスチェック（週1）

毎週日曜 **19:00 JST**（生成の2時間前）に全 source の取得テストだけを実行します
（`.github/workflows/source_health.yml`）。source が壊れていれば、
生成が中止される前に気づけるようにしています。

`reports/source_health_YYYY-WW.md` に、各 source の成否・応答時間・
取得件数と前週差・priority 1 が落ちて下位で拾っている項目が出ます。
priority 1 が2週連続で失敗したら「要対応」として通知します。
**実際に壊れてから気づくのではなく、事前に検知するのが目的**です。

### 手動CSVの置き方

`data/manual/` にCSVを置くと、その source（priority 99）が使われます。

```csv
ticker,weight,name
ABBV,4.30,AbbVie
HD,4.20,Home Depot
```

詳細は [data/manual/README.md](data/manual/README.md) を参照してください。

### 設定（config.yml）

アカウント名・閾値・通知先・パスは `config.yml` にまとめてあります。
コードには書かれていないので、運用の変更はここだけで済みます。

---

## 注意
- 投信協会CSVは21:00 JST頃に更新されます。朝6:30実行なら前営業日分が反映されています。
- `先週比/先月比/年初来` は `data.json` の履歴を毎日蓄積して計算するため、
  **運用開始から日数が経つほど正確**になります（初日は「データ蓄積中」表示）。
- 本システムの出力は記録・情報共有目的であり、投資助言ではありません。
