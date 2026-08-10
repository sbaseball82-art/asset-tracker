# -*- coding: utf-8 -*-
"""
キャッシュの鮮度管理と、週次ヘルスチェック（連続失敗の検出）のテスト。
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from src.lookthrough import constituents as C
from src.lookthrough import health


def iso_days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat(
        timespec="seconds")


# --------------------------------------------------------------------------
# 鮮度（0〜35日=正常 / 36〜90日=警告 / 91日〜=期限切れ）
# --------------------------------------------------------------------------

@pytest.mark.parametrize("days,want", [
    (0, "正常"), (35, "正常"), (36, "警告"), (90, "警告"),
    (91, "期限切れ"), (400, "期限切れ"), (None, "不明"),
])
def test_鮮度の区分(days, want):
    assert C.freshness_label(days) == want


def test_経過日数の計算():
    assert C.cache_age_days(iso_days_ago(10)) == 10
    assert C.cache_age_days(iso_days_ago(0)) == 0
    assert C.cache_age_days(None) is None
    assert C.cache_age_days("壊れた日付") is None


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "cache_dir", lambda: tmp_path)
    return tmp_path


def write_cache(dirpath, fund_id: str, days_old: int, count: int = 3):
    payload = {
        "fund_id": fund_id,
        "fetched_at": iso_days_ago(days_old),
        "as_of": "2026-08-01",
        "source": "test",
        "source_id": "test_source",
        "items": [{"ticker": f"T{i}", "weight_pct": 1.0, "name": None,
                   "sector": None} for i in range(count)],
    }
    (dirpath / f"{fund_id}.json").write_text(
        json.dumps(payload), encoding="utf-8")


def test_新しいキャッシュは使える(tmp_cache):
    write_cache(tmp_cache, "VTI", days_old=10)
    cached, age, why = C._load_cache("VTI")
    assert cached is not None
    assert age == 10
    assert why is None


def test_警告範囲のキャッシュはまだ使える(tmp_cache):
    write_cache(tmp_cache, "VTI", days_old=60)
    cached, age, why = C._load_cache("VTI")
    assert cached is not None
    assert age == 60
    assert C.freshness_label(age) == "警告"


def test_91日超のキャッシュは取得失敗と同じ扱い(tmp_cache):
    """古すぎるキャッシュでカバレッジを水増ししないための門。"""
    write_cache(tmp_cache, "VTI", days_old=120)
    cached, age, why = C._load_cache("VTI")
    assert cached is None
    assert age == 120
    assert "古すぎます" in why


def test_期限切れでも入替判定には前回分を読む(tmp_cache):
    """入替の比較対象としてなら古くても使う（採用はしない）。"""
    write_cache(tmp_cache, "F", days_old=200, count=2)
    assert C._previous_tickers("F") == ["T0", "T1"]


def test_キャッシュが無ければNone(tmp_cache):
    cached, age, why = C._load_cache("NOPE")
    assert cached is None and age is None and why is None


def test_壊れたキャッシュは理由つきで拒否(tmp_cache):
    (tmp_cache / "BAD.json").write_text("{壊れています", encoding="utf-8")
    cached, _, why = C._load_cache("BAD")
    assert cached is None
    assert "壊れています" in why


# --------------------------------------------------------------------------
# 週次ヘルスチェックの連続失敗検出
# --------------------------------------------------------------------------

def hist(*weeks) -> dict:
    return {"weeks": list(weeks)}


def week(name: str, **sources) -> dict:
    return {"week": name,
            "sources": {k: {"ok": v[0], "count": v[1], "priority": v[2]}
                        for k, v in sources.items()}}


def test_連続失敗を数える():
    h = hist(
        week("2026-30", VTI_a=(True, 3600, 1)),
        week("2026-31", VTI_a=(False, 0, 1)),
        week("2026-32", VTI_a=(False, 0, 1)),
    )
    assert health.degraded_streaks(h) == {"VTI_a": 2}


def test_成功したら連続はリセットされる():
    h = hist(
        week("2026-30", VTI_a=(False, 0, 1)),
        week("2026-31", VTI_a=(False, 0, 1)),
        week("2026-32", VTI_a=(True, 3600, 1)),
    )
    assert health.degraded_streaks(h) == {}


def test_直近が失敗なら1週から数える():
    h = hist(
        week("2026-31", VTI_a=(True, 3600, 1)),
        week("2026-32", VTI_a=(False, 0, 1)),
    )
    assert health.degraded_streaks(h) == {"VTI_a": 1}


def test_priority1以外は連続失敗の対象外():
    h = hist(
        week("2026-31", VTI_b=(False, 0, 2)),
        week("2026-32", VTI_b=(False, 0, 2)),
    )
    assert health.degraded_streaks(h) == {}


def test_履歴が空なら何も出ない():
    assert health.degraded_streaks({"weeks": []}) == {}


def test_前週の件数を引ける():
    h = hist(week("2026-31", VTI_a=(True, 3600, 1)),
             week("2026-32", VTI_a=(True, 3610, 1)))
    prev = health.previous_counts(h, "2026-32")
    assert prev["VTI_a"]["count"] == 3600


def test_履歴の保存は指定週数だけ残す(tmp_path, monkeypatch):
    monkeypatch.setattr(health, "history_path",
                        lambda: tmp_path / "hist.json")
    h = {"weeks": [{"week": f"2026-{i:02d}", "sources": {}}
                   for i in range(1, 20)]}
    h = health.save_history(h, [], "2026-20", keep=5)
    assert len(h["weeks"]) == 5
    assert h["weeks"][-1]["week"] == "2026-20"


def test_同じ週を二度記録しても重複しない(tmp_path, monkeypatch):
    monkeypatch.setattr(health, "history_path",
                        lambda: tmp_path / "hist.json")
    h = health.save_history({"weeks": []}, [], "2026-32")
    h = health.save_history(h, [], "2026-32")
    assert [w["week"] for w in h["weeks"]] == ["2026-32"]


# --------------------------------------------------------------------------
# レポート
# --------------------------------------------------------------------------

def probe(fund="VTI", src="vanguard_api", priority=1, ok=True, count=3600):
    return health.ProbeResult(
        fund_id=fund, fund_name=f"{fund} テスト", source_id=src,
        kind="json", priority=priority, ok=ok, count=count, elapsed_ms=120,
        error=None if ok else "HTTP 403")


def test_レポートに成功数が出る():
    md = health.to_markdown([probe(), probe(src="manual", priority=99,
                                            ok=False)], "テスト")
    assert "1/2 source が成功" in md


def test_priority1の失敗が警告として出る():
    results = [probe(ok=False), probe(src="manual", priority=99, count=500)]
    md = health.to_markdown(results, "テスト")
    assert "priority 1 が失敗している" in md


def test_連続失敗は要対応として出る():
    results = [probe(ok=False)]
    md = health.to_markdown(results, "テスト",
                            degraded_streaks={"VTI/vanguard_api": 3})
    assert "要対応" in md
    assert "3週連続" in md


def test_priority1が成功していれば警告は出ない():
    md = health.to_markdown([probe()], "テスト")
    assert "priority 1 が失敗している" not in md
