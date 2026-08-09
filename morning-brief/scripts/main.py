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
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_loader import load_config, ROOT                     # noqa: E402
from sources import market as l1                                # noqa: E402
from sources import primary as l2                               # noqa: E402
from sources import buzz as l3                                  # noqa: E402
from sources import trends as l3t                               # noqa: E402
from sources import fixtures as fx                              # noqa: E402
import ranking                                                  # noqa: E402
import gate                                                     # noqa: E402
import learner                                                  # noqa: E402
import report                                                   # noqa: E402
import themes                                                   # noqa: E402
from story_builder import build_quiet_story, build_story        # noqa: E402
from render import render_card                                  # noqa: E402
from templates import ALL_TEMPLATES                             # noqa: E402

OUT_DIR = os.path.join(ROOT, "out")
LOG_DIR = os.path.join(ROOT, "logs")


STATE_FILE = "STATE.json"


def _write_state(latest: str, market_day: str, cards: int, quiet: bool = False):
    """latest/ が「どの取引日の何枚か」を記録する。

    同じ取引日での再実行（週末・cron2本立て・手動再実行）が、既にある
    カードを「該当なし」で上書きしてしまうのを防ぐための状態。
    """
    with open(os.path.join(latest, STATE_FILE), "w", encoding="utf-8") as f:
        json.dump({"market_day": market_day, "cards": cards,
                   "quiet_day": quiet,
                   "generated_at": dt.datetime.now().isoformat(timespec="seconds")},
                  f, ensure_ascii=False, indent=1)


def _completed_state(latest: str) -> dict | None:
    """latest/ の生成済み状態を読む。壊れていれば None（作り直しに倒す）。"""
    path = os.path.join(latest, STATE_FILE)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[warn] STATE.json を読めないため再生成します: {e}")
        return None
    if not isinstance(state, dict) or not state.get("market_day"):
        return None
    # 記録上カードがあるのに実体が消えている場合は作り直す
    if state.get("cards", 0) > 0:
        pngs = [n for n in os.listdir(latest) if n.endswith(".png")]
        if not pngs:
            print("[warn] STATE.json はカードありだが画像が無いため再生成します")
            return None
    return state


