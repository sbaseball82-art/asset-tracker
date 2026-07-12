# -*- coding: utf-8 -*-
"""毎朝の本体：ニュース取得→5枚の深掘りカード生成→投稿文生成→保存。

使い方:
  python scripts/main.py                          # 本番（RSSライブ取得）
  python scripts/main.py --local fixtures/*.xml   # ローカルRSSでテスト
"""
from __future__ import annotations
import os, sys, json, argparse, datetime as dt

sys.path.insert(0, os.path.dirname(__file__))
from fetch_news import fetch_top_stories                     # noqa: E402
from generate_images import (news_card, evergreen_card,
                             STANCES, EVERGREEN)             # noqa: E402
from market_charts import fetch_market_data                  # noqa: E402
from generate_posts import (template_post, evergreen_post,
                            maybe_llm_upgrade)               # noqa: E402

N_CARDS = 5

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_ROOT = os.path.join(ROOT, "output")
KEEP_DAYS = 14


def prune_old(today: dt.date):
    if not os.path.isdir(OUT_ROOT):
        return
    for name in os.listdir(OUT_ROOT):
        p = os.path.join(OUT_ROOT, name)
        if not os.path.isdir(p) or name == "latest":
            continue
        try:
            d = dt.date.fromisoformat(name)
        except ValueError:
            continue
        if (today - d).days > KEEP_DAYS:
            for f in os.listdir(p):
                os.remove(os.path.join(p, f))
            os.rmdir(p)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", nargs="*", default=None)
    ap.add_argument("--date", default=None)
    args = ap.parse_args()

    today = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    date_str = today.strftime("%Y/%m/%d")
    out_dir = os.path.join(OUT_ROOT, today.isoformat())
    latest = os.path.join(OUT_ROOT, "latest")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(latest, exist_ok=True)
    # 同日の再実行や旧仕様の残骸（5_summary.png等）が混ざらないよう先に空にする
    for f in os.listdir(out_dir):
        os.remove(os.path.join(out_dir, f))

    stories = fetch_top_stories(N_CARDS, args.local)   # 全カード＝ニュース（まとめ無し）
    if stories:
        intl = sum(1 for s in stories if s.get("region") == "海外")
        print(f"[ok] {len(stories)}件の話題ニュースを取得（海外{intl}・国内{len(stories)-intl}）")
    else:
        print("[warn] ニュース取得に失敗 → 原則カードへフォールバック")

    market = fetch_market_data()   # チャート・統計タイル用（失敗時は{}→話題度バーで代替）

    posts: list[str] = []
    seed = today.toordinal()

    # 1〜5枚目：すべてニュース深掘り（足りない分は原則カード）
    for i in range(N_CARDS):
        png = os.path.join(out_dir, f"{i+1}_news.png")
        stance = STANCES[(seed + i) % len(STANCES)]
        if stories and i < len(stories):
            news_card(i + 1, N_CARDS, stories[i], date_str, png, stance, market)
            posts.append(template_post(i, stories[i], today))
        else:
            idx = (seed + i) % len(EVERGREEN)
            evergreen_card(idx, i + 1, N_CARDS, date_str, png, stance, market)
            t = EVERGREEN[idx]
            posts.append(evergreen_post(idx, t[0], t[1]))

    posts = maybe_llm_upgrade(posts, stories)

    md = [f"# {date_str} の投稿文（画像1〜5に対応）\n"]
    for i, p in enumerate(posts, 1):
        md.append(f"## 画像{i}\n```\n{p}\n```\n")
    with open(os.path.join(out_dir, "posts.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    import shutil
    for f in os.listdir(latest):
        os.remove(os.path.join(latest, f))
    for f in os.listdir(out_dir):
        shutil.copy(os.path.join(out_dir, f), os.path.join(latest, f))

    if stories:
        with open(os.path.join(out_dir, "stories.json"), "w", encoding="utf-8") as f:
            json.dump(stories, f, ensure_ascii=False, indent=1)

    prune_old(today)
    print(f"[ok] 生成完了: {out_dir}（latest/ にも複製）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
