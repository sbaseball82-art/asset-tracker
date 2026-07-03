---
name: update-holdings
description: 既存の保有銘柄の買い増し・売却を holdings.json に反映する。「◯◯を△円買った」「△株買い増した」「売却した」と言われたときに使う。config.py に登録がない新しい銘柄の追加には使わない（その場合は add-instrument スキルを使う）。
---

# 買い増し・売却の holdings.json 反映

保有数量は `holdings.json` だけで管理されている（`config.py` は名前・ISINのマスタで、数量は持たない）。
編集対象はこのファイル1つ。翌朝の GitHub Actions（平日 JST 6:30）で自動的にスライドへ反映される。

## 手順

### 1. 銘柄を特定する

ユーザーが言った銘柄名を `config.py` で引く。

- ETF → `_ETF_NAMES`（キー: シンボル。例 `VYM`）
- 投資信託 → `_FUND_META`（キー: 協会コード8桁。例 `04311181`）

名前が部分一致で複数候補に当たる場合（例:「高配当」は VYM/HDV/8931224C の3つに当たる）は、
推測で選ばず候補を提示してユーザーに確認する。1つに絞れたらそのまま進む。
`config.py` に見つからない銘柄なら、このスキルを中断して add-instrument に切り替える。

### 2. 新しい数量を計算する

`holdings.json` の値は「合計保有数」なので、購入分を**加算**（売却なら減算）する。整数のみ。

| ユーザーの指定 | 計算 |
|---|---|
| 株数・口数を直接指定 | そのまま加減算する |
| 投資信託を金額指定（円） | `追加口数 = round(金額 ÷ curr_nav × 10000)`。`curr_nav` は `data.json` の `fund["<協会コード>"]["curr_nav"]`（1万口あたり基準価額） |
| ETFを金額指定（円） | `追加株数 = floor(金額 ÷ (curr_price × usdjpy))`。`data.json` の `etf["<シンボル>"]` から取る |

金額からの換算は**概算**（約定日の価格と一致しない）。計算結果を報告するとき「証券会社の約定通知に
口数/株数があればそちらが正」と一言添える。ユーザーが約定数量を提示したら計算値より優先する。

売却で数量が0未満になる場合はエラーとして報告し、編集しない。

### 3. holdings.json を編集する

`etf` または `fund` の該当キーの値だけを書き換える。キーの追加・削除・`_comment` の変更はしない。

### 4. 検証する（完了条件）

以下がすべて通ったら完了。1つでも失敗したら編集を見直す。

```bash
python3 -c "import json; json.load(open('holdings.json'))"          # valid JSON
python3 -c "import config; print(config.ETF_HOLDINGS); print(config.FUND_HOLDINGS)"  # 新数量が表示される
```

### 5. コミットする

メッセージ形式（実績 commit 735be8d に準拠）:

```
Modify fund '<協会コード>' value(buy JPY<金額> of <表示名>) in holdings.json
Modify etf '<シンボル>' value(buy <株数> shares of <表示名>) in holdings.json
```

売却なら `buy` を `sell` にする。

## 例

**良い例** — 「FANG+を10万円買い増した」:
`_FUND_META` で `04311181`（iFreeNEXT FANG+）を特定 → `data.json` の
`fund["04311181"]["curr_nav"]` が 93,722円なら `round(100000/93722*10000) = 10670` 口を
現在値 276836 に加算 → `287506` に書き換え → 検証2つ実行 →
`Modify fund '04311181' value(buy JPY100000 of iFreeNEXT FANG+) in holdings.json` でコミット。

**悪い例** — 同じ依頼で `holdings.json` の値を `16295` に**置き換える**（加算し忘れ。値は合計保有数）。
**悪い例** — 「高配当を買った」に対し確認せず VYM を選ぶ（HDV・SBI米国高配当too。候補提示が必須）。