def refresh_latest_empty(latest: str, asof: dt.date, reason: str,
                         market_day: str | None = None,
                         write_state: bool = True):
    """カード0枚の日も latest/ を必ず「今日の状態」に更新する。

    以前は該当なしの日に latest/ を触らなかったため、数日前のカードと
    古いNOTE.txtが残り続け「自動更新が止まった」ように見えていた。
    毎朝必ず latest/ の中身が入れ替わることで、実行された事実が見える。
    """
    for name in os.listdir(latest):
        os.remove(os.path.join(latest, name))
    with open(os.path.join(latest, "NOTE.txt"), "w", encoding="utf-8") as f:
        f.write(f"{asof} {reason}。空の枠は埋めない方針です。\n"
                f"（この実行: {dt.datetime.now().isoformat(timespec='seconds')}）\n")
    if write_state:
        _write_state(latest, market_day or asof.isoformat(), 0)


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
    ap.add_argument("--template", default=None, choices=ALL_TEMPLATES,
                    help="テンプレートを固定して検証（例: --template T3）")
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
        # yfinance側の一時障害で前営業日のカードを消してしまわないよう、
        # latest/ には手を触れない（取得失敗は「該当なし」とは別物）。
        print("[error] マーケットデータ全滅。latest/ は前回のまま維持して終了")
        _write_log(asof, cfg, [], [], note="market_unavailable")
        return 1
    market_metrics = {}
    for tk, s in mkt.items():
        m = l1.metrics(s, cfg)
        if m:
            market_metrics[tk] = m

    # 「最後に市場が動いた日」を基準日にする。
    # - cronが数時間遅延して日付をまたいでも、直近の取引日のカードを正しく作る
    # - 週末・休場日は最終バーが変わらないため、同一内容の再生成（差分なし）になる
    # ※多数決で決める。^GSPC 1本の最終バーが更新遅れだと、require_asof で
    #   他の全銘柄が候補から外れ「異常検知0件」に見える事故が起きるため。
    day_votes = Counter(s["dates"][-1] for s in mkt.values())
    market_day = day_votes.most_common(1)[0][0]
    spx_day = (mkt.get("^GSPC") or {}).get("dates", [None])[-1]
    if spx_day and spx_day != market_day:
        print(f"[warn] ^GSPC の最終バー({spx_day})が多数派({market_day})と不一致。"
              "多数派を基準日に採用")
    if len(day_votes) > 1:
        print(f"[ok] 最終バーの分布: {dict(day_votes)}")
    if not args.date:
        asof = dt.date.fromisoformat(market_day)
        date_str = asof.strftime("%Y/%m/%d")
        print(f"[ok] 基準日（最終取引日）: {market_day}")

    # 同じ取引日で既にカードを作ってあるなら、latest/ に触れずに終了する。
    # 週末・祝日の再実行が金曜のカードを「該当なし」で上書きするのを防ぐ。
    if not args.date and not args.fixtures:
        done = _completed_state(latest)
        if done and done.get("market_day") == market_day and done.get("cards", 0) > 0:
            print(f"[ok] 取引日 {market_day} のカードは生成済み"
                  f"（{done['cards']}枚）。latest/ を維持して終了")
            return 0

    candidates = l1.find_anomalies(mkt, cfg, require_asof=market_day)
    print(f"[ok] 異常検知: {len(candidates)} 銘柄 "
          f"({', '.join(c['ticker'] for c in candidates[:8])})")

    # 0件の日に原因を追えるよう、常に上位の変動を残す（黒箱にしない）
    top_z = sorted(market_metrics.items(),
                   key=lambda kv: -abs(kv[1]["zscore"]))[:5]
    print("[ok] 変動上位: " + ", ".join(
        f"{tk} {m['ret1d_pct']:+.2f}%/z={m['zscore']:+.2f}" for tk, m in top_z))

    # ── レイヤ3：話題性 / レイヤ2：一次情報 ──
    # 候補0件の日は外部取得を丸ごと省く（無駄打ちとレート制限の回避）
    focus = [c["ticker"] for c in candidates[:8]]
    buzz: dict = {}
    primary: dict = {}
    if focus:
        buzz = fx.fixture_buzz(asof) if args.fixtures else l3.fetch_buzz(focus)
        primary = (fx.fixture_primary(asof) if args.fixtures
                   else l2.fetch_primary(cfg, asof, focus))

        # トレンドシグナル（Google Trends / Reddit RSS / HN）を SNS 熱量に合成
        trend = {} if args.fixtures else l3t.trend_heat()
        if trend:
            sns = buzz.setdefault("sns", {})
            for tk, v in trend.items():
                sns[tk] = max(sns.get(tk, 0.0), v)

    # ── フィードバック学習（Views実績）──
    window = int(cfg.get("learning", {}).get("window_days", 30))
    fb_rows = learner.load_feedback(asof, window)
    tag_bonus = learner.topic_bonuses(fb_rows, cfg)
    if tag_bonus:
        print(f"[ok] 学習ボーナス（話題タグ）: {tag_bonus}")

    # ── スコアリング＋同一トピック束ね ──
    ranked = (ranking.score_candidates(candidates, buzz, primary, cfg, tag_bonus)
              if candidates else [])

    # ── 生成ゲート → テンプレ選択（ε-greedy）→ 描画（上限 MAX_CARDS 枚）──
    max_cards = int(cfg["max_cards"])
    adopted, skipped = [], []
    n = 0
    min_score = cfg["scoring"].get("min_score", 0.0)
    recent_tpls = learner.recent_templates(LOG_DIR, asof)   # 直近3日の使用テンプレ
    today_used: set[str] = set()
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

        tag = cand.get("topic_tag", "other")
        template_id = args.template or learner.choose_template(
            tag, n + 1, asof, fb_rows, recent_tpls, today_used, cfg)
        theme = themes.theme_for_tag(tag)

        png = os.path.join(OUT_DIR, f"{asof.isoformat()}_{n + 1}.png")
        if not render_card(story, mkt.get(cand["ticker"]), date_str, png, cfg,
                           template_id=template_id, theme=theme):
            skipped.append({"ticker": cand["ticker"], "score": cand["score"],
                            "unmet": ["描画検証NG（短縮しても収まらず）"]})
            continue
        today_used.add(template_id)
        txt = os.path.join(OUT_DIR, f"{asof.isoformat()}_{n + 1}.txt")
        with open(txt, "w", encoding="utf-8") as f:
            f.write(story["post"] + "\n")
        adopted.append({**{k: story[k] for k in
                           ("ticker", "name", "theme", "headline", "conclusion",
                            "score", "score_parts", "n_media", "sns_heat")},
                        "slot": n + 1, "template_id": template_id,
                        "topic_tag": tag,
                        "numbers": story["numbers"], "files": [png, txt]})
        n += 1
        print(f"[ok] カード{n}: {story['headline']} ({cand['ticker']}, "
              f"{template_id}×{tag})")

    # ── 静かな日のフォールバック ──
    # 深掘りできる材料が無い日でも、実測値だけのカードを1枚出す。
    # これが無いと材料の薄い日が続いたときブリーフが何日も空になり、
    # 「自動更新が止まった」と区別がつかなくなる（2026-08-06〜09に発生）。
    quiet_used, quiet_reason = False, None
    if not adopted and cfg.get("quiet_day_card", True):
        # 「動いた銘柄が無かった」のか「動いたが裏取りできなかった」のかで
        # 書くべき理由が違う。取り違えると画像の文面が事実と食い違う。
        quiet_reason = "no_anomaly" if not candidates else "gate_failed"
        qstory = build_quiet_story(market_metrics, cfg, asof,
                                   names=l1.all_tickers(cfg),
                                   reason=quiet_reason)
        if qstory is None:
            print("[warn] 静かな日カード: 基準指数が取れず作成を見送り")
        else:
            unmet = gate.check(qstory, cfg)
            if unmet:
                print(f"[warn] 静かな日カード: ゲート未充足 {unmet}")
            else:
                png = os.path.join(OUT_DIR, f"{asof.isoformat()}_1.png")
                txt = os.path.join(OUT_DIR, f"{asof.isoformat()}_1.txt")
                # 日替わりで見た目を変えつつ、失敗しても T2 で必ず描ける
                rotated = ALL_TEMPLATES[asof.toordinal() % len(ALL_TEMPLATES)]
                for tpl in (args.template or rotated, "T2"):
                    if render_card(qstory, mkt.get("^GSPC"), date_str, png, cfg,
                                   template_id=tpl,
                                   theme=themes.theme_for_tag("index")):
                        with open(txt, "w", encoding="utf-8") as f:
                            f.write(qstory["post"] + "\n")
                        adopted.append({
                            "ticker": qstory["ticker"], "name": qstory["name"],
                            "theme": qstory["theme"],
                            "headline": qstory["headline"],
                            "conclusion": qstory["conclusion"],
                            "score": None, "score_parts": None,
                            "n_media": 0, "sns_heat": 0.0,
                            "slot": 1, "template_id": tpl,
                            "topic_tag": "quiet",
                            "numbers": qstory["numbers"], "files": [png, txt]})
                        quiet_used = True
                        print(f"[ok] 静かな日カード: {qstory['headline']} ({tpl})")
                        break
                else:
                    print("[warn] 静かな日カード: 描画に失敗（NOTEに切替）")

    _write_log(asof, cfg, adopted, skipped,
               note=f"quiet_day:{quiet_reason}" if quiet_used else None)

    # ── meta.json（record.py がViewsと紐付けるための生成メタ）──
    if adopted:
        meta = [{"slot": a["slot"], "template_id": a["template_id"],
                 "topic_tag": a["topic_tag"], "ticker": a["ticker"],
                 "score": a["score"], "headline": a["headline"]}
                for a in adopted]
        meta_path = os.path.join(OUT_DIR, f"{asof.isoformat()}_meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)

    if not adopted:
        print(f"[ok] {asof} 本日は該当なし（ゲート通過0件）。画像0枚で正常終了")
        refresh_latest_empty(latest, asof, "本日は該当なし（生成ゲート通過0件）",
                             market_day,
                             write_state=not (args.date or args.fixtures))
    else:
        for f in os.listdir(latest):
            os.remove(os.path.join(latest, f))
        for a in adopted:
            for p in a["files"]:
                shutil.copy(p, os.path.join(latest, os.path.basename(p)))
        shutil.copy(os.path.join(OUT_DIR, f"{asof.isoformat()}_meta.json"),
                    os.path.join(latest, "meta.json"))
        # ドライラン(--date/--fixtures)の結果を本番の状態として残さない
        if not args.date and not args.fixtures:
            _write_state(latest, market_day, len(adopted), quiet_used)
        print(f"[ok] 生成完了: {len(adopted)}枚 → {OUT_DIR}（latest/ にも複製）")

    # ── 週次レポート（日曜の実行時のみ。実績データが無い週はスキップ）──
    if dt.date.today().weekday() == 6 and not args.fixtures:
        report.generate(dt.date.today())

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
