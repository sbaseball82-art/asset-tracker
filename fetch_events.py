# -*- coding: utf-8 -*-
"""
fetch_events.py
===============
その日の米国株式市場の動き3件を用意して events.json に保存する。

3件は必ず「別カテゴリ」から1つずつ選び（指数 / マクロ・金利 / 個別・テーマ）、
重複・古いニュースを除外し、日本語の見出しに整える。

モード(config.EVENT_MODE):
  "semi"   : RSSの英語見出しを取得 → 重複/古い記事を除外 → 3カテゴリから選抜
             → 無料の機械翻訳で日本語化（detailは空）。
             events_manual.json があればそちらを優先（手動上書き可）。
  "auto"   : ANTHROPIC_API_KEY があればAIで「見出し+解説+方向」を日本語生成（高品質）。
  "manual" : events_manual.json をそのまま使う。

events.json 形式:
  {"date":"...", "events":[{"title","detail","dir","cat"}, x3]}
    dir: "up" / "down" / "flat"  （スライドで ▲▼ 表示に使用）
    cat: "指数" / "マクロ" / "個別"
"""

import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

from config import EVENT_MODE

JST = timezone(timedelta(hours=9))
OUT = Path("events.json")
MANUAL = Path("events_manual.json")
UA = "Mozilla/5.0 (compatible; asset-tracker/1.0)"

RSS_FEEDS = [
    "https://feeds.marketwatch.com/marketwatch/marketpulse/",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",  # markets
    "https://feeds.marketwatch.com/marketwatch/topstories/",
]

# ---- カテゴリ判定キーワード（英語見出し向け）----
CAT_KEYWORDS = {
    "指数": ["s&p", "s & p", "nasdaq", "dow", "stocks", "wall street", "wall-street",
            "index", "indexes", "indices", "equities", "shares", "rally", "selloff",
            "sell-off", "record", "all-time", "close", "closing", "futures", "benchmark"],
    "マクロ": ["fed", "federal reserve", "powell", "rate", "rates", "yield", "yields",
             "treasury", "inflation", "cpi", "ppi", "pce", "jobs", "payroll", "payrolls",
             "jobless", "unemployment", "gdp", "economy", "economic", "retail sales",
             "tariff", "tariffs", "consumer", "spending"],
    "個別": ["nvidia", "apple", "tesla", "microsoft", "amazon", "alphabet", "google",
            "meta", "netflix", "broadcom", "intel", "boeing", "ai", "chip", "chips",
            "semiconductor", "oil", "crude", "earnings", "bitcoin", "crypto", "energy"],
}
CAT_PRIORITY = ["指数", "マクロ", "個別"]

UP_WORDS = ["rise", "rises", "rising", "gain", "gains", "jump", "jumps", "surge", "surges",
            "rally", "rallies", "higher", "soar", "soars", "climb", "climbs", "advance",
            "record high", "all-time high", "up ", "rebound", "boost", "lifts", "lift"]
DOWN_WORDS = ["fall", "falls", "falling", "drop", "drops", "slump", "slumps", "sink", "sinks",
              "lower", "sell-off", "selloff", "plunge", "plunges", "tumble", "tumbles",
              "slide", "slides", "down ", "decline", "declines", "loss", "losses", "sags"]

MONTHS = ["january", "february", "march", "april", "may", "june",
          "july", "august", "september", "october", "november", "december"]


def fetch_headlines(limit: int = 25) -> list[str]:
    heads: list[str] = []
    for url in RSS_FEEDS:
        try:
            res = requests.get(url, headers={"User-Agent": UA}, timeout=15)
            res.raise_for_status()
            root = ET.fromstring(res.content)
            for item in root.iter("item"):
                t = item.findtext("title")
                if t:
                    t = re.sub(r"\s+", " ", t).strip()
                    if t and t not in heads:
                        heads.append(t)
        except Exception as e:
            print(f"  ⚠️ RSS取得失敗 {url}: {e}")
        if len(heads) >= limit:
            break
    return heads[:limit]


def is_stale(title: str, now: datetime) -> bool:
    """当月・前月以外の月名を含む見出しは「古い/季節外れ」とみなして除外。"""
    low = title.lower()
    cur = now.month
    prev = 12 if cur == 1 else cur - 1
    allowed = {MONTHS[cur - 1], MONTHS[prev - 1]}
    for m in MONTHS:
        if re.search(rf"\b{m}\b", low) and m not in allowed:
            return True
    return False


def categorize(title: str) -> str:
    low = title.lower()
    scores = {c: sum(1 for k in kws if k in low) for c, kws in CAT_KEYWORDS.items()}
    best = max(CAT_PRIORITY, key=lambda c: (scores[c], -CAT_PRIORITY.index(c)))
    return best if scores[best] > 0 else "指数"


def detect_dir(title: str) -> str:
    low = title.lower()
    up = any(w in low for w in UP_WORDS)
    down = any(w in low for w in DOWN_WORDS)
    if up and not down:
        return "up"
    if down and not up:
        return "down"
    return "flat"


def _tokens(title: str) -> set:
    return set(re.findall(r"[a-z]+", title.lower())) - {
        "the", "a", "an", "to", "of", "in", "on", "as", "is", "are", "for", "and", "at"}


