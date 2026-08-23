# -*- coding: utf-8 -*-
"""
スコアと選抜のテスト。

  - その日しか作れない話題（surprise が高い）が固定テーマより上に来る
  - ローテーション違反は減点ではなく除外
  - logs/posts.csv のサンプルが足りないうちは学習補正をかけない
"""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from src.common import settings
from src.daily_growth import facts, history as H, render, score, topics
from src.daily_growth.compose import Draft

TODAY = date(2026, 8, 17)
FIXTURE = Path(__file__).parent / "fixtures" / "daily_growth_data.json"
WEIGHTS = {"freshness": 0.30, "personal_asset_relevance": 0.30,
           "surprise": 0.20, "timeliness": 0.10, "visual_clarity": 0.10}
ROTATION = {"topic_reuse_days": 14, "hook_avoid_days": 30,
            "design_max_consecutive_days": 3, "hook_similarity": 0.80,
            "prev_day_similarity": 0.72}


def draft(tid="dg001", *, category="daily_move", surprise=0.5, hook=None,
          text=None, designs=None, builder="") -> Draft:
    return Draft(topic_id=tid, category=category, builder=builder,
                 hook=hook or f"{tid}の書き出しです",
                 text=text or f"{tid}の本文です。ここに固有の話を書きます。",
                 values={}, card={}, surprise=surprise,
                 designs=designs or ["dark_financial_report", "light_editorial",
                                     "receipt", "versus", "milestone"])


def entry(d: date, topic="dg001", hook="hook", design="dark_financial_report",
          text="本文") -> dict:
    return H.make_entry(d.isoformat(), topic, hook, design, text, {}, [])


@pytest.fixture(scope="module")
def f() -> dict:
    return facts.build(json.loads(FIXTURE.read_text(encoding="utf-8")), TODAY)


# --------------------------------------------------------------------------
# freshness
# --------------------------------------------------------------------------

def test_未使用の話題はfreshnessが最大():
    assert score.freshness("dg001", TODAY, [], 14) == 1.0


def test_直近で使った話題はfreshnessがゼロ():
    assert score.freshness("dg001", TODAY, [entry(TODAY - timedelta(days=3))],
                           14) == 0.0


def test_時間が経つほどfreshnessが戻る():
    a = score.freshness("dg001", TODAY, [entry(TODAY - timedelta(days=20))], 14)
    b = score.freshness("dg001", TODAY, [entry(TODAY - timedelta(days=40))], 14)
    assert 0 < a < b <= 1.0


# --------------------------------------------------------------------------
# 重み
# --------------------------------------------------------------------------

def test_重みの合計は1():
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)
    assert sum(settings.dg_weights().values()) == pytest.approx(1.0)


def test_その日しか作れない話題が固定テーマより上に来る():
    event = draft("dgEVENT", surprise=0.95)
    fixed = draft("dgFIXED", surprise=0.20)
    ranked = score.rank([fixed, event], TODAY, [], WEIGHTS, ROTATION)
    assert ranked[0].draft.topic_id == "dgEVENT"


def test_設定から重みを変えられる():
    only_surprise = {"freshness": 0, "personal_asset_relevance": 0,
                     "surprise": 1.0, "timeliness": 0, "visual_clarity": 0}
    s = score.rank([draft(surprise=0.4)], TODAY, [], only_surprise, ROTATION)[0]
    assert s.score == pytest.approx(0.4)


# --------------------------------------------------------------------------
# 除外（減点ではなく除外）
# --------------------------------------------------------------------------

def test_14日以内の同一topicは除外される():
    entries = [entry(TODAY - timedelta(days=5), topic="dg001")]
    s = score.rank([draft("dg001")], TODAY, entries, WEIGHTS, ROTATION)[0]
    assert "14日以内" in s.excluded


def test_30日以内の類似hookは除外される():
    entries = [entry(TODAY - timedelta(days=10), topic="dg999",
                     hook="総資産が増えました")]
    s = score.rank([draft("dg001", hook="総資産が増えました")], TODAY, entries,
                   WEIGHTS, ROTATION)[0]
    assert "書き出し" in s.excluded


def test_前日と似すぎた候補は除外される():
    same = "同じような本文がならびます。ここは前日とほぼ同じ内容です。"
    entries = [entry(TODAY - timedelta(days=1), topic="dg999", hook="別のhook",
                     text=same)]
    s = score.rank([draft("dg001", text=same)], TODAY, entries,
                   WEIGHTS, ROTATION)[0]
    assert "前日" in s.excluded


def test_全デザインが連続制限なら除外される():
    entries = [entry(TODAY - timedelta(days=i), topic=f"dgX{i}",
                     hook=f"hook{i}", design="receipt") for i in (1, 2)]
    s = score.rank([draft("dg001", designs=["receipt"])], TODAY, entries,
                   WEIGHTS, ROTATION)[0]
    assert "デザイン" in s.excluded


def test_除外された候補は選ばれない():
    entries = [entry(TODAY - timedelta(days=5), topic="dg001")]
    ranked = score.rank([draft("dg001", surprise=1.0), draft("dg002")],
                        TODAY, entries, WEIGHTS, ROTATION)
    chosen, _ = score.select(ranked, 2, 2, render.load_designs(), ROTATION,
                             entries, TODAY)
    assert [c.draft.topic_id for c in chosen] == ["dg002"]


# --------------------------------------------------------------------------
# 選抜の制約
# --------------------------------------------------------------------------

