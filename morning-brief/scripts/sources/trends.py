# -*- coding: utf-8 -*-
"""レイヤ3拡張：話題性シグナル（X/InstagramのAPIを使わない無料の代替）。

- Google Trends 日次トレンドRSS（geo=JP / geo=US。キー不要）
- Reddit 投資系サブレディットの公開RSS（top/day。JSON APIが403でも通ることがある）
- Hacker News（hnrss.org frontpage, points>=200。テック・AI系の注目度）

出力は ticker -> 熱量(0..1)。ここも「何が話題か」の検出にだけ使い、
画像に載せる数字はレイヤ1・2から取る。1つでも生きていれば動き、
全滅なら {} を返す（呼び出し側は他のシグナルだけで続行）。
リクエスト間に1秒のスリープを入れ、User-Agentを明示する。

単体実行: python scripts/sources/trends.py
"""
from __future__ import annotations
import time

try:
    from .http_util import get
    from .buzz import TICKER_KEYWORDS
except ImportError:          # 単体実行用
    from http_util import get
    from buzz import TICKER_KEYWORDS

_SOURCES = [
    ("Google Trends JP", "https://trends.google.co.jp/trending/rss?geo=JP", 1.0),
    ("Google Trends US", "https://trends.google.com/trending/rss?geo=US", 1.0),
    ("Reddit r/investing", "https://www.reddit.com/r/investing/top/.rss?t=day", 0.8),
    ("Reddit r/stocks", "https://www.reddit.com/r/stocks/top/.rss?t=day", 0.8),
    ("Reddit r/wallstreetbets", "https://www.reddit.com/r/wallstreetbets/top/.rss?t=day", 0.8),
    ("Hacker News", "https://hnrss.org/frontpage?points=200", 0.6),
]


def fetch_trend_titles() -> list[tuple[str, float]]:
    """各ソースのエントリタイトルを (タイトル, ソース重み) で返す。"""
    out: list[tuple[str, float]] = []
    ok = 0
    for name, url, weight in _SOURCES:
        text = get(url)
        time.sleep(1.0)   # 連続リクエストを避ける（規約配慮）
        if not text:
            continue
        try:
            import feedparser
            fp = feedparser.parse(text)
            titles = [(e.get("title") or "").strip() for e in fp.entries[:25]]
            titles = [t for t in titles if t]
            if titles:
                ok += 1
                out += [(t, weight) for t in titles]
        except Exception:
            continue
    print(f"[ok] トレンドソース: {ok}/{len(_SOURCES)} 生存・{len(out)} 見出し")
    return out


def trend_heat(titles: list[tuple[str, float]] | None = None) -> dict[str, float]:
    """トレンド見出しを ticker -> 熱量(0..1) に正規化。"""
    if titles is None:
        titles = fetch_trend_titles()
    heat: dict[str, float] = {}
    for title, weight in titles:
        low = title.lower()
        for tk, keys in TICKER_KEYWORDS.items():
            if any(k in low for k in keys):
                heat[tk] = heat.get(tk, 0.0) + weight
    if not heat:
        return {}
    mx = max(heat.values())
    return {tk: v / mx for tk, v in heat.items()} if mx > 0 else {}


if __name__ == "__main__":
    import json
    print(json.dumps(trend_heat(), ensure_ascii=False, indent=1))
