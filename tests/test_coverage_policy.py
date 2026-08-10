# -*- coding: utf-8 -*-
"""
coverage_policy（required / best_effort / excluded）と
カバレッジ闾値ゲートのテスト。

「取れなかった」と「取らないと決めた」を区別できていることを確かめる。
"""

import pytest

from src.lookthrough import generate
from src.lookthrough.compute import (
    POLICY_BEST_EFFORT, POLICY_EXCLUDED, POLICY_REQUIRED,
    Constituent, Fund, FundConstituents, look_through,
)


def fc(fund_id, pairs, policy=POLICY_REQUIRED, **kw):
    items = tuple(Constituent(ticker=t, weight_pct=w) for t, w in pairs)
    return FundConstituents(fund_id=fund_id, items=items, policy=policy, **kw)


def excluded(fund_id, reason="小さいので対象外"):
    return FundConstituents(fund_id=fund_id, policy=POLICY_EXCLUDED,
                            excluded_reason=reason, error="分解対象外（excluded）")


# --------------------------------------------------------------------------
# excluded
# --------------------------------------------------------------------------

def test_excludedは未分解ではなく対象外になる():
    funds = [Fund("VTI", "VTI 全米株式ETF", "etf", 9_900_000),
             Fund("AI", "イノベーションAI", "fund", 100_000)]
    cons = {"VTI": fc("VTI", [("AAPL", 100.0)]), "AI": excluded("AI")}

    r = look_through(funds, cons, total_jpy=10_000_000)

    assert r.unresolved == []                    # 警告に出さない
    assert len(r.excluded) == 1
    assert r.excluded[0].fund_name == "イノベーションAI"
    assert r.excluded_jpy == pytest.approx(100_000)


def test_excludedは分母から外すとカバレッジが下がらない():
    funds = [Fund("VTI", "VTI", "etf", 9_900_000),
             Fund("AI", "イノベーションAI", "fund", 100_000)]
    cons = {"VTI": fc("VTI", [("AAPL", 100.0)]), "AI": excluded("AI")}
    r = look_through(funds, cons, total_jpy=10_000_000)

    # 総資産に対しては99%だが、対象外を除けば100%
    assert r.coverage_pct == pytest.approx(99.0)
    assert r.effective_coverage_pct(exclude_declared=True) == pytest.approx(100.0)
    assert r.effective_coverage_pct(exclude_declared=False) == pytest.approx(99.0)


def test_excludedを含めても突合は成り立つ():
    funds = [Fund("A", "A", "etf", 6_000_000),
             Fund("B", "B", "etf", 3_000_000),
             Fund("C", "C", "fund", 1_000_000)]
    cons = {"A": fc("A", [("AAPL", 50.0)]),       # 50%だけ
            "B": fc("B", [("XOM", 100.0)]),
            "C": excluded("C")}
    r = look_through(funds, cons, total_jpy=10_000_000)

    total = (r.attributed_jpy + r.uncovered_jpy
             + r.unresolved_jpy + r.excluded_jpy)
    assert total == pytest.approx(10_000_000)


# --------------------------------------------------------------------------
# required / best_effort
# --------------------------------------------------------------------------

def test_requiredが取れなければ中止対象になる():
    funds = [Fund("VTI", "VTI", "etf", 5_000_000),
             Fund("VYM", "VYM", "etf", 5_000_000)]
    cons = {"VTI": fc("VTI", [("AAPL", 100.0)]),
            "VYM": FundConstituents(fund_id="VYM", policy=POLICY_REQUIRED,
                                    error="取得失敗")}
    r = look_through(funds, cons, total_jpy=10_000_000)

    assert len(r.missing_required) == 1
    assert r.missing_required[0].fund_id == "VYM"
    assert generate._halt_reason(r, 50.0, {}) is not None


