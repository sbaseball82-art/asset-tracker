# -*- coding: utf-8 -*-
"""
score.py
========
候補（Draft）に点をつけて、その日の5本を選ぶ。

考え方
------
- **その日しか作れない話題を勝たせる**。固定テーマ（比率ランキング・
  為替感応度など）は surprise を低くしてあるので、異常・逆転・記録更新が
  起きた日はそちらが自動的に上に来る。
- ローテーション違反（14日以内の同一topic / 30日以内の類似hook /
  3日連続の同一design）は **減点ではなく除外**。点数で押し切れないようにする。
- logs/posts.csv の実績はサンプルが貯まるまで使わない。
  データ不足のときに「学習済み」のふりをしない。

スコアの重みは config.yml の daily_growth.weights で変えられる。
このモジュールは純粋関数だけにする。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from src.daily_growth import history as H
from src.daily_growth.compose import Draft

# 目的関数の優先順位（前ほど重い）。1指標あたりの重みは 2倍ずつ差をつける。
OBJECTIVE_DEFAULT = ["follows", "profile_clicks", "bookmarks",
                     "replies", "likes", "views"]


@dataclass
class Scored:
    draft: Draft
    design_id: str
    score: float
    parts: dict[str, float]
    excluded: str = ""
    learned_bonus: float = 0.0
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# 各成分
# --------------------------------------------------------------------------

def freshness(topic_id: str, today: date, entries: list[dict],
              reuse_days: int = 14) -> float:
    """最近使っていないほど高い。未使用は 1.0。"""
    days = H.days_since_topic(topic_id, today, entries)
    if days is None:
        return 1.0
    if days <= reuse_days:
        return 0.0
    # 再利用解禁からさらに時間が経つほど 1.0 に近づく
    return min(1.0, (days - reuse_days) / (reuse_days * 2))


def components(d: Draft, today: date, entries: list[dict],
               reuse_days: int = 14) -> dict[str, float]:
    return {
        "freshness": freshness(d.topic_id, today, entries, reuse_days),
        "personal_asset_relevance": d.relevance,
        "surprise": d.surprise,
        "timeliness": d.timeliness,
        "visual_clarity": d.clarity,
    }


def weighted(parts: dict[str, float], weights: dict[str, float]) -> float:
    return sum(parts.get(k, 0.0) * float(w) for k, w in weights.items())


# --------------------------------------------------------------------------
# logs/posts.csv からの学習（サンプルが貯まるまでは効かせない）
# --------------------------------------------------------------------------

def _to_float(v) -> float | None:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def format_performance(rows: list[dict], objective: list[str] | None = None,
                       type_filter: str = "daily_growth",
                       min_samples: int = 8) -> dict[str, float]:
    """format（＝design_id）ごとの相対的な良し悪しを -1.0〜1.0 で返す。

    実績が min_samples 件に満たない format は **返さない**。
    「データが足りないのに学習した気になる」ことを避けるため。
    """
    objective = objective or OBJECTIVE_DEFAULT
    weights = {k: 2 ** (len(objective) - i - 1)
               for i, k in enumerate(objective)}

    buckets: dict[str, list[float]] = {}
    for r in rows:
        if type_filter and r.get("type") != type_filter:
            continue
        vals = {k: _to_float(r.get(k)) for k in objective}
        if all(v is None for v in vals.values()):
            continue  # 実績が未入力の行は数えない
        views = vals.get("views") or 0.0
        if views <= 0:
            continue
        # 表示あたりの反応で正規化する（伸びた日のバイアスを避ける）
        raw = sum(weights[k] * ((vals.get(k) or 0.0) / views) for k in objective)
        buckets.setdefault(str(r.get("format", "")), []).append(raw)

    usable = {k: v for k, v in buckets.items() if len(v) >= min_samples}
    if len(usable) < 2:
        return {}

    means = {k: sum(v) / len(v) for k, v in usable.items()}
    lo, hi = min(means.values()), max(means.values())
    if hi <= lo:
        return {}
    return {k: (2 * (v - lo) / (hi - lo)) - 1 for k, v in means.items()}


def is_learned(perf: dict[str, float]) -> bool:
    return bool(perf)


# --------------------------------------------------------------------------
# 選抜
# --------------------------------------------------------------------------

def rank(drafts: list[Draft], today: date, entries: list[dict],
         weights: dict[str, float], rotation: dict,
         perf: dict[str, float] | None = None,
         learn_weight: float = 0.05) -> list[Scored]:
    """全候補にデザインを割り当てて点をつける（除外理由も残す）。"""
    perf = perf or {}
    reuse_days = int(rotation.get("topic_reuse_days", 14))
    hook_days = int(rotation.get("hook_avoid_days", 30))
    hook_sim = float(rotation.get("hook_similarity", 0.80))
    design_max = int(rotation.get("design_max_consecutive_days", 3))
    prev_sim = float(rotation.get("prev_day_similarity", 0.72))
    prev_texts = H.previous_day_texts(today, entries)

    out: list[Scored] = []
    for d in drafts:
        parts = components(d, today, entries, reuse_days)
        base = weighted(parts, weights)

        usable = [x for x in d.designs
                  if not H.design_blocked(x, today, entries, design_max)]
        design = max(usable, key=lambda x: perf.get(x, 0.0)) if usable else (
            d.designs[0] if d.designs else "dark_financial_report")
        bonus = perf.get(design, 0.0) * learn_weight

        excluded = ""
        if H.topic_blocked(d.topic_id, today, entries, reuse_days):
            excluded = f"同じ話題を{reuse_days}日以内に使っています"
        elif H.hook_blocked(d.hook, today, entries, hook_days, hook_sim):
            excluded = f"似た書き出しを{hook_days}日以内に使っています"
        elif not usable:
            excluded = f"使えるデザインが{design_max}日連続の制限にかかっています"
        elif H.max_similarity(d.text, prev_texts) >= prev_sim:
            excluded = "前日の投稿と内容が近すぎます"

        out.append(Scored(draft=d, design_id=design, score=base + bonus,
                          parts=parts, excluded=excluded, learned_bonus=bonus))
    out.sort(key=lambda s: s.score, reverse=True)
    return out


def select(scored: list[Scored], count: int = 5,
           max_per_category: int = 2,
           design_pool: dict[str, dict] | None = None,
           rotation: dict | None = None,
           entries: list[dict] | None = None,
           today: date | None = None) -> tuple[list[Scored], list[Scored]]:
    """点の高い順に、制約を守りながら count 本選ぶ。

    制約:
      - 同じ topic は1日1本
      - 同じ builder（同じ事実の言い換え）は1日1本
      - 同じ category は max_per_category 本まで
      - 同じ design_id を1日の中で重複させない（5枚が同じ見た目にならない）
      - 互いに似すぎている候補は採らない
    """
    rotation = rotation or {}
    sim_limit = float(rotation.get("prev_day_similarity", 0.72))
    design_max = int(rotation.get("design_max_consecutive_days", 3))
    entries = entries or []

    chosen: list[Scored] = []
    used_designs: set[str] = set()
    used_builders: set[str] = set()
    cat_count: dict[str, int] = {}

    for s in scored:
        if s.excluded or len(chosen) >= count:
            continue
        cat = s.draft.category
        if cat_count.get(cat, 0) >= max_per_category:
            continue
        if s.draft.builder and s.draft.builder in used_builders:
            continue  # 同じ計算の言い換えを2本出さない
        if any(H.similarity(s.draft.text, c.draft.text) >= sim_limit
               for c in chosen):
            continue
        design = _pick_design(s, used_designs, design_pool, design_max,
                              entries, today)
        if design is None:
            continue
        s.design_id = design
        chosen.append(s)
        used_designs.add(design)
        if s.draft.builder:
            used_builders.add(s.draft.builder)
        cat_count[cat] = cat_count.get(cat, 0) + 1

    rest = [s for s in scored if s not in chosen]
    return chosen, rest


def relaxation_ladder(rotation: dict, floor_days: int = 3) -> list[dict]:
    """ローテーションを段階的にゆるめる順番を作る。

    なぜ必要か
    ----------
    「1日5本 × 同一topicは14日間禁止」は、常に成立させるには
    5×14=70本の話題が要る。ネタプールが尽きた日に、
      - 黙って本数を減らす
      - 黙って同じ話題を出す
    のどちらもやりたくないので、**ゆるめ方をあらかじめ決めて記録する**。

    どこまでゆるめても、次の3つは最後まで守る。
      - 前日と同じ話題は出さない（最終段でも2日は空ける）
      - 同じデザインを3日連続で使わない
      - 前日の投稿と似すぎたものは出さない
    """
    out = [dict(rotation)]
    for ratio in (0.7, 0.5, 0.35, 0.2):
        step = dict(rotation)
        for key in ("topic_reuse_days", "hook_avoid_days"):
            base = int(rotation.get(key, 0))
            step[key] = max(floor_days, int(base * ratio))
        if step != out[-1]:
            out.append(step)
    # 最終段: 書き出しの回避をいったん外し、「連日で同じ話題にしない」だけ守る。
    # ここまで来たら summary.md と qa.json に必ず「ゆるめた」と出る。
    last = {**rotation, "topic_reuse_days": 2, "hook_avoid_days": 0}
    if last != out[-1]:
        out.append(last)
    return out


def describe_relaxation(base: dict, used: dict) -> str:
    diffs = [f'{k}: {base.get(k)}日→{used.get(k)}日'
             for k in ("topic_reuse_days", "hook_avoid_days")
             if base.get(k) != used.get(k)]
    return "、".join(diffs)


def _pick_design(s: Scored, used: set[str], pool: dict[str, dict] | None,
                 design_max: int, entries: list[dict],
                 today: date | None) -> str | None:
    """その候補に割り当てられるデザインを1つ選ぶ（当日重複と連続使用を避ける）。"""
    candidates = [d for d in s.draft.designs if d not in used]
    if today is not None and entries:
        candidates = [d for d in candidates
                      if not H.design_blocked(d, today, entries, design_max)]
    if pool:
        candidates = [d for d in candidates if d in pool]
    return candidates[0] if candidates else None
