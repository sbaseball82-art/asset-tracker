# -*- coding: utf-8 -*-
"""
generate.py（機能A: 保存版コンテンツ生成）
==========================================
毎週日曜21:00 JSTに実行。生成のみ行い、投稿はしない。

出力: output/evergreen/YYYY-MM-DD/
  post.txt   … 1枚目のテキスト投稿（画像なしで成立・280字以内）
  reply.txt  … 2投稿目（画像を添える返信）のテキスト
  table.png  … ASSET LOGデザインの表/グラフ/チェックリスト
  ammo.md    … リプライ先の想定と返信文の雛形3案

使い方:
  python -m src.evergreen.generate               # 未使用ネタから自動選択
  python -m src.evergreen.generate --topic ev003 # ネタ指定
  python -m src.evergreen.generate --dry-run     # 使用済みフラグ・ログを書かない
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.common import postlog
from src.common.notify import notify
from src.common.render import build_html, render_png
from src.common.textcheck import check_post
from src.common.util import REPO_ROOT, today_jst
from src.evergreen import builders
from src.evergreen.topics import find_duplicates, load_topics, mark_used, pick_topic

DISCLAIMER = "※報道／公表ベースの概算。投資助言ではありません"


def _fill(text: str, values: dict) -> str:
    try:
        return text.format(**values) if values else text
    except (KeyError, IndexError) as e:
        raise ValueError(f"テンプレの差し込み値が不足: {e}") from e


def build_post_text(topic: dict, values: dict) -> str:
    """依頼書のテンプレ構造で post.txt を組み立てる。"""
    p = topic["post"]
    lines = [f"【{_fill(p['headline'], values)}】", ""]
    lines += [f"・{_fill(n, values)}" for n in p["numbers"]]
    lines += ["", _fill(p["view"], values).rstrip(), "",
              "詳細は返信に表を置いておきます。", "", DISCLAIMER]
    tags = p.get("hashtags", [])[:2]  # 最大2個・末尾のみ
    if tags:
        lines += ["", " ".join(tags)]
    return "\n".join(lines)


def build_reply_text(topic: dict, values: dict, stale: bool) -> str:
    p = topic["post"]
    lines = [f"{_fill(p['headline'], values)}の詳細です。", "",
             "数字はすべて報道／公表ベースの概算です。"]
    if stale:
        lines.append("（データは前回取得分のキャッシュを使用しています）")
    lines += ["", DISCLAIMER]
    return "\n".join(lines)


def build_ammo_md(topic: dict, values: dict, date_str: str) -> str:
    a = topic["ammo"]
    lines = [f"# ammo: {topic['id']}（{date_str}生成）", "",
             f"素材: {topic['theme']}", "",
             "## 想定リプライ先"]
    lines += [f"- {t}" for t in a["targets"]]
    lines += ["", "## 返信文の雛形"]
    for d in a["drafts"]:
        lines += [f"### {d['label']}", _fill(d["text"], values), ""]
    lines += ["---",
              "使い方: 大型アカウントの該当話題に、雛形＋table.png を添えて返信する。",
              "断定しない・煽らない・推測形はそのまま維持すること。"]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", help="トピックIDを指定（例: ev003）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-image", action="store_true", help="画像を生成しない")
    ap.add_argument("--force", action="store_true", help="同日の生成済みでも再生成")
    args = ap.parse_args(argv)

    today = today_jst()

    # cron遅延対策で複数回起動されても、同じ日に2本目を作らない
    #（2本目を作ると使用済みフラグが無駄に進むため）
    out_dir = REPO_ROOT / "output" / "evergreen" / today.isoformat()
    if (out_dir / "post.txt").exists() and not args.force:
        print(f"[skip] 本日分は生成済み: {out_dir}（--force で再生成）")
        return 0

    topics = load_topics()

    dups = find_duplicates(topics)
    if dups:
        print("::warning::重複ネタを検出しました: " + " / ".join(dups))

    topic = pick_topic(today, topics, topic_id=args.topic)
    if topic is None:
        notify("evergreen: 選択可能なネタがありません（全て使用済み・90日未経過）")
        return 1

    print(f"[ok] 選択: {topic['id']} {topic['theme']}")
    title, subtitle, spec, values, stale, stale_asof = builders.build(topic, today)

    post = build_post_text(topic, values)
    ok, n, warn = check_post(post)
    if not ok:
        print(f"::warning::{topic['id']} post.txt {warn}")

    reply = build_reply_text(topic, values, stale)
    ammo = build_ammo_md(topic, values, today.isoformat())

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "post.txt").write_text(post, encoding="utf-8")
    (out_dir / "reply.txt").write_text(reply, encoding="utf-8")
    (out_dir / "ammo.md").write_text(ammo, encoding="utf-8")

    account = ""
    try:
        import config as _c  # リポジトリ直下の config.py
        account = f"@{_c.X_ACCOUNT}"
    except Exception:  # noqa: BLE001
        pass

    has_image = False
    if not args.no_image:
        html = build_html(title, subtitle, topic["format"], spec,
                          account=account, stale=stale, stale_asof=stale_asof)
        has_image = render_png(html, out_dir / "table.png")

    if not args.dry_run:
        mark_used(topic["id"], today)
        postlog.append_row(today.isoformat(), "evergreen", topic["id"],
                           topic["format"], n, has_image)

    notify(f"evergreen 生成完了: {topic['id']} {topic['theme']}\n"
           f"→ {out_dir.relative_to(REPO_ROOT)}/ (post {n}字{'・画像あり' if has_image else '・画像なし'})")
    print(f"[done] {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
