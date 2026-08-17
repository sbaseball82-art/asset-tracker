# -*- coding: utf-8 -*-
"""
history.py
==========
``data/daily_growth_history.jsonl`` の読み書きと、
「毎日同じ内容になる」ことを防ぐローテーション判定。

1行1投稿のJSONL。最低限の記録項目（依頼仕様）:
    date / topic_id / hook / design_id / post_text /
    source_values / generated_files

判定はすべて純粋関数（引数で entries を受け取る）にしてあり、
テストから実ファイルなしで検証できる。
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, timedelta
from difflib import SequenceMatcher
from pathlib import Path

from src.common.util import REPO_ROOT

HISTORY_PATH = REPO_ROOT / "data" / "daily_growth_history.jsonl"

REQUIRED_FIELDS = ("date", "topic_id", "hook", "design_id", "post_text",
                   "source_values", "generated_files")


# --------------------------------------------------------------------------
# 入出力
# --------------------------------------------------------------------------

def load(path: Path = HISTORY_PATH) -> list[dict]:
    """壊れた行は黙って捨てる（履歴が読めないことを理由に生成を止めない）。"""
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("date"):
            out.append(row)
    return out


def append(entries: list[dict], path: Path = HISTORY_PATH) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as fh:
        for e in entries:
            missing = [k for k in REQUIRED_FIELDS if k not in e]
            if missing:
                raise ValueError(f"履歴の必須項目が足りません: {missing}")
            fh.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")


def make_entry(date_str: str, topic_id: str, hook: str, design_id: str,
               post_text: str, source_values: dict,
               generated_files: list[str], **extra) -> dict:
    entry = {
        "date": date_str, "topic_id": topic_id, "hook": hook,
        "design_id": design_id, "post_text": post_text,
        "source_values": source_values, "generated_files": generated_files,
    }
    entry.update(extra)
    return entry


# --------------------------------------------------------------------------
# 類似度
# --------------------------------------------------------------------------

_TAG_RE = re.compile(r"#\S+")


def _boilerplate() -> tuple[str, ...]:
    """全投稿に必ず入る定型（免責・概算・タグ）。類似度の計算から外す。

    これを残したまま比べると、どの投稿も定型のぶんだけ似てしまい、
    「中身が同じか」を見られなくなる。
    """
    from src.daily_growth.compose import (APPROX_TAIL, DISCLAIMER_ASSET,
                                          DISCLAIMER_NEWS)
    return (DISCLAIMER_ASSET, DISCLAIMER_NEWS, APPROX_TAIL)


def normalize(text: str) -> str:
    """比較用の正規化。数字は伏せる（数字違いの同じ文を同じとみなすため）。"""
    s = unicodedata.normalize("NFKC", text or "")
    for boiler in _boilerplate():
        s = s.replace(unicodedata.normalize("NFKC", boiler), "")
    s = _TAG_RE.sub("", s)
    s = re.sub(r"[0-9][0-9,.]*", "#", s)
    s = re.sub(r"[\s\W_]+", "", s)
    return s.lower()


def similarity(a: str, b: str) -> float:
    """0.0〜1.0。1.0 が同一。"""
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def max_similarity(text: str, others: list[str]) -> float:
    return max((similarity(text, o) for o in others), default=0.0)


# --------------------------------------------------------------------------
# ローテーション判定
# --------------------------------------------------------------------------

def _within(entries: list[dict], today: date, days: int) -> list[dict]:
    since = today - timedelta(days=days)
    out = []
    for e in entries:
        try:
            d = date.fromisoformat(str(e.get("date"))[:10])
        except ValueError:
            continue
        if since <= d <= today:
            out.append(e)
    return out


def topic_blocked(topic_id: str, today: date, entries: list[dict],
                  days: int = 14) -> bool:
    """同一 topic_id は days 日間再利用しない（当日を含む区間で判定）。"""
    recent = _within(entries, today, days - 1) if days > 0 else []
    return any(e.get("topic_id") == topic_id for e in recent)


def hook_blocked(hook: str, today: date, entries: list[dict],
                 days: int = 30, threshold: float = 0.80) -> bool:
    """同一・きわめて近い hook を days 日間避ける。"""
    recent = _within(entries, today, days - 1) if days > 0 else []
    return max_similarity(hook, [str(e.get("hook", "")) for e in recent]) >= threshold


def design_blocked(design_id: str, today: date, entries: list[dict],
                   max_consecutive_days: int = 3) -> bool:
    """同一 design_id の「連続使用日数」が上限に達していたら使わせない。

    max_consecutive_days=3 なら、直近2日連続で使っている design は今日は不可
    （使うと3日連続になるため）。
    """
    if max_consecutive_days <= 1:
        return True
    need = max_consecutive_days - 1
    for i in range(1, need + 1):
        day = (today - timedelta(days=i)).isoformat()
        used = {e.get("design_id") for e in entries
                if str(e.get("date"))[:10] == day}
        if design_id not in used:
            return False
    return True


def previous_day_texts(today: date, entries: list[dict],
                       lookback_days: int = 1) -> list[str]:
    """前日（既定）に出した投稿文の一覧。類似度の比較対象にする。"""
    days = {(today - timedelta(days=i)).isoformat()
            for i in range(1, lookback_days + 1)}
    return [str(e.get("post_text", "")) for e in entries
            if str(e.get("date"))[:10] in days]


def days_since_topic(topic_id: str, today: date,
                     entries: list[dict]) -> int | None:
    """その topic を最後に使ってからの日数。未使用なら None。"""
    used = []
    for e in entries:
        if e.get("topic_id") != topic_id:
            continue
        try:
            used.append(date.fromisoformat(str(e.get("date"))[:10]))
        except ValueError:
            continue
    if not used:
        return None
    return (today - max(used)).days


def entries_on(entries: list[dict], day: date) -> list[dict]:
    return [e for e in entries if str(e.get("date"))[:10] == day.isoformat()]


def checkback_source(entries: list[dict], today: date,
                     min_age_days: int = 7,
                     max_age_days: int = 60) -> dict | None:
    """「過去投稿の答え合わせ」に使える過去エントリを1件返す。

    条件: min_age_days 以上前で、総資産（total_jpy）を記録していること。
    見つからなければ None（＝その話題は今日は作らない）。
    """
    best = None
    for e in entries:
        try:
            d = date.fromisoformat(str(e.get("date"))[:10])
        except ValueError:
            continue
        age = (today - d).days
        if not (min_age_days <= age <= max_age_days):
            continue
        sv = e.get("source_values") or {}
        raw = (sv.get("total_jpy") or {}).get("raw") if isinstance(
            sv.get("total_jpy"), dict) else None
        if raw is None:
            continue
        cand = {"date": d.isoformat(), "age_days": age,
                "total_jpy": float(raw), "topic_id": e.get("topic_id"),
                "hook": e.get("hook", "")}
        # いちばん古いもの＝いちばん「答え合わせ」らしいものを選ぶ
        if best is None or cand["age_days"] > best["age_days"]:
            best = cand
    return best
