# -*- coding: utf-8 -*-
"""
source_health.py
================
週1回、全 source に取得テストだけを実行して健康状態を記録する。

    python scripts/source_health.py

出力:
  reports/source_health_YYYY-WW.md      … その週のレポート
  reports/source_health_history.json    … 直近12週の履歴（連続失敗の判定用）

目的は「実際に壊れてから気づく」のを避けること。
priority 1 が落ちて priority 2 以降で拾っている状態は、
まだ生成は成功しているが直しておくべきサイン。
これが2週続いたら「要対応」として通知する。
"""

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common import settings                       # noqa: E402
from src.common.notify import notify                  # noqa: E402
from src.lookthrough import health                    # noqa: E402
from src.lookthrough.constituents import (            # noqa: E402
    load_fund_map, load_holdings,
)


def week_id(d: date | None = None) -> str:
    d = d or date.today()
    iso = d.isocalendar()
    return f"{iso[0]}-{iso[1]:02d}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="全sourceの週次ヘルスチェック")
    ap.add_argument("--week", default=None, help="週ID（既定は今週 YYYY-WW）")
    args = ap.parse_args(argv)

    week = args.week or week_id()
    fmap = load_fund_map()
    try:
        funds, _, _ = load_holdings()
        names = {f.id: f.name for f in funds}
    except FileNotFoundError:
        names = {}

    results = health.probe_all(fmap, names=names)

    hist = health.load_history()
    prev = health.previous_counts(hist, week)
    hist = health.save_history(hist, results, week)
    streaks = health.degraded_streaks(hist)

    body = health.to_markdown(
        results, f"source ヘルスチェック {week}",
        prev=prev, degraded_streaks=streaks)
    path = settings.path_of("reports") / f"source_health_{week}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")

    ok_n = sum(1 for r in results if r.ok)
    print(f"{ok_n}/{len(results)} source が成功")
    print(f"レポート: {path}")

    # ---- 通知 ----------------------------------------------------------
    need = int(settings.get("source_health", "degraded_after_weeks", 2))
    alarming = {k: v for k, v in streaks.items() if v >= need}
    dead = _dead_funds(results)

    lines = []
    if dead:
        lines.append("すべてのsourceが失敗: "
                     + "、".join(n for _, n in dead))
    if alarming:
        lines.append(f"priority 1 が{need}週以上連続で失敗: "
                     + "、".join(f"{k}({v}週)" for k, v in alarming.items()))

    if lines:
        msg = f"source健康チェック {week} 要対応\n" + "\n".join(lines)
        print(f"::warning::{msg}")
        if settings.notify_on("source_degraded"):
            notify(msg, critical=bool(dead))
        return 2

    print("要対応の項目はありません。")
    return 0


def _dead_funds(results) -> list[tuple[str, str]]:
    by_fund: dict[str, list] = {}
    for r in results:
        by_fund.setdefault(r.fund_id, []).append(r)
    return [(fid, rs[0].fund_name) for fid, rs in by_fund.items()
            if not any(r.ok for r in rs)]


if __name__ == "__main__":
    sys.exit(main())
