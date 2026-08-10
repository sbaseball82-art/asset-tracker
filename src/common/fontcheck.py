# -*- coding: utf-8 -*-
"""
fontcheck.py
============
画像に豆腐（□ = グリフ欠落）が出ていないかを自動チェックする。

やり方
------
ピクセルを走査して□を探すのは誤検出が多い（本文に実際の□があるかも
しれない）。代わりに **フォントファイルにグリフがあるか** を直接見る。

1. 日本語が出せるフォント（Noto Sans CJK JP など）を fc-match で探す。
   ``fc-match`` は見つからないと DejaVu などに黙って落ちるため、
   「返ってきたファイルが本当に日本語を持っているか」まで検査する。
2. 私用領域(PUA)の絶対に存在しないはずの符号位置を数点描画し、
   その .notdef グリフのビットマップを「豆腐の指紋」として得る。
3. 実際に画像へ描く文字を1字ずつ描画し、指紋と一致したら豆腐と判定する。
"""

from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

# 「まず割り当てられていない」符号位置（私用領域）。.notdef の見本を得るのに使う
_PROBES = ("", "", "")

# fc-match が使えない環境向けの候補
_FALLBACK_PATHS = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansJP-Regular.otf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/System/Library/Fonts/ttf/HiraginoSans-W3.ttc",
)

# フォントが日本語を持っているかの判定に使う文字
_JP_SAMPLE = "資産推移銘柄比率円社"


class FontNotFoundError(RuntimeError):
    """日本語を描けるフォントが見つからない。推測で続行せず失敗させる。"""


@lru_cache(maxsize=8)
def find_cjk_font(preferred: str = "Noto Sans JP") -> Path:
    """日本語を描けるフォントファイルを探す。

    fc-match の結果を鵜呑みにせず、日本語グリフを持つか検証してから返す。
    """
    candidates: list[str] = []
    if shutil.which("fc-match"):
        for family in (preferred, "Noto Sans CJK JP", "Noto Sans JP",
                       "sans-serif:lang=ja"):
            try:
                out = subprocess.run(
                    ["fc-match", "-f", "%{file}", family],
                    capture_output=True, text=True, timeout=15)
                if out.returncode == 0 and out.stdout.strip():
                    candidates.append(out.stdout.strip())
            except Exception:  # noqa: BLE001
                pass
    candidates.extend(_FALLBACK_PATHS)

    tried = []
    for path in candidates:
        p = Path(path)
        if not p.exists() or str(p) in tried:
            continue
        tried.append(str(p))
        if _supports_japanese(p):
            return p

    raise FontNotFoundError(
        "日本語を描けるフォントが見つかりません。"
        "`apt-get install -y fonts-noto-cjk` を実行してください。"
        f"（試したパス: {tried or 'なし'}）")


def _supports_japanese(path: Path) -> bool:
    try:
        return not missing_chars(_JP_SAMPLE, path)
    except Exception:  # noqa: BLE001
        return False


def missing_chars(text: str, font_path: Path | str, size: int = 40) -> list[str]:
    """text のうち、そのフォントにグリフが無い文字を返す（＝豆腐になる文字）。

    空リストなら豆腐なし。
    """
    from PIL import ImageFont

    font = ImageFont.truetype(str(font_path), size)
    fingerprints = {_glyph_sig(font, ch) for ch in _PROBES}
    # PUA が実際に描けてしまうフォントだと指紋が割れる。その場合は
    # 「全プローブで共通の見た目」だけを .notdef とみなす
    if len(fingerprints) > 1:
        fingerprints = {s for s in fingerprints
                        if sum(1 for ch in _PROBES
                               if _glyph_sig(font, ch) == s) > 1}

    missing: list[str] = []
    seen: set[str] = set()
    for ch in text:
        if ch in seen or ch.isspace() or not ch.isprintable():
            continue
        seen.add(ch)
        if _glyph_sig(font, ch) in fingerprints:
            missing.append(ch)
    return missing


def _glyph_sig(font, ch: str):
    """1文字のビットマップ指紋。描画できない文字は .notdef と同じ絵になる。"""
    try:
        mask = font.getmask(ch, mode="L")
    except Exception:  # noqa: BLE001
        return ("error", ch)
    try:
        return (mask.size, mask.tobytes())
    except Exception:  # noqa: BLE001
        return (mask.size, bytes(bytearray(mask)))


def check_texts(texts: list[str], preferred: str = "Noto Sans JP"
                ) -> tuple[bool, list[str], str]:
    """画像に描く文字列群をまとめて検査する。

    Returns:
        (豆腐なしか, 欠落文字リスト, 使用フォントのパス)
    """
    font_path = find_cjk_font(preferred)
    joined = "".join(texts)
    missing = missing_chars(joined, font_path)
    return (not missing), missing, str(font_path)
