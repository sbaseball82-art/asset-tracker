# -*- coding: utf-8 -*-
"""MORNING BRIEF 本体：1日1〜2枚の深掘りカードを生成する。

パイプライン:
  レイヤ1(市場の実際の動き) → 異常検知 → レイヤ3(話題度)・レイヤ2(一次情報)
  → スコアリング＋重複排除 → 生成ゲート → 描画＋投稿文 → ログ

- 条件を満たす記事が0件の日は「本日は該当なし」で正常終了（空の枠は埋めない）
- 採用理由・スコア内訳・未充足項目は logs/YYYY-MM-DD.json に残す

使い方:
  python scripts/main.py                       # 本番（ライブ取得）
  python scripts/main.py --date 2026-07-22     # 過去日のドライラン再現
  python scripts/main.py --date 2026-07-22 --fixtures   # オフライン合成データ
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_loader import load_config, ROOT                     # noqa: E402
from sources import market as l1                                # noqa: E402
from sources import primary as l2                               # noqa: E402
from sources import buzz as l3                                  # noqa: E402
from sources import fixtures as fx                              # noqa: E402
import ranking                                                  # noqa: E402
import gate                                                     # noqa: E402
from story_builder import build_story                           # noqa: E402
from render import render_card                                  # noqa: E402

OUT_DIR = os.path.join(ROOT, "out")
LOG_DIR = os.path.join(ROOT, "logs")


def prune_old(asof: dt.date, keep_days: int):
    for d in (OUT_DIR, LOG_DIR):
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            stem = name.split("_")[0].split(".")[0]
            try:
                fdate = dt.date.fromisoformat(stem)
            except ValueError:
                continue
            if (asof - fdate).days > keep_days:
                os.remove(os.path.join(d, name))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD（過去日のドライラン）")
    ap.add_argument("--fixtures", action="store_true",
                    help="外部通信なしの合成データで実行（開発・受け入れテスト用）")
    args = ap.parse_args()

    cfg = load_config()
    asof = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    date_str = asof.strftime("%Y/%m/%d")
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    latest = os.path.join(OUT_DIR, "latest")
    os.makedirs(latest, exist_ok=True)

    # ── レイヤ1：市場の実際の動き（最優先シグナル）──
    mkt = fx.fixture_market(asof) if args.fixtures else l1.fetch_market(cfg, asof)
    if not mkt:
        print("[error] マーケットデータ全滅。画像は生成せず終了（空の枠は埋めない）")
        _write_log(asof, cfg, [], [], note="market_unavailable")
        return 0
    market_metrics = {}
    for tk, s in mkt.items():
        m = l1.metrics(s, cfg)
        if m:
            market_metrics[tk] = m

    candidates = l1.find_anomalies(mkt, cfg)
    print(f"[ok] 異常検知: {len(candidates)} 銘柄 "
          f"({', '.join(c['ticker'] for c in candidates[:8])})")

    if not candidates:
        print(f"[ok] {asof} 本日は該当なし（実際に動いた銘柄がない）。画像0枚で正常終了")
        _write_log(asof, cfg, [], [], note="no_anomaly")
        prune_old(asof, cfg["output"]["keep_days"])
        return 0

    # ── レイヤ3：話題性 / レイヤ2：一次情報 ──
    focus = [c["ticker"] for c in candidates[:8]]
    buzz = fx.fixture_buzz(asof) if args.fixtures else l3.fetch_buzz(focus)
    primary = fx.fixture_primary(asof) if args.fixtures else l2.fetch_primary(cfg, asof, focus)

    # ── スコアリング＋同一トピック束ね ──
    ranked = ranking.score_candidates(candidates, buzz, primary, cfg)

    # ── 生成ゲート → 描画（上限 MAX_CARDS 枚）──
    max_cards = int(cfg["max_cards"])
    adopted, skipped = [], []
    n = 0
    min_score = cfg["scoring"].get("min_score", 0.0)
    for cand in ranked:
        if n >= max_cards:
            break
        if cand["score"] < min_score:
            skipped.append({"ticker": cand["ticker"], "score": cand["score"],
                            "unmet": [f"スコア{cand['score']:.2f}が閾値{min_score}未満（材料薄）"]})
            continue
        story = build_story(cand, market_metrics, primary, cfg, asof)
        unmet = gate.check(story, cfg)
        if unmet:
            skipped.append({"ticker": cand["ticker"], "score": cand["score"],
                            "unmet": unmet})
            print(f"[skip] {cand['ticker']}: 未充足 {unmet}")
            continue
        png = os.path.join(OUT_DIR, f"{asof.isoformat()}_{n + 1}.png")
        if not render_card(story, mkt.get(cand["ticker"]), date_str, png, cfg):
            skipped.append({"ticker": cand["ticker"], "score": cand["score"],
                            "unmet": ["描画検証NG（短縮しても収まらず）"]})
            continue
        txt = os.path.join(OUT_DIR, f"{asof.isoformat()}_{n + 1}.txt")
        with open(txt, "w", encoding="utf-8") as f:
            f.write(story["post"] + "\n")
        adopted.append({**{k: story[k] for k in
                           ("ticker", "name", "theme", "headline", "conclusion",
                            "score", "score_parts", "n_media", "sns_heat")},
                        "numbers": story["numbers"], "files": [png, txt]})
        n += 1
        print(f"[ok] カード{n}: {story['headline']} ({cand['ticker']})")

    _write_log(asof, cfg, adopted, skipped)

    if not adopted:
        print(f"[ok] {asof} 本日は該当なし（ゲート通過0件）。画像0枚で正常終了")
    else:
        for f in os.listdir(latest):
            os.remove(os.path.join(latest, f))
        for a in adopted:
            for p in a["files"]:
                shutil.copy(p, os.path.join(latest, os.path.basename(p)))
        print(f"[ok] 生成完了: {len(adopted)}枚 → {OUT_DIR}（latest/ にも複製）")

    prune_old(asof, cfg["output"]["keep_days"])
    return 0


def _write_log(asof: dt.date, cfg: dict, adopted: list, skipped: list,
               note: str | None = None):
    """採用理由・スコア内訳・未充足項目を logs/YYYY-MM-DD.json に残す。"""
    log = {
        "date": asof.isoformat(),
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "max_cards": cfg.get("max_cards"),
        "adopted": adopted,
        "skipped": skipped,
    }
    if note:
        log["note"] = note
    path = os.path.join(LOG_DIR, f"{asof.isoformat()}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=1, default=str)
    print(f"[ok] ログ: {path}")


if __name__ == "__main__":
    raise SystemExit(main())
