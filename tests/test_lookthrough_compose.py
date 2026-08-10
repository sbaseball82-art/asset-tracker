# -*- coding: utf-8 -*-
"""投稿文の組み立てと、方針チェック（文字数・トーン・免責）のテスト。"""

import pytest

from src.common.textcheck import zenkaku_len
from src.lookthrough.compose import (
    APPROX_TAIL, DISCLAIMER, build_posts, build_reply, man_yen, validate_post,
)

LIMITS = (100, 150, 165)


@pytest.fixture
def metrics():
    return {
        "total_jpy": 33_175_799,
        "top10_pct": 46.2,
        "multi_fund_count_top10": 7,
        "multi_fund_pct_top10": 38.4,
        "multi_fund_count_all": 23,
        "multi_fund_pct_all": 51.8,
        "fund_count": 11,
        "top1": {"ticker": "NVDA", "pct": 6.31,
                 "via_text": "VTI経由 約119万円 + QQQ経由 約17万円"},
        "rank_note": "前月と比べるとAVGOが3つ上がって4位になっていました。",
        "dup_examples": ["AVGOはVTIとVYMの重なりで、合わせて4.1%"],
        "proxy_note": "投信は構成銘柄が非公開のため、連動対象ETFの構成で代用しています。",
        "manual_note": "イノベーションAIは構成銘柄を取得できていないため、"
                       "この集計には入れていません（要手動確認）。",
        "coverage_note": None,
    }


# --------------------------------------------------------------------------
# 文字数（受け入れ条件）
# --------------------------------------------------------------------------

def test_各投稿文が全角の上限に収まる(metrics):
    posts = build_posts(metrics, limits=LIMITS)
    for limit, text in posts.items():
        assert zenkaku_len(text) <= limit, (
            f"post_{limit} が {zenkaku_len(text):.1f} 全角で超過:\n{text}")


def test_上限が大きいほど中身が増える(metrics):
    posts = build_posts(metrics, limits=LIMITS)
    assert zenkaku_len(posts[100]) <= zenkaku_len(posts[150])
    assert zenkaku_len(posts[150]) <= zenkaku_len(posts[165])


def test_上限ぎりぎりでも見出しと免責は必ず残る(metrics):
    text = build_posts(metrics, limits=(60,))[60]
    assert DISCLAIMER in text
    assert len([ln for ln in text.split("\n") if ln.strip()]) >= 2


# --------------------------------------------------------------------------
# 方針（トーン・免責・ハッシュタグ）
# --------------------------------------------------------------------------

def test_生成された投稿文が方針チェックを通る(metrics):
    posts = build_posts(metrics, limits=LIMITS)
    for limit, text in posts.items():
        assert validate_post(text, limit=limit) == [], f"post_{limit}: {text}"


def test_返信文も方針チェックを通る(metrics):
    """返信文はハッシュタグを付けない方針なので require_hashtags=False で見る。"""
    reply = build_reply(metrics)
    assert DISCLAIMER in reply
    assert validate_post(reply, require_hashtags=False) == []
    assert "#" not in reply


def test_1行目と2行目だけで意味が通る(metrics):
    posts = build_posts(metrics, limits=LIMITS)
    for text in posts.values():
        lines = [ln for ln in text.split("\n") if ln.strip()]
        head = lines[0] + lines[1]
        # 総額・上位10社の比率という主題が冒頭2行に入っていること
        assert "万円" in head
        assert "上位10社" in head
        assert "46.2%" in head


def ok_text(first: str = "1行目です。", tags: str = "#資産推移 #米国株") -> str:
    """方針を満たす最小の投稿文。1か所だけ崩して検査するために使う。"""
    return (f"{first}\n2行目です。\n\n{APPROX_TAIL}\n{DISCLAIMER}\n{tags}")


def test_最小構成の投稿文は合格する():
    assert validate_post(ok_text()) == []


def test_断定表現を検出する():
    assert any("必ず" in p for p in validate_post(ok_text("これは必ず上がります。")))


def test_予測表現を検出する():
    assert any("底打ち" in p
               for p in validate_post(ok_text("底打ちしたように見えます。")))


def test_免責文が無ければ不合格():
    text = ok_text().replace(DISCLAIMER, "")
    assert any("免責" in p for p in validate_post(text))


def test_概算である旨が無ければ不合格():
    text = ok_text().replace(APPROX_TAIL, "")
    assert any("概算" in p for p in validate_post(text))


def test_ハッシュタグは2から3個():
    assert any("ハッシュタグ" in p for p in validate_post(ok_text(tags="#資産推移")))
    assert any("ハッシュタグ" in p
               for p in validate_post(ok_text(tags="#a #b #c #d")))
    assert validate_post(ok_text(tags="#資産推移 #米国株 #ETF")) == []


def test_ハッシュタグが本文途中にあると不合格():
    text = ok_text(first="1行目 #米国株 です。", tags="#資産推移 #ETF")
    assert any("ハッシュタグ" in p for p in validate_post(text))


# --------------------------------------------------------------------------
# メモリ／DRAM は必ず「シクリカル」を添える
# --------------------------------------------------------------------------

def test_メモリに触れたらシクリカルが補われる(metrics):
    m = dict(metrics)
    m["rank_note"] = "DRAM関連の比率が上がっていました。"
    posts = build_posts(m, limits=(165,))
    text = posts[165]
    if "DRAM" in text:
        assert "シクリカル" in text


def test_シクリカルが無いメモリ言及を検出する():
    assert any("シクリカル" in p
               for p in validate_post(ok_text("DRAMの比率が上がりました。")))


def test_シクリカルがあれば通る():
    text = ok_text("DRAMの比率が上がりました。メモリはシクリカルな業種だと思います。")
    assert validate_post(text) == []


# --------------------------------------------------------------------------
# 補助
# --------------------------------------------------------------------------

@pytest.mark.parametrize("jpy,want", [
    (33_175_799, "約3,318万円"),
    (1_000_000, "約100万円"),
])
def test_万円表記(jpy, want):
    assert man_yen(jpy) == want


def test_概算であることが本文に入る(metrics):
    posts = build_posts(metrics, limits=(165,))
    assert "概算" in posts[165] or "概算" in build_reply(metrics)
