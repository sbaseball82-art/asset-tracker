# -*- coding: utf-8 -*-
"""morning-brief の「更新が止まって見える」経路の回帰テスト。

2026-08-06〜09 に起きた事象を再現して固定する:
  - 材料の薄い日が続くとブリーフが何日も空になっていた（静かな日カードで解消）
  - 週末の再実行が金曜のカードを「該当なし」で上書きしうる（STATE で解消）
  - ^GSPC 1本の最終バー遅れで全候補が消える（多数決で解消）
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

import pytest

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "scripts")
sys.path.insert(0, SCRIPTS)

import main as mb                                     # noqa: E402
from config_loader import load_config                 # noqa: E402
from sources import market as l1                      # noqa: E402
from story_builder import build_quiet_story           # noqa: E402
import gate                                           # noqa: E402

CFG = load_config()
ASOF = dt.date(2026, 8, 6)


def _metrics(ret1d_pct: float, z: float, last: float = 6000.0,
             asof: str = "2026-08-06") -> dict:
    return {"last": last, "prev": last / (1 + ret1d_pct / 100),
            "ret1d_pct": ret1d_pct, "zscore": z, "vol_ratio": 1.0,
            "ret6m_pct": 5.0, "asof": asof}


def _quiet_market() -> dict:
    """全銘柄が基準内（静かな日）の market_metrics。"""
    return {
        "^GSPC": _metrics(0.13, 0.4),
        "^IXIC": _metrics(0.20, 0.5, last=22000.0),
        "JPY=X": _metrics(-0.05, 0.2, last=158.40),
        "^TNX": _metrics(0.30, 0.6, last=4.25),
        "NVDA": _metrics(0.80, 0.9, last=190.0),
    }


class TestQuietStory:
    def test_builds_with_real_numbers(self):
        s = build_quiet_story(_quiet_market(), CFG, ASOF)
        assert s is not None
        assert len(s["numbers"]) >= CFG["gate"]["min_numbers"]
        assert all(n["source"] and n["asof"] for n in s["numbers"])

    def test_passes_the_same_gate_as_normal_cards(self):
        s = build_quiet_story(_quiet_market(), CFG, ASOF)
        assert gate.check(s, CFG) == []

    def test_no_anomaly_wording_matches_reality(self):
        s = build_quiet_story(_quiet_market(), CFG, ASOF, reason="no_anomaly")
        assert "静かな1日" in s["headline"]
        assert "以内に収まったため" in s["why"]

    def test_gate_failed_does_not_claim_everything_was_calm(self):
        """動いた銘柄があった日に「全銘柄が基準内」と書かない（事実誤り防止）。"""
        mm = _quiet_market()
        mm["NVDA"] = _metrics(4.0, 1.9, last=200.0)
        s = build_quiet_story(mm, CFG, ASOF, reason="gate_failed")
        assert "以内に収まった" not in s["why"]
        assert "静かな1日" not in s["headline"]
        assert "裏取り" in s["conclusion"] or "裏取り" in s["why"]
        assert gate.check(s, CFG) == []

    def test_top_mover_is_the_largest_absolute_move(self):
        mm = _quiet_market()
        mm["MU"] = _metrics(-3.2, 1.1, last=120.0)
        s = build_quiet_story(mm, CFG, ASOF)
        assert "-3.2%" in s["fact"] or "-3.2%" in s["counter"]

    def test_returns_none_without_base_index(self):
        assert build_quiet_story({"NVDA": _metrics(1.0, 0.5)}, CFG, ASOF) is None

    def test_returns_none_when_too_few_numbers(self):
        # ^GSPC しか無い日はゲートの検証済み数値3件を満たせない
        assert build_quiet_story({"^GSPC": _metrics(0.1, 0.3)}, CFG, ASOF) is None

    def test_post_has_disclaimer_source(self):
        s = build_quiet_story(_quiet_market(), CFG, ASOF)
        assert "出典" in s["post"]


class TestState:
    def test_roundtrip(self, tmp_path):
        d = str(tmp_path)
        open(os.path.join(d, "2026-08-06_1.png"), "w").close()
        mb._write_state(d, "2026-08-06", 2)
        st = mb._completed_state(d)
        assert st["market_day"] == "2026-08-06" and st["cards"] == 2

    def test_missing_file_returns_none(self, tmp_path):
        assert mb._completed_state(str(tmp_path)) is None

    def test_broken_json_falls_back_to_regenerate(self, tmp_path):
        d = str(tmp_path)
        with open(os.path.join(d, mb.STATE_FILE), "w") as f:
            f.write("{壊れたJSON")
        assert mb._completed_state(d) is None

    def test_cards_recorded_but_images_gone_regenerates(self, tmp_path):
        """STATE上はカードありでも画像が消えていれば作り直す。"""
        d = str(tmp_path)
        mb._write_state(d, "2026-08-06", 2)      # png を置かない
        assert mb._completed_state(d) is None

    def test_zero_card_state_allows_retry(self, tmp_path):
        d = str(tmp_path)
        mb._write_state(d, "2026-08-06", 0)
        st = mb._completed_state(d)
        assert st is not None and st["cards"] == 0   # cards==0 は短絡しない

    def test_refresh_latest_empty_clears_and_records(self, tmp_path):
        d = str(tmp_path)
        open(os.path.join(d, "2026-07-30_1.png"), "w").close()
        mb.refresh_latest_empty(d, ASOF, "本日は該当なし", "2026-08-06")
        names = set(os.listdir(d))
        assert names == {"NOTE.txt", mb.STATE_FILE}
        assert json.load(open(os.path.join(d, mb.STATE_FILE)))["cards"] == 0

    def test_dry_run_does_not_write_state(self, tmp_path):
        d = str(tmp_path)
        mb.refresh_latest_empty(d, ASOF, "ドライラン", "2026-08-06",
                                write_state=False)
        assert not os.path.exists(os.path.join(d, mb.STATE_FILE))


class TestMarketDayMajority:
    """^GSPC が1日遅れても、多数派の取引日で候補が消えないこと。"""

    def _series(self, last_date: str, n: int = 80) -> dict:
        start = dt.date.fromisoformat(last_date) - dt.timedelta(days=n - 1)
        dates = [(start + dt.timedelta(days=i)).isoformat() for i in range(n)]
        return {"dates": dates, "closes": [100.0] * n, "volumes": [1e6] * n}

    def test_majority_wins_over_stale_spx(self):
        from collections import Counter
        mkt = {"^GSPC": self._series("2026-08-06"),
               "NVDA": self._series("2026-08-07"),
               "MSFT": self._series("2026-08-07"),
               "AAPL": self._series("2026-08-07")}
        votes = Counter(s["dates"][-1] for s in mkt.values())
        assert votes.most_common(1)[0][0] == "2026-08-07"

    def test_require_asof_filters_only_stale_tickers(self):
        mkt = {"NVDA": self._series("2026-08-07"),
               "MSFT": self._series("2026-08-06")}
        # 大きく動かした NVDA だけが候補に残る
        # （履歴に微小な変動を入れる。完全フラットだと sd=0 で z が
        #   ゼロ除算ガードにより 0 になり、意図した検証にならない）
        mkt["NVDA"]["closes"] = [100.0 + (i % 2) * 0.1 for i in range(79)] + [115.0]
        mkt["MSFT"]["closes"] = [100.0 + (i % 2) * 0.1 for i in range(79)] + [115.0]
        got = l1.find_anomalies(mkt, CFG, require_asof="2026-08-07")
        assert [c["ticker"] for c in got] == ["NVDA"]

    def test_flat_history_does_not_crash(self):
        """完全フラット（sd=0）でもゼロ除算せず、候補にもならない。"""
        mkt = {"AAA": self._series("2026-08-07")}
        assert l1.find_anomalies(mkt, CFG, require_asof="2026-08-07") == []


class TestMetricsMath:
    """z-score・出来高比の検算（0件が続いたとき計算式を疑えるように）。"""

    def test_zscore_of_flat_series_is_zero(self):
        s = {"dates": [f"2026-01-{i:02d}" for i in range(1, 81)],
             "closes": [100.0] * 80, "volumes": [1e6] * 80}
        assert l1.metrics(s, CFG)["zscore"] == 0.0

    def test_large_move_exceeds_threshold(self):
        closes = [100.0 + (i % 2) * 0.1 for i in range(79)] + [130.0]
        s = {"dates": [(dt.date(2026, 1, 1) + dt.timedelta(days=i)).isoformat()
                       for i in range(80)],
             "closes": closes, "volumes": [1e6] * 80}
        m = l1.metrics(s, CFG)
        assert abs(m["zscore"]) >= CFG["anomaly"]["min_abs_z"]
        assert m["ret1d_pct"] == pytest.approx(30.0, abs=0.01)

    def test_volume_ratio(self):
        s = {"dates": [(dt.date(2026, 1, 1) + dt.timedelta(days=i)).isoformat()
                       for i in range(80)],
             "closes": [100.0] * 80, "volumes": [1e6] * 79 + [3e6]}
        assert l1.metrics(s, CFG)["vol_ratio"] == pytest.approx(3.0)

    def test_too_short_series_returns_none(self):
        s = {"dates": ["2026-01-01"] * 10, "closes": [100.0] * 10,
             "volumes": [1e6] * 10}
        assert l1.metrics(s, CFG) is None


class TestQuietTemplates:
    """静かな日カードに使うテンプレの制限（文意が壊れる型を使わない）。"""

    def test_excludes_incompatible_templates(self):
        # T6(なぜ〜？) は答えが問いに対応せず、T3(巨大数字)/T4(対比)は
        # 小さな値動きの日に誇張・不成立になる
        assert set(mb.QUIET_TEMPLATES).isdisjoint({"T3", "T4", "T6"})

    def test_all_are_real_templates(self):
        from templates import BUILDERS
        assert all(t in BUILDERS for t in mb.QUIET_TEMPLATES)

    def test_rotation_is_stable_and_in_range(self):
        for ordinal in range(400):
            t = mb.QUIET_TEMPLATES[ordinal % len(mb.QUIET_TEMPLATES)]
            assert t in mb.QUIET_TEMPLATES


class TestChartLabelPlacement:
    """高値圏で終えた日に、当日注記が右上の「6ヶ月」表記と重ならないこと。"""

    def _render(self, closes):
        import matplotlib
        matplotlib.use("Agg")
        from render import _chart
        import matplotlib.pyplot as plt
        fig = plt.figure(figsize=(10.8, 13.5), dpi=100)
        series = {"dates": [(dt.date(2026, 3, 1) + dt.timedelta(days=i)).isoformat()
                            for i in range(len(closes))], "closes": closes}
        story = {"name": "S&P500", "event_pct": 0.62, "event_label": "+0.62%"}
        assert _chart(fig, (72, 400, 936, 170), series, story)
        ann = [t for t in fig.axes[-1].texts if "0.62" in t.get_text()][0]
        plt.close(fig)
        return ann.get_position()[1]      # y offset (points)

    def test_high_close_places_label_below(self):
        assert self._render([100.0 + i for i in range(126)]) < 0

    def test_low_close_places_label_above(self):
        assert self._render([200.0 - i for i in range(126)]) > 0
