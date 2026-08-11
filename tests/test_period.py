# -*- coding: utf-8 -*-
"""
period（実行の単位）のテスト。

config.yml の schedule.lookthrough を weekly / monthly のどちらにしても、
出力先・履歴の粒度・「前週比／前月比」の表記が揃って変わることを確かめる。
"""

from datetime import date

import pytest

from src.lookthrough import history


# --------------------------------------------------------------------------
# period ID の生成
# --------------------------------------------------------------------------

@pytest.mark.parametrize("mode,d,want", [
    ("weekly", date(2026, 8, 10), "2026-W33"),
    ("weekly", date(2026, 1, 1), "2026-W01"),
    ("monthly", date(2026, 8, 10), "2026-08"),
    ("monthly", date(2026, 1, 1), "2026-01"),
])
def test_period_idを作る(mode, d, want):
    assert history.current_period(mode, d) == want


def test_モード指定が曖昧でも週次と解釈する():
    d = date(2026, 8, 10)
    assert history.current_period("weekly", d) == history.current_period("week", d)


def test_未知のモードは月次にする():
    assert history.current_period("なんとなく", date(2026, 8, 10)) == "2026-08"


@pytest.mark.parametrize("period,want", [
    ("2026-W33", True), ("2026-W01", True),
    ("2026-08", False), ("2026-1", False),
])
def test_週次かどうかを判定する(period, want):
    assert history.is_weekly(period) is want


# --------------------------------------------------------------------------
# 1つ前の period
# --------------------------------------------------------------------------

@pytest.mark.parametrize("period,want", [
    ("2026-W33", "2026-W32"),
    ("2026-W02", "2026-W01"),
    ("2026-W01", "2025-W52"),      # 年をまたぐ
    ("2026-08", "2026-07"),
    ("2026-01", "2025-12"),        # 年をまたぐ
])
def test_1つ前のperiod(period, want):
    assert history.prev_period(period) == want


def test_旧名prev_ymも同じ動きをする():
    assert history.prev_ym("2026-08") == "2026-07"
    assert history.prev_ym("2026-W33") == "2026-W32"


def test_週次のprevを繰り返すと1年前に戻る():
    p = "2026-W33"
    for _ in range(52):
        p = history.prev_period(p)
    assert p in ("2025-W33", "2025-W32")   # ISO年の週数（52/53）で1週ずれる


# --------------------------------------------------------------------------
# 表示ラベル
# --------------------------------------------------------------------------

def test_週次のラベルは日付まで出す():
    # 2026-W33 の日曜
    assert history.period_label("2026-W33") == "2026年8月16日 時点"


def test_月次のラベルは年月まで():
    assert history.period_label("2026-08") == "2026年8月 時点"


@pytest.mark.parametrize("period,prev,cmp_", [
    ("2026-W33", "前週", "前週比"),
    ("2026-08", "前月", "前月比"),
])
def test_比較の表記がperiodに追随する(period, prev, cmp_):
    assert history.prev_label(period) == prev
    assert history.comparison_label(period) == cmp_


# --------------------------------------------------------------------------
# スナップショットが period 単位で分かれること
# --------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_history(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "HISTORY_DIR", tmp_path)
    return tmp_path


def build(weights: dict[str, float]):
    from src.lookthrough.compute import (
        Constituent, Fund, FundConstituents, look_through,
    )
    items = tuple(Constituent(ticker=t, weight_pct=w)
                  for t, w in weights.items())
    funds = [Fund("F", "ファンドF", "etf", 1_000_000)]
    cons = {"F": FundConstituents(fund_id="F", items=items)}
    return look_through(funds, cons, total_jpy=1_000_000)


def test_週次スナップショットのファイル名(tmp_history):
    history.save_snapshot("2026-W33", build({"AAPL": 100.0}))
    assert (tmp_history / "lookthrough_2026-W33.json").exists()


def test_週次で前週と比較できる(tmp_history):
    history.save_snapshot("2026-W32", build({"AAPL": 60.0, "MSFT": 40.0}))
    changes, prev = history.compare_with_prev(
        "2026-W33", build({"MSFT": 70.0, "AAPL": 30.0}))

    assert prev == "2026-W32"
    by = {c.ticker: c for c in changes}
    assert by["MSFT"].delta == 1
    assert by["AAPL"].delta == -1


def test_週次と月次のスナップショットは混ざらない(tmp_history):
    history.save_snapshot("2026-08", build({"AAPL": 100.0}))
    # 週次で走らせても、月次のスナップショットは前週分として拾わない
    changes, prev = history.compare_with_prev("2026-W33", build({"AAPL": 100.0}))
    assert prev is None
    assert changes[0].is_new


def test_前週分が無ければ比較しない(tmp_history):
    changes, prev = history.compare_with_prev("2026-W33", build({"AAPL": 100.0}))
    assert prev is None
    assert changes[0].prev_rank is None
