# -*- coding: utf-8 -*-
"""指数寄与の計算（構成比 × 騰落率）の検算テスト。受け入れ条件の必須項目。"""

import pytest

from src.earnings.contribution import (effective_holding_pct,
                                       index_contribution,
                                       portfolio_impact_pct)


class TestIndexContribution:
    def test_basic(self):
        # S&P500構成比7%の銘柄が-5% → 指数寄与 -0.35%pt
        assert index_contribution(7.0, -5.0) == pytest.approx(-0.35)

    def test_positive(self):
        # 構成比6%が+10% → +0.6%pt
        assert index_contribution(6.0, 10.0) == pytest.approx(0.6)

    def test_zero_weight(self):
        assert index_contribution(0.0, 12.3) == 0.0

    def test_zero_change(self):
        assert index_contribution(7.0, 0.0) == 0.0

    def test_kensan_manual(self):
        # 検算: NVDA構成比7.0% × 騰落-8.2% = -0.574%pt（手計算と一致）
        assert index_contribution(7.0, -8.2) == pytest.approx(-0.574)


class TestEffectiveHolding:
    def test_multi_fund(self):
        # VTI 35%保有 × VTI内5% + QQQ 5.5%保有 × QQQ内8%
        shares = {"VTI": 35.0, "QQQ": 5.5}
        weights = {"VTI": 5.0, "QQQ": 8.0}
        expected = 35.0 * 0.05 + 5.5 * 0.08  # = 1.75 + 0.44 = 2.19
        assert effective_holding_pct(shares, weights) == pytest.approx(expected)

    def test_missing_fund_ignored(self):
        # 保有していないファンドのウェイトは無視される
        assert effective_holding_pct({"VTI": 35.0}, {"QQQ": 8.0}) == 0.0

    def test_fund_id_as_int_key(self):
        # 投信協会コードのようなキーは文字列比較される
        assert effective_holding_pct({"89311199": 10.0},
                                     {"89311199": 6.0}) == pytest.approx(0.6)


class TestPortfolioImpact:
    def test_basic(self):
        # 実効保有3.5% × 騰落-8% → 資産全体 -0.28%
        assert portfolio_impact_pct(3.5, -8.0) == pytest.approx(-0.28)

    def test_chain(self):
        # 依頼書テンプレの流れ: 構成比x×騰落率→寄与y、保有w×騰落率→影響v
        change = -5.0
        y = index_contribution(6.0, change)
        v = portfolio_impact_pct(3.1, change)
        assert y == pytest.approx(-0.30)
        assert v == pytest.approx(-0.155)