def test_5本選ばれデザインが重複しない(f):
    drafts, _ = topics.build_all(topics.load_topics(), f)
    ranked = score.rank(drafts, TODAY, [], WEIGHTS, ROTATION)
    chosen, _ = score.select(ranked, 5, 2, render.load_designs(), ROTATION,
                             [], TODAY)
    assert len(chosen) == 5
    assert len({c.design_id for c in chosen}) == 5
    assert len({c.draft.topic_id for c in chosen}) == 5


def test_同じカテゴリは上限までしか採らない(f):
    drafts, _ = topics.build_all(topics.load_topics(), f)
    ranked = score.rank(drafts, TODAY, [], WEIGHTS, ROTATION)
    chosen, _ = score.select(ranked, 5, 2, render.load_designs(), ROTATION,
                             [], TODAY)
    cats: dict[str, int] = {}
    for c in chosen:
        cats[c.draft.category] = cats.get(c.draft.category, 0) + 1
    assert max(cats.values()) <= 2


def test_似すぎた候補は同じ日に2本採らない():
    same = "ほとんど同じ内容の本文です。ここは共通の文章になっています。"
    ranked = score.rank([draft("dg001", text=same, category="a"),
                         draft("dg002", text=same, category="b")],
                        TODAY, [], WEIGHTS, ROTATION)
    chosen, _ = score.select(ranked, 2, 2, render.load_designs(), ROTATION,
                             [], TODAY)
    assert len(chosen) == 1


# --------------------------------------------------------------------------
# 実績からの学習
# --------------------------------------------------------------------------

def _row(fmt: str, follows: int, views: int = 1000) -> dict:
    return {"type": "daily_growth", "format": fmt, "views": views,
            "likes": 10, "bookmarks": 5, "replies": 1,
            "profile_clicks": 3, "follows": follows}


def test_サンプル不足なら学習しない():
    rows = [_row("receipt", 5) for _ in range(3)]
    perf = score.format_performance(rows, min_samples=8)
    assert perf == {}
    assert score.is_learned(perf) is False


def test_実績が空でも落ちない():
    assert score.format_performance([]) == {}


def test_未入力の行は数えない():
    rows = [{"type": "daily_growth", "format": "receipt", "views": "",
             "likes": "", "bookmarks": "", "replies": "",
             "profile_clicks": "", "follows": ""} for _ in range(20)]
    assert score.format_performance(rows, min_samples=8) == {}


def test_十分たまればフォロー数の多い型が高くなる():
    rows = ([_row("receipt", 20) for _ in range(8)] +
            [_row("versus", 1) for _ in range(8)])
    perf = score.format_performance(rows, min_samples=8)
    assert score.is_learned(perf)
    assert perf["receipt"] > perf["versus"]
    assert -1.0 <= perf["versus"] <= perf["receipt"] <= 1.0


def test_学習補正は小さくローテーションを覆さない():
    entries = [entry(TODAY - timedelta(days=5), topic="dg001")]
    perf = {"receipt": 1.0}
    s = score.rank([draft("dg001", designs=["receipt"])], TODAY, entries,
                   WEIGHTS, ROTATION, perf)[0]
    assert s.excluded  # 学習補正があっても除外は覆らない


def test_現在のposts_csvはまだ学習済みではない():
    from src.common import postlog
    assert score.format_performance(postlog.read_rows()) == {}


# --------------------------------------------------------------------------
# ネタが尽きたときのゆるめ方
# --------------------------------------------------------------------------

def test_ゆるめる順番は段階的():
    ladder = score.relaxation_ladder(ROTATION)
    assert ladder[0] == ROTATION
    days = [x["topic_reuse_days"] for x in ladder]
    assert days == sorted(days, reverse=True)
    assert days[-1] == 2, "最終段でも前日との重複は避ける"


def test_ゆるめてもデザインと前日類似の条件は変えない():
    for step in score.relaxation_ladder(ROTATION):
        assert step["design_max_consecutive_days"] == 3
        assert step["prev_day_similarity"] == 0.72


def test_ゆるめたことを説明できる():
    base, used = ROTATION, {**ROTATION, "topic_reuse_days": 2}
    assert "14日→2日" in score.describe_relaxation(base, used)
    assert score.describe_relaxation(base, base) == ""


def test_10日連続で5本そろい前日と同じ話題が出ない(f):
    from src.daily_growth.generate import _choose
    designs = render.load_designs()
    entries: list[dict] = []
    drafts, _ = topics.build_all(topics.load_topics(), f)
    for i in range(10):
        day = TODAY + timedelta(days=i)
        chosen, _rest, _rot, _cat = _choose(drafts, day, entries, ROTATION,
                                            designs, {}, 5, 2)
        assert len(chosen) == 5, f"{day} に5本そろいません"
        assert len({c.design_id for c in chosen}) == 5
        yesterday = {e["topic_id"] for e in entries
                     if e["date"] == (day - timedelta(days=1)).isoformat()}
        assert not (yesterday & {c.draft.topic_id for c in chosen})
        entries += [H.make_entry(day.isoformat(), c.draft.topic_id,
                                 c.draft.hook, c.design_id, c.draft.text, {}, [])
                    for c in chosen]


def test_同じ計算の言い換えを1日に2本入れない():
    ranked = score.rank([draft("dg003", category="fx", builder="fx_decomp",
                               surprise=0.9),
                         draft("dg020", category="fx", builder="fx_decomp",
                               surprise=0.8)],
                        TODAY, [], WEIGHTS, ROTATION)
    chosen, _ = score.select(ranked, 5, 2, render.load_designs(), ROTATION,
                             [], TODAY)
    assert [c.draft.topic_id for c in chosen] == ["dg003"]