def is_similar(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / min(len(ta), len(tb))
    return overlap >= 0.5  # 半分以上の語が被れば重複扱い（例: jobless claims の重複）


def select_three(headlines: list, now: datetime) -> list:
    """重複・古い記事を除外し、3カテゴリから1件ずつ選ぶ。"""
    fresh = [h for h in headlines if not is_stale(h, now)]
    picked = []
    used_titles = []

    def try_add(h: str, cat: str) -> bool:
        if any(is_similar(h, u) for u in used_titles):
            return False
        picked.append({"title_en": h, "cat": cat, "dir": detect_dir(h)})
        used_titles.append(h)
        return True

    # 1) 各カテゴリから1件ずつ
    for cat in CAT_PRIORITY:
        for h in fresh:
            if categorize(h) == cat and try_add(h, cat):
                break
    # 2) 足りなければ残りから重複しないものを補充
    for h in fresh:
        if len(picked) >= 3:
            break
        try_add(h, categorize(h))

    return picked[:3]


def translate_ja(text: str) -> str:
    """無料の機械翻訳で日本語化。失敗時は原文を返す。"""
    try:
        from deep_translator import GoogleTranslator
        out = GoogleTranslator(source="auto", target="ja").translate(text)
        return out or text
    except Exception as e:
        print(f"  ⚠️ 翻訳失敗（原文のまま）: {e}")
        return text


def mode_semi(now: datetime) -> list:
    heads = fetch_headlines(25)
    if not heads:
        return [{"title": "(見出し取得失敗 — 手動入力してください)", "detail": "",
                 "dir": "flat", "cat": "指数"}]
    chosen = select_three(heads, now)
    events = []
    for c in chosen:
        events.append({
            "title": translate_ja(c["title_en"]),
            "detail": "",
            "dir": c["dir"],
            "cat": c["cat"],
        })
    return events


def mode_auto(now: datetime):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("  ⚠️ ANTHROPIC_API_KEY未設定 → semiにフォールバック")
        return None
    heads = fetch_headlines(15)
    if not heads:
        return None
    today = now.strftime("%Y年%m月%d日")
    prompt = (
        f"あなたは個人投資家向けに米国株式市場を解説するアナリストです。本日は{today}。\n"
        "以下は本日の米国市場ニュース見出し（英語）です。ここから重要な3件を選び、"
        "必ず『指数』『マクロ（金利・経済指標）』『個別・テーマ』の3カテゴリから1件ずつ選んでください。\n"
        "・内容が重複する見出しは選ばない\n"
        "・当日と無関係な古い月のデータ（数か月前の指標など）は選ばない\n"
        "各件について次のJSONオブジェクトを作成:\n"
        '  {"title":"20字以内の日本語見出し","detail":"60字程度の平易な日本語解説",'
        '"dir":"up|down|flat（相場/その指標が上向きか下向きか）","cat":"指数|マクロ|個別"}\n'
        "投資助言や売買推奨はせず、事実と背景の説明に徹してください。\n"
        "出力はJSON配列のみ。前置き・コードフェンス禁止。\n\n"
        "見出し:\n" + "\n".join(f"- {h}" for h in heads)
    )
    try:
        res = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={
                # 安価なHaikuで十分。品質を上げたい場合は claude-sonnet-4-6 に変更
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        res.raise_for_status()
        text = "".join(b.get("text", "") for b in res.json().get("content", [])
                       if b.get("type") == "text")
        text = re.sub(r"```json|```", "", text).strip()
        events = json.loads(text)
        out = []
        for e in events[:3]:
            out.append({
                "title": e.get("title", "—"),
                "detail": e.get("detail", ""),
                "dir": e.get("dir", "flat"),
                "cat": e.get("cat", ""),
            })
        return out or None
    except Exception as e:
        print(f"  ⚠️ AI生成失敗: {e} → semiにフォールバック")
        return None


def main():
    now = datetime.now(JST)
    print(f"[events] モード={EVENT_MODE}")

    if MANUAL.exists():
        try:
            m = json.load(open(MANUAL, encoding="utf-8"))
            evs = m.get("events", [])
            if evs and any(e.get("detail") for e in evs):
                print("  ✅ events_manual.json を使用")
                _save(now, evs[:3])
                return
        except Exception as e:
            print(f"  ⚠️ events_manual.json 読込失敗: {e}")

    if EVENT_MODE == "manual":
        events = [{"title": "(events_manual.jsonを編集してください)", "detail": "",
                   "dir": "flat", "cat": ""}]
    elif EVENT_MODE == "auto":
        events = mode_auto(now) or mode_semi(now)
    else:
        events = mode_semi(now)

    _save(now, events)


def _save(now, events):
    for e in events:
        e.setdefault("dir", "flat")
        e.setdefault("cat", "")
        e.setdefault("detail", "")
    while len(events) < 3:
        events.append({"title": "—", "detail": "", "dir": "flat", "cat": ""})
    out = {"date": now.strftime("%Y-%m-%d"), "events": events[:3]}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"💾 {OUT} を保存（{len(out['events'])}件）")
    for e in out["events"]:
        print(f"   • [{e['cat']}/{e['dir']}] {e['title']}")


if __name__ == "__main__":
    main()

