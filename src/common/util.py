# -*- coding: utf-8 -*-
"""
util.py
=======
共通ユーティリティ（リトライ / JST日時 / YAML入出力）。
方針: データが取れない箇所は推測で埋めず「要手動入力」とする。
"""

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

JST = timezone(timedelta(hours=9))
MANUAL = "要手動入力"

REPO_ROOT = Path(__file__).resolve().parents[2]


def now_jst() -> datetime:
    return datetime.now(JST)


def today_jst():
    return now_jst().date()


def retry(func, tries: int = 3, wait: float = 5.0, label: str = "",
          backoff: float = 1.0):
    """3回リトライ。全滅なら None（呼び出し側は「要手動入力」で埋める）。

    backoff > 1 を渡すと待ち時間を指数的に伸ばす（wait, wait*backoff, ...）。
    """
    for i in range(tries):
        try:
            return func()
        except Exception as e:  # noqa: BLE001
            print(f"[warn] {label} 失敗 ({i + 1}/{tries}): {e}")
            if i < tries - 1:
                time.sleep(wait * (backoff ** i))
    return None


def load_yaml(path: Path, default=None):
    if not Path(path).exists():
        return default
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_yaml(path: Path, data) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def fmt_or_manual(value, fmt: str = "{}") -> str:
    """None は推測で埋めず「要手動入力」を返す。"""
    if value is None:
        return MANUAL
    return fmt.format(value)
