# -*- coding: utf-8 -*-
"""フィードバック学習：Views実績（data/feedback.csv）から

1. テンプレート選択（ε-greedy バンディット）
2. 話題タグの学習ボーナス（ranking のスコアに加点）

を行う。過学習防止のため直近30日のみ使用し、平均は上下10%をトリムする。
サンプル不足のテンプレ/タグは「未検証」として扱う（探索対象・ボーナス0）。
選択は日付+スロットでシード固定し、--date の再現実行で同じ結果になる。
"""
from __future__ import annotations
import csv
import datetime as dt
import os
import random

from config_loader import ROOT
from templates import AFFINITY, ALL_TEMPLATES

FEEDBACK_CSV = os.path.join(ROOT, "data", "feedback.csv")
FIELDNAMES = ["date", "slot", "template_id", "topic_tag", "score", "views", "likes"]


def load_feedback(until: dt.date, window_days: int = 30,
                  path: str = FEEDBACK_CSV) -> list[dict]:
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                d = dt.date.fromisoformat(r["date"])
                views = float(r["views"])
            except (KeyError, ValueError):
                continue
            if 0 <= (until - d).days <= window_days:
                rows.append({**r, "views": views})
    return rows


def _trimmed_mean(vals: list[float]) -> float:
    """上下10%をトリムした平均（バズ・障害など1日の異常値の影響を抑える）。"""
    if not vals:
        return 0.0
    vals = sorted(vals)
    k = int(len(vals) * 0.1)
    core = vals[k:len(vals) - k] or vals
    return sum(core) / len(core)


def template_stats(rows: list[dict]) -> dict[str, tuple[int, float]]:
    """template_id -> (サンプル数, トリム平均Views)"""
    by: dict[str, list[float]] = {}
    for r in rows:
        by.setdefault(r.get("template_id", ""), []).append(r["views"])
    return {tid: (len(v), _trimmed_mean(v)) for tid, v in by.items() if tid}


def topic_bonuses(rows: list[dict], cfg: dict) -> dict[str, float]:
    """topic_tag -> スコア加点（全体平均との比から。上限クリップ・少サンプルは0）。"""
    lc = cfg.get("learning", {})
    min_n = int(lc.get("min_samples_tag", 5))
    cap = float(cfg["scoring"].get("learn_bonus_cap", 0.2))
    if not rows:
        return {}
    overall = _trimmed_mean([r["views"] for r in rows])
    if overall <= 0:
        return {}
    by: dict[str, list[float]] = {}
    for r in rows:
        by.setdefault(r.get("topic_tag", ""), []).append(r["views"])
    out = {}
    for tag, vals in by.items():
        if not tag or len(vals) < min_n:
            continue
        ratio = _trimmed_mean(vals) / overall
        out[tag] = round(min(cap, max(0.0, (ratio - 1.0) * 0.35)), 4)
    return out


def choose_template(tag: str, slot: int, date: dt.date, rows: list[dict],
                    recent: list[str], today_used: set[str], cfg: dict) -> str:
    """ε-greedy でテンプレートを選ぶ。

    - 話題タグとの相性表（AFFINITY）で候補を絞る
    - 同じ日に同じテンプレートを繰り返さない（today_used を除外）
    - 直近3日で使ったテンプレ（recent）は同点なら優先度を下げる
    - 全テンプレが min_samples_template 回試されるまでは ε を引き上げ（初期探索を厚く）
    - 日付+スロットでシード固定（--date 再現性）
    """
    lc = cfg.get("learning", {})
    eps_base = float(lc.get("epsilon", 0.3))
    eps_boot = float(lc.get("epsilon_bootstrap", 0.5))
    min_tpl = int(lc.get("min_samples_template", 5))

    stats = template_stats(rows)
    cands = [t for t in AFFINITY.get(tag, ALL_TEMPLATES) if t not in today_used]
    if not cands:
        cands = [t for t in ALL_TEMPLATES if t not in today_used] or list(ALL_TEMPLATES)

    rng = random.Random(f"morning-brief-{date.isoformat()}-{slot}")
    eps = eps_boot if any(stats.get(t, (0, 0.0))[0] < min_tpl
                          for t in ALL_TEMPLATES) else eps_base

    def prefer_fresh(pool: list[str]) -> list[str]:
        fresh = [t for t in pool if t not in recent]
        return fresh or pool

    if rng.random() < eps:
        # 探索：未検証（サンプル3未満）を優先し、直近使用は避ける
        unverified = [t for t in cands if stats.get(t, (0, 0.0))[0] < 3]
        pool = prefer_fresh(unverified or cands)
        return rng.choice(pool)

    # 活用：トリム平均Viewsが最大のもの（実績のない候補は平均0扱い）
    ranked = sorted(cands, key=lambda t: (-stats.get(t, (0, 0.0))[1], t))
    top_avg = stats.get(ranked[0], (0, 0.0))[1]
    top = [t for t in ranked if abs(stats.get(t, (0, 0.0))[1] - top_avg) < 1e-9]
    return prefer_fresh(top)[0]


def recent_templates(log_dir: str, until: dt.date, days: int = 3) -> list[str]:
    """直近days日のログから使用テンプレートを収集（マンネリ防止用）。"""
    import json
    used = []
    for i in range(1, days + 1):
        p = os.path.join(log_dir, f"{(until - dt.timedelta(days=i)).isoformat()}.json")
        if not os.path.exists(p):
            continue
        try:
            log = json.load(open(p, encoding="utf-8"))
            used += [a.get("template_id") for a in log.get("adopted", [])
                     if a.get("template_id")]
        except Exception:
            continue
    return used


if __name__ == "__main__":
    import sys
    from config_loader import load_config
    cfg = load_config()
    today = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else dt.date.today()
    rows = load_feedback(today, int(cfg.get("learning", {}).get("window_days", 30)))
    print("feedback rows:", len(rows))
    print("template_stats:", template_stats(rows))
    print("topic_bonuses:", topic_bonuses(rows, cfg))
    for slot, tag in ((1, "semiconductor"), (2, "rates")):
        print(f"slot{slot} {tag} ->",
              choose_template(tag, slot, today, rows, [], set(), cfg))
