# -*- coding: utf-8 -*-
"""
textcheck.py
============
X投稿テキストの文字数チェック。

依頼書の基準は「全角280字以内」。全角=1字、半角=0.5字、URLは
X仕様の固定23半角=11.5字として数える（X Premium運用が前提。
無印Xの140全角に収めたい場合は limit=140 を渡す）。
"""

import re
import unicodedata

ZENKAKU_LIMIT = 280
_URL_RE = re.compile(r"https?://\S+")
_URL_UNITS = 23  # X仕様: URLは半角23文字換算


def x_units(text: str) -> int:
    """Xの重み付き単位数（全角=2 / 半角=1 / URL=23）。"""
    total = 0
    pos = 0
    for m in _URL_RE.finditer(text):
        total += _segment_units(text[pos:m.start()]) + _URL_UNITS
        pos = m.end()
    total += _segment_units(text[pos:])
    return total


def _segment_units(seg: str) -> int:
    n = 0
    for ch in seg:
        n += 2 if unicodedata.east_asian_width(ch) in ("W", "F", "A") else 1
    return n


def zenkaku_len(text: str) -> float:
    """全角換算の文字数（全角=1 / 半角=0.5）。"""
    return x_units(text) / 2


def check_post(text: str, limit: float = ZENKAKU_LIMIT) -> tuple[bool, int, str]:
    """(OK?, 全角換算文字数(切り上げ), 警告メッセージ) を返す。"""
    import math
    n = math.ceil(zenkaku_len(text))
    if n > limit:
        return False, n, f"⚠ 文字数超過: {n}/{limit}（全角換算）"
    return True, n, ""
