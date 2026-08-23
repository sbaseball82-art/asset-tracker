# -*- coding: utf-8 -*-
"""
ネタプールと builder のテスト。

いちばん大事なのは「取れないデータを推測で埋めない」こと。
requires が欠けている話題が候補に出ないこと、
データ源が無い話題は理由つきで残ることを確認する。
"""

import json
from datetime import date
from pathlib import Path

import pytest

from src.common.util import REPO_ROOT
from src.daily_growth import facts, topics
from src.daily_growth.compose import Val

FIXTURE = Path(__file__).parent / "fixtures" / "daily_growth_data.json"
TODAY = date(2026, 8, 17)


@pytest.fixture(scope="module")
def data() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def f(data) -> dict:
    return facts.build(data, TODAY)


@pytest.fixture(scope="module")
def pool() -> list[dict]:
    return topics.load_topics()


# --------------------------------------------------------------------------
# プールの健全性
# --------------------------------------------------------------------------

def test_ネタプールに不備がない(pool):
    assert topics.find_duplicates(pool) == []


def test_依頼の10テーマぶんの本数がある(pool):
    # 固定10テーマ＋既存運用からの追加テーマ。順番に回さないだけの厚みが要る
    assert len(pool) >= 30


def test_IDが一意(pool):
    ids = [t["id"] for t in pool]
    assert len(ids) == len(set(ids))


def test_designsは実在するデザインだけ(pool):
    from src.daily_growth import render
    known = set(render.load_designs())
    for t in pool:
        for d in t.get("designs") or []:
            assert d in known, f"{t['id']} に未定義のデザイン {d}"


def test_テンプレに金融数値を直書きしていない(pool):
    """YAML に「72%」のような数字を手書きしても通らないようにする。

    プレースホルダを外した状態で、単位つきの数字が残っていたら不合格。
    """
    import re
    ph = re.compile(r"\{[a-z_0-9]+\}")
    bad = []
    for t in pool:
        for key in ("hook", "view", "headline"):
            s = t.get(key)
            if not s:
                continue
            stripped = ph.sub("", str(s))
            if re.search(r"\d+(?:\.\d+)?\s*(?:%|円|万円|億円|%pt)", stripped):
                bad.append(f"{t['id']}.{key}")
        for n in t.get("numbers") or []:
            stripped = ph.sub("", str(n))
            if re.search(r"\d+(?:\.\d+)?\s*(?:%|円|万円|億円|%pt)", stripped):
                bad.append(f"{t['id']}.numbers")
    assert bad == [], f"テンプレに数値の直書きがあります: {bad}"


# --------------------------------------------------------------------------
# requires によるゲート
# --------------------------------------------------------------------------

def test_必要なデータが無い話題は候補にならない(f, pool):
    t = next(t for t in pool if t["id"] == "dg091")   # 1年前との比較
    assert "year_ago" not in f, "テスト前提: 履歴は1年ぶん無い"
    assert topics.build_draft(t, f) is None


def test_データ源が無い話題は理由つきでスキップされる(f, pool):
    _, skipped = topics.build_all(pool, f)
    ids = {s["id"]: s["reason"] for s in skipped}
    for tid in ("dg100", "dg101", "dg102", "dg103", "dg104"):
        assert tid in ids
        assert ids[tid]


def test_ルックスルーが無ければ企業別分解を作らない(f, pool):
    assert "lookthrough" not in f
    t = next(t for t in pool if t["id"] == "dg092")
    assert topics.build_draft(t, f) is None


def test_不足キーはmissing_requirementsで分かる(pool):
    t = next(t for t in pool if t["id"] == "dg001")
    assert topics.missing_requirements(t, {}) == t["requires"]


# --------------------------------------------------------------------------
# builder が作る値
# --------------------------------------------------------------------------

def test_作れた候補は全部Valで数字を持つ(f, pool):
    drafts, _ = topics.build_all(pool, f)
    assert drafts, "1本も作れていません"
    for d in drafts:
        assert d.values, f"{d.topic_id} に source_values がありません"
        assert all(isinstance(v, Val) for v in d.values.values())


def test_今日のデータで作れる話題が5本以上ある(f, pool):
    drafts, _ = topics.build_all(pool, f)
    assert len(drafts) >= 5


def test_寄与はptで表示される(f, pool):
    t = next(t for t in pool if t["id"] == "dg010")
    d = topics.build_draft(t, f)
    assert "%pt" in d.values["top_pt"].text


def test_比率はptにしない(f, pool):
    t = next(t for t in pool if t["id"] == "dg050")
    d = topics.build_draft(t, f)
    assert d.values["top_pct"].text.endswith("%")
    assert "%pt" not in d.values["top_pct"].text


def test_DRAMの話題にはシクリカルが入る(f, pool):
    t = next(t for t in pool if t["id"] == "dg071")
    d = topics.build_draft(t, f)
    assert d is not None
    assert "シクリカル" in d.text


def test_条件を満たさない日は作らない(f, pool):
    """静かな日でなければ「何も起きなかった日」は作られない。"""
    t = next(t for t in pool if t["id"] == "dg002")
    assert f["quiet"]["is_quiet"] is False
    assert topics.build_draft(t, f) is None


def test_価格要因と為替要因を足すと前日比になる(f, pool):
    t = next(t for t in pool if t["id"] == "dg020")
    d = topics.build_draft(t, f)
    v = d.values
    assert (float(v["price"].raw) + float(v["fx"].raw)
            == pytest.approx(float(v["total"].raw), abs=1.0))


def test_カードは図を1つだけ持つ(f, pool):
    drafts, _ = topics.build_all(pool, f)
    for d in drafts:
        assert d.card["figure"]["kind"] in (
            "bars", "compare", "progress", "table", "sparkline")


# --------------------------------------------------------------------------
# 自動投稿の不在（仕様）
# --------------------------------------------------------------------------

def test_daily_growthに自動投稿コードがない():
    import re
    posting = re.compile(
        r"\b(tweepy|api\.twitter\.com|create_tweet|update_status|/2/tweets)\b",
        re.I)
    for p in (REPO_ROOT / "src" / "daily_growth").rglob("*.py"):
        assert not posting.search(p.read_text(encoding="utf-8")), p


def test_テンプレの文言に禁止語が入っていない(pool):
    """YAMLの時点で煽り・断定が混ざっていないかを見る。

    生成後のQAでも落とすが、ネタを足したときにその場で気づけるようにする。
    """
    from src.daily_growth.compose import FORBIDDEN
    hits = []
    for t in pool:
        blob = " ".join(str(t.get(k) or "") for k in
                        ("title", "hook", "view", "headline")) + \
            " ".join(str(n) for n in (t.get("numbers") or []))
        for word in FORBIDDEN:
            if word in blob:
                hits.append(f"{t['id']}: {word}")
    assert hits == [], f"テンプレに禁止語があります: {hits}"


def test_全候補の本文が方針検査を通る(f, pool):
    from src.daily_growth.compose import validate_text
    drafts, _ = topics.build_all(pool, f, 165.0)
    for d in drafts:
        assert validate_text(d.text, 165.0) == [], f"{d.topic_id}: {d.text}"
