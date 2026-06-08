# -*- coding: utf-8 -*-
"""
fetch_events.py
===============
その日の米国株式市場イベント3件を用意して events.json に保存する。

モード(config.EVENT_MODE):
  "semi"   : ニュース見出しをRSSから自動取得 → 解説欄は空で出力。
             events_manual.json があればそちらを優先(手動で上書き可能)。
  "auto"   : ANTHROPIC_API_KEY があればAIで見出し+解説を自動生成。
  "manual" : events_manual.json をそのまま使う。

events.json 形式:
  {"date": "...", "events": [{"title": "...", "detail": "..."}, x3]}
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

# 米国市況の代表的なニュースRSS(無料・登録不要)
RSS_FEEDS = [
    "https://feeds.marketwatch.com/marketwatch/marketpulse/",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",  # markets
]


def fetch_headlines(limit: int = 6) -> list[str]:
    headlines = []
    for url in RSS_FEEDS:
        try:
            res = requests.get(url, headers={"User-Agent": UA}, timeout=15)
            res.raise_for_status()
            root = ET.fromstring(res.content)
            for item in root.iter("item"):
                t = item.findtext("title")
                if t:
                    t = re.sub(r"\s+", " ", t).strip()
                    if t and t not in headlines:
                        headlines.append(t)
                if len(headlines) >= limit:
                    break
        except Exception as e:
            print(f"  ⚠️ RSS取得失敗 {url}: {e}")
        if len(headlines) >= limit:
            break
    return headlines[:limit]


def mode_semi() -> list[dict]:
    """見出しだけ自動取得。解説は手動で events_manual.json に書く想定。"""
    heads = fetch_headlines(3)
    if not heads:
        heads = ["(見出し取得失敗 — 手動で入力してください)"]
    return [{"title": h, "detail": ""} for h in heads[:3]]


def mode_auto() -> list[dict] | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("  ⚠️ ANTHROPIC_API_KEY未設定 → semiにフォールバック")
        return None
    heads = fetch_headlines(8)
    prompt = (
        "あなたは個人投資家向けに米国株式市場を解説するアナリストです。"
        "以下は本日の米国市場ニュース見出しです。この中から重要な3件を選び、"
        "それぞれ日本語で「title(20字以内の見出し)」と"
        "「detail(60字程度の平易な解説)」を作ってください。"
        "投資助言や売買推奨はせず、事実と背景の説明にとどめてください。"
        "出力はJSON配列のみ。前置き・コードフェンス禁止。\n\n"
        "見出し:\n" + "\n".join(f"- {h}" for h in heads)
    )
    try:
        res = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        res.raise_for_status()
        text = "".join(
            b.get("text", "") for b in res.json().get("content", [])
            if b.get("type") == "text"
        )
        text = re.sub(r"```json|```", "", text).strip()
        events = json.loads(text)
        return [{"title": e["title"], "detail": e["detail"]} for e in events[:3]]
    except Exception as e:
        print(f"  ⚠️ AI生成失敗: {e} → semiにフォールバック")
        return None


def main():
    now = datetime.now(JST)
    print(f"[events] モード={EVENT_MODE}")

    # manual優先(存在し中身があれば常に尊重)
    if MANUAL.exists():
        try:
            m = json.load(open(MANUAL, encoding="utf-8"))
            evs = m.get("events", [])
            if evs and any(e.get("detail") for e in evs):
                print("  ✅ events_manual.json を使用")
                events = evs[:3]
                _save(now, events)
                return
        except Exception as e:
            print(f"  ⚠️ events_manual.json 読込失敗: {e}")

    if EVENT_MODE == "manual":
        events = [{"title": "(events_manual.jsonを編集してください)", "detail": ""}]
    elif EVENT_MODE == "auto":
        events = mode_auto() or mode_semi()
    else:
        events = mode_semi()

    _save(now, events)


def _save(now, events):
    while len(events) < 3:
        events.append({"title": "—", "detail": ""})
    out = {"date": now.strftime("%Y-%m-%d"), "events": events[:3]}
    json.dump(out, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"💾 {OUT} を保存（{len(out['events'])}件）")
    for e in out["events"]:
        print(f"   • {e['title']}")


if __name__ == "__main__":
    main()
