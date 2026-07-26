# -*- coding: utf-8 -*-
"""生成のスモークテスト（ネットワーク不要・画像なしモード）。"""

import os
from datetime import date
from pathlib import Path

import pytest

from src.common import postlog
from src.common.util import MANUAL
from src.earnings.generate import (build_morning, build_post_phase, build_pre)
from src.earnings.scheduler import due_phases
from src.evergreen import builders
from src.evergreen.generate import build_ammo_md, build_post_text
from src.evergreen.topics import load_topics

TODAY = date(2026, 7, 26)


def _topic(tid):
    for t in load_topics():
        if t["id"] == tid:
            return t
    raise AssertionError(f"{tid} が見つからない")


class TestEvergreenBuilders:
    @pytest.mark.parametrize("tid", ["ev001", "ev002", "ev003", "ev009", "ev006", "ev010"])
    def test_builds_and_post_within_limit(self, tid):
        from src.common.textcheck import check_post
        topic = _topic(tid)
        title, subtitle, spec, values, stale, asof = builders.build(topic, TODAY)
        post = build_post_text(topic, values)
        ok, n, warn = check_post(post)
        assert ok, f"{tid}: {warn}\n{post}"
        assert "投資助言ではありません" in post
        assert "詳細は返信に表を置いておきます" in post

    def test_overlap_values_computed(self):
        topic = _topic("ev001")
        _, _, spec, values, stale, _ = builders.build(topic, TODAY)
        assert 0 <= values["overlap_VYM_HDV"] <= 10
        assert len(spec["rows"]) == 3  # 3ペア

    def test_ammo_has_three_drafts(self):
        topic = _topic("ev003")
        md = build_ammo_md(topic, {}, "2026-07-26")
        assert md.count("### 案") == 3
        assert "想定リプライ先" in md


class TestEarningsTemplates:
    INFO = {"name_ja": "エヌビディア", "sp500_weight": 7.0, "qqq_weight": 9.3,
            "fund_weights": {"VTI": 6.0}, "focus": "データセンター売上"}
    EST_EMPTY = {"eps_estimate": None, "eps_actual": None,
                 "revenue_estimate": None, "revenue_actual": None, "hour": None}

    def test_pre_manual_when_no_api(self):
        text = build_pre("NVDA", "2026-08-27", self.INFO, self.EST_EMPTY,
                         2.5, is_macro=False)
        # API失敗時に推測値で埋めず「要手動入力」と表示される（受け入れ条件）
        assert MANUAL in text
        assert "分岐条件" in text

    def test_post_marks_afterhours(self):
        est = dict(self.EST_EMPTY, eps_estimate=1.0, eps_actual=1.1)
        text = build_post_phase("NVDA", "2026-08-27", self.INFO, est, False)
        assert "時間外" in text
        assert "ビート" in text

    def test_morning_contribution_math(self):
        # 構成比7.0% × -8.0% = -0.56%pt がテンプレに出ること
        text = build_morning("NVDA", "2026-08-27", self.INFO,
                             change_pct=-8.0, exposure=3.5, is_macro=False)
        assert "-0.56%pt" in text
        assert "約-0.28%" in text  # 3.5% × -8% = -0.28
        assert "投資助言ではありません" in text

    def test_morning_manual_when_no_price(self):
        text = build_morning("NVDA", "2026-08-27", self.INFO,
                             change_pct=None, exposure=3.5, is_macro=False)
        assert MANUAL in text


class TestScheduler:
    EVENT = {"date": "2026-07-28", "ticker": "ZZZTEST",
             "announce_jst": "2026-07-29 05:05", "type": "earnings"}

    def _now(self, s):
        from src.earnings.scheduler import _parse_jst
        return _parse_jst(s)

    def test_pre_window(self):
        assert "pre" in due_phases(self.EVENT, self._now("2026-07-29 04:05"))
        assert "pre" not in due_phases(self.EVENT, self._now("2026-07-29 03:00"))
        assert "pre" not in due_phases(self.EVENT, self._now("2026-07-29 05:10"))

    def test_post_window(self):
        assert "post" in due_phases(self.EVENT, self._now("2026-07-29 06:00"))
        assert "post" not in due_phases(self.EVENT, self._now("2026-07-29 12:00"))

    def test_morning_window(self):
        assert "morning" in due_phases(self.EVENT, self._now("2026-07-30 07:00"))
        assert "morning" not in due_phases(self.EVENT, self._now("2026-07-30 12:00"))


class TestPostLog:
    def test_append_and_read(self, tmp_path):
        p = tmp_path / "posts.csv"
        postlog.append_row("2026-07-26", "evergreen", "ev001", "table",
                           250, True, path=p)
        rows = postlog.read_rows(p)
        assert rows[0]["topic_id"] == "ev001"
        assert rows[0]["posted"] == "false"
        assert rows[0]["views"] == ""


class TestWeeklyAnalyze:
    def _row(self, d, fmt, views, type_="evergreen"):
        return {"date": d, "type": type_, "format": fmt, "posted": "true",
                "views": str(views)}

    def test_no_reduce_before_4_weeks(self):
        from src.report.weekly import analyze
        rows = [self._row("2026-07-06", "table", 100),
                self._row("2026-07-13", "line", 10)]
        assert analyze(rows)["reduced_formats"] == []

    def test_reduce_after_4_weeks(self):
        from src.report.weekly import analyze
        rows = []
        for i, d in enumerate(["2026-06-01", "2026-06-08", "2026-06-15",
                               "2026-06-22", "2026-06-29", "2026-07-06"]):
            rows.append(self._row(d, "table", 1000))
        for d in ["2026-06-02", "2026-06-09", "2026-06-16"]:
            rows.append(self._row(d, "line", 10))
        result = analyze(rows)
        assert "line" in result["reduced_formats"]
        assert "table" not in result["reduced_formats"]
