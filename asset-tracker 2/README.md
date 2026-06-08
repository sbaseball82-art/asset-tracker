# 資産推移スライド自動生成

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

## 注意
- 投信協会CSVは21:00 JST頃に更新されます。朝6:30実行なら前営業日分が反映されています。
- `先週比/先月比/年初来` は `data.json` の履歴を毎日蓄積して計算するため、
  **運用開始から日数が経つほど正確**になります（初日は「データ蓄積中」表示）。
- 本システムの出力は記録・情報共有目的であり、投資助言ではありません。
