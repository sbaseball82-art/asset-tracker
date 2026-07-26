# -*- coding: utf-8 -*-
"""レイヤ3：報道・話題性（見出し候補と「バズ」検出）。

- Google News RSS（日本語＋英語・キー不要）
- Yahoo Finance 銘柄別RSS
- Finnhub /news・/company-news（FINNHUB_API_KEY があるときのみ）
- Reddit JSON API（r/stocks, r/investing, r/wallstreetbets。キー不要・UA必須）
- Hacker News Algolia API（AI・半導体・データセンター）

このレイヤは「何が話題か」（媒体一致数・SNS熱量）を知るためだけに使う。
画像に載せる数字は必ずレイヤ1・2から取る。本文の長文引用はしない。

単体実行: python scripts/sources/buzz.py NVDA MU
"""
from __future__ import annotations
import os
import re

try:
    from .http_util import get
except ImportError:
    from http_util import get

# ティッカー ↔ 見出しキーワード（日英）。媒体一致数の銘柄ひも付けに使う
TICKER_KEYWORDS: dict[str, tuple[str, ...]] = {
    "NVDA": ("nvidia", "エヌビディア"),
    "MSFT": ("microsoft", "マイクロソフト"),
    "AAPL": ("apple", "アップル"),
    "GOOGL": ("google", "alphabet", "グーグル", "アルファベット"),
    "AMZN": ("amazon", "アマゾン"),
    "META": ("meta platforms", "meta ", "メタ"),
    "TSLA": ("tesla", "テスラ"),
    "AVGO": ("broadcom", "ブロードコム"),
    "MU": ("micron", "マイクロン", "dram", "hbm", "メモリ半導体", "sk hynix", "ハイニックス"),
    "INTC": ("intel", "インテル"),
    "TSM": ("tsmc", "taiwan semiconductor", "台湾積体"),
    "AMD": ("amd ", " amd", "advanced micro"),
    "^SOX": ("semiconductor", "半導体", "chip stocks"),
    "^TNX": ("treasury yield", "10-year", "米長期金利", "米国債"),
    "JPY=X": ("yen", "円安", "円高", "ドル円", "円相場"),
    "^GSPC": ("s&p 500", "s&p500", "wall street", "米国株"),
    "^IXIC": ("nasdaq", "ナスダック"),
    "^DJI": ("dow", "ダウ"),
    "XLE": ("oil", "crude", "原油", "energy stocks"),
    "XLF": ("bank stocks", "銀行株", "金融株"),
    "XLU": ("utilities", "電力株", "公益株"),
}

_GN_JA = "https://news.google.com/rss/search?q={q}&hl=ja&gl=JP&ceid=JP:ja"
_GN_EN = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
_YF_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={s}&region=US&lang=en-US"


_CJK_RE = re.compile(r"[ぁ-んァ-ヶ一-龠]")


def _parse_feed(text: str, source_hint: str) -> list[dict]:
    if not text:
        return []
    try:
        import feedparser
        fp = feedparser.parse(text)
        out = []
        for e in fp.entries[:25]:
            title = re.sub(r"\s+", " ", e.get("title") or "").strip()
            if not title:
                continue
            # Google News の「見出し - 媒体名」から独立媒体名を拾う
            m = re.match(r"^(.*\S)\s+-\s+([^-]{2,45})$", title)
            src = m.group(2).strip() if m else source_hint
            body = m.group(1) if m else title
            out.append({"title": body, "outlet": src, "url": e.get("link", ""),
                        "lang": "ja" if _CJK_RE.search(body) else "en"})
        return out
    except Exception:
        return []


def fetch_headlines(queries_ja: list[str], queries_en: list[str],
                    yahoo_tickers: list[str]) -> list[dict]:
    """Google News（日英）＋ Yahoo Finance RSS ＋ Finnhub の見出しを集める。"""
    items: list[dict] = []
    from urllib.parse import quote
    for q in queries_ja:
        items += _parse_feed(get(_GN_JA.format(q=quote(f"{q} when:1d"))), "Google News")
    for q in queries_en:
        items += _parse_feed(get(_GN_EN.format(q=quote(f"{q} when:1d"))), "Google News")
    for tk in yahoo_tickers[:12]:
        items += _parse_feed(get(_YF_RSS.format(s=tk)), "Yahoo Finance")

    key = os.environ.get("FINNHUB_API_KEY")
    if key:
        data = get("https://finnhub.io/api/v1/news",
                   params={"category": "general", "token": key}, as_json=True)
        for d in (data or [])[:30]:
            if d.get("headline"):
                items.append({"title": d["headline"], "outlet": d.get("source", "Finnhub"),
                              "url": d.get("url", "")})
    return items


def fetch_sns_heat() -> dict[str, float]:
    """Reddit hot/rising ＋ HN の話題を ticker -> 熱量(0..1) に正規化して返す。"""
    posts: list[dict] = []
    for sub in ("stocks", "investing", "wallstreetbets"):
        for listing in ("hot", "rising"):
            data = get(f"https://www.reddit.com/r/{sub}/{listing}.json",
                       params={"limit": 25}, as_json=True)
            try:
                for c in data["data"]["children"]:
                    d = c["data"]
                    posts.append({"title": d.get("title", ""),
                                  "heat": d.get("score", 0) + 2 * d.get("num_comments", 0)})
            except Exception:
                continue
    for q in ("AI datacenter", "semiconductor", "HBM memory"):
        data = get("https://hn.algolia.com/api/v1/search",
                   params={"query": q, "tags": "story",
                           "numericFilters": "created_at_i>0"}, as_json=True)
        try:
            for h in (data or {}).get("hits", [])[:15]:
                posts.append({"title": h.get("title", ""),
                              "heat": h.get("points", 0) + 2 * h.get("num_comments", 0)})
        except Exception:
            continue

    heat: dict[str, float] = {}
    for p in posts:
        low = p["title"].lower()
        for tk, keys in TICKER_KEYWORDS.items():
            if any(k in low for k in keys):
                heat[tk] = heat.get(tk, 0.0) + p["heat"]
    if not heat:
        return {}
    mx = max(heat.values())
    return {tk: v / mx for tk, v in heat.items()} if mx > 0 else {}


def match_headlines(items: list[dict]) -> dict[str, list[dict]]:
    """見出しをティッカーにひも付ける。"""
    out: dict[str, list[dict]] = {}
    for it in items:
        low = it["title"].lower()
        for tk, keys in TICKER_KEYWORDS.items():
            if any(k in low for k in keys):
                out.setdefault(tk, []).append(it)
    return out


def fetch_buzz(focus_tickers: list[str]) -> dict:
    """レイヤ3一括取得。{"headlines": {tk: [..]}, "sns": {tk: 0..1}}"""
    queries_ja = ["米国株 市場", "半導体 株", "FRB 金利"]
    queries_en = ["stock market", "semiconductor stocks", "Fed rates"]
    items = fetch_headlines(queries_ja, queries_en, focus_tickers)
    return {"headlines": match_headlines(items), "sns": fetch_sns_heat()}


if __name__ == "__main__":
    import json, sys
    print(json.dumps(fetch_buzz(sys.argv[1:] or ["NVDA", "MU"]),
                     ensure_ascii=False, indent=1))
