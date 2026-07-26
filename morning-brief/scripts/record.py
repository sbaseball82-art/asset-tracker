# -*- coding: utf-8 -*-
"""Views実績の記録CLI（ユーザーの入力コスト＝1日1回・数十秒）。

Xのアナリティクスを見て、画像番号とViewsを並べるだけ:

  python scripts/record.py --date 2026-07-28 --views 1 520 2 310
  python scripts/record.py --date 2026-07-28 --views 1 520 --likes 1 8

引数なしで実行すると対話モード（1枚ずつ「画像NのViewsは？」と聞く）。
template_id / topic_tag / score は生成時の out/YYYY-MM-DD_meta.json から
自動で紐付けるので、ユーザーはViewsだけ入力すればよい。
記録先: data/feedback.csv（同じ date+slot は上書き）。
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config_loader import ROOT                     # noqa: E402
from learner import FEEDBACK_CSV, FIELDNAMES       # noqa: E402

OUT_DIR = os.path.join(ROOT, "out")


def load_meta(date: dt.date) -> dict[int, dict]:
    p = os.path.join(OUT_DIR, f"{date.isoformat()}_meta.json")
    if not os.path.exists(p):
        raise SystemExit(f"[error] meta が見つかりません: {p}\n"
                         "（その日のカードが未生成か、0枚だった可能性があります）")
    return {int(m["slot"]): m for m in json.load(open(p, encoding="utf-8"))}


def _pairs(vals: list[str], what: str) -> dict[int, float]:
    if len(vals) % 2 != 0:
        raise SystemExit(f"[error] --{what} は「スロット番号 値」のペアで指定してください")
    return {int(vals[i]): float(vals[i + 1]) for i in range(0, len(vals), 2)}


def upsert(rows_new: list[dict]):
    existing: list[dict] = []
    if os.path.exists(FEEDBACK_CSV):
        with open(FEEDBACK_CSV, encoding="utf-8") as f:
            existing = list(csv.DictReader(f))
    keys_new = {(r["date"], str(r["slot"])) for r in rows_new}
    kept = [r for r in existing if (r.get("date"), str(r.get("slot"))) not in keys_new]
    os.makedirs(os.path.dirname(FEEDBACK_CSV), exist_ok=True)
    with open(FEEDBACK_CSV, "w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=FIELDNAMES)
        wr.writeheader()
        for r in sorted(kept + rows_new, key=lambda x: (x["date"], str(x["slot"]))):
            wr.writerow({k: r.get(k, "") for k in FIELDNAMES})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD（省略時は昨日）")
    ap.add_argument("--views", nargs="*", default=None,
                    help="スロット番号とViewsのペア（例: 1 520 2 310）")
    ap.add_argument("--likes", nargs="*", default=None,
                    help="スロット番号とLikesのペア（任意）")
    a = ap.parse_args()

    date = (dt.date.fromisoformat(a.date) if a.date
            else dt.date.today() - dt.timedelta(days=1))
    meta = load_meta(date)

    if a.views:
        views = _pairs(a.views, "views")
    else:   # 対話モード
        views = {}
        print(f"{date} のカードは {len(meta)} 枚です。XのViewsを入力してください（空Enterでスキップ）")
        for slot, m in sorted(meta.items()):
            v = input(f"  画像{slot}「{m['headline']}」のViews: ").strip()
            if v:
                views[slot] = float(v.replace(",", ""))
    likes = _pairs(a.likes, "likes") if a.likes else {}

    rows = []
    for slot, v in views.items():
        if slot not in meta:
            print(f"[warn] スロット{slot}は{date}のmetaに存在しません。スキップ")
            continue
        m = meta[slot]
        rows.append({"date": date.isoformat(), "slot": slot,
                     "template_id": m["template_id"], "topic_tag": m["topic_tag"],
                     "score": m.get("score", ""), "views": int(v),
                     "likes": int(likes.get(slot, 0))})
    if not rows:
        print("[warn] 記録なし")
        return 0
    upsert(rows)
    print(f"[ok] {len(rows)}件を {FEEDBACK_CSV} に記録しました")
    for r in rows:
        print(f"  {r['date']} #{r['slot']} {r['template_id']}×{r['topic_tag']} views={r['views']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
