# -*- coding: utf-8 -*-
"""
weekly.py
=========
週次レポート生成: reports/weekly_YYYY-WW.md
- format別・type別の平均View（views入力済みの行のみ）
- 4週間分（4つ以上のISO週）のデータがたまったら、
  平均Viewが全体平均の50%未満かつサンプル3件以上の format を
  data/format_weights.yml に "reduced" として書き出す
  → evergreen の選択が自動的にその型を後回しにする（生成を減らす）
"""

import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.common import postlog
from src.common.util import REPO_ROOT, now_jst, save_yaml

REDUCE_THRESHOLD = 0.5   # 全体平均の50%未満
MIN_SAMPLES = 3
MIN_WEEKS = 4


def _avg(nums: list[int]) -> float:
    return sum(nums) / len(nums) if nums else 0.0


def analyze(rows: list[dict]) -> dict:
    """views入力済み行から format別/type別の平均などを計算する。"""
    filled = [r for r in rows
              if r.get("views", "").isdigit() and r.get("posted") == "true"]
    by_format, by_type = defaultdict(list), defaultdict(list)
    weeks = set()
    for r in filled:
        v = int(r["views"])
        by_format[r["format"]].append(v)
        by_type[r["type"]].append(v)
        try:
            y, w, _ = date.fromisoformat(r["date"]).isocalendar()
            weeks.add((y, w))
        except ValueError:
            pass
    overall = _avg([int(r["views"]) for r in filled])
    reduced = []
    if len(weeks) >= MIN_WEEKS and overall > 0:
        for fmt, vals in by_format.items():
            if len(vals) >= MIN_SAMPLES and _avg(vals) < overall * REDUCE_THRESHOLD:
                reduced.append(fmt)
    return {
        "n_filled": len(filled), "n_total": len(rows),
        "n_weeks": len(weeks), "overall_avg": overall,
        "by_format": {k: (_avg(v), len(v)) for k, v in by_format.items()},
        "by_type": {k: (_avg(v), len(v)) for k, v in by_type.items()},
        "reduced_formats": reduced,
    }


def build_md(stats: dict, iso_year: int, iso_week: int) -> str:
    lines = [f"# 週次レポート {iso_year}-W{iso_week:02d}", "",
             f"- 記録行数: {stats['n_total']}（うちView入力済み {stats['n_filled']}）",
             f"- データのある週数: {stats['n_weeks']}",
             f"- 全体平均View: {stats['overall_avg']:,.0f}", "",
             "## format別 平均View", "",
             "| format | 平均View | 件数 |", "|---|---:|---:|"]
    for k, (avg, n) in sorted(stats["by_format"].items(),
                              key=lambda x: -x[1][0]):
        lines.append(f"| {k} | {avg:,.0f} | {n} |")
    lines += ["", "## type別 平均View", "",
              "| type | 平均View | 件数 |", "|---|---:|---:|"]
    for k, (avg, n) in sorted(stats["by_type"].items(),
                              key=lambda x: -x[1][0]):
        lines.append(f"| {k} | {avg:,.0f} | {n} |")
    lines.append("")
    if stats["reduced_formats"]:
        lines += ["## 自動調整",
                  f"- 平均が全体の{REDUCE_THRESHOLD:.0%}未満のため生成を減らす型: "
                  + ", ".join(stats["reduced_formats"]), ""]
    elif stats["n_weeks"] < MIN_WEEKS:
        lines += ["## 自動調整",
                  f"- データが{MIN_WEEKS}週分たまるまで型の自動調整は行いません"
                  f"（現在{stats['n_weeks']}週）", ""]
    lines.append("※Viewsは scripts/log_metrics.py で週1回手入力する")
    return "\n".join(lines)


def main() -> int:
    rows = postlog.read_rows()
    stats = analyze(rows)
    now = now_jst().date()
    iso_year, iso_week, _ = now.isocalendar()

    out = REPO_ROOT / "reports" / f"weekly_{iso_year}-{iso_week:02d}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_md(stats, iso_year, iso_week), encoding="utf-8")
    print(f"[ok] {out}")

    save_yaml(REPO_ROOT / "data" / "format_weights.yml", {
        "updated": now.isoformat(),
        "formats": {f: "reduced" for f in stats["reduced_formats"]},
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
