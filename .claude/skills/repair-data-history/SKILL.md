---
name: repair-data-history
description: data.json の履歴（history）に異常値が混入したときの診断と修復。「昨日の総資産がおかしい」「前日比が異常な値になっている」「スライドの数字が急落/急騰しておかしい」と言われたときに使う。通常のパイプライン実行には使わない（その場合は run-daily-pipeline スキル）。
---

# data.json 履歴の診断と修復

## ⚠️ これは危険作業。以下の禁止事項を最初に読むこと

`data.json` の `history` は運用開始から毎日蓄積してきた総資産の記録で、
**外部から再取得する手段がない**。壊すと先週比・先月比・年初来が永久に狂う。

**禁止事項（例外なし）:**
- `data.json` を削除しない。空にしない。ゼロから再生成しようとしない
- `history` の複数エントリを一括で書き換えない（修正は疑わしい1日分のみ）
- 修復前に必ずバックアップを取る（手順1）。バックアップなしで編集を始めない
- main に force-push しない
- `history` 以外のキー（etf/fund/comparisons等）は手で編集しない
  （それらは次回の fetch_prices.py 実行で正しく上書きされる）

## 異常の典型パターンと見分け方

| 症状 | 原因 | 見分け方 |
|---|---|---|
| ある日だけ総資産が10%以上急落→翌日戻る | その日の取得で一部銘柄が失敗し、欠けた合計が記録された | その日の `etf`/`fund` に銘柄が8個ない（当日中なら）。過去日なら前後の日と比べて不自然な段差 |
| 円換算額だけ全体に数%ズレる | USD/JPY取得失敗で固定値150.00が使われた | `history` のその日の `usdjpy` がちょうど `150.0` |
| 投信の額が微妙にずれる | 協会CSV失敗でYahoo!推定値が使われた | `fund` の `source` が `"Yahoo!(推定)"` |
| historyに日付の欠落がある（例: 金→翌週火） | **ほぼ正常**。Actionsは平日のみ実行＋日米市場の休場日はデータが動かない | 欠落が土日祝を挟んでいれば正常。**欠落日を捏造して埋めるのは禁止**。平日なのに5営業日以上連続で欠けている場合のみ、Actionsの実行履歴を確認 |

本物の市場急落と混同しないこと。判断基準: **保有銘柄の実際の値動き**（その日の各銘柄の
change_pct）で説明できる下落は本物。1銘柄の欠落や為替の段差で説明できるものは異常値。
迷ったらオーナーに「◯月◯日のデータが異常に見える。原因は△△と推定。修復してよいか」と確認する。

## 修復手順

### 1. バックアップ（必須・最初）

```bash
cp data.json /tmp/data.json.backup-$(date +%Y%m%d-%H%M%S)
git log --oneline -3 -- data.json   # gitにも直近版があることを確認
```

### 2. 異常エントリの特定

```bash
python3 - <<'EOF'
import json
h = json.load(open("data.json"))["history"]
for prev, curr in zip(h, h[1:]):
    pct = (curr["total_jpy"] - prev["total_jpy"]) / prev["total_jpy"] * 100
    flag = "  ⚠️" if abs(pct) > 5 else ""
    print(f'{curr["date"]}  ¥{curr["total_jpy"]:,}  ({pct:+.2f}%)  usdjpy={curr["usdjpy"]}{flag}')
EOF
```

⚠️ が付いた日について、上の表で原因を推定する。

**合計に異常がなくても安心しない**: 1銘柄だけの異常は合計では希釈されて見えないことがある。
「数字がおかしい気がする」という曖昧な訴えのときは、投信の銘柄別日次も確認する:

```bash
python3 - <<'EOF2'
import json
d = json.load(open("data.json"))
for code, f in d["fund"].items():
    s = f.get("nav_series", [])
    for newer, older in zip(s, s[1:]):   # nav_seriesは新しい順
        if older["jpy"]:
            pct = (newer["jpy"] - older["jpy"]) / older["jpy"] * 100
            if abs(pct) > 5:
                print(f'⚠️ {f["name"]}: {older["date"]}→{newer["date"]} {pct:+.2f}%')
print("(何も表示されなければ投信の銘柄別にも異常なし)")
EOF2
```

ETFは data.json に銘柄別の時系列を持たない（当日の prev/curr のみ）ため、
過去日のETF異常は合計値の段差からしか推定できない。その場合は git 履歴で
当該日のコミットの data.json を見る: `git show <commit>:data.json`

### 3. 修復

- **当日の異常**（今朝の実行が失敗データを書いた）: 修復不要。原因解消後に
  `python3 fetch_prices.py` を再実行すれば同日エントリは自動で上書きされる（same-day上書き仕様）。
- **過去日の異常**: その1日分のエントリを `history` 配列から削除する（値の捏造はしない。
  正しい値は分からないので「その日の記録なし」にするのが正）。
  比較計算は「指定日以前で最も近い日」を使う設計なので、1日欠けても壊れない。

```bash
python3 - <<'EOF'
import json
BAD_DATE = "YYYY-MM-DD"   # ← 特定した異常日に書き換える
d = json.load(open("data.json"))
before = len(d["history"])
d["history"] = [h for h in d["history"] if h["date"] != BAD_DATE]
assert len(d["history"]) == before - 1, "削除対象が1件ではない。中断してdateを確認"
json.dump(d, open("data.json", "w"), ensure_ascii=False, indent=2)
print(f"removed {BAD_DATE}: {before} -> {len(d['history'])} entries")
EOF
```

### 4. 検証（完了条件）

- [ ] `python3 -c "import json; json.load(open('data.json'))"` が通る
- [ ] 手順2のスクリプトを再実行し、⚠️ が消えている（本物の市場変動の⚠️は残ってよい）
- [ ] `git diff data.json` の差分が **削除した1エントリ分だけ** であること
- [ ] コミットメッセージ: `Repair data.json history: remove bad entry for YYYY-MM-DD (<原因>)`

### 5. 事後

修復したら、原因と再発条件を `.claude/memory/` に教訓として1件残す（書式は
`.claude/memory/README.md`）。

## 例

**良い例** — 「6/25の前日比がおかしかった」: 手順2で 2026-06-25 に -12% の段差、
usdjpy=150.0 を発見 → 為替フォールバックが原因と特定 → オーナーに報告・了承 →
バックアップ → 6/25の1件を削除 → 検証4項目 → コミット → memoryに教訓追加。

**悪い例** — 急落を見て「データが壊れている」と判断し data.json を削除して
fetch_prices.py で作り直す（history が1日分だけになり、比較機能が全て「データ蓄積中」に退行。
**復旧不能**）。

**悪い例** — 異常日の total_jpy を前後の日の平均値に書き換える（記録の捏造。
削除して「記録なし」にするのが正）。
