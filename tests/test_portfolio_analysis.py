"""手計算できる架空データで集中・為替・拠出調整を検算する。"""
from copy import deepcopy

import pytest

from src.portfolio_analysis import analyze


@pytest.fixture
def portfolio():
    return {
        "date": "2026-10-03", "total_jpy": 1000, "usdjpy": 100, "complete": True,
        "etf": {"VTI": {"name": "全米株", "curr_jpy": 500}},
        "fund": {"29313233": {"name": "NASDAQ投信", "curr_jpy": 300}},
        "stocks": {"FTNT": {"name": "Fortinet", "curr_jpy": 200, "shares": 2}},
        "history": [],
    }


def test_concentration_and_currency_sensitivity_are_hand_calculable(portfolio):
    result = analyze(portfolio)
    assert result["largest_holding"]["symbol"] == "VTI"
    assert result["largest_holding"]["pct"] == 50
    assert result["category_weights_pct"] == {"etf": 50, "fund": 30, "stocks": 20}
    assert result["direct_usd_exposure"]["value_jpy"] == 700
    assert result["direct_usd_exposure"]["per_yen_jpy"] == 7
    assert result["direct_usd_exposure"]["weight_pct"] == 70
    assert result["overlap"]["underlying_overlap_pct"] is None


def test_unknown_fund_does_not_become_assumed_us_exposure(portfolio):
    portfolio["fund"] = {"unknown": {"curr_jpy": 300}}
    result = analyze(portfolio)
    assert result["us_market_policy"]["known_product_weight_pct"] == 70
    assert result["us_market_policy"]["unknown_weight_pct"] == 30


def test_overlapping_nasdaq_products_are_qualitative_only(portfolio):
    portfolio["etf"]["QQQ"] = portfolio["etf"].pop("VTI")
    result = analyze(portfolio)
    assert result["overlap"]["groups"][0]["symbols"] == ["29313233", "QQQ"]
    assert result["overlap"]["underlying_overlap_pct"] is None


@pytest.mark.parametrize("bad_value", [None, float("nan"), float("inf"), -1, True])
def test_missing_or_invalid_position_never_creates_plausible_weights(portfolio, bad_value):
    portfolio["stocks"]["FTNT"]["curr_jpy"] = bad_value
    result = analyze(portfolio)
    assert result["category_weights_pct"] is None
    assert result["direct_usd_exposure"] is None


def test_total_mismatch_stops_ratios(portfolio):
    portfolio["total_jpy"] = 10000
    assert analyze(portfolio)["largest_holding"] is None


def test_drawdown_removes_deposit_and_withdrawal(portfolio):
    portfolio["history"] = [
        {"date": "2026-09-30", "total_jpy": 1000, "cash_flow_jpy": 0, "complete": True, "stale": False},
        {"date": "2026-10-01", "total_jpy": 2000, "cash_flow_jpy": 1000, "complete": True, "stale": False},
        {"date": "2026-10-02", "total_jpy": 1800, "cash_flow_jpy": 0, "complete": True, "stale": False},
        {"date": "2026-10-03", "total_jpy": 1700, "cash_flow_jpy": -100, "complete": True, "stale": False},
    ]
    portfolio["total_jpy"] = 1700
    portfolio["fund"]["29313233"]["curr_jpy"] = 1000
    assert analyze(portfolio)["max_drawdown"]["pct"] == -10


@pytest.mark.parametrize("mutation", ["stale", "missing_flow", "gap", "legacy", "wrong_last_value"])
def test_drawdown_declines_unverified_history(portfolio, mutation):
    portfolio["history"] = [
        {"date": "2026-10-02", "total_jpy": 1100, "cash_flow_jpy": 0, "complete": True, "stale": False},
        {"date": "2026-10-03", "total_jpy": 1000, "cash_flow_jpy": 0, "complete": True, "stale": False},
    ]
    first = portfolio["history"][0]
    if mutation == "stale":
        first["stale"] = True
    elif mutation == "missing_flow":
        first.pop("cash_flow_jpy")
    elif mutation == "gap":
        first["date"] = "2026-10-01"
    elif mutation == "legacy":
        first.pop("complete")
    else:
        portfolio["history"][-1]["total_jpy"] = 500
    assert analyze(portfolio)["max_drawdown"]["pct"] is None


def test_analysis_does_not_modify_input(portfolio):
    original = deepcopy(portfolio)
    analyze(portfolio)
    assert portfolio == original


def test_unknown_fx_and_stale_prices_are_explicit(portfolio):
    portfolio["usdjpy"] = None
    portfolio["stocks"]["FTNT"]["stale"] = True
    result = analyze(portfolio)
    assert result["direct_usd_exposure"] is None
    assert "旧価格" in result["notes"][0]
