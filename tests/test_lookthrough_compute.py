# -*- coding: utf-8 -*-
"""
ルックスルー計算の検算テスト。

投稿に出す数字そのものなので、手計算で答えを出せる小さな例を用意し、
それと一致することを確かめる。
"""

import pytest

from src.lookthrough.compute import (
    Constituent, Fund, FundConstituents, ReconciliationError,
    group_pct, look_through, multi_fund_all, multi_fund_in_top_n,
    normalize_ticker, sector_breakdown, top_n_pct, via_breakdown_text,
)


def fc(fund_id, pairs, **kw):
    """(ticker, weight) の並びから FundConstituents を作る。"""
    items = tuple(Constituent(ticker=t, weight_pct=w,
                              name=kw.pop(f"name_{t}", None),
                              sector=kw.pop(f"sector_{t}", None))
                  for t, w in pairs)
    return FundConstituents(fund_id=fund_id, items=items, **kw)


# --------------------------------------------------------------------------
# 手計算での検算
# --------------------------------------------------------------------------

def test_実質保有額は評価額かける構成比():
    """1本だけ・構成比100%の単純な例。手計算と一致すること。

    VTI 1,000,000円、AAPL 40% / MSFT 60%
      AAPL = 1,000,000 × 0.40 = 400,000円 → 総資産比 40%
      MSFT = 1,000,000 × 0.60 = 600,000円 → 総資産比 60%
    """
    funds = [Fund("VTI", "VTI 全米株式ETF", "etf", 1_000_000)]
    cons = {"VTI": fc("VTI", [("AAPL", 40.0), ("MSFT", 60.0)])}

    r = look_through(funds, cons, total_jpy=1_000_000)

    assert [p.ticker for p in r.positions] == ["MSFT", "AAPL"]
    assert r.positions[0].amount_jpy == pytest.approx(600_000)
    assert r.positions[1].amount_jpy == pytest.approx(400_000)
    assert r.positions[1].pct_of_total == pytest.approx(40.0)
    assert r.uncovered_jpy == pytest.approx(0.0)
    assert r.coverage_pct == pytest.approx(100.0)


def test_複数ファンド経由の内訳が正しく合算される():
    """この機能の主眼。同じ銘柄を2本から持っている場合の内訳。

    VTI 1,000,000円 の AVGO 2.0% =  20,000円
    VYM   500,000円 の AVGO 5.0% =  25,000円
      → AVGO 合計 45,000円 / 総資産1,500,000円 の 3.0%
    """
    funds = [Fund("VTI", "VTI 全米株式ETF", "etf", 1_000_000),
             Fund("VYM", "VYM 米国高配当ETF", "etf", 500_000)]
    cons = {
        "VTI": fc("VTI", [("AVGO", 2.0), ("NVDA", 98.0)]),
        "VYM": fc("VYM", [("AVGO", 5.0), ("XOM", 95.0)]),
    }

    r = look_through(funds, cons, total_jpy=1_500_000)
    avgo = next(p for p in r.positions if p.ticker == "AVGO")

    assert avgo.amount_jpy == pytest.approx(45_000)
    assert avgo.pct_of_total == pytest.approx(3.0)
    assert avgo.fund_count == 2
    assert avgo.is_multi_fund

    # 内訳は金額の大きい順
    assert [(v.fund_id, v.amount_jpy) for v in avgo.via] == [
        ("VYM", pytest.approx(25_000)),
        ("VTI", pytest.approx(20_000)),
    ]


def test_内訳の合計は実質保有額に一致する():
    funds = [Fund("A", "ファンドA", "etf", 3_000_000),
             Fund("B", "ファンドB", "etf", 2_000_000),
             Fund("C", "ファンドC", "fund", 5_000_000)]
    cons = {
        "A": fc("A", [("NVDA", 10.0), ("MSFT", 90.0)]),
        "B": fc("B", [("NVDA", 25.0), ("XOM", 75.0)]),
        "C": fc("C", [("NVDA", 4.0), ("AAPL", 96.0)]),
    }
    r = look_through(funds, cons, total_jpy=10_000_000)
    nvda = next(p for p in r.positions if p.ticker == "NVDA")

    # 300,000 + 500,000 + 200,000 = 1,000,000
    assert nvda.amount_jpy == pytest.approx(1_000_000)
    assert sum(v.amount_jpy for v in nvda.via) == pytest.approx(nvda.amount_jpy)
    assert nvda.pct_of_total == pytest.approx(10.0)
    assert nvda.fund_count == 3


