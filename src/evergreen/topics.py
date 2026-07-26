# -*- coding: utf-8 -*-
"""
topics.py
=========
保存版ネタストック（data/evergreen_topics.yml）の選択・使用済み管理。

- 未使用（last_used が空 or 90日以上前）のものから1本選ぶ
- 週次レポートが data/format_weights.yml に「伸びていない型」を書くと、
  その format の選択を後回しにする（生成を自動的に減らす）
- 重複ネタ検出: ID重複と、テーマの正規化文字列の重複を検出する
"""

import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path

from src.common.util import REPO_ROOT, load_yaml, save_yaml

TOPICS_PATH = REPO_ROOT / "data" / "evergreen_topics.yml"
WEIGHTS_PATH = REPO_ROOT / "data" / "format_weights.yml"
REUSE_DAYS = 90


def load_topics(path: Path = TOPICS_PATH) -> list[dict]:
    data = load_yaml(path, default={"topics": []})
    return data.get("topics", [])


def _normalize_theme(theme: str) -> str:
    s = unicodedata.normalize("NFKC", theme or "").lower()
    return re.sub(r"[\s\W_]+", "", s)


def find_duplicates(topics: list[dict]) -> list[str]:
    """重複ネタ（ID or テーマ）を検出してメッセージのリストを返す。"""
    problems = []
    seen_ids, seen_themes = {}, {}
    for t in topics:
        tid = t.get("id", "")
        theme = _normalize_theme(t.get("theme", ""))
        if tid in seen_ids:
            problems.append(f"ID重複: {tid}")
        seen_ids[tid] = True
        if theme and theme in seen_themes:
            problems.append(f"テーマ重複: {t.get('id')} と {seen_themes[theme]}")
        else:
            seen_themes[theme] = t.get("id")
    return problems


def is_available(topic: dict, today: date) -> bool:
    """未使用、または使用から90日経過していれば選択可能。"""
    lu = topic.get("last_used")
    if not lu:
        return True
    if isinstance(lu, str):
        lu = date.fromisoformat(lu)
    return (today - lu) >= timedelta(days=REUSE_DAYS)


def _reduced_formats() -> set[str]:
    data = load_yaml(WEIGHTS_PATH, default={}) or {}
    return {f for f, v in (data.get("formats") or {}).items()
            if v == "reduced"}


def pick_topic(today: date, topics: list[dict] | None = None,
               topic_id: str | None = None) -> dict | None:
    """今週の1本を選ぶ。topic_id 指定時はそれを強制選択。"""
    topics = topics if topics is not None else load_topics()
    if topic_id:
        for t in topics:
            if t.get("id") == topic_id:
                return t
        return None

    # needs_review はAI提案の骨子（人間がデータを埋めるまで自動選択しない）
    avail = [t for t in topics
             if is_available(t, today) and not t.get("needs_review")]
    if not avail:
        return None
    # 伸びていない型（週次レポート判定）は後回しにする＝生成を減らす
    reduced = _reduced_formats()
    preferred = [t for t in avail if t.get("format") not in reduced]
    return (preferred or avail)[0]


def mark_used(topic_id: str, used_on: date, path: Path = TOPICS_PATH) -> None:
    data = load_yaml(path, default={"topics": []})
    for t in data.get("topics", []):
        if t.get("id") == topic_id:
            t["last_used"] = used_on.isoformat()
    save_yaml(path, data)
