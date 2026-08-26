# -*- coding: utf-8 -*-
"""
fonts.py
========
日本語を描けるフォントを探す。**パスをハードコードしない。**

``fc-match`` は該当が無いと DejaVu などを黙って返すため、
返ってきたファイルが本当に日本語グリフを持っているかまで検証してから採用する。
（既存の src/common/fontcheck.py と同じ考え方。こちらは Pillow だけで完結させる）
"""

from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

# fc-match が使えない環境向けの候補（上から順に試す）
FALLBACK_PATHS: tuple[str, ...] = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansJP-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansJP-Regular.ttf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/System/Library/Fonts/ttf/HiraginoSans-W3.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "C:/Windows/Fonts/YuGothM.ttc",
    "C:/Windows/Fonts/meiryo.ttc",
)

BOLD_HINTS = ("Bold", "bold", "-B.", "Medium")

# フォントが日本語を持っているかの判定に使う文字（画像に実際に出る字を含める）
_JP_SAMPLE = "今週の米国決算寄付前引け後場中予想売上社月火水木金"


class FontNotFoundError(RuntimeError):
    """日本語を描けるフォントが見つからない。推測で続行せず失敗させる。"""


def _has_japanese(path: Path, index: int = 0) -> bool:
    try:
        font = ImageFont.truetype(str(path), 24, index=index)
    except Exception:  # noqa: BLE001 — 壊れたフォント/未対応形式
        return False
    try:
        return all(font.getmask(ch).getbbox() is not None for ch in _JP_SAMPLE)
    except Exception:  # noqa: BLE001
        return False


def _fc_match(family: str) -> str | None:
    if not shutil.which("fc-match"):
        return None
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}", family],
                             capture_output=True, text=True, timeout=15)
    except Exception:  # noqa: BLE001
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


@lru_cache(maxsize=8)
def find_font_path(preferred: str = "Noto Sans CJK JP", index: int = 0) -> Path:
    """日本語を描けるフォントファイルを探して返す。

    見つからなければ ``FontNotFoundError``。豆腐（□）の混じった画像を
    出すくらいなら生成を止める。
    """
    candidates: list[str] = []
    for family in (preferred, "Noto Sans CJK JP", "Noto Sans JP", "sans-serif:lang=ja"):
        hit = _fc_match(family)
        if hit:
            candidates.append(hit)
    candidates.extend(FALLBACK_PATHS)

    tried: list[str] = []
    for cand in candidates:
        path = Path(cand)
        if str(path) in tried:
            continue
        tried.append(str(path))
        if path.exists() and _has_japanese(path, index):
            return path

    raise FontNotFoundError(
        "日本語を描けるフォントが見つかりません。"
        "`sudo apt-get install -y fonts-noto-cjk` を実行してください。"
        f"（試したパス: {tried or 'なし'}）")


@lru_cache(maxsize=8)
def _bold_path(regular: Path) -> tuple[str, int]:
    """Regular と対になる Bold を探す。無ければ Regular を使う。

    Noto Sans CJK は 1ファイルに複数ウェイトを持たないため、
    ファイル名の Regular を Bold に置き換えたものを探す。
    """
    for token in ("Regular", "regular"):
        if token in regular.name:
            bold = regular.with_name(regular.name.replace(token, "Bold"))
            if bold.exists() and _has_japanese(bold):
                return str(bold), 0
    return str(regular), 0


@lru_cache(maxsize=256)
def load(size: int, bold: bool = False, preferred: str = "Noto Sans CJK JP",
         index: int = 0) -> ImageFont.FreeTypeFont:
    """指定サイズのフォントを返す（同じ組み合わせは使い回す）。"""
    regular = find_font_path(preferred, index)
    if bold:
        path, idx = _bold_path(regular)
    else:
        path, idx = str(regular), index
    return ImageFont.truetype(path, size, index=idx)
