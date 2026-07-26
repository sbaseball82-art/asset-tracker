# -*- coding: utf-8 -*-
"""
postlog.py
==========
logs/posts.csv への生成物記録と読み込み。

列: date, type, topic_id, format, char_count, has_image,
    posted(bool), views, likes, bookmarks, replies, profile_clicks, follows

views 以降は人間が週1回 scripts/log_metrics.py で入力する。
"""

import csv
from pathlib import Path

from .util import REPO_ROOT

CSV_PATH = REPO_ROOT / "logs" / "posts.csv"
COLUMNS = ["date", "type", "topic_id", "format", "char_count", "has_image",
           "posted", "views", "likes", "bookmarks", "replies",
           "profile_clicks", "follows"]


def append_row(date: str, type_: str, topic_id: str, format_: str,
               char_count: int, has_image: bool, path: Path = CSV_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(COLUMNS)
        w.writerow([date, type_, topic_id, format_, char_count,
                    str(bool(has_image)).lower(), "false",
                    "", "", "", "", "", ""])


def read_rows(path: Path = CSV_PATH) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_rows(rows: list[dict], path: Path = CSV_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in COLUMNS})
