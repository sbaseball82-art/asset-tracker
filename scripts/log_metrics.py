# -*- coding: utf-8 -*-
"""
log_metrics.py
==============
logs/posts.csv への実績入力を対話式で補助する（週1回・5分以内が目標）。

- 未入力（views が空）の行だけを新しい順に出す
- 「投稿した？」→ y なら views/likes/bookmarks/replies/profile_clicks/follows
  をまとめて1行で入力（スペース区切り。省略した項目は空欄のまま）
- n なら posted=false のまま次へ / q で保存して終了

使い方: python scripts/log_metrics.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common import postlog  # noqa: E402

METRIC_KEYS = ["views", "likes", "bookmarks", "replies",
               "profile_clicks", "follows"]


def main() -> int:
    rows = postlog.read_rows()
    if not rows:
        print("posts.csv がまだありません（生成が走ると作られます）")
        return 0

    pending = [r for r in rows if not r.get("views")]
    if not pending:
        print("未入力の行はありません 🎉")
        return 0

    print(f"未入力 {len(pending)}件。X アナリティクスを見ながら入力してください。")
    print("形式: views likes bookmarks replies profile_clicks follows")
    print("（例: 1200 15 8 2 30 1 ／ 途中まででOK・q で保存終了・n で未投稿のまま次へ）")
    print("-" * 60)

    for r in pending:
        print(f"\n[{r['date']}] {r['type']}/{r['topic_id']} "
              f"({r['format']}, {r['char_count']}字)")
        ans = input("  投稿した？ [y/n/q] > ").strip().lower()
        if ans == "q":
            break
        if ans != "y":
            r["posted"] = "false"
            continue
        r["posted"] = "true"
        vals = input("  数値 > ").strip().split()
        for k, v in zip(METRIC_KEYS, vals):
            if v.isdigit():
                r[k] = v

    postlog.write_rows(rows)
    print(f"\n[ok] 保存しました → {postlog.CSV_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
