# -*- coding: utf-8 -*-
"""ネタストックの重複検出・90日再利用・選択ロジックのテスト。"""

from datetime import date

from src.evergreen.topics import (find_duplicates, is_available, load_topics,
                                  pick_topic)

TODAY = date(2026, 7, 26)


def _t(id_, theme, last_used=None, fmt="table", needs_review=False):
    return {"id": id_, "theme": theme, "format": fmt,
            "last_used": last_used, "needs_review": needs_review}


class TestDuplicates:
    def test_no_dup(self):
        assert find_duplicates([_t("ev001", "高配当比較"),
                                _t("ev002", "指数比較")]) == []

    def test_id_dup(self):
        probs = find_duplicates([_t("ev001", "A"), _t("ev001", "B")])
        assert any("ID重複" in p for p in probs)

    def test_theme_dup_normalized(self):
        # 空白・記号・全半角の違いは同一テーマとみなす
        probs = find_duplicates([_t("ev001", "高配当ETF比較（VYM/HDV）"),
                                 _t("ev002", "高配当ＥＴＦ比較 VYM HDV")])
        assert any("テーマ重複" in p for p in probs)

    def test_real_stock_has_no_duplicates(self):
        # 実データ（data/evergreen_topics.yml）に重複がないこと
        assert find_duplicates(load_topics()) == []


class TestAvailability:
    def test_unused_is_available(self):
        assert is_available(_t("ev001", "A"), TODAY)

    def test_recent_use_blocks(self):
        assert not is_available(_t("ev001", "A", "2026-07-01"), TODAY)

    def test_90days_reopens(self):
        assert is_available(_t("ev001", "A", "2026-04-01"), TODAY)
        assert not is_available(_t("ev001", "A", "2026-04-30"), TODAY)


class TestPick:
    def test_picks_first_unused(self):
        topics = [_t("ev001", "A", "2026-07-20"), _t("ev002", "B")]
        assert pick_topic(TODAY, topics)["id"] == "ev002"

    def test_skips_needs_review(self):
        topics = [_t("ev001", "A", needs_review=True), _t("ev002", "B")]
        assert pick_topic(TODAY, topics)["id"] == "ev002"

    def test_none_when_exhausted(self):
        topics = [_t("ev001", "A", "2026-07-20")]
        assert pick_topic(TODAY, topics) is None

    def test_forced_id(self):
        topics = [_t("ev001", "A"), _t("ev002", "B", "2026-07-20")]
        assert pick_topic(TODAY, topics, topic_id="ev002")["id"] == "ev002"

    def test_real_stock_has_20_or_more(self):
        assert len(load_topics()) >= 20
