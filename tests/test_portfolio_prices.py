"""価格・資金移動の検算。価格はネットワークを使わない架空のテスト値。"""
import copy
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import config
import fetch_prices as prices

NOW = datetime(2026, 10, 30, 7, tzinfo=prices.JST)
FX = {"rate": 150.0, "prev_rate": 148.0, "curr_date": "2026-10-29",
      "prev_date": "2026-10-28", "source": "test fixture", "stale": False}
META = {"name": "Fortinet", "shares": 7, "purchase_price_usd": None,
        "purchase_date": None, "purchase_usdjpy": None, "currency": "USD", "market": "NASDAQ"}
QUOTE = {"curr_price": 110.0, "prev_price": 100.0, "curr_date": "2026-10-29",
         "prev_date": "2026-10-28", "change_pct": 10.0, "stale": False, "source": "test fixture"}


def public_data():
    etf = {symbol: {"name": name, "shares": qty, "curr_price": 100.0,
                   "prev_price": 100.0, "curr_jpy": round(qty * 100 * 150),
                   "prev_jpy": round(qty * 100 * 148), "curr_date": "2026-10-29"}
           for symbol, (name, qty) in config.ETF_HOLDINGS.items()}
    fund = {symbol: {"name": name, "units": qty, "curr_nav": 10000.0,
                    "prev_nav": 10000.0, "curr_jpy": qty, "prev_jpy": qty,
                    "curr_date": "2026-10-29"}
            for symbol, (name, qty, isin) in config.FUND_HOLDINGS.items()}
    total = sum(row["curr_jpy"] for row in [*etf.values(), *fund.values()])
    return {"etf": etf, "fund": fund, "fx": copy.deepcopy(FX), "usdjpy": 150.0,
            "date": "2026-10-30", "updated_at": NOW.isoformat(), "total_jpy": total,
            "history": [{"date": "2026-10-29", "total_jpy": total, "cash_flow_jpy": 0}]}


def test_config_reads_all_quantities_from_holdings():
    holdings = json.loads((Path(__file__).parents[1] / "holdings.json").read_text())
    assert {s: row[1] for s, row in config.ETF_HOLDINGS.items()} == holdings["etf"]
    assert {s: row[1] for s, row in config.FUND_HOLDINGS.items()} == holdings["fund"]
    assert config.load_stocks()["FTNT"]["shares"] == holdings["stocks"]["FTNT"]["shares"]
    assert len(holdings["etf"]) + len(holdings["fund"]) + len(holdings["stocks"]) == 12


def test_requested_stock_quantity_82_has_exact_yen_value():
    row = prices.stock_valuation({**META, "shares": 82}, QUOTE, FX)
    assert row["curr_jpy"] == 1_353_000


def test_stock_value_includes_previous_fx_and_unknown_cost():
    row = prices.stock_valuation(META, QUOTE, FX)
    assert row["curr_jpy"] == 115500
    assert row["prev_jpy"] == 103600
    assert row["change_jpy"] == 11900
    assert row["unrealized_gain_usd"] is None
    assert row["unrealized_jpy"] is None
    assert row["unrealized_pct"] is None
    assert row["cost_basis_status"] == "未設定"


def test_dollar_cost_does_not_guess_purchase_fx():
    meta = {**META, "purchase_price_usd": 100}
    row = prices.stock_valuation(meta, QUOTE, FX)
    assert row["unrealized_gain_usd"] == 70
    assert row["unrealized_pct"] == 10
    assert row["unrealized_jpy"] is None
    row = prices.stock_valuation({**meta, "purchase_usdjpy": 140}, QUOTE, FX)
    assert row["unrealized_jpy"] == 17500


def test_twelve_holdings_and_first_integrated_history_is_separate():
    public = public_data()
    result = prices.portfolio_snapshot(public, {}, {"FTNT": prices.stock_valuation(META, QUOTE, FX)}, NOW)
    assert len(result["etf"]) + len(result["fund"]) + len(result["stocks"]) == 12
    assert result["total_jpy"] == public["total_jpy"] + 115500
    assert result["legacy_history"] == public["history"]
    assert len(result["history"]) == 1
    assert result["history"][0]["cash_flow_jpy"] == 0
    assert all(v is None for v in result["comparisons"].values())