def test_単独保有は重複扱いにならない():
    funds = [Fund("A", "ファンドA", "etf", 1_000_000)]
    cons = {"A": fc("A", [("AAPL", 100.0)])}
    r = look_through(funds, cons, total_jpy=1_000_000)
    assert r.positions[0].fund_count == 1
    assert not r.positions[0].is_multi_fund
    assert multi_fund_all(r) == (0, 0.0)


# --------------------------------------------------------------------------
# 推測で埋めない
# --------------------------------------------------------------------------

def test_構成データが無いファンドは按分せず未分解になる():
    funds = [Fund("VTI", "VTI 全米株式ETF", "etf", 900_000),
             Fund("AI", "イノベーションAI", "fund", 100_000)]
    cons = {"VTI": fc("VTI", [("AAPL", 100.0)])}   # AI は渡さない

    r = look_through(funds, cons, total_jpy=1_000_000)

    assert len(r.unresolved) == 1
    assert r.unresolved[0].fund_id == "AI"
    assert r.unresolved[0].value_jpy == pytest.approx(100_000)
    # 未分解分は 0 で埋めず、按分にも入れない
    assert r.attributed_jpy == pytest.approx(900_000)
    assert r.coverage_pct == pytest.approx(90.0)
    assert all(p.ticker != "AI" for p in r.positions)


def test_エラー付きの構成データも未分解になる():
    funds = [Fund("X", "ファンドX", "etf", 1_000_000)]
    cons = {"X": FundConstituents(fund_id="X", error="取得失敗")}
    r = look_through(funds, cons, total_jpy=1_000_000)
    assert len(r.unresolved) == 1
    assert r.unresolved[0].reason == "取得失敗"
    assert r.positions == []


def test_構成比が100未満なら残りは未カバーとして別枠になる():
    """上位N銘柄しか取れないケース。取れていない分を推測で配らない。"""
    funds = [Fund("VTI", "VTI 全米株式ETF", "etf", 1_000_000)]
    cons = {"VTI": fc("VTI", [("AAPL", 30.0), ("MSFT", 20.0)])}  # 合計50%

    r = look_through(funds, cons, total_jpy=1_000_000)

    assert r.attributed_jpy == pytest.approx(500_000)
    assert r.uncovered_jpy == pytest.approx(500_000)
    assert r.fund_coverage["VTI"] == pytest.approx(50.0)
    assert r.coverage_pct == pytest.approx(50.0)


def test_構成比合計が100超ならデータ異常で止まる():
    funds = [Fund("X", "ファンドX", "etf", 1_000_000)]
    cons = {"X": fc("X", [("A", 60.0), ("B", 60.0)])}
    with pytest.raises(ValueError, match="100%を超え"):
        look_through(funds, cons, total_jpy=1_000_000)


# --------------------------------------------------------------------------
# 突合（受け入れ条件: 誤差1%以内）
# --------------------------------------------------------------------------

def test_按分と未カバーと未分解の合計は総資産に一致する():
    funds = [Fund("A", "A", "etf", 6_000_000),
             Fund("B", "B", "etf", 3_000_000),
             Fund("C", "C", "fund", 1_000_000)]
    cons = {"A": fc("A", [("AAPL", 50.0), ("MSFT", 30.0)]),   # 80%
            "B": fc("B", [("XOM", 100.0)])}                    # C は未分解
    r = look_through(funds, cons, total_jpy=10_000_000)

    total = r.attributed_jpy + r.uncovered_jpy + r.unresolved_jpy
    assert total == pytest.approx(10_000_000)


def test_保有合計が総資産と1パーセント超ずれたら止まる():
    funds = [Fund("A", "A", "etf", 1_000_000)]
    cons = {"A": fc("A", [("AAPL", 100.0)])}
    with pytest.raises(ReconciliationError, match="ずれて"):
        look_through(funds, cons, total_jpy=2_000_000)


