# -*- coding: utf-8 -*-
"""
propose_topics.py
=================
Claude API に保有銘柄リストと既存テーマを渡し、保存版ネタの候補を
自動提案させて data/evergreen_topics.yml に追記する。

- ANTHROPIC_API_KEY が無ければ何もせず正常終了（無料枠運用を壊さない）
- 追記前に find_duplicates で重複チェック（重複候補は捨てる）
- 提案されるのは builder: static のテーマ骨子のみ。
  数値はプレースホルダで出力させ、`要手動入力` を明記する
  （推測の数値をそのまま投稿させない）
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.common.util import REPO_ROOT, load_yaml, save_yaml
from src.evergreen.topics import TOPICS_PATH, find_duplicates

MODEL = "claude-sonnet-5"


def main(count: int = 5) -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("[skip] ANTHROPIC_API_KEY 未設定のためネタ提案をスキップ")
        return 0

    data = load_yaml(TOPICS_PATH, default={"topics": []})
    topics = data.get("topics", [])
    themes = [t.get("theme", "") for t in topics]
    holdings = load_yaml(REPO_ROOT / "data" / "holdings.yml", default={})
    fund_names = [f["name"] for f in holdings.get("funds", [])]

    prompt = f"""あなたは日本の個人投資家のX運用を手伝う編集者です。
保有商品: {", ".join(fund_names)}
既存の保存版テーマ（重複禁止）:
{chr(10).join("- " + t for t in themes)}

保存版コンテンツ（比較表・チェックリスト）の新ネタを{count}本提案してください。
条件:
- 保有銘柄と自分のデータから作れるものに限定
- ブックマークされる「比較表」or「チェックリスト」型
- 数値が必要な箇所は「要手動入力」と書く（推測の数値を入れない）
- 出力はJSON配列のみ: [{{"theme": "...", "format": "table|checklist",
  "headline": "...", "numbers": ["...", "...", "..."], "view": "...",
  "targets": ["...", "..."]}}]"""

    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps({
                "model": MODEL, "max_tokens": 4000,
                "messages": [{"role": "user", "content": prompt}],
            }).encode("utf-8"),
            headers={"x-api-key": api_key,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as res:
            body = json.loads(res.read().decode("utf-8"))
        text = body["content"][0]["text"]
        start, end = text.find("["), text.rfind("]") + 1
        proposals = json.loads(text[start:end])
    except Exception as e:  # noqa: BLE001
        print(f"[warn] ネタ提案の取得に失敗: {e}（スキップ）")
        return 0

    next_num = max((int(t["id"][2:]) for t in topics
                    if str(t.get("id", "")).startswith("ev")), default=0) + 1
    added = 0
    for p in proposals:
        candidate = {
            "id": f"ev{next_num + added:03d}",
            "theme": p["theme"],
            "format": p.get("format", "table"),
            "builder": "static",
            "last_used": None,
            "needs_review": True,  # 人間がデータを埋めてから使う
            "table": {
                "title": p["theme"], "subtitle": "要手動入力（データを埋めてから使用）",
                "columns": [{"label": "項目"}, {"label": "値", "num": True}],
                "rows": [{"cells": ["要手動入力", "要手動入力"]}],
            } if p.get("format", "table") == "table" else None,
            "checklist": {
                "title": p["theme"], "subtitle": "要手動入力",
                "items": [{"label": "要手動入力"}],
            } if p.get("format") == "checklist" else None,
            "post": {
                "headline": p.get("headline", p["theme"]),
                "numbers": p.get("numbers", ["要手動入力"] * 3),
                "view": p.get("view", "要手動入力"),
                "hashtags": ["#米国株"],
            },
            "ammo": {
                "targets": p.get("targets", ["要手動入力"]),
                "drafts": [
                    {"label": "案A（データ提示型）", "text": "要手動入力"},
                    {"label": "案B（自分の保有と結びつける型）", "text": "要手動入力"},
                    {"label": "案C（疑問を投げる型）", "text": "要手動入力"},
                ],
            },
        }
        trial = topics + [candidate]
        if find_duplicates(trial):
            print(f"[skip] 重複のため不採用: {p['theme']}")
            continue
        topics.append(candidate)
        added += 1
        print(f"[ok] 追加: {candidate['id']} {p['theme']}")

    if added:
        data["topics"] = topics
        save_yaml(TOPICS_PATH, data)
        print(f"[done] {added}本追記（needs_review: true → 人間がデータを埋めてから使用）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
