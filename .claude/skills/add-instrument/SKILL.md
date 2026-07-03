---
name: add-instrument
description: 新しいETFまたは投資信託をポートフォリオに追加する（config.py と holdings.json の両方に登録）。「◯◯を新しく買い始めた」「銘柄を追加して」と言われたときに使う。すでに config.py に登録済みの銘柄の数量変更には使わない（その場合は update-holdings スキルを使う）。
---

# 新規銘柄の追加

銘柄マスタは `config.py`、保有数量は `holdings.json` に分かれている。新規追加は**両方**を編集する。
片方だけだと数量0扱い、または KeyError にはならないが表示されない。

## 手順

### 1. 種別を判定する

- 米国ETF（ティッカーシンボルがある。例 VYM, QQQ）→ 手順2A
- 投資信託（協会コード8桁で管理。例 89311199）→ 手順2B

どちらか不明なら、ティッカーの有無をユーザーに確認する。

### 2A. ETFの場合

1. `config.py` の `_ETF_NAMES` にシンボルと表示名を追記する。表示名は既存に倣い
   「シンボル + 日本語の性格説明」（例: `"VOO": "VOO S&P500ETF"`）。
2. `holdings.json` の `etf` にシンボルと保有株数（整数）を追記する。

### 2B. 投資信託の場合

1. 協会コード（8桁英数字）と ISIN を特定する。
   [投信総合検索ライブラリー](https://toushin-lib.fwg.ne.jp/FdsWeb/) でファンド名を検索し、
   詳細ページの「CSVダウンロード」リンクURLに含まれる `isinCd=` の値（例 `JP90C000H1T1`）が ISIN、
   同URLの `associFundCd=` の値が協会コード。
2. ISIN がどうしても特定できない場合のみ `None` を入れる（Yahoo! 推定値フォールバックになり
   **精度が落ちる**。その旨を必ずユーザーに報告する）。勝手に ISIN を推測して埋めない。
3. `config.py` の `_FUND_META` に `"協会コード": ("表示名", "ISIN")` を追記する。
4. `holdings.json` の `fund` に協会コードと保有口数（整数）を追記する。
   口数が不明で購入金額だけ分かる場合の換算は update-holdings スキルの手順2に従う。

### 3. 検証する（完了条件）

以下がすべて通ったら完了。

```bash
python3 -c "import json; json.load(open('holdings.json'))"      # valid JSON
python3 -c "import config; print(config.ETF_HOLDINGS); print(config.FUND_HOLDINGS)"  # 新銘柄が数量つきで表示される
python3 fetch_prices.py    # エラーなく完走し data.json に新銘柄の価格が出る（要ネット接続）
```

`fetch_prices.py` は外部サイトに接続する。ネットが使えない環境では最初の2つまでで完了とし、
「価格取得の確認は翌朝の Actions 実行で行われる」と報告する。
初回は Playwright が必要: `pip install -r requirements.txt && playwright install chromium`。

### 4. コミットする

```
Add <fund|etf> '<コード|シンボル>' (<表示名>) to config.py and holdings.json
```

## 例

**良い例** — 「楽天・オールカントリーを50万円分買い始めた」:
投信総合検索ライブラリーで検索 → 協会コード `9C31121B`・ISIN `JP90C000J9G4` を URL から取得 →
`_FUND_META` に `"9C31121B": ("楽天・オールカントリー", "JP90C000J9G4")` を追記 →
口数を換算して `holdings.json` の `fund` に追記 → 検証3つ → コミット。

**悪い例** — ISIN が見つからないので `"JP90C000XXXX"` と形式だけ合わせて埋める
（誤ったファンドの基準価額を取り続ける。不明なら `None` + 報告が正）。
**悪い例** — `config.py` だけ編集して `holdings.json` を忘れる（数量0でスライドに出ない）。
