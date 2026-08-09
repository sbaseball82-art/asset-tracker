# -*- coding: utf-8 -*-
"""
history.py
==========
月次スナップショットの保存と、前月比の順位変動の算出。

``data/history/lookthrough_YYYY-MM.json`` に毎月1本ずつ残す。
前月分が無い初回は「前月比なし」を返す（0埋めや推測はしない）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.common.util import REPO_ROOT

HISTORY_DIR = REPO_ROOT / "data" / "history"


@dataclass
class RankChange:
    ticker: str
    rank: int
    prev_rank: int | None      # None = 前月は圏外／データなし
    delta: int | None          # プラス = 順位が上がった
    pct: float
    prev_pct: float | None
    pct_delta: float | None

    @property
    def is_new(self) -> bool:
        return self.prev_rank is None


def snapshot_path(ym: str) -> Path:
    return HISTORY_DIR / f"lookthrough_{ym}.json"


def prev_ym(ym: str) -> str:
    """'2026-08' -> '2026-07'"""
    y, m = (int(x) for x in ym.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def save_snapshot(ym: str, result, top: int = 50) -> Path:
    """当月のスナップショットを保存する（上位 top 銘柄のみ）。"""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "ym": ym,
        "saved_at": date.today().isoformat(),
        "total_jpy": result.total_jpy,
        "coverage_pct": round(result.coverage_pct, 3),
        "positions": [
            {"rank": i + 1, "ticker": p.ticker,
             "pct": round(p.pct_of_total, 4),
             "amount_jpy": round(p.amount_jpy),
             "fund_count": p.fund_count}
            for i, p in enumerate(result.positions[:top])
        ],
    }
    path = snapshot_path(ym)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return path


def load_snapshot(ym: str) -> dict | None:
    path = snapshot_path(ym)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"[warn] スナップショット読込失敗 {path.name}: {e}")
        return None


def compare_with_prev(ym: str, result, n: int = 20
                      ) -> tuple[list[RankChange], str | None]:
    """前月スナップショットと比較して順位変動を返す。

    Returns:
        (順位変動リスト, 比較対象のYYYY-MM)。前月分が無ければ (変動なしリスト, None)。
    """
    prev = load_snapshot(prev_ym(ym))
    prev_rank: dict[str, int] = {}
    prev_pct: dict[str, float] = {}
    if prev:
        for row in prev.get("positions", []):
            prev_rank[row["ticker"]] = int(row["rank"])
            prev_pct[row["ticker"]] = float(row["pct"])

    out: list[RankChange] = []
    for i, p in enumerate(result.positions[:n]):
        pr = prev_rank.get(p.ticker)
        pp = prev_pct.get(p.ticker)
        out.append(RankChange(
            ticker=p.ticker,
            rank=i + 1,
            prev_rank=pr,
            delta=(pr - (i + 1)) if pr is not None else None,
            pct=p.pct_of_total,
            prev_pct=pp,
            pct_delta=(p.pct_of_total - pp) if pp is not None else None,
        ))
    return out, (prev.get("ym") if prev else None)


def arrow(delta: int | None) -> str:
    """順位変動を短い記号にする（画像・notes用）。"""
    if delta is None:
        return "NEW"
    if delta > 0:
        return f"▲{delta}"
    if delta < 0:
        return f"▼{abs(delta)}"
    return "—"
