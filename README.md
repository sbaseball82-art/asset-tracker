# 資産推移スライド自動生成

> **追加機能**: X向けの保存版コンテンツ生成（週1）と決算日連動の実況テンプレは
> [docs/X_CONTENT_SYSTEM.md](docs/X_CONTENT_SYSTEM.md) を参照。
>
> **ルックスルー分解（月1）**: 保有ファンドを個別銘柄まで分解して
> 「実質どの企業を何円分持っているか」を出す機能は [下記](#ルックスルー分解月1) を参照。
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

## ルックスルー分解（月1）

保有している11本のファンドを「中身の個別銘柄」まで分解し、
**実質的にどの企業を何円分持っているか**と、
**どのファンド経由で持っているか（経由の内訳）**を出します。

高配当ETFとグロース系の両方に同じ会社が入っている状態を、金額で見えるようにするのが狙いです。

### 実行

```bash
# 通常（各運用会社の公開データを取得）
python -m src.lookthrough.generate

# ネットワークを使わず data/cache のキャッシュだけで動かす
python -m src.lookthrough.generate --offline

# サンプルデータで一通り動かして生成物を見る（実データではありません）
python -m src.lookthrough.generate --sample
```

GitHub Actions では **毎月1日 21:00 JST** に自動実行します
（`.github/workflows/lookthrough.yml`）。生成のみで、投稿はしません。

### 出力（`output/lookthrough/YYYY-MM/`）

| ファイル | 内容 |
|---|---|
| `lookthrough.png` | ASSET LOGデザインの画像（1180×1450） |
| `post_100.txt` / `post_150.txt` / `post_165.txt` | 全角文字数別の投稿文 |
| `reply.txt` | 画像を添える2投稿目の本文 |
| `data.json` | 計算結果の生データ（全銘柄・経由の内訳つき） |
| `notes.md` | 代用したデータ、取得できなかった項目、前月からの変化 |

機能②（指数寄与）が読む `data/lookthrough.json` も同時に更新されます。

### データソース一覧

取得元は `data/fund_map.yml` に宣言してあります。列名の変更などは
YAMLの修正だけで追随できます。

| ファンド | 取得元 | 代用 |
|---|---|---|
| VTI / VYM | Vanguard 公開API | — |
| HDV | iShares(BlackRock) 公開CSV | — |
| QQQ | Invesco 公開CSV | — |
| SBI・V・S&P500 | Vanguard 公開API | **VOO** で代用 |
| SBI NASDAQ100 / ニッセイNASDAQ100 | Invesco 公開CSV | **QQQ** で代用 |
| SBI S 米国高配当(年4回) | `data/manual/SCHD.csv` | **SCHD** で代用（手動配置） |
| iFreeNEXT FANG+ | `fund_map.yml` の `members` | NYSE FANG+ の等ウェイト（**四半期ごとに要確認**） |
| イノベーションAI | `data/manual/innovation_ai.csv` | 代用先なし（未配置なら未分解） |
| DRAM メモリ半導体ETF | `data/manual/DRAM.csv` | 代用先なし（未配置なら未分解） |

投信は構成銘柄を公表しないため、連動対象ETFの構成で代用しています。
**代用したことは画像・`data.json`・`notes.md` に必ず記録されます。**

### 手動CSVの置き方

取得元が無いファンドは、`data/manual/` にCSVを置くと分解対象になります。
置かなければ「要手動確認」として未分解のまま出力されます（推測では埋めません）。

```csv
ticker,weight,name
ABBV,4.30,AbbVie
HD,4.20,Home Depot
```

### 取れなかったときの挙動

| 状況 | 挙動 |
|---|---|
| 取得失敗・キャッシュあり | キャッシュを使い `stale: true` を画像に明記 |
| 取得失敗・キャッシュなし | そのファンドを**未分解**にし「要手動確認」と表示 |
| 上位N銘柄しか取れない | 取れた分だけ按分し、残りは「未カバー」として別枠 |
| どのファンドも取れない | **生成を中止**（空の投稿文を作らない） |

いずれの場合も、取れなかった値をそれらしい数字で埋めることはしません。

---

## 注意
- 投信協会CSVは21:00 JST頃に更新されます。朝6:30実行なら前営業日分が反映されています。
- `先週比/先月比/年初来` は `data.json` の履歴を毎日蓄積して計算するため、
  **運用開始から日数が経つほど正確**になります（初日は「データ蓄積中」表示）。
- 本システムの出力は記録・情報共有目的であり、投資助言ではありません。