def test_1パーセント以内のずれは許容される():
    funds = [Fund("A", "A", "etf", 1_000_000)]
    cons = {"A": fc("A", [("AAPL", 100.0)])}
    r = look_through(funds, cons, total_jpy=1_005_000)   # 0.5%ずれ
    assert r.attributed_jpy == pytest.approx(1_000_000)


# --------------------------------------------------------------------------
# 表記ゆれ
# --------------------------------------------------------------------------

@pytest.mark.parametrize("raw,want", [
    ("brk.b", "BRK.B"), ("BRK-B", "BRK.B"), ("BRK/B", "BRK.B"),
    (" aapl ", "AAPL"), ("BF--B", "BF.B"),
])
def test_ティッカーの表記ゆれを吸収する(raw, want):
    assert normalize_ticker(raw) == want


def test_表記ゆれのある同一銘柄は合算される():
    funds = [Fund("A", "A", "etf", 1_000_000),
             Fund("B", "B", "etf", 1_000_000)]
    cons = {"A": fc("A", [("BRK.B", 100.0)]),
            "B": fc("B", [("BRK-B", 100.0)])}
    r = look_through(funds, cons, total_jpy=2_000_000)
    assert len(r.positions) == 1
    assert r.positions[0].ticker == "BRK.B"
    assert r.positions[0].fund_count == 2


def test_別クラス株は別銘柄のまま扱う():
    funds = [Fund("A", "A", "etf", 1_000_000)]
    cons = {"A": fc("A", [("GOOG", 50.0), ("GOOGL", 50.0)])}
    r = look_through(funds, cons, total_jpy=1_000_000)
    assert {p.ticker for p in r.positions} == {"GOOG", "GOOGL"}


# --------------------------------------------------------------------------
# 集計指標
# --------------------------------------------------------------------------

def _sample():
    funds = [Fund("VTI", "VTI 全米株式ETF", "etf", 6_000_000),
             Fund("VYM", "VYM 米国高配当ETF", "etf", 4_000_000)]
    cons = {
        "VTI": fc("VTI", [("NVDA", 40.0), ("AVGO", 30.0), ("MSFT", 30.0)]),
        "VYM": fc("VYM", [("AVGO", 50.0), ("XOM", 50.0)]),
    }
    return look_through(funds, cons, total_jpy=10_000_000)


def test_上位n社の合計比率():
    r = _sample()
    # AVGO 1,800,000+2,000,000=3,800,000 / NVDA 2,400,000 / MSFT 1,800,000
    # / XOM 2,000,000  → 上位2社 = AVGO 38% + NVDA 24% = 62%
    assert top_n_pct(r, 2) == pytest.approx(62.0)
    assert top_n_pct(r, 10) == pytest.approx(100.0)


def test_上位n社のうち重複保有の数と比率():
    r = _sample()
    n, pct, hits = multi_fund_in_top_n(r, 10)
    assert n == 1
    assert [p.ticker for p in hits] == ["AVGO"]
    assert pct == pytest.approx(38.0)


def test_セクター別比率はセクター情報が無ければNone():
    r = _sample()
    assert sector_breakdown(r) is None


def test_セクター別比率は不明分を明示して残す():
    funds = [Fund("A", "A", "etf", 1_000_000)]
    cons = {"A": fc("A", [("AAPL", 60.0), ("XOM", 40.0)],
                    sector_AAPL="情報技術")}
    r = look_through(funds, cons, total_jpy=1_000_000)
    sec = sector_breakdown(r)
    assert sec == {"情報技術": pytest.approx(60.0), "不明": pytest.approx(40.0)}


def test_指定銘柄群の合計比率():
    r = _sample()
    assert group_pct(r, ["NVDA", "MSFT"]) == pytest.approx(42.0)
    assert group_pct(r, ["brk-b"]) == pytest.approx(0.0)


def test_経由内訳の文言():
    r = _sample()
    avgo = next(p for p in r.positions if p.ticker == "AVGO")
    text = via_breakdown_text(avgo)
    assert text.startswith("AVGO = ")
    assert "VYM 米国高配当ETF経由 2,000,000円" in text
    assert "VTI 全米株式ETF経由 1,800,000円" in text
