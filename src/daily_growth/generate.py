# -*- coding: utf-8 -*-
"""
generate.py（Daily Growth System）
==================================
毎朝、data.json から「その日しか作れない話題」を選んで
X投稿の候補を5本つくる。**投稿はしない。人間が見てから手で出す。**

出力: ``output/daily-growth/YYYY-MM-DD/``
    post_1.png / post_1.txt … post_5.png / post_5.txt
    summary.md   … 選ばれた5本と、選ばれなかった理由
    qa.json      … 自動QAの結果（ok=false なら投稿素材として使わない）

使い方:
    python -m src.daily_growth.generate              # 通常
    python -m src.daily_growth.generate --dry-run    # 履歴・ログを書かない
    python -m src.daily_growth.generate --sample     # 隔離ディレクトリに出す
    python -m src.daily_growth.generate --no-render  # 画像を作らず本文だけ見る
    python -m src.daily_growth.generate --date 2026-08-17
    python -m src.daily_growth.generate --force     # 同日ぶんを作り直す

終了コード: 0=成功 / 1=QA不合格 / 2=生成中止（データが古い・足りない）
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.common import postlog, settings  # noqa: E402
from src.common.notify import notify  # noqa: E402
from src.common.textcheck import zenkaku_len  # noqa: E402
from src.common.util import REPO_ROOT, today_jst  # noqa: E402
from src.daily_growth import facts, history, qa, render, score, topics  # noqa: E402

DATA_PATH = REPO_ROOT / "data.json"
OUT_ROOT = REPO_ROOT / "output" / "daily-growth"


# --------------------------------------------------------------------------
# 入力
# --------------------------------------------------------------------------

def load_json(path: Path) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[warn] {path} を読めません: {e}")
        return None


def load_facts(today: date) -> tuple[dict, list[str]]:
    """facts と、生成を止める理由（あれば）を返す。"""
    data = load_json(DATA_PATH)
    if not data:
        return {}, ["data.json が読めません。価格取得が動いているか確認してください"]

    lookthrough = None
    feed = settings.path_of("feed")
    if feed.exists():
        lookthrough = load_json(feed)

    f = facts.build(data, today, lookthrough)
    if not f:
        return {}, ["data.json から日付・総資産を取れませんでした"]

    cfg = settings.daily_growth("data")
    level, msg = facts.staleness(f, int(cfg.get("halt_age_days", 4)),
                                 int(cfg.get("warn_age_days", 1)))
    if level == "halt":
        return f, [msg]
    if level == "warn":
        print(f"[warn] {msg}")
        f["stale_warning"] = msg
    return f, []


# --------------------------------------------------------------------------
# 生成
# --------------------------------------------------------------------------

def build_posts(chosen: list[score.Scored], f: dict, out_dir: Path,
                designs: dict[str, dict], account: str,
                do_render: bool) -> list[dict]:
    posts: list[dict] = []
    for i, s in enumerate(chosen, start=1):
        d = s.draft
        design = designs.get(s.design_id, {})
        png = out_dir / f"post_{i}.png"
        txt = out_dir / f"post_{i}.txt"
        txt.parent.mkdir(parents=True, exist_ok=True)
        txt.write_text(d.text + "\n", encoding="utf-8")

        report: dict = {}
        rendered = False
        if do_render:
            rendered = render.render(d.card, design, png, account, report)

        posts.append({
            "index": i,
            "topic_id": d.topic_id,
            "category": d.category,
            "design_id": s.design_id,
            "hook": d.hook,
            "text": d.text,
            "zenkaku": round(zenkaku_len(d.text), 1),
            "asof": d.card["asof"],
            "source_values": d.source_values(),
            "literals": d.literals,
            "figure": d.card["figure"],
            "image": str(png),
            "text_file": str(txt),
            "image_texts": render.collect_texts(d.card, account, design),
            "render_report": report,
            "rendered": rendered,
            "score": round(s.score, 4),
            "score_parts": {k: round(v, 3) for k, v in s.parts.items()},
        })
    return posts


def write_summary(path: Path, f: dict, posts: list[dict],
                  rest: list[score.Scored], skipped: list[dict],
                  result: qa.Result, today: date, learned: bool,
                  relaxed: str = "") -> None:
    L: list[str] = [
        f"# Daily Growth — {today.isoformat()}", "",
        f"- データ基準日: **{f.get('data_date')}**（data.json）",
        f"- 総資産: {f.get('total_jpy', 0):,.0f}円 / USD/JPY {f.get('usdjpy', 0)}",
        f"- QA: **{'合格' if result.ok else '不合格（投稿素材として使わない）'}**",
        f"- 実績からの学習: {'有効' if learned else '未学習（サンプル不足のため補正なし）'}",
    ]
    if f.get("stale_warning"):
        L.append(f"- ⚠ {f['stale_warning']}")
    if relaxed:
        L.append(f"- ⚠ ローテーションをゆるめました（{relaxed}）")
    L += ["", "## 今日の5本", ""]
    for p in posts:
        L += [f"### post_{p['index']} — {p['topic_id']}（{p['design_id']}）",
              f"- 全角 {p['zenkaku']}字 / スコア {p['score']}",
              f"- 内訳: " + " / ".join(f"{k} {v}" for k, v in
                                       p["score_parts"].items()),
              "", "```", p["text"], "```", ""]

    if result.errors:
        L += ["## QAエラー（要修正）", ""] + [f"- {e}" for e in result.errors] + [""]
    if result.warnings:
        L += ["## QA警告", ""] + [f"- {w}" for w in result.warnings] + [""]

    L += ["## 選ばれなかった候補（上位10件）", ""]
    for s in rest[:10]:
        why = s.excluded or "スコアが届かなかった"
        L.append(f"- {s.draft.topic_id}（{round(s.score, 3)}）… {why}")

    L += ["", "## 今日は作れなかった話題", "",
          "データが無い項目は推測で埋めません。理由を残しておきます。", ""]
    for sk in skipped:
        L.append(f"- {sk['id']} {sk['title']} … {sk['reason']}")

    L += ["", "---", "",
          "生成物は人間が確認してから手で投稿してください。",
          "投稿後の実績（views / likes / bookmarks / replies / profile_clicks /",
          "follows）は `scripts/log_metrics.py` で `logs/posts.csv` に入れます。", ""]
    path.write_text("\n".join(L), encoding="utf-8")


# --------------------------------------------------------------------------
# 本体
# --------------------------------------------------------------------------

def run(args) -> int:
    today = date.fromisoformat(args.date) if args.date else today_jst()
    f, halt = load_facts(today)
    if halt:
        for m in halt:
            print(f"[halt] {m}")
        _notify_halt("daily-growth 生成中止", halt)
        return 2

    entries = [] if args.sample else history.load()

    # 同日二重生成のガード。スケジュールの予備実行が走っても、
    # すでに作った日の候補を別物に差し替えない（＝毎日のコミットも1回で済む）。
    writes_history = not (args.sample or args.dry_run)
    if writes_history and history.entries_on(entries, today) and not args.force:
        print(f"{today} ぶんの候補はすでにあります。作り直すなら --force を付けてください")
        return 0

    cb = history.checkback_source(entries, today)
    if cb:
        f["checkback"] = cb

    pool = topics.load_topics()
    problems = topics.find_duplicates(pool)
    if problems:
        for p in problems:
            print(f"[halt] ネタプールの不備: {p}")
        return 2

    char_limit = float(settings.dg_char_limit())
    drafts, skipped = topics.build_all(pool, f, char_limit)
    if not drafts:
        print("[halt] 今日のデータで書ける話題がありません")
        _notify_halt("daily-growth 生成中止", ["書ける話題がありません"])
        return 2

    perf = score.format_performance(
        postlog.read_rows(),
        objective=list(settings.daily_growth("learning").get("objective") or []),
        min_samples=int(settings.daily_growth("learning")
                        .get("min_samples_per_format", 8)))
    learned = score.is_learned(perf)

    base_rotation = settings.dg_rotation()
    designs = render.load_designs()
    want = int(args.count or settings.dg_posts_per_day())
    base_cat = int(settings.daily_growth("max_per_category", 2))

    chosen, rest, rotation, max_cat = _choose(
        drafts, today, entries, base_rotation, designs, perf, want, base_cat)
    relaxed = score.describe_relaxation(base_rotation, rotation)

    out_dir = OUT_ROOT / ("sample" if args.sample else today.isoformat())
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("post_*"):
        old.unlink()

    account = settings.x_handle(with_at=True)
    posts = build_posts(chosen, f, out_dir, designs, account,
                        do_render=not args.no_render)

    result = qa.run(posts, f, today, entries, designs, out_dir, want,
                    char_limit, rotation)
    if relaxed:
        result.warn(f"ネタが足りず、ローテーション条件をゆるめました（{relaxed}）。"
                    "data/daily_growth_topics.yml に話題を足すと解消します")
        result.checks["relaxed_rotation"] = rotation
    if max_cat != base_cat:
        result.warn(f"同一カテゴリの上限を{base_cat}→{max_cat}本にゆるめました")
    if args.no_render:
        result.warnings.append("--no-render のため画像の検査は一部省略しています")

    (out_dir / "qa.json").write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    write_summary(out_dir / "summary.md", f, posts, rest, skipped, result,
                  today, learned, relaxed)

    _print_report(posts, result, out_dir)

    if not result.ok:
        _notify_halt("daily-growth QA不合格", result.errors[:10])
        return 1

    if args.dry_run or args.sample:
        print("（dry-run／sample のため履歴と logs/posts.csv は更新しません）")
        return 0

    history.append([
        history.make_entry(
            date_str=today.isoformat(), topic_id=p["topic_id"], hook=p["hook"],
            design_id=p["design_id"], post_text=p["text"],
            source_values=p["source_values"],
            generated_files=[Path(p["image"]).name, Path(p["text_file"]).name],
            category=p["category"], data_date=f["data_date"],
            zenkaku=p["zenkaku"], qa_ok=True)
        for p in posts])
    for p in posts:
        postlog.append_row(today.isoformat(), "daily_growth", p["topic_id"],
                           p["design_id"], int(round(p["zenkaku"])), True)
    return 0


def _choose(drafts, today, entries, base_rotation, designs, perf, want,
            base_cat):
    """5本そろうまで、決めた順番でローテーションをゆるめる。

    ゆるめたかどうかは呼び出し側で summary.md と qa.json に必ず残す。
    黙って条件を下げない。
    """
    best = ([], [], base_rotation, base_cat)
    for rotation in score.relaxation_ladder(base_rotation):
        scored = score.rank(drafts, today, entries, settings.dg_weights(),
                            rotation, perf)
        for max_cat in range(base_cat, want + 1):
            chosen, rest = score.select(scored, want, max_cat, designs,
                                        rotation, entries, today)
            if len(chosen) > len(best[0]):
                best = (chosen, rest, rotation, max_cat)
            if len(chosen) >= want:
                return chosen, rest, rotation, max_cat
    return best


def _notify_halt(title: str, lines: list[str]) -> None:
    """中止・不合格は通知する（config.yml の notification.notify_on に従う）。"""
    if not settings.notify_on("halt"):
        return
    notify(f"{title}\n" + "\n".join(f"- {x}" for x in lines), critical=True)


def _print_report(posts: list[dict], result: qa.Result, out_dir: Path) -> None:
    print(f"\n出力先: {out_dir}")
    for p in posts:
        print(f"  post_{p['index']}  {p['topic_id']:<7} {p['design_id']:<22} "
              f"{p['zenkaku']:>5}字  {p['hook'][:28]}")
    for w in result.warnings:
        print(f"[warn] {w}")
    for e in result.errors:
        print(f"[error] {e}")
    print(f"QA: {'OK' if result.ok else 'NG'}")


def main() -> int:
    ap = argparse.ArgumentParser(description="毎朝の投稿候補を5本つくる（投稿はしない）")
    ap.add_argument("--date", help="生成日（YYYY-MM-DD）。既定は今日(JST)")
    ap.add_argument("--count", type=int, help="生成本数（既定は config.yml）")
    ap.add_argument("--dry-run", action="store_true",
                    help="履歴と logs/posts.csv を書かない")
    ap.add_argument("--sample", action="store_true",
                    help="output/daily-growth/sample/ にだけ書く（履歴も汚さない）")
    ap.add_argument("--no-render", action="store_true",
                    help="画像を作らず本文だけ確認する")
    ap.add_argument("--force", action="store_true",
                    help="同じ日の候補がすでにあっても作り直す")
    return run(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
