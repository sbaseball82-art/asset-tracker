# -*- coding: utf-8 -*-
"""複数RSSを横断して「話題度」の高い株式・マーケットニュースを抽出する。

「最も閲覧数の多いニュース」を直接返す無料APIは存在しないため、
- 複数の大手メディアが同時に報じている度合い（媒体横断の出現数）
- 新しさ（発行からの経過時間）
- 相場ホットワード（半導体・AI・最高値・急落 等）
でスコア化し、上位を「今日の話題ニュース」として返す。

全フィード取得失敗時は None を返し、呼び出し側でエバーグリーン
（普遍ネタ）カードに自動フォールバックする。
"""
from __future__ import annotations
import re, time, datetime as dt
import feedparser

# 株式・マーケット系の公開RSS（実環境=GitHub Actionsで到達可能な想定。
# 将来止まるフィードがあっても、生きているものだけで動く設計）
FEEDS = [
    ("Yahoo!ニュース 経済",      "https://news.yahoo.co.jp/rss/topics/business.xml"),
    ("NHK 経済",               "https://www3.nhk.or.jp/rss/news/cat5.xml"),
    ("ロイター ビジネス(GN)",    "https://news.google.com/rss/search?q=%E6%A0%AA%E5%BC%8F%20when:1d&hl=ja&gl=JP&ceid=JP:ja"),
    ("Google News 米国株",      "https://news.google.com/rss/search?q=%E7%B1%B3%E5%9B%BD%E6%A0%AA%20when:1d&hl=ja&gl=JP&ceid=JP:ja"),
    ("Google News 日経平均",    "https://news.google.com/rss/search?q=%E6%97%A5%E7%B5%8C%E5%B9%B3%E5%9D%87%20when:1d&hl=ja&gl=JP&ceid=JP:ja"),
    ("Google News 半導体",      "https://news.google.com/rss/search?q=%E5%8D%8A%E5%B0%8E%E4%BD%93%20%E6%A0%AA%20when:1d&hl=ja&gl=JP&ceid=JP:ja"),
]

HOT_WORDS = {"半導体":3,"AI":3,"エヌビディア":3,"最高値":4,"急落":4,"急騰":4,"暴落":5,
             "日銀":2,"FRB":2,"利上げ":3,"利下げ":3,"円安":3,"円高":3,"決算":2,
             "メモリ":3,"日経平均":2,"S&P":2,"ナスダック":2,"ダウ":2,"上場":2,"IPO":2}

MARKET_HINT = ("株","相場","日経","ダウ","ナスダック","S&P","半導体","円","ドル","金利",
               "日銀","FRB","決算","投資","市場","指数","上場","債券","AI","エヌビディア","メモリ")

_token_re = re.compile(r"[ァ-ヶー]{2,}|[一-龠]{2,}|[A-Za-z0-9&+]{2,}")

def _tokens(title: str) -> set:
    toks = set()
    for run in _token_re.findall(title):
        toks.add(run)
        # 漢字・カタカナの長い連なりはバイグラムにも分解して照合精度を上げる
        if len(run) >= 3 and not re.match(r"^[A-Za-z0-9&+]+$", run):
            for i in range(len(run) - 1):
                toks.add(run[i:i+2])
    return toks

def _is_market_news(title: str) -> bool:
    return any(k in title for k in MARKET_HINT)

def _age_hours(entry) -> float:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return max(0.0, (time.time() - time.mktime(t)) / 3600.0)
    return 24.0

def fetch_top_stories(n: int = 5, local_files: list[str] | None = None):
    """上位n件の話題ニュースを返す。全滅なら None。"""
    sources = local_files if local_files else [u for _, u in FEEDS]
    names = [f"local{i}" for i in range(len(sources))] if local_files else [nm for nm, _ in FEEDS]

    entries = []
    ok_feeds = 0
    for name, src in zip(names, sources):
        try:
            fp = feedparser.parse(src)
            if fp.entries:
                ok_feeds += 1
            for e in fp.entries[:30]:
                title = re.sub(r"\s+", " ", (e.get("title") or "")).strip()
                # Google Newsは末尾に「 - 媒体名」が付くので除去
                title = re.sub(r"\s*-\s*[^-]{2,25}$", "", title)
                if not title or not _is_market_news(title):
                    continue
                entries.append({
                    "title": title, "source": name,
                    "link": e.get("link", ""), "age_h": _age_hours(e),
                    "tokens": _tokens(title),
                })
        except Exception:
            continue
    if ok_feeds == 0 or not entries:
        return None

    # 類似タイトルをクラスタリング（トークンのJaccard係数）
    clusters: list[dict] = []
    for e in entries:
        placed = False
        for c in clusters:
            inter = len(e["tokens"] & c["tokens"])
            base = min(len(e["tokens"]), len(c["tokens"])) or 1
            if inter >= 3 and inter / base >= 0.35:
                c["items"].append(e)
                c["tokens"] |= e["tokens"]
                c["sources"].add(e["source"])
                placed = True
                break
        if not placed:
            clusters.append({"items":[e], "tokens":set(e["tokens"]), "sources":{e["source"]}})

    # スコア：媒体横断数×10 ＋ 新しさ ＋ ホットワード
    scored = []
    for c in clusters:
        rep = min(c["items"], key=lambda x: x["age_h"])   # 最新のタイトルを代表に
        hot = sum(w for k, w in HOT_WORDS.items() if k in rep["title"])
        recency = max(0.0, 24.0 - rep["age_h"]) / 3.0
        score = len(c["sources"]) * 10 + hot + recency
        scored.append({
            "title": rep["title"], "link": rep["link"],
            "n_sources": len(c["sources"]), "score": round(score, 1),
        })
    scored.sort(key=lambda x: -x["score"])

    # タイトルがほぼ同じものを除いて上位n件
    out, seen = [], []
    for s in scored:
        tk = _tokens(s["title"])
        if any(len(tk & p) / (min(len(tk), len(p)) or 1) > 0.55 for p in seen):
            continue
        out.append(s); seen.append(tk)
        if len(out) >= n:
            break
    return out

if __name__ == "__main__":
    import sys, json
    local = sys.argv[1:] or None
    top = fetch_top_stories(5, local)
    print(json.dumps(top, ensure_ascii=False, indent=1) if top else "FETCH FAILED (fallback expected)")
