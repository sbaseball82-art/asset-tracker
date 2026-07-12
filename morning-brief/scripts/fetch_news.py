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
# region: "国内"=日本の話題 / "海外"=海外メディアが特集している話題（英語→自動翻訳）
FEEDS = [
    ("Yahoo!ニュース 経済",      "https://news.yahoo.co.jp/rss/topics/business.xml", "国内", "ja"),
    ("NHK 経済",               "https://www3.nhk.or.jp/rss/news/cat5.xml", "国内", "ja"),
    ("Google News 日経平均",    "https://news.google.com/rss/search?q=%E6%97%A5%E7%B5%8C%E5%B9%B3%E5%9D%87%20when:1d&hl=ja&gl=JP&ceid=JP:ja", "国内", "ja"),
    ("Google News 半導体",      "https://news.google.com/rss/search?q=%E5%8D%8A%E5%B0%8E%E4%BD%93%20%E6%A0%AA%20when:1d&hl=ja&gl=JP&ceid=JP:ja", "国内", "ja"),
    ("GN US stock market",     "https://news.google.com/rss/search?q=stock%20market%20when:1d&hl=en-US&gl=US&ceid=US:en", "海外", "en"),
    ("GN US AI/semiconductor", "https://news.google.com/rss/search?q=AI%20OR%20semiconductor%20stocks%20when:1d&hl=en-US&gl=US&ceid=US:en", "海外", "en"),
    ("GN US Fed/economy",      "https://news.google.com/rss/search?q=Fed%20OR%20inflation%20markets%20when:1d&hl=en-US&gl=US&ceid=US:en", "海外", "en"),
    ("CNBC Top News",          "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "海外", "en"),
]

# 英語見出しのマーケット判定用ヒント
MARKET_HINT_EN = ("stock", "market", "nasdaq", "s&p", "dow", "fed", "inflation",
                  "semiconductor", "chip", "nvidia", "ai ", "yield", "treasury",
                  "earnings", "wall street", "rally", "sell-off", "selloff",
                  "memory", "micron", "tech", "ipo", "oil", "dollar", "yen")


def _translate_titles(entries: list[dict]) -> None:
    """英語見出しを日本語へ翻訳（失敗した見出しは英語のまま使う）。"""
    targets = [e for e in entries if e.get("lang") == "en"]
    if not targets:
        return
    try:
        from deep_translator import GoogleTranslator
        tr = GoogleTranslator(source="en", target="ja")
        for e in targets:
            try:
                jp = tr.translate(e["title"][:220])
                if jp and len(jp) >= 8:
                    e["title_en"] = e["title"]
                    e["title"] = jp.strip()
            except Exception:
                continue  # この見出しだけ英語のまま
        print(f"[ok] 海外見出しの翻訳: {sum(1 for e in targets if 'title_en' in e)}/{len(targets)} 件")
    except Exception as ex:
        print(f"[warn] 翻訳モジュール不可（英語のまま続行）: {ex}")

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

# ニュースではないページタイトル（株価情報・掲示板・チャートページ等）の除外パターン
_JUNK_PATTERNS = ("株価・株式情報", "：株価", ":株価", "掲示板", "株価予想",
                  "チャート -", "- チャート", "夜間PTS", "PTS含む", "リアルタイム株価")


def _is_junk_title(title: str) -> bool:
    return any(p in title for p in _JUNK_PATTERNS)


def _is_market_news(title: str, lang: str = "ja") -> bool:
    if _is_junk_title(title):
        return False
    if lang == "en":
        low = title.lower()
        return any(k in low for k in MARKET_HINT_EN)
    return any(k in title for k in MARKET_HINT)

def _age_hours(entry) -> float:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return max(0.0, (time.time() - time.mktime(t)) / 3600.0)
    return 24.0

def _strip_source_suffix(title: str) -> str:
    """Google News等が見出し末尾に付ける「 - 媒体名」を除去する。

    「執筆 - Investing.com - FX | 株式市場 | ファイナンス | 金融ニュース」の
    ように複数段付くことがあるため、本文が短くなりすぎない範囲で繰り返し剥がす。
    """
    while True:
        m = re.match(r"^(.*\S)\s+-\s+[^-]{2,45}$", title)
        if not m or len(m.group(1)) < 10:
            break
        title = m.group(1)
    return re.sub(r"\s*執筆$", "", title).strip()

def fetch_top_stories(n: int = 5, local_files: list[str] | None = None):
    """上位n件の話題ニュースを返す（国内＋海外ミックス）。全滅なら None。"""
    if local_files:
        # ローカルRSSテスト: 偶数番目=国内 / 奇数番目=海外として扱う
        feed_defs = [(f"local{i}", p, ("国内" if i % 2 == 0 else "海外"), "ja")
                     for i, p in enumerate(local_files)]
    else:
        feed_defs = FEEDS

    entries = []
    ok_feeds = 0
    for name, src, region, lang in feed_defs:
        try:
            fp = feedparser.parse(src)
            if fp.entries:
                ok_feeds += 1
            for e in fp.entries[:30]:
                title = re.sub(r"\s+", " ", (e.get("title") or "")).strip()
                title = _strip_source_suffix(title)
                if not title or not _is_market_news(title, lang):
                    continue
                entries.append({
                    "title": title, "source": name, "region": region,
                    "lang": lang, "link": e.get("link", ""),
                    "age_h": _age_hours(e),
                })
        except Exception:
            continue
    if ok_feeds == 0 or not entries:
        return None

    # 英語見出しを日本語化してからトークン化（クラスタリング精度のため）
    _translate_titles(entries)
    for e in entries:
        e["tokens"] = _tokens(e["title"])

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
        regions = {i["region"] for i in c["items"]}
        scored.append({
            "title": rep["title"], "link": rep["link"],
            "region": "海外" if "海外" in regions else "国内",
            "n_sources": len(c["sources"]), "score": round(score, 1),
        })
    scored.sort(key=lambda x: -x["score"])

    # タイトルがほぼ同じものを除いた候補リスト
    cands, seen = [], []
    for s in scored:
        tk = _tokens(s["title"])
        if any(len(tk & p) / (min(len(tk), len(p)) or 1) > 0.55 for p in seen):
            continue
        cands.append(s); seen.append(tk)

    # 国内・海外をミックスして上位n件（可能なら海外・国内それぞれ最低2件を確保）
    out = cands[:n]
    for want in ("海外", "国内"):
        have = sum(1 for s in out if s["region"] == want)
        pool = [s for s in cands if s["region"] == want and s not in out]
        while have < 2 and pool:
            # スコア最下位の「多数派地域」の枠を入れ替える
            other = [s for s in out if s["region"] != want]
            if not other:
                break
            out.remove(other[-1])
            out.append(pool.pop(0))
            have += 1
    out.sort(key=lambda x: -x["score"])
    return out[:n]

if __name__ == "__main__":
    import sys, json
    local = sys.argv[1:] or None
    top = fetch_top_stories(5, local)
    print(json.dumps(top, ensure_ascii=False, indent=1) if top else "FETCH FAILED (fallback expected)")
