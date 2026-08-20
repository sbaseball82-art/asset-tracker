#!/usr/bin/env python3
"""動画で使う文字だけに絞った Noto Sans JP を video/public/fonts/ に作る。

フルのCJKフォントは1ウェイト5MB超あり、そのままリポジトリに置くには重い。
一方でシステムフォント任せにすると豆腐（□）の原因になるので、
「使う文字だけを同梱する」という折衷にしている。

文字集合は video/src 以下のソースとデータJSONから拾う。
文言を足したら必ずこれを再実行すること（check_video_glyphs.py が検査する）。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIDEO = ROOT / "video"
SRC = VIDEO / "src"
OUT = VIDEO / "public" / "fonts"
FONT_PKG = VIDEO / "node_modules" / "@expo-google-fonts" / "noto-sans-jp"

WEIGHTS = [
    ("700Bold", "NotoSansJP_700Bold.ttf", "NotoSansJP-Bold.woff2"),
    ("900Black", "NotoSansJP_900Black.ttf", "NotoSansJP-Black.woff2"),
]

# ソースに現れなくても描画されうる文字（数値の書式・記号まわり）
BASE_CHARS = set(
    "0123456789"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    " .,-+%()[]:;/'\"#&*!?<>=_|~^@$\\`{}"
    "０１２３４５６７８９"
    "　、。・「」『』（）［］％／＼－ー〜！？：；＝＋"
    "→←↑↓※◯○●◆■□▲▼"
    "①②③④⑤⑥⑦⑧⑨⑩"
    "年月期円ドル億万千百"
)


def collect_chars() -> set[str]:
    chars = set(BASE_CHARS)

    for path in sorted(SRC.rglob("*")):
        if path.suffix in (".ts", ".tsx"):
            chars |= set(path.read_text(encoding="utf-8"))
        elif path.suffix == ".json":
            chars |= _json_strings(json.loads(path.read_text(encoding="utf-8")))

    # 制御文字は入れない
    return {c for c in chars if c.isprintable() or c == " "}


def _json_strings(node) -> set[str]:
    out: set[str] = set()
    if isinstance(node, str):
        out |= set(node)
    elif isinstance(node, dict):
        for k, v in node.items():
            out |= set(k) | _json_strings(v)
    elif isinstance(node, list):
        for v in node:
            out |= _json_strings(v)
    return out


def main() -> int:
    if not FONT_PKG.exists():
        print(f"エラー: {FONT_PKG} が無い。video/ で npm install を実行すること",
              file=sys.stderr)
        return 1

    chars = collect_chars()
    OUT.mkdir(parents=True, exist_ok=True)
    text_file = OUT / ".charset.txt"
    text_file.write_text("".join(sorted(chars)), encoding="utf-8")

    for folder, ttf, woff2 in WEIGHTS:
        src = FONT_PKG / folder / ttf
        if not src.exists():
            print(f"エラー: {src} が無い", file=sys.stderr)
            return 1
        dst = OUT / woff2
        subprocess.run(
            [
                sys.executable, "-m", "fontTools.subset", str(src),
                f"--text-file={text_file}",
                "--flavor=woff2",
                f"--output-file={dst}",
                "--layout-features=kern,liga,palt,vert",
                "--no-subset-tables+=DSIG",
                "--drop-tables+=DSIG",
            ],
            check=True,
        )
        print(f"wrote {dst}  ({dst.stat().st_size / 1024:.0f} KB / {len(chars)} 文字)")

    text_file.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
