# -*- coding: utf-8 -*-
"""投稿文の自動生成（テンプレート方式・ブランド準拠）。

LLMを使わないテンプレート生成のため、文は定型＋見出し要約の組み合わせ。
ANTHROPIC_API_KEY を環境変数に設定すると、Claude APIで自然な文面に
自動アップグレードする（未設定でもテンプレートで必ず動く）。
"""
from __future__ import annotations
import os, re, json, datetime as dt

OPENERS = ["今朝の話題。", "朝のニュースから。", "出勤前にこれだけ。", "今日はこの話題。"]
CLOSERS = [
    "予想は当てず、指数で淡々と継続します。",
    "個社は追わず、束（指数）で持って眺めます。",
    "読めないものは読まない。積立は自動で継続。",
    "上げでも下げでも、やることは同じです。",
]
TAG_MAP = [
    (("半導体","エヌビディア","メモリ","チップ","TSMC","マイクロン","キオクシア"), "#半導体"),
    (("AI","人工知能"), "#AI"),
    (("円安","円高","為替","ドル円","円相場","日銀"), "#ドル円"),
    (("FRB","金利","利上げ","利下げ"), "#FRB"),
    (("決算",), "#決算"),
    (("日経平均","東京株"), "#日本株"),
    (("ダウ","ナスダック","S&P","米国株","NY株"), "#米国株"),
]

def _tags(title: str) -> str:
    tags = [t for keys, t in TAG_MAP if any(k in title for k in keys)]
    if not tags:
        tags = ["#米国株"]
    return " ".join((tags + ["#投資"])[:3])

def _risk_line(title: str) -> str:
    if any(k in title for k in ("メモリ","半導体","エヌビディア")):
        return "半導体・メモリはシクリカル（変動が激しい）なので、"
    if any(k in title for k in ("最高値","急騰")):
        return "高値の後は振れも大きくなりがちなので、"
    if any(k in title for k in ("急落","暴落","安")):
        return "こういう日は狼狽しやすいからこそ、"
    return "この手のニュースの先は読めないので、"

def template_post(i: int, story: dict, date: dt.date) -> str:
    seed = date.toordinal() + i
    opener = OPENERS[seed % len(OPENERS)]
    closer = CLOSERS[seed % len(CLOSERS)]
    where = "海外メディア" if story.get("region") == "海外" else "複数媒体"
    body = f"「{story['title']}」が{where}（{story['n_sources']}媒体）で話題になっています。"
    return f"{opener}{body}\n{_risk_line(story['title'])}{closer}\n{_tags(story['title'])}"

def evergreen_post(idx: int, title: str, body: str) -> str:
    flat = body.replace("\n", "")
    return f"今日の投資の原則：“{title}”。\n{flat}\n自分もこれを守って、今日も淡々と継続します。\n#インデックス投資 #投資"

def maybe_llm_upgrade(posts: list[str], stories) -> list[str]:
    """ANTHROPIC_API_KEYがあればClaudeで文面を自然化（無ければそのまま）。"""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return posts
    try:
        import requests
        upgraded = []
        for p in posts:
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": "claude-sonnet-4-6", "max_tokens": 300,
                      "messages": [{"role": "user", "content":
                        "次のX投稿下書きを、意味を変えずに自然で読みやすい日本語に整えてください。"
                        "断定・煽りは禁止。リスク併記と『指数で淡々と継続』の着地は維持。"
                        "140〜200字・ハッシュタグは末尾のまま。下書き:\n" + p}]},
                timeout=45)
            r.raise_for_status()
            data = r.json()
            txt = "".join(b.get("text","") for b in data.get("content",[]) if b.get("type")=="text").strip()
            upgraded.append(txt or p)
        return upgraded
    except Exception:
        return posts  # 失敗時はテンプレ文で続行（止めない）
