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
