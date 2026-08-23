# -*- coding: utf-8 -*-
"""
履歴（data/daily_growth_history.jsonl）とローテーション判定のテスト。

「毎日同じ内容になる」ことを防ぐ規則はここで固める。
  - 同一 topic_id は14日間再利用しない
  - 同一・類似 hook は30日間避ける
  - 同一 design_id は3日連続で使わない
"""

from datetime import date, timedelta

import pytest

from src.daily_growth import history as H

TODAY = date(2026, 8, 17)


def entry(d: date, topic="dg001", hook="今日の資産の話です", design="dark_financial_report",
          text="本文", values=None) -> dict:
    return H.make_entry(d.isoformat(), topic, hook, design, text,
                        values or {"total_jpy": {"raw": 1000.0, "text": "約0円"}},
                        ["post_1.png", "post_1.txt"])


# --------------------------------------------------------------------------
# 入出力
# --------------------------------------------------------------------------

def test_書いて読める(tmp_path):
    p = tmp_path / "h.jsonl"
    H.append([entry(TODAY), entry(TODAY, topic="dg002")], p)
    rows = H.load(p)
    assert [r["topic_id"] for r in rows] == ["dg001", "dg002"]
    assert rows[0]["generated_files"] == ["post_1.png", "post_1.txt"]


def test_必須項目が欠けたら書けない(tmp_path):
    p = tmp_path / "h.jsonl"
    broken = entry(TODAY)
    del broken["design_id"]
    with pytest.raises(ValueError):
        H.append([broken], p)


def test_壊れた行があっても読める(tmp_path):
    p = tmp_path / "h.jsonl"
    H.append([entry(TODAY)], p)
    with open(p, "a", encoding="utf-8") as fh:
        fh.write("{壊れたJSON\n\n")
    assert len(H.load(p)) == 1


def test_ファイルが無ければ空(tmp_path):
    assert H.load(tmp_path / "none.jsonl") == []


# --------------------------------------------------------------------------
# topic の再利用禁止
# --------------------------------------------------------------------------

@pytest.mark.parametrize("days_ago,blocked", [(0, True), (1, True), (13, True),
                                              (14, False), (30, False)])
def test_同一topicは14日間使えない(days_ago, blocked):
    entries = [entry(TODAY - timedelta(days=days_ago))]
    assert H.topic_blocked("dg001", TODAY, entries, 14) is blocked


def test_別のtopicなら使える():
    entries = [entry(TODAY - timedelta(days=1))]
    assert H.topic_blocked("dg002", TODAY, entries, 14) is False


def test_最後に使ってからの日数が分かる():
    entries = [entry(TODAY - timedelta(days=20)),
               entry(TODAY - timedelta(days=5))]
    assert H.days_since_topic("dg001", TODAY, entries) == 5
    assert H.days_since_topic("dg999", TODAY, entries) is None


# --------------------------------------------------------------------------
# hook の回避
# --------------------------------------------------------------------------

def test_同じhookは30日間避ける():
    entries = [entry(TODAY - timedelta(days=20), hook="総資産が増えました")]
    assert H.hook_blocked("総資産が増えました", TODAY, entries, 30, 0.8) is True


def test_数字だけ違うhookも同じとみなす():
    entries = [entry(TODAY - timedelta(days=3),
                     hook="総資産約3,400万円。前日比+0.12%でした。")]
    assert H.hook_blocked("総資産約3,469万円。前日比+0.04%でした。",
                          TODAY, entries, 30, 0.8) is True


def test_違うhookなら通る():
    entries = [entry(TODAY - timedelta(days=3), hook="総資産が増えました")]
    assert H.hook_blocked("ETFと投資信託で反映日がズレています",
                          TODAY, entries, 30, 0.8) is False


def test_31日前のhookは効かない():
    entries = [entry(TODAY - timedelta(days=31), hook="総資産が増えました")]
    assert H.hook_blocked("総資産が増えました", TODAY, entries, 30, 0.8) is False


# --------------------------------------------------------------------------
# design の連続使用
# --------------------------------------------------------------------------

def test_2日連続で使ったデザインは3日目に使えない():
    entries = [entry(TODAY - timedelta(days=1), design="receipt"),
               entry(TODAY - timedelta(days=2), design="receipt")]
    assert H.design_blocked("receipt", TODAY, entries, 3) is True


def test_1日だけならまだ使える():
    entries = [entry(TODAY - timedelta(days=1), design="receipt")]
    assert H.design_blocked("receipt", TODAY, entries, 3) is False


def test_間が空いていれば使える():
    entries = [entry(TODAY - timedelta(days=1), design="receipt"),
               entry(TODAY - timedelta(days=3), design="receipt")]
    assert H.design_blocked("receipt", TODAY, entries, 3) is False


# --------------------------------------------------------------------------
# 前日との類似
# --------------------------------------------------------------------------

def test_前日の本文を取り出せる():
    entries = [entry(TODAY - timedelta(days=1), text="きのうの本文"),
               entry(TODAY - timedelta(days=2), text="おとといの本文")]
    assert H.previous_day_texts(TODAY, entries) == ["きのうの本文"]


def test_類似度は同じ文で1になる():
    assert H.similarity("同じ文です", "同じ文です") == pytest.approx(1.0)
    assert H.similarity("同じ文です", "") == 0.0


def test_ハッシュタグは類似度に影響しない():
    a = "総資産の話です\n#資産推移 #米国株"
    b = "総資産の話です\n#ETF #高配当ETF"
    assert H.similarity(a, b) == pytest.approx(1.0)


# --------------------------------------------------------------------------
# 答え合わせの素材
# --------------------------------------------------------------------------

def test_7日以上前の記録から答え合わせの素材を選ぶ():
    entries = [entry(TODAY - timedelta(days=3)),
               entry(TODAY - timedelta(days=10))]
    src = H.checkback_source(entries, TODAY)
    assert src is not None and src["age_days"] == 10


def test_総資産の記録が無ければ答え合わせしない():
    e = entry(TODAY - timedelta(days=10), values={"pct": {"raw": 1, "text": "1%"}})
    assert H.checkback_source([e], TODAY) is None


def test_直近すぎる記録は使わない():
    assert H.checkback_source([entry(TODAY - timedelta(days=2))], TODAY) is None