def test_buying_more_is_not_market_profit_and_rerun_is_idempotent():
    public = public_data()
    previous = prices.portfolio_snapshot(public, {}, {"FTNT": prices.stock_valuation(META, QUOTE, FX)}, NOW)
    public["date"] = "2026-10-31"
    row = prices.stock_valuation({**META, "shares": 9}, QUOTE, FX)
    result = prices.portfolio_snapshot(public, previous, {"FTNT": row}, NOW + timedelta(days=1))
    assert result["history"][-1]["cash_flow_jpy"] == 33000
    assert result["comparisons"]["day"]["gross_change_jpy"] == 33000
    assert result["comparisons"]["day"]["change_jpy"] == 0
    rerun = prices.portfolio_snapshot(public, result, {"FTNT": row}, NOW + timedelta(days=1))
    assert rerun["history"] == result["history"]
    assert rerun["comparisons"] == result["comparisons"]
    row2 = prices.stock_valuation({**META, "shares": 10}, QUOTE, FX)
    again = prices.portfolio_snapshot(public, rerun, {"FTNT": row2}, NOW + timedelta(days=1))
    assert again["history"][-1]["cash_flow_jpy"] == 49500
    assert again["comparisons"]["day"]["change_jpy"] == 0


def test_missing_price_is_not_zero_or_a_partial_total():
    public = public_data()
    quote = {"curr_price": None, "stale": True, "curr_date": None}
    result = prices.portfolio_snapshot(public, {}, {"FTNT": prices.stock_valuation(META, quote, FX)}, NOW)
    assert result["stocks"]["FTNT"]["curr_jpy"] is None
    assert result["complete"] is False
    assert result["total_jpy"] is None
    assert result["known_total_jpy"] == public["total_jpy"]
    assert result["history"] == []


