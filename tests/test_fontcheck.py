# -*- coding: utf-8 -*-
"""豆腐（□）検出のテスト。

日本語フォントが入っていない環境（CIの初期状態など）では skip する。
ワークフローでは fonts-noto-cjk を入れてから実行するため、そこでは動く。
"""

import shutil
from pathlib import Path

import pytest

from src.common import fontcheck

pytest.importorskip("PIL", reason="Pillow が必要")

# 日本語を持たないフォント（豆腐が出る側の確認に使う）
_LATIN_ONLY = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def _jp_font():
    try:
        return fontcheck.find_cjk_font()
    except fontcheck.FontNotFoundError:
        pytest.skip("日本語フォントが未インストール")


def test_日本語フォントが見つかる():
    path = _jp_font()
    assert Path(path).exists()


def test_日本語フォントなら豆腐は出ない():
    path = _jp_font()
    text = "わたしの資産推移｜中身の分解 総資産 ¥33,175,799 実質比率 ASSET LOG"
    assert fontcheck.missing_chars(text, path) == []


def test_記号や絵文字風の文字も検査対象になる():
    path = _jp_font()
    # ここで使う記号は Noto CJK に入っているはずのもの
    assert fontcheck.missing_chars("※・｜▲▼—", path) == []


@pytest.mark.skipif(not _LATIN_ONLY.exists(), reason="DejaVuSans が無い")
def test_日本語を持たないフォントでは豆腐として検出される():
    missing = fontcheck.missing_chars("資産推移", _LATIN_ONLY)
    assert set(missing) == set("資産推移")


@pytest.mark.skipif(not _LATIN_ONLY.exists(), reason="DejaVuSans が無い")
def test_英数字は日本語なしフォントでも欠落しない():
    assert fontcheck.missing_chars("ASSET LOG 123", _LATIN_ONLY) == []


@pytest.mark.skipif(not _LATIN_ONLY.exists(), reason="DejaVuSans が無い")
def test_日本語を出せないフォントはCJKフォントとして採用されない():
    assert not fontcheck._supports_japanese(_LATIN_ONLY)


def test_空白や改行は検査対象外():
    path = _jp_font()
    assert fontcheck.missing_chars("  \n\t ", path) == []


def test_check_textsはまとめて検査する():
    _jp_font()
    ok, missing, used = fontcheck.check_texts(["資産推移", "ASSET LOG"])
    assert ok
    assert missing == []
    assert used


@pytest.mark.skipif(shutil.which("fc-match") is None, reason="fc-match が無い")
def test_fc_matchの結果を鵜呑みにしない():
    """fc-match は日本語が無いフォントを返すことがある。

    'Noto Sans JP' が未インストールの環境では DejaVu などに落ちるため、
    find_cjk_font は日本語グリフを持つことを確かめてから返す必要がある。
    """
    path = _jp_font()
    assert fontcheck.missing_chars("資産", path) == []
