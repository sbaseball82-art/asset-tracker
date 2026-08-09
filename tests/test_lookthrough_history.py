# -*- coding: utf-8 -*-
"""月次スナップショットと前月比（順位変動）のテスト。"""

import pytest

from src.lookthrough import history
from src.lookthrough.compute import Constituent, Fund, FundConstituents, look_through


@pytest.fixture(autouse=True)
def tmp_history(tmp_path, monkeypatch):
    """本物の data/history を汚さないよう一時ディレクトリに差し替える。"""
    monkeypatch.setattr(history, "HISTORY_DIR", tmp_path)
    return tmp_path


def build(weights: dict[str, float]):
    """{ティッカー: 構成比} 1本のファンドから結果を作る。"""
    items = tuple(Constituent(ticker=t, weight_pct=w)
                  for t, w in weights.items())
    funds = [Fund("F", "ファンドF", "etf", 1_000_000)]
    cons = {"F": FundConstituents(fund_id="F", items=items)}
    return look_through(funds, cons, total_jpy=1_000_000)


@pytest.mark.parametrize("ym,want", [
    ("2026-08", "2026-07"),
    ("2026-01", "2025-12"),
    ("2026-12", "2026-11"),
])
def test_前月の年月(ym, want):
    assert history.prev_ym(ym) == want


def test_スナップショットを保存して読み戻せる():
    r = build({"AAPL": 60.0, "MSFT": 40.0})
    history.save_snapshot("2026-07", r)
    snap = history.load_snapshot("2026-07")
    assert snap["ym"] == "2026-07"
    assert snap["positions"][0]["ticker"] == "AAPL"
    assert snap["positions"][0]["rank"] == 1


def test_前月データが無ければ比較しない():
    r = build({"AAPL": 100.0})
    changes, prev = history.compare_with_prev("2026-08", r)
    assert prev is None
    assert changes[0].prev_rank is None
    assert changes[0].delta is None
    assert changes[0].is_new


def test_順位が上がったらプラスの変動になる():
    history.save_snapshot("2026-07", build({"AAPL": 60.0, "MSFT": 40.0}))
    # 翌月は MSFT が1位に入れ替わる
    r = build({"MSFT": 70.0, "AAPL": 30.0})
    changes, prev = history.compare_with_prev("2026-08", r)

    assert prev == "2026-07"
    by = {c.ticker: c for c in changes}
    assert by["MSFT"].rank == 1 and by["MSFT"].prev_rank == 2
    assert by["MSFT"].delta == 1            # 2位→1位 は +1
    assert by["AAPL"].delta == -1           # 1位→2位 は -1
    assert by["MSFT"].pct_delta == pytest.approx(30.0)


def test_新しく入った銘柄はNEW扱い():
    history.save_snapshot("2026-07", build({"AAPL": 100.0}))
    r = build({"AAPL": 60.0, "NVDA": 40.0})
    changes, _ = history.compare_with_prev("2026-08", r)
    nvda = next(c for c in changes if c.ticker == "NVDA")
    assert nvda.is_new
    assert history.arrow(nvda.delta) == "NEW"


@pytest.mark.parametrize("delta,want", [(3, "▲3"), (-2, "▼2"), (0, "—"),
                                        (None, "NEW")])
def test_変動記号(delta, want):
    assert history.arrow(delta) == want


def test_壊れたスナップショットは無視される(tmp_history):
    (tmp_history / "lookthrough_2026-07.json").write_text("{壊れています",
                                                          encoding="utf-8")
    r = build({"AAPL": 100.0})
    changes, prev = history.compare_with_prev("2026-08", r)
    assert prev is None
    assert changes[0].prev_rank is None