def test_best_effortが取れなくても中止しない():
    funds = [Fund("VTI", "VTI", "etf", 9_900_000),
             Fund("X", "小さいファンド", "fund", 100_000)]
    cons = {"VTI": fc("VTI", [("AAPL", 100.0)]),
            "X": FundConstituents(fund_id="X", policy=POLICY_BEST_EFFORT,
                                  error="取得失敗")}
    r = look_through(funds, cons, total_jpy=10_000_000)

    assert r.missing_required == []
    assert len(r.unresolved) == 1                 # 記録は残る
    assert r.unresolved[0].policy == POLICY_BEST_EFFORT
    assert generate._halt_reason(r, 99.0, {}) is None


# --------------------------------------------------------------------------
# カバレッジ闾値ゲート
# --------------------------------------------------------------------------

def _ok_result():
    funds = [Fund("VTI", "VTI", "etf", 10_000_000)]
    cons = {"VTI": fc("VTI", [("AAPL", 100.0)])}
    return look_through(funds, cons, total_jpy=10_000_000)


def test_カバレッジが下限を下回ったら中止する():
    r = _ok_result()
    reason = generate._halt_reason(r, 72.0, {})
    assert reason is not None
    assert "72.0%" in reason
    assert "90%" in reason


def test_カバレッジが下限以上なら中止しない():
    assert generate._halt_reason(_ok_result(), 90.0, {}) is None
    assert generate._halt_reason(_ok_result(), 99.7, {}) is None


def test_requiredの欠落はカバレッジより先に報告される():
    funds = [Fund("A", "ファンドA", "etf", 10_000_000)]
    cons = {"A": FundConstituents(fund_id="A", policy=POLICY_REQUIRED,
                                  error="取得失敗")}
    r = look_through(funds, cons, total_jpy=10_000_000)
    reason = generate._halt_reason(r, 0.0, {})
    assert "required" in reason
    assert "ファンドA" in reason


# --------------------------------------------------------------------------
# 画像の注記
# --------------------------------------------------------------------------

def test_対象外は要手動確認ではなく分解対象外と書かれる():
    funds = [Fund("VTI", "VTI 全米株式ETF", "etf", 9_900_000),
             Fund("AI", "イノベーションAI", "fund", 100_000)]
    cons = {"VTI": fc("VTI", [("AAPL", 100.0)]), "AI": excluded("AI")}
    r = look_through(funds, cons, total_jpy=10_000_000)

    warning = generate._image_warning(r, {"AI": "イノベーションAI"})
    assert "分解対象外" in warning
    assert "イノベーションAI" in warning
    assert "要手動確認" not in warning


def test_取得失敗は要手動確認と書かれる():
    funds = [Fund("VTI", "VTI", "etf", 9_900_000),
             Fund("X", "取れないファンド", "fund", 100_000)]
    cons = {"VTI": fc("VTI", [("AAPL", 100.0)]),
            "X": FundConstituents(fund_id="X", policy=POLICY_BEST_EFFORT,
                                  error="取得失敗")}
    r = look_through(funds, cons, total_jpy=10_000_000)

    warning = generate._image_warning(r, {})
    assert "要手動確認" in warning
    assert "取れないファンド" in warning


# --------------------------------------------------------------------------
# source の記録
# --------------------------------------------------------------------------

def test_採用したsourceが記録される():
    funds = [Fund("VTI", "VTI", "etf", 10_000_000)]
    cons = {"VTI": fc("VTI", [("AAPL", 100.0)], source_id="vanguard_api")}
    r = look_through(funds, cons, total_jpy=10_000_000)
    assert r.sources["VTI"] == "vanguard_api"


def test_銘柄入替が結果に載る():
    funds = [Fund("F", "iFreeNEXT FANG+", "fund", 10_000_000)]
    cons = {"F": fc("F", [("META", 100.0)],
                    change_note="銘柄入替を検出（追加: TSLA / 除外: CRWD）")}
    r = look_through(funds, cons, total_jpy=10_000_000)
    assert len(r.changes) == 1
    assert "TSLA" in r.changes[0]["note"]
