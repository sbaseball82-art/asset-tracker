#!/usr/bin/env python3
"""同梱フォントに、動画で使う全文字のグリフがあるか確かめる。

1文字でも欠けていたら失敗させる。豆腐（□）のまま書き出すより止めたほうがよい。
"""
from __future__ import annotations

import sys
from pathlib import Path

from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from subset_fonts import OUT, WEIGHTS, collect_chars  # noqa: E402


def covered(path: Path) -> set[int]:
    font = TTFont(str(path))
    out: set[int] = set()
    for table in font["cmap"].tables:
        out |= set(table.cmap.keys())
    return out


def main() -> int:
    needed = {ord(c) for c in collect_chars() if c not in ("\n", "\t")}
    failed = False

    for _, _, woff2 in WEIGHTS:
        path = OUT / woff2
        if not path.exists():
            print(f"エラー: {path} が無い。scripts/subset_fonts.py を実行すること",
                  file=sys.stderr)
            return 1
        missing = sorted(needed - covered(path))
        if missing:
            failed = True
            shown = "".join(chr(c) for c in missing[:60])
            print(f"エラー: {path.name} に {len(missing)} 文字のグリフが無い: {shown}",
                  file=sys.stderr)
        else:
            print(f"OK  {path.name}  {len(needed)} 文字すべてにグリフがある")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
