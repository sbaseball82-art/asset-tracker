# -*- coding: utf-8 -*-
"""
settings.py
===========
``config.yml`` を読む。運用まわりの設定はここ経由で参照し、
コードに閾値やアカウント名を書かない。

config.yml が無い場合でも既定値で動く（新規クローン直後など）。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from .util import REPO_ROOT, load_yaml

CONFIG_PATH = REPO_ROOT / "config.yml"

DEFAULTS: dict = {
    "account": {"x_handle": "your_account"},
    "paths": {
        "holdings": "data/holdings.yml",
        "fund_map": "data/fund_map.yml",
        "output": "output/",
        "cache": "data/cache/constituents/",
        "manual": "data/manual/",
        "history": "data/history/",
        "reports": "reports/",
        "feed": "data/lookthrough.json",
    },
    "coverage": {"halt_below": 0.90, "warn_below": 0.95,
                 "exclude_declared": True, "feed_min": 0.90},
    "freshness": {"ok_days": 35, "warn_days": 90},
    "notification": {"method": "slack", "webhook_env": "SLACK_WEBHOOK_URL",
                     "notify_on": ["halt", "stale", "source_degraded",
                                   "constituent_change"]},
    "schedule": {"lookthrough": "monthly", "source_health": "weekly"},
    "post": {"limits": [100, 150, 165]},
    "source_health": {"degraded_after_weeks": 2, "timeout_sec": 60},
    "daily_growth": {
        "posts_per_day": 5,
        "char_limit": 165,
        "max_per_category": 2,
        "weights": {"freshness": 0.30, "personal_asset_relevance": 0.30,
                    "surprise": 0.20, "timeliness": 0.10,
                    "visual_clarity": 0.10},
        "rotation": {"topic_reuse_days": 14, "hook_avoid_days": 30,
                     "design_max_consecutive_days": 3,
                     "hook_similarity": 0.80, "prev_day_similarity": 0.72},
        "learning": {"min_samples_per_format": 8,
                     "objective": ["follows", "profile_clicks", "bookmarks",
                                   "replies", "likes", "views"]},
        "data": {"halt_age_days": 4, "warn_age_days": 1},
    },
}


def _merge(base: dict, over: dict) -> dict:
    """1階層ネストの浅いマージ（config.yml は2階層しか使わない）。"""
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


@lru_cache(maxsize=1)
def load(path: Path | None = None) -> dict:
    raw = load_yaml(path or CONFIG_PATH, default=None) or {}
    return _merge(DEFAULTS, raw)


def get(section: str, key: str, default=None):
    return load().get(section, {}).get(key, default)


def path_of(key: str) -> Path:
    """paths セクションの値を絶対パスで返す。"""
    return REPO_ROOT / str(get("paths", key, DEFAULTS["paths"].get(key, "")))


def x_handle(with_at: bool = False) -> str:
    """Xのハンドル。config.yml では @ の有無どちらでも書ける。"""
    h = str(get("account", "x_handle", "your_account")).strip().lstrip("@")
    return f"@{h}" if with_at else h


def notify_on(event: str) -> bool:
    """その種類の通知を出す設定になっているか。"""
    return event in (get("notification", "notify_on", []) or [])


def coverage_halt_below() -> float:
    return float(get("coverage", "halt_below", 0.90))


def coverage_warn_below() -> float:
    return float(get("coverage", "warn_below", 0.95))


def coverage_feed_min() -> float:
    return float(get("coverage", "feed_min", 0.90))


def exclude_declared() -> bool:
    return bool(get("coverage", "exclude_declared", True))


def freshness_days() -> tuple[int, int]:
    """(正常とみなす日数, 警告つきで使える日数) を返す。"""
    return (int(get("freshness", "ok_days", 35)),
            int(get("freshness", "warn_days", 90)))


def post_limits() -> tuple[int, ...]:
    return tuple(get("post", "limits", [100, 150, 165]))


# --------------------------------------------------------------------------
# Daily Growth System
# --------------------------------------------------------------------------

def daily_growth(key: str, default=None):
    """daily_growth セクションの値。書かれていなければ DEFAULTS を返す。

    ネストした dict（weights / rotation など）は、config.yml に書いた
    キーだけを既定値に重ねる（一部だけ上書きできるようにするため）。
    """
    fallback = DEFAULTS["daily_growth"].get(key, default)
    value = get("daily_growth", key, None)
    if value is None:
        return fallback
    if isinstance(fallback, dict) and isinstance(value, dict):
        merged = dict(fallback)
        merged.update(value)
        return merged
    return value


def dg_weights() -> dict[str, float]:
    return {k: float(v) for k, v in daily_growth("weights").items()}


def dg_rotation() -> dict:
    return daily_growth("rotation")


def dg_char_limit() -> int:
    return int(daily_growth("char_limit", 165))


def dg_posts_per_day() -> int:
    return int(daily_growth("posts_per_day", 5))
