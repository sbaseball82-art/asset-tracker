# -*- coding: utf-8 -*-
"""アクセントテーマ：話題タグに応じてアクセント色だけを変える。

背景・カード色・チャートの騰落色・フッターの ASSET LOG（ゴールド）は
ブランド維持のため固定。変えるのは main（バッジ・❶❸ラベル等）と
sub（一行結論・❷ラベル等）の2色のみ。
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    main: str
    sub: str


THEMES: dict[str, Theme] = {
    "semiconductor": Theme(main="#7C8CF8", sub="#4ED4C4"),
    "rates":         Theme(main="#35C7B8", sub="#E0AC4E"),
    "earnings":      Theme(main="#E0AC4E", sub="#7C8CF8"),
    "fx":            Theme(main="#6FA8F0", sub="#5FD08F"),
    "ai":            Theme(main="#9B8CF8", sub="#4ED4C4"),
    "macro":         Theme(main="#d8b56a", sub="#6aa6e8"),
    "default":       Theme(main="#d8b56a", sub="#6aa6e8"),
}

# story_builder のセクター → 話題タグ（学習・テーマ・meta.json で使用）
TOPIC_TAG = {
    "memory": "semiconductor",
    "ai_semi": "semiconductor",
    "megatech": "ai",
    "rates": "rates",
    "fx": "fx",
    "index": "macro",
    "dividend": "other",
    "energy": "other",
    "financials": "other",
    "utilities": "other",
}


def tag_for_sector(sector: str) -> str:
    return TOPIC_TAG.get(sector, "other")


def theme_for_tag(tag: str) -> Theme:
    return THEMES.get(tag, THEMES["default"])
