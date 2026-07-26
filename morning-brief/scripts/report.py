# -*- coding: utf-8 -*-
"""週次レポート：テンプレート別・話題タグ別の実績を集計し、示唆をルールベースで生成。

毎週日曜の実行時に main.py から呼ばれ、out/weekly_report.md を出力する。
手動実行: python scripts/report.py [YYYY-MM-DD(週の最終日)]
"""
from __future__ import annotations
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config_loader import ROOT                              # noqa: E402
from learner import _trimmed_mean, load_feedback            # noqa: E402

TEMPLATE_NAMES = {"T1": "classic", "T2": "stat_deep", "T3": "hero_number",
                  "T4": "contrast", "T5": "timeline", "T6": "qa"}


def _group(rows, key):
    by = {}
    for r in rows:
        k = r.get(key, "")
        if k:
            by.setdefault(k, []).append(r["views"])
    return {k: (len(v), _trimmed_mean(v)) for k, v in by.items()}


def _table(stats: dict, name_map=None, overall=1.0) -> list[str]:
    lines = ["| 区分 | 使用回数 | 平均Views | 全体比 |", "|---|---|---|---|"]
    for k, (n, avg) in sorted(stats.items(), key=lambda kv: -kv[1][1]):
        label = f"{k} {name_map[k]}" if name_map and k in name_map else k
        lines.append(f"| {label} | {n} | {avg:.0f} | {avg / overall:.1f}x |")
    return lines


def generate(until: dt.date, out_path: str | None = None) -> str | None:
    """直近7日のfeedbackから週次レポートを生成。データが無い週は生成しない。"""
    rows = load_feedback(until, window_days=6)
    out_path = out_path or os.path.join(ROOT, "out", "weekly_report.md")
    since = until - dt.timedelta(days=6)
    if not rows:
        print(f"[ok] 週次レポート: {since}〜{until} の実績データなし（record.py 未入力）→ 生成スキップ")
        return None

    overall = _trimmed_mean([r["views"] for r in rows]) or 1.0
    tstats = _group(rows, "template_id")
    gstats = _group(rows, "topic_tag")

    combos = {}
    for r in rows:
        key = f"{r.get('template_id')} × {r.get('topic_tag')}"
        combos.setdefault(key, []).append(r["views"])
    combo_avg = {k: _trimmed_mean(v) for k, v in combos.items()}
    best = max(combo_avg, key=combo_avg.get)
    worst = min(combo_avg, key=combo_avg.get)

    md = [f"# 週次レポート {since} 〜 {until}", "",
          f"記録件数: {len(rows)}件 / 全体平均Views: {overall:.0f}", "",
          "## テンプレート別 平均Views", *_table(tstats, TEMPLATE_NAMES, overall), "",
          "## 話題タグ別 平均Views", *_table(gstats, None, overall), "",
          "## 今週の示唆（ルールベース自動生成）"]

    md.append(f"- 最も伸びた組み合わせ: {best}（平均 {combo_avg[best]:.0f}）")
    md.append(f"- 最も伸びなかった: {worst}（平均 {combo_avg[worst]:.0f}）")
    top_tpl = max(tstats, key=lambda k: tstats[k][1]) if tstats else None
    if top_tpl and tstats[top_tpl][1] > overall * 1.2:
        md.append(f"- {top_tpl}（{TEMPLATE_NAMES.get(top_tpl, '')}）が全体比"
                  f"{tstats[top_tpl][1] / overall:.1f}xと好調。学習が自動で優先します")
    thin = [t for t, (n, _) in tstats.items() if n < 3]
    if thin:
        md.append(f"- サンプル不足のテンプレ: {', '.join(sorted(thin))}"
                  "（探索対象として自動的に試行されます）")
    top_tag = max(gstats, key=lambda k: gstats[k][1]) if gstats else None
    if top_tag and gstats[top_tag][1] > overall * 1.2:
        md.append(f"- 話題タグ「{top_tag}」が好調。スコアの学習ボーナスに反映されます")
    md.append("")
    md.append("※平均は上下10%トリム・直近実績のみ。サンプルが少ない週は参考程度に。")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print(f"[ok] 週次レポート: {out_path}")
    return out_path


if __name__ == "__main__":
    until = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else dt.date.today()
    generate(until)
