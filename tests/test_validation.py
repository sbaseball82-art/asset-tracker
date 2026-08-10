# -*- coding: utf-8 -*-
"""
構成銘柄の検証（FANG+ の3ルールなど）のテスト。

壊れたレスポンスを採用しないこと、正常な四半期入替は
「中止」ではなく「検出」として扱われることを確かめる。
"""

import pytest

from src.lookthrough.compute import Constituent
from src.lookthrough.validation import validate_constituents

FANG_RULES = {"exact_count": 10, "weight_range": [8.0, 12.0],
              "max_member_diff": 2}

FANG10 = ["META", "AAPL", "AMZN", "NFLX", "NVDA",
          "GOOGL", "MSFT", "AVGO", "CRWD", "NOW"]


def equal_weight(tickers, weight=10.0):
    return [Constituent(ticker=t, weight_pct=weight) for t in tickers]


# --------------------------------------------------------------------------
# 正常系
# --------------------------------------------------------------------------

def test_等ウェイト10銘柄は検証を通る():
    r = validate_constituents(equal_weight(FANG10), FANG_RULES)
    assert r.ok
    assert r.problems == []


def test_多少ばらついていても範囲内なら通る():
    items = equal_weight(FANG10)
    items[0] = Constituent(ticker="META", weight_pct=11.5)
    items[1] = Constituent(ticker="AAPL", weight_pct=8.5)
    assert validate_constituents(items, FANG_RULES).ok


# --------------------------------------------------------------------------
# ルール1: 銘柄数がちょうど10
# --------------------------------------------------------------------------

def test_銘柄数が10でなければ不合格():
    r = validate_constituents(equal_weight(FANG10[:9], 11.11), FANG_RULES)
    assert not r.ok
    assert any("銘柄数が9件" in p for p in r.problems)


def test_多すぎても不合格():
    r = validate_constituents(equal_weight(FANG10 + ["TSLA"], 9.09), FANG_RULES)
    assert not r.ok
    assert any("11件" in p for p in r.problems)


# --------------------------------------------------------------------------
# ルール2: 概ね等ウェイト（8〜12%）
# --------------------------------------------------------------------------

def test_等ウェイトから外れたら不合格():
    items = equal_weight(FANG10)
    items[0] = Constituent(ticker="META", weight_pct=25.0)
    items[1] = Constituent(ticker="AAPL", weight_pct=3.0)
    r = validate_constituents(items, FANG_RULES)
    assert not r.ok
    assert any("範囲外" in p for p in r.problems)
    assert any("META" in p for p in r.problems)


def test_範囲外が多いときは件数を丸める():
    items = [Constituent(ticker=t, weight_pct=1.0) for t in FANG10]
    r = validate_constituents(items, FANG_RULES)
    assert not r.ok
    assert any("ほか" in p for p in r.problems)


# --------------------------------------------------------------------------
# ルール3: 前回からの差分が2銘柄以内
# --------------------------------------------------------------------------

def test_入替なしなら差分は空():
    r = validate_constituents(equal_weight(FANG10), FANG_RULES,
                              previous_tickers=FANG10)
    assert r.ok
    assert not r.changed
    assert r.diff_text() == "入替なし"


def test_2銘柄までの入替は通り入替として記録される():
    """四半期リバランスは正常。中止せず『検出』として扱う。"""
    now = FANG10[:8] + ["TSLA", "AMD"]
    r = validate_constituents(equal_weight(now), FANG_RULES,
                              previous_tickers=FANG10)
    assert r.ok                      # 中止しない
    assert r.changed                 # 入替は検出する
    assert set(r.added) == {"TSLA", "AMD"}
    assert set(r.removed) == {"CRWD", "NOW"}
    assert r.diff_count == 2
    assert "追加: AMD, TSLA" in r.diff_text()


def test_3銘柄以上の入替は不合格():
    now = FANG10[:7] + ["TSLA", "AMD", "INTC"]
    r = validate_constituents(equal_weight(now), FANG_RULES,
                              previous_tickers=FANG10)
    assert not r.ok
    assert any("3銘柄も入れ替わ" in p for p in r.problems)


def test_前回データが無ければ差分は見ない():
    r = validate_constituents(equal_weight(FANG10), FANG_RULES,
                              previous_tickers=None)
    assert r.ok
    assert not r.changed


def test_表記ゆれは入替とみなさない():
    prev = ["BRK-B"] + FANG10[:9]
    now = ["BRK.B"] + FANG10[:9]
    r = validate_constituents(equal_weight(now), FANG_RULES,
                              previous_tickers=prev)
    assert not r.changed


# --------------------------------------------------------------------------
# 最低件数（壊れたレスポンスを弾く）
# --------------------------------------------------------------------------

def test_件数が少なすぎるレスポンスは不合格():
    """『10銘柄しか返ってこないVTI』を掴まないための門。"""
    items = [Constituent(ticker=f"T{i}", weight_pct=0.5) for i in range(10)]
    r = validate_constituents(items, None, min_constituents=1000)
    assert not r.ok
    assert any("件数が少なすぎます: 10件" in p for p in r.problems)


def test_件数が足りていれば通る():
    items = [Constituent(ticker=f"T{i}", weight_pct=0.05) for i in range(1200)]
    assert validate_constituents(items, None, min_constituents=1000).ok


def test_0件は不合格():
    r = validate_constituents([], None)
    assert not r.ok
    assert "構成銘柄が0件" in r.problems


# --------------------------------------------------------------------------
# 構成比の合計
# --------------------------------------------------------------------------

def test_合計が100を超えたら不合格():
    items = [Constituent(ticker="A", weight_pct=60.0),
             Constituent(ticker="B", weight_pct=60.0)]
    r = validate_constituents(items, None)
    assert not r.ok
    assert any("100%を超え" in p for p in r.problems)


def test_合計が100未満でも件数条件を満たせば通る():
    """上位N銘柄しか取れないのは異常ではない（未カバー枠で扱う）。"""
    items = [Constituent(ticker=f"T{i}", weight_pct=1.0) for i in range(30)]
    assert validate_constituents(items, None, min_constituents=20).ok
