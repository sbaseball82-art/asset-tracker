# -*- coding: utf-8 -*-
"""文字数チェック（全角280字・半角0.5字換算）のテスト。"""

from src.common.textcheck import check_post, x_units, zenkaku_len


def test_ascii_counts_half():
    assert x_units("abc 123") == 7
    assert zenkaku_len("abc 123") == 3.5


def test_zenkaku_counts_one():
    assert x_units("あいう") == 6
    assert zenkaku_len("あいう") == 3.0


def test_mixed():
    # 半角3文字 + 全角4文字
    assert zenkaku_len("VYMは高配当") == 1.5 + 4.0


def test_url_fixed_weight():
    assert x_units("https://example.com/very/long/path/here") == 23
    assert zenkaku_len("見て https://example.com") == 2.0 + 0.5 + 11.5


def test_check_post_ok():
    ok, n, warn = check_post("あ" * 280)  # 全角280字ちょうど
    assert ok and n == 280 and warn == ""


def test_check_post_over():
    ok, n, warn = check_post("あ" * 281)
    assert not ok and n == 281 and "超過" in warn


def test_halfwidth_rounds_up():
    ok, n, _ = check_post("a")
    assert ok and n == 1  # 0.5 → 切り上げ
