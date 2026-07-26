# -*- coding: utf-8 -*-
"""
contribution.py
===============
指数寄与と実効保有比率の計算（機能Bの差別化点）。純粋関数のみ・要テスト。

  指数寄与(%pt) = 指数内の構成比(%) × 銘柄の騰落率(%) / 100
  実効保有比率(%) = Σ (ファンドの保有比率(%) × ファンド内ウェイト(%) / 100)
  資産への影響(%) = 実効保有比率(%) × 騰落率(%) / 100
"""


def index_contribution(weight_pct: float, change_pct: float) -> float:
    """指数寄与を%ポイントで返す。例: 構成比7% × 騰落-5% = -0.35%pt"""
    return weight_pct * change_pct / 100.0


def effective_holding_pct(fund_shares: dict[str, float],
                          fund_weights: dict[str, float]) -> float:
    """自分の資産に対する銘柄の実効保有比率(%)。

    fund_shares  : {fund_id: 資産全体に占めるファンドの比率(%)}
    fund_weights : {fund_id: ファンド内での銘柄ウェイト(%)}
    """
    total = 0.0
    for fund_id, w in fund_weights.items():
        share = fund_shares.get(str(fund_id))
        if share:
            total += share * w / 100.0
    return total


def portfolio_impact_pct(effective_pct: float, change_pct: float) -> float:
    """資産全体への影響(%)。例: 実効3.5% × 騰落-8% = -0.28%"""
    return effective_pct * change_pct / 100.0