def test_failed_stock_fetch_keeps_confirmed_price_date_and_revalues_quantity(monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("offline")
    monkeypatch.setattr(prices.yf, "Ticker", lambda sym: SimpleNamespace(history=fail))
    old = prices.stock_valuation(META, QUOTE, FX)
    row = prices.fetch_stock_prices({"FTNT": {**META, "shares": 9}}, FX, {"FTNT": old})["FTNT"]
    assert row["curr_jpy"] == 148500
    assert row["curr_date"] == "2026-10-29"
    assert row["stale"] and row["fetch_failed"]
    assert row["change_pct"] is None
    assert row["prev_jpy"] is None


def test_invalid_prices_are_not_accepted(monkeypatch):
    frame = pd.DataFrame({"Close": [100.0, float("inf")]}, index=pd.date_range("2026-10-28", periods=2))
    monkeypatch.setattr(prices.yf, "Ticker", lambda sym: SimpleNamespace(history=lambda **kwargs: frame))
    row = prices.fetch_stock_prices({"FTNT": META}, FX)["FTNT"]
    assert row["missing"] and row["curr_jpy"] is None
    for invalid in (float("nan"), float("inf"), -10, 0, True, None):
        assert not prices.valid_price(invalid)


def test_stock_uses_unadjusted_close(monkeypatch):
    frame = pd.DataFrame({"Close": [100.0, 110.0]}, index=pd.date_range("2026-10-28", periods=2))
    calls = []
    def history(**kwargs):
        calls.append(kwargs)
        return frame
    monkeypatch.setattr(prices.yf, "Ticker", lambda sym: SimpleNamespace(history=history))
    row = prices.fetch_stock_prices({"FTNT": META}, FX)["FTNT"]
    assert calls[0]["auto_adjust"] is False
    assert row["curr_jpy"] == 115500


def test_fx_failure_never_uses_a_fabricated_rate(monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("offline")
    monkeypatch.setattr(prices.yf, "Ticker", lambda sym: SimpleNamespace(history=fail))
    with pytest.raises(RuntimeError, match="確認済み為替"):
        prices.fetch_fx({"usdjpy": 150.0})
    cached = prices.fetch_fx({"fx": FX})
    assert cached["rate"] == 150.0
    assert cached["curr_date"] == FX["curr_date"]
    assert cached["stale"] is True


def test_no_false_ytd_or_week_when_history_is_too_short():
    history = [{"date": "2026-10-29", "total_jpy": 100, "cash_flow_jpy": 0},
               {"date": "2026-10-30", "total_jpy": 110, "cash_flow_jpy": 0}]
    comp = prices.build_comparisons(history, 110, NOW)
    assert comp["day"]["change_jpy"] == 10
    assert comp["week"] is None and comp["month"] is None and comp["ytd"] is None


def test_ytd_uses_previous_year_end_and_excludes_contributions():
    history = [{"date": "2025-12-31", "total_jpy": 100, "cash_flow_jpy": 0},
               {"date": "2026-01-01", "total_jpy": 200, "cash_flow_jpy": 100},
               {"date": "2026-10-30", "total_jpy": 220, "cash_flow_jpy": 0}]
    comp = prices.build_comparisons(history, 220, NOW)["ytd"]
    assert comp["base_date"] == "2025-12-31"
    assert comp["change_jpy"] == 20 and comp["change_pct"] == 20


def test_stock_configuration_rejects_invalid_input(monkeypatch):
    monkeypatch.setattr(config, "STOCK_HOLDINGS", {"FTNT": {**META, "shares": -7}})
    with pytest.raises(ValueError):
        config.load_stocks()
    monkeypatch.setattr(config, "STOCK_HOLDINGS", {"FTNT": META})
    assert config.load_stocks()["FTNT"]["shares"] == 7


def test_public_failure_keeps_previous_data_and_stops(monkeypatch, tmp_path):
    dest = tmp_path / "data.json"
    dest.write_text('{"history": []}')
    monkeypatch.setattr(prices, "OUTPUT_FILE", dest)
    monkeypatch.setattr(prices, "fetch_fx", lambda *args: FX)
    monkeypatch.setattr(prices, "fetch_etf_prices", lambda *args: {})
    monkeypatch.setattr(prices, "fetch_fund_prices", lambda: {})
    with pytest.raises(RuntimeError, match="部分合計"):
        prices.main()
    assert dest.read_text() == '{"history": []}'


def test_selling_all_stock_is_withdrawal_not_market_loss():
    public = public_data()
    previous = prices.portfolio_snapshot(public, {}, {"FTNT": prices.stock_valuation(META, QUOTE, FX)}, NOW)
    public["date"] = "2026-10-31"
    row = prices.stock_valuation({**META, "shares": 0}, QUOTE, FX)
    sold = prices.portfolio_snapshot(public, previous, {"FTNT": row}, NOW + timedelta(days=1))
    assert sold["history"][-1]["cash_flow_jpy"] == -115500
    assert sold["comparisons"]["day"]["change_jpy"] == 0
    assert sold["stocks"]["FTNT"]["curr_jpy"] == 0


def test_stale_fx_does_not_claim_daily_yen_change():
    row = prices.stock_valuation(META, QUOTE, {**FX, "stale": True})
    assert row["curr_jpy"] == 115500
    assert row["prev_jpy"] is None
    assert row["change_jpy"] is None


def test_quantity_mismatch_in_legacy_data_is_incomplete():
    public = public_data()
    public["etf"]["VTI"]["shares"] += 1
    result = prices.portfolio_snapshot(public, {}, {"FTNT": prices.stock_valuation(META, QUOTE, FX)}, NOW)
    assert result["complete"] is False
    assert result["total_jpy"] is None
    assert result["history"] == []


def test_old_fx_without_provenance_is_not_adopted():
    public = public_data()
    del public["fx"]
    result = prices.portfolio_snapshot(public, {}, {"FTNT": prices.stock_valuation(META, QUOTE, FX)}, NOW)
    assert result["complete"] is False
    assert result["total_jpy"] is None
    assert result["fx"]["rate"] is None


def test_stale_period_and_missing_yesterday_are_not_returns():
    history = [{"date": "2026-10-28", "total_jpy": 100, "cash_flow_jpy": 0},
               {"date": "2026-10-30", "total_jpy": 110, "cash_flow_jpy": 0}]
    assert prices.build_comparisons(history, 110, NOW)["day"] is None
    history[0]["date"] = "2026-10-29"
    history[0]["stale"] = True
    assert prices.build_comparisons(history, 110, NOW)["day"] is None


def test_portfolio_cli_keeps_last_complete_on_failed_quote(monkeypatch, tmp_path):
    public = public_data()
    previous = prices.portfolio_snapshot(public, {}, {"FTNT": prices.stock_valuation(META, QUOTE, FX)}, NOW)
    monkeypatch.chdir(tmp_path)
    Path("data.json").write_text(json.dumps(public))
    old = json.dumps(previous)
    Path("portfolio_last_complete.json").write_text(old)
    missing = prices.stock_valuation(META, {"curr_price": None, "curr_date": None, "stale": True}, FX)
    monkeypatch.setattr(prices, "fetch_stock_prices", lambda *args: {"FTNT": missing})
    assert prices.portfolio_main() == 2
    assert Path("portfolio_last_complete.json").read_text() == old
    output = json.loads(Path("portfolio.json").read_text())
    assert output["total_jpy"] is None
    assert output["history"] == previous["history"]
    assert "analysis" in output


def test_stock_jpy_daily_change_requires_matching_fx_dates():
    row = prices.stock_valuation(META, QUOTE, {**FX, "curr_date": "2026-10-30", "prev_date": "2026-10-29"})
    assert row["curr_jpy"] == 115500
    assert row["change_pct"] == 10  # USD価格の比較は成立する
    assert row["prev_jpy"] is None and row["change_jpy"] is None
    row = prices.stock_valuation(META, QUOTE, {**FX, "prev_date": None})
    assert row["prev_jpy"] is None and row["change_jpy"] is None


@pytest.mark.parametrize("key,base_date", [("week", "2026-10-18"), ("month", "2026-09-25"), ("ytd", "2025-12-23")])
def test_comparison_does_not_substitute_a_distant_record(key, base_date):
    history = [{"date": base_date, "total_jpy": 100, "cash_flow_jpy": 0},
               {"date": "2026-10-30", "total_jpy": 110, "cash_flow_jpy": 0}]
    assert prices.build_comparisons(history, 110, NOW)[key] is None


@pytest.mark.parametrize("key,base_date", [("week", "2026-10-19"), ("month", "2026-09-26"), ("ytd", "2025-12-24")])
def test_comparison_accepts_bounded_holiday_gap(key, base_date):
    history = [{"date": base_date, "total_jpy": 100, "cash_flow_jpy": 0},
               {"date": "2026-10-30", "total_jpy": 110, "cash_flow_jpy": 0}]
    assert prices.build_comparisons(history, 110, NOW)[key]["change_jpy"] == 10


def test_reported_split_preserves_quantity_and_suppresses_performance(monkeypatch):
    frame = pd.DataFrame({"Close": [100.0, 110.0], "Stock Splits": [0.0, 2.0]},
                         index=pd.date_range("2026-10-28", periods=2))
    monkeypatch.setattr(prices.yf, "Ticker", lambda sym: SimpleNamespace(history=lambda **kwargs: frame))
    row = prices.fetch_stock_prices({"FTNT": META}, FX)["FTNT"]
    assert row["shares"] == 7 and row["curr_jpy"] == 115500
    assert row["corporate_action_review"] is True
    assert row["change_pct"] is None and row["change_jpy"] is None
    assert row["split_events"] == [{"date": "2026-10-29", "ratio": 2.0}]
    public = public_data()
    previous = prices.portfolio_snapshot(public, {}, {"FTNT": prices.stock_valuation(META, QUOTE, FX)}, NOW - timedelta(days=1))
    current = prices.portfolio_snapshot(public, previous, {"FTNT": row}, NOW)
    assert any("株式分割" in warning for warning in current["warnings"])
    assert current["comparisons"]["day"] is None


def test_etf_keeps_legacy_previous_value_but_suppresses_misaligned_daily_change(monkeypatch):
    frame = pd.DataFrame({"Close": [100.0, 110.0], "Stock Splits": [0.0, 0.0]},
                         index=pd.date_range("2026-10-28", periods=2))
    monkeypatch.setattr(prices, "ETF_HOLDINGS", {"TEST": ("Test ETF", 7)})
    monkeypatch.setattr(prices.yf, "download", lambda **kwargs: frame)
    row = prices.fetch_etf_prices(150, 148, {**FX, "curr_date": "2026-10-30"})["TEST"]
    assert row["curr_jpy"] == 115500 and row["prev_jpy"] == 103600
    assert row["change_jpy"] is None
    row = prices.fetch_etf_prices(150, 148, FX)["TEST"]
    assert row["change_jpy"] == 11900
