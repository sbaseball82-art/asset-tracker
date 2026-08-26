# -*- coding: utf-8 -*-
"""
qa.py
=====
生成した画像の自動検査。**1つでも落ちたら異常終了させる。**

検査するもの
------------
1. 豆腐（□ / U+FFFD / 未定義グリフ）が無いこと
   ピクセルを走査して□を探すのは誤検出が多いので、フォントに
   グリフがあるかを直接見る。私用領域(PUA)の絶対に割り当てられていない
   符号位置を描いて .notdef の見本を取り、それと一致する字を豆腐とみなす。
   **描画前**に呼ぶ（render.Canvas が描画のたびに通す）。
2. テキストが領域からはみ出していないこと（実測 bbox と許容矩形の比較）
3. テキスト同士が重なっていないこと（矩形の交差判定）
4. 画像サイズが所定であること
5. 掲載社数が1社以上あること

サムネイル（幅400px）も併せて書き出す。Xのタイムラインで潰れないかを
人間が目視で確かめるため。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

# 「まず割り当てられていない」符号位置。.notdef の見本を得るのに使う
_PROBES = ("\ue0f0", "\uf8f3", "\U000f0123")

# 空のマスクになって当然の文字（豆腐判定から除く）
_BLANK_OK = set(" 　\t\n")

# そのまま出てはいけない文字
_FORBIDDEN_CHARS = {"�": "U+FFFD（置換文字）", "□": "□（豆腐）"}


class QAError(RuntimeError):
    """画像の品質検査に落ちた。生成物を出さずに異常終了させる。"""


@dataclass(frozen=True)
class TextBox:
    """描いたテキスト1つ分の記録。"""

    text: str
    rect: tuple[float, float, float, float]   # 実測の外接矩形（デザイン座標）
    clip: tuple[float, float, float, float]   # はみ出してはいけない範囲
    label: str = ""
    # 重なり判定の対象にするか（ロゴ内の代替ティッカーなど、
    # 意図的に別要素の上へ重ねるものは False）
    collide: bool = True


@dataclass
class QAReport:
    boxes: list[TextBox] = field(default_factory=list)
    companies: int = 0
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- 豆腐


def _glyph_sig(font, ch: str):
    """1文字のビットマップ指紋。描けない文字は .notdef と同じ絵になる。"""
    try:
        mask = font.getmask(ch, mode="L")
    except Exception:  # noqa: BLE001
        return ("error", ch)
    try:
        raw = mask.tobytes()
    except AttributeError:
        raw = bytes(bytearray(mask))
    return (mask.size, raw)


def _notdef_signatures(font) -> set:
    """このフォント・この級数での .notdef の指紋。

    PUA が実際に描けてしまうフォントでは指紋が割れるので、
    その場合は「複数のプローブで共通の見た目」だけを .notdef とみなす。
    """
    sigs = {_glyph_sig(font, ch) for ch in _PROBES}
    if len(sigs) > 1:
        sigs = {s for s in sigs
                if sum(1 for ch in _PROBES if _glyph_sig(font, ch) == s) > 1}
    return sigs


_NOTDEF_CACHE: dict[int, set] = {}


def missing_glyphs(text: str, font) -> list[str]:
    """フォントにグリフが無い文字を返す（空なら豆腐なし）。"""
    key = id(font)
    sigs = _NOTDEF_CACHE.get(key)
    if sigs is None:
        sigs = _notdef_signatures(font)
        _NOTDEF_CACHE[key] = sigs

    bad: list[str] = []
    seen: set[str] = set()
    for ch in text:
        if ch in _FORBIDDEN_CHARS:
            if ch not in seen:
                seen.add(ch)
                bad.append(ch)
            continue
        if ch in seen or ch in _BLANK_OK:
            continue
        seen.add(ch)
        if not ch.isprintable():
            bad.append(ch)
            continue
        sig = _glyph_sig(font, ch)
        if sig in sigs or sig[0] == (0, 0):
            bad.append(ch)
    return bad


def assert_glyphs(text: str, font, label: str = "") -> None:
    bad = missing_glyphs(text, font)
    if bad:
        detail = " ".join(f"{ch!r}(U+{ord(ch):04X})" for ch in dict.fromkeys(bad))
        raise QAError(
            f"豆腐（グリフ欠落）: {detail} — 対象テキスト「{text}」"
            f"{f' [{label}]' if label else ''}。"
            "フォントを確認してください（fonts-noto-cjk）。")


# ---------------------------------------------------------------- 矩形


def _intersect(a, b) -> float:
    """2つの矩形の重なり面積。"""
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[2], b[2])
    y1 = min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0)


def check_overflow(boxes: list[TextBox], tol: float = 1.0) -> list[str]:
    errs: list[str] = []
    for box in boxes:
        r, c = box.rect, box.clip
        if (r[0] < c[0] - tol or r[1] < c[1] - tol
                or r[2] > c[2] + tol or r[3] > c[3] + tol):
            errs.append(
                f"はみ出し: 「{box.text}」[{box.label}] "
                f"rect={tuple(round(v) for v in r)} clip={tuple(round(v) for v in c)}")
    return errs


def check_overlap(boxes: list[TextBox], tol_area: float = 4.0) -> list[str]:
    errs: list[str] = []
    targets = [b for b in boxes if b.collide]
    for i, a in enumerate(targets):
        for b in targets[i + 1:]:
            area = _intersect(a.rect, b.rect)
            if area > tol_area:
                errs.append(
                    f"重なり: 「{a.text}」[{a.label}] と 「{b.text}」[{b.label}] "
                    f"が {round(area)}px² 交差しています")
    return errs


# ---------------------------------------------------------------- 全体


def verify(image: Image.Image, report: QAReport,
           expected_size: tuple[int, int]) -> None:
    """全チェックをまとめて実行し、1つでも落ちたら QAError。"""
    errs: list[str] = []

    if image.size != expected_size:
        errs.append(f"画像サイズが違います: {image.size} != {expected_size}")
    if report.companies < 1:
        errs.append("掲載社数が0です（DATA WAIT のはずで画像を作ってはいけません）")

    errs += check_overflow(report.boxes)
    errs += check_overlap(report.boxes)

    if errs:
        raise QAError("画像の品質検査に失敗しました:\n  - " + "\n  - ".join(errs))


def write_thumbnail(image: Image.Image, path: Path, width: int = 400) -> Path:
    """目視確認用のサムネイル（既定 幅400px）を書き出す。"""
    height = round(image.height * width / image.width)
    thumb = image.convert("RGB").resize((width, height), Image.LANCZOS)
    path.parent.mkdir(parents=True, exist_ok=True)
    thumb.save(path, "PNG")
    return path


def _unused_draw_hint(draw: ImageDraw.ImageDraw) -> None:  # pragma: no cover
    """ImageDraw を import しておくための型ヒント用（実処理は render 側）。"""
