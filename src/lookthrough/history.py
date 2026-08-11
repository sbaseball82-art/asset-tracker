# -*- coding: utf-8 -*-
"""
history.py
==========
スナップショットの保存と、前回比の順位変動の算出。

実行の間隔（period）は ``config.yml`` の ``schedule.lookthrough`` で決める。

    monthly … "2026-08"    → data/history/lookthrough_2026-08.json
    weekly  … "2026-W33"   → data/history/lookthrough_2026-W33.json

前回分が無い初回は「比較なし」を返す（0埋めや推測はしない）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from src.common.util import REPO_ROOT

HISTORY_DIR = REPO_ROOT / "data" / "history"

_WEEK_RE = re.compile(r"^(\d{4})-W(\d{1,2})$")


# --------------------------------------------------------------------------
# period（実行の単位）
# --------------------------------------------------------------------------

def current_period(mode: str = "monthly", d: date | None = None) -> str:
    """今の period ID を返す。mode は "weekly" か "monthly"。"""
    d = d or date.today()
    if str(mode).lower().startswith("week"):
        iso = d.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    return d.strftime("%Y-%m")


def is_weekly(period: str) -> bool:
    return bool(_WEEK_RE.match(str(period)))


def prev_period(period: str) -> str:
    """1つ前の period ID。週次なら前週、月次なら前月。"""
    m = _WEEK_RE.match(str(period))
    if m:
        y, w = int(m.group(1)), int(m.group(2))
        monday = date.fromisocalendar(y, w, 1) - timedelta(days=7)
        iso = monday.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    y, mo = (int(x) for x in str(period).split("-"))
    return f"{y - 1}-12" if mo == 1 else f"{y}-{mo - 1:02d}"


# 後方互換（以前の呼び名）
prev_ym = prev_period


def period_end(period: str) -> date:
    """その period の最終日。週次はその週の日曜、月次は月初で代表する。"""
    m = _WEEK_RE.match(str(period))
    if m:
        return date.fromisocalendar(int(m.group(1)), int(m.group(2)), 7)
    y, mo = (int(x) for x in str(period).split("-"))
    return date(y, mo, 1)


def period_label(period: str) -> str:
    """画像のサブタイトル用。週次は日付まで、月次は年月まで。"""
    d = period_end(period)
    if is_weekly(period):
        return f"{d.year}年{d.month}月{d.day}日 時点"
    return f"{d.year}年{d.month}月 時点"


def prev_label(period: str) -> str:
    """「前週」「前月」。"""
    return "前週" if is_weekly(period) else "前月"


def comparison_label(period: str) -> str:
    """「前週比」「前月比」。"""
    return prev_label(period) + "比"


@dataclass
class RankChange:
    ticker: str
    rank: int
    prev_rank: int | None      # None = 前回は圏外／データなし
    delta: int | None          # プラス = 順位が上がった
    pct: float
    prev_pct: float | None
    pct_delta: float | None

    @property
    def is_new(self) -> bool:
        return self.prev_rank is None


def snapshot_path(period: str) -> Path:
    return HISTORY_DIR / f"lookthrough_{period}.json"


def save_snapshot(period: str, result, top: int = 50) -> Path:
    """その period のスナップショットを保存する（上位 top 銘柄のみ）。"""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "ym": period,
        "period": period,
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
    path = snapshot_path(period)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return path


def load_snapshot(period: str) -> dict | None:
    path = snapshot_path(period)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"[warn] スナップショット読込失敗 {path.name}: {e}")
        return None


def compare_with_prev(period: str, result, n: int = 20
                      ) -> tuple[list[RankChange], str | None]:
    """1つ前のスナップショットと比較して順位変動を返す。

    Returns:
        (順位変動リスト, 比較対象のperiod)。前回分が無ければ (変動なしリスト, None)。
    """
    prev = load_snapshot(prev_period(period))
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
    return out, ((prev.get("period") or prev.get("ym")) if prev else None)


def arrow(delta: int | None) -> str:
    """順位変動を短い記号にする（画像・notes用）。"""
    if delta is None:
        return "NEW"
    if delta > 0:
        return f"▲{delta}"
    if delta < 0:
        return f"▼{abs(delta)}"
    return "—"
