# -*- coding: utf-8 -*-
"""
generate.py
===========
ルックスルー分解の実行エントリ。

    python -m src.lookthrough.generate              # 通常（公開データを取得）
    python -m src.lookthrough.generate --offline    # 取得せずキャッシュのみ
    python -m src.lookthrough.generate --sample     # サンプルデータで動作確認

出力先: ``output/lookthrough/YYYY-MM/``
  lookthrough.png / post_100.txt / post_150.txt / post_165.txt
  reply.txt / data.json / notes.md

加えて、機能②（指数寄与）が読む ``data/lookthrough.json`` を更新する。

推測で埋めない
--------------
構成銘柄が取れなかったファンドは按分せず「要手動確認」として
画像・notes.md・data.json のすべてに残す。0 や仮の値では埋めない。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from src.common import fontcheck, postlog
from src.common.notify import notify
from src.common.textcheck import zenkaku_len
from src.common.util import REPO_ROOT, load_yaml, now_jst
from src.lookthrough import compose, compute, history, render
from src.lookthrough.constituents import collect, load_fund_map, load_holdings

OUT_ROOT = REPO_ROOT / "output" / "lookthrough"
FEED_PATH = REPO_ROOT / "data" / "lookthrough.json"   # 機能②が読む
SAMPLE_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "constituents_sample.yml"

LIMITS = (100, 150, 165)

# これ未満のカバレッジでは data/lookthrough.json（機能②の入力）を更新しない
FEED_MIN_COVERAGE = 60.0


# --------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="保有ファンドのルックスルー分解")
    ap.add_argument("--offline", action="store_true",
                    help="公開データを取得せず data/cache のみ使う")
    ap.add_argument("--sample", action="store_true",
                    help="サンプル構成データで通しの動作確認をする（実データではない）")
    ap.add_argument("--ym", default=None, help="出力月（既定は当月 YYYY-MM）")
    ap.add_argument("--allow-tofu", action="store_true",
                    help="豆腐（□）が出ても失敗にしない")
    args = ap.parse_args(argv)

    ym = args.ym or now_jst().strftime("%Y-%m")
    funds, total_jpy, holdings_asof = load_holdings()
    fmap = load_fund_map()

    if args.sample:
        cons = _sample_constituents([f.id for f in funds])
        print("⚠ サンプルデータで実行しています（実際の構成比ではありません）")
    else:
        cons = collect([f.id for f in funds], offline=args.offline,
                       fund_map=fmap)

    try:
        result = compute.look_through(funds, cons, total_jpy)
    except (compute.ReconciliationError, ValueError) as e:
        print(f"::error::ルックスルー計算に失敗: {e}")
        notify(f"ルックスルー生成失敗: {e}", critical=True)
        return 1

    if not result.positions:
        names = "、".join(u.fund_name for u in result.unresolved)
        print("::error::どのファンドの構成銘柄も取得できませんでした。"
              "推測では埋めないため、生成を中止します。")
        print(f"  未取得: {names}")
        print("  対処: ネットワークを確認して再実行するか、"
              "data/manual/ にCSVを置いてください。")
        notify("ルックスルー生成中止: 構成銘柄をひとつも取得できず", critical=True)
        return 1

    if result.coverage_pct < 60.0:
        print(f"::warning::分解できたのは総資産の {result.coverage_pct:.1f}% だけです。"
              "上位N銘柄しか取れていない可能性があります（notes.md を確認）")

    metrics = _metrics(result, funds, fmap, ym)
    outdir = OUT_ROOT / ("sample" if args.sample else ym)
    outdir.mkdir(parents=True, exist_ok=True)

    # ---- 画像 -----------------------------------------------------------
    names = {f.id: f.name for f in funds}
    ctx = _render_ctx(result, metrics, ym, holdings_asof, names,
                      sample=args.sample)
    layout: dict = {}
    ok_png = render.render(ctx, outdir / "lookthrough.png", report=layout)
    if layout.get("overflow_px"):
        print(f"::warning::画像の中身が {layout['overflow_px']}px はみ出しています"
              "（表の行数か文言を減らしてください）")

    tofu_ok, tofu_chars, font_used = _check_tofu(ctx)
    if not tofu_ok and not args.allow_tofu:
        print(f"::error::画像に豆腐が出ます（グリフ欠落: {''.join(tofu_chars)}）")
        notify(f"ルックスルー画像に豆腐: {''.join(tofu_chars)}", critical=True)
        return 1

    # ---- 投稿文 ---------------------------------------------------------
    posts = compose.build_posts(metrics["post"], limits=LIMITS)
    reply = compose.build_reply(metrics["post"])

    violations: dict[str, list[str]] = {}
    for lim, text in posts.items():
        v = compose.validate_post(text, limit=lim)
        if v:
            violations[f"post_{lim}"] = v
        (outdir / f"post_{lim}.txt").write_text(text + "\n", encoding="utf-8")
    v = compose.validate_post(reply, require_hashtags=False)
    if v:
        violations["reply"] = v
    (outdir / "reply.txt").write_text(reply + "\n", encoding="utf-8")

    for name, probs in violations.items():
        for p in probs:
            print(f"::warning::{name}: {p}")

    # ---- データ ---------------------------------------------------------
    payload = _payload(result, metrics, ym, holdings_asof, cons,
                       sample=args.sample)
    (outdir / "data.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    # 機能②（指数寄与）が読む data/lookthrough.json は、十分に分解できた
    # ときだけ更新する。カバレッジの低い結果で上書きすると、②の
    # 「私の資産への寄与」が実態より小さく出てしまうため。
    if not args.sample:
        if result.coverage_pct >= FEED_MIN_COVERAGE:
            FEED_PATH.write_text(
                json.dumps(payload, ensure_ascii=False, indent=1),
                encoding="utf-8")
        else:
            print(f"::warning::カバレッジ {result.coverage_pct:.1f}% のため "
                  f"{FEED_PATH.name} は更新しません"
                  f"（{FEED_MIN_COVERAGE:.0f}%以上で更新）")

    # ---- notes.md -------------------------------------------------------
    (outdir / "notes.md").write_text(
        _notes(result, metrics, cons, ym, violations, tofu_chars, font_used,
               ok_png, names, sample=args.sample),
        encoding="utf-8")

    # ---- 月次スナップショット（サンプル実行では汚さない） ----------------
    if not args.sample:
        history.save_snapshot(ym, result)
        postlog.append_row(date.today().isoformat(), "ルックスルー", f"lt-{ym}",
                           "画像+本文", int(zenkaku_len(posts[165])), ok_png)

    print(f"\n✅ 出力: {outdir}")
    print(f"   分解カバレッジ {result.coverage_pct:.1f}% / "
          f"銘柄数 {len(result.positions)} / 未分解 {len(result.unresolved)}本")
    if violations:
        print(f"   ⚠ 投稿文の要確認: {len(violations)}件（notes.md 参照）")
    notify(f"ルックスルー生成完了 {ym}: 上位10社 "
           f"{metrics['top10_pct']:.1f}% / 重複{metrics['dup_all_n']}社")
    return 0


# --------------------------------------------------------------------------
# 集計
# --------------------------------------------------------------------------

def _metrics(result, funds, fmap, ym) -> dict:
    top10_pct = compute.top_n_pct(result, 10)
    dup10_n, dup10_pct, dup10 = compute.multi_fund_in_top_n(result, 10)
    dup_all_n, dup_all_pct = compute.multi_fund_all(result)

    ai = fmap.get("ai_megatech", {}) or {}
    ai_pct = compute.group_pct(result, ai.get("tickers", []))

    changes, prev_ym_used = history.compare_with_prev(ym, result, n=20)
    change_by_ticker = {c.ticker: c for c in changes}

    # 前月の上位10社比率（あれば）
    prev = history.load_snapshot(history.prev_ym(ym))
    prev_top10 = (sum(r["pct"] for r in prev["positions"][:10])
                  if prev and prev.get("positions") else None)

    top1 = result.positions[0] if result.positions else None
    dup_examples = [_via_line(p) for p in dup10[:3]]

    post = {
        "total_jpy": result.total_jpy,
        "top10_pct": top10_pct,
        "multi_fund_count_top10": dup10_n,
        "multi_fund_pct_top10": dup10_pct,
        "multi_fund_count_all": dup_all_n,
        "multi_fund_pct_all": dup_all_pct,
        "fund_count": len(funds),
        "top1": ({"ticker": top1.ticker, "pct": top1.pct_of_total,
                  "via_text": _via_text(top1)} if top1 else None),
        "rank_note": _rank_note(changes, prev_ym_used),
        "dup_examples": dup_examples,
        "proxy_note": _proxy_note(result),
        "manual_note": _manual_note(result),
        "coverage_note": _coverage_note(result),
    }

    return {
        "top10_pct": top10_pct,
        "dup10_n": dup10_n, "dup10_pct": dup10_pct,
        "dup_all_n": dup_all_n, "dup_all_pct": dup_all_pct,
        "ai_pct": ai_pct, "ai_label": ai.get("label", "実質AI・大型ハイテク"),
        "ai_criteria": ai.get("criteria", ""),
        "changes": changes, "change_by_ticker": change_by_ticker,
        "prev_ym": prev_ym_used, "prev_top10_pct": prev_top10,
        "sectors": compute.sector_breakdown(result),
        "post": post,
    }


def _short_fund(name: str) -> str:
    """「VTI 全米株式ETF」→「VTI」のように、本文で使う短い呼び方にする。"""
    return str(name).split()[0] if name else name


def _via_text(pos) -> str:
    """「VTI経由 約119万円 + QQQ経由 約17万円」形式。"""
    return " + ".join(
        f"{_short_fund(v.fund_name)}経由 {compose.man_yen(v.amount_jpy)}"
        for v in pos.via[:3])


def _via_line(pos) -> str:
    """返信文に使う「◯◯はAとBの重なりで、合わせて◯%」形式。"""
    names = [_short_fund(v.fund_name) for v in pos.via]
    if len(names) <= 2:
        via = "と".join(names)
    else:
        via = "、".join(names[:2]) + f"など{len(names)}本"
    return (f"{pos.ticker}は{via}の重なりで、"
            f"合わせて{compose.pct(pos.pct_of_total)}")


def _rank_note(changes, prev_ym_used) -> str | None:
    if not prev_ym_used:
        return None
    moved = [c for c in changes[:10]
             if c.delta is not None and abs(c.delta) >= 2]
    if not moved:
        return None
    c = max(moved, key=lambda x: abs(x.delta))
    direction = "上がって" if c.delta > 0 else "下がって"
    return (f"前月と比べると{c.ticker}が{abs(c.delta)}つ{direction}"
            f"{c.rank}位になっていました。")


#
# 返信文に載せる但し書きは短くする。ファンドごとの代用先や取得失敗の理由は
# notes.md に全部残してあるので、投稿側は「代用がある」「未取得がある」と
# 分かれば足りる。
#

def _proxy_note(result) -> str | None:
    if not result.proxies:
        return None
    return (f"投信は中身が公開されていないため、連動対象ETFの構成で"
            f"代用しています（{len(result.proxies)}本）。")


def _manual_note(result) -> str | None:
    if not result.unresolved:
        return None
    names = "、".join(_short_fund(u.fund_name) for u in result.unresolved)
    pct_ = sum(u.value_jpy for u in result.unresolved) / result.total_jpy * 100
    return (f"{names}は構成銘柄が取れず、集計から外しています"
            f"（総額の{pct_:.1f}%・要手動確認）。")


def _coverage_note(result) -> str | None:
    if result.coverage_pct >= 99.0:
        return None
    return f"個別銘柄まで分解できたのは総資産の{result.coverage_pct:.1f}%です。"


# --------------------------------------------------------------------------
# 画像コンテキスト
# --------------------------------------------------------------------------

def _render_ctx(result, metrics, ym, holdings_asof, names, sample=False) -> dict:
    from config import X_ACCOUNT

    y, m = ym.split("-")
    subtitle = f"{y}年{int(m)}月 時点 ・ ルックスルー分析"
    if sample:
        subtitle += "（サンプルデータ）"

    via_ids_seen: list[str] = []
    rows = []
    for i, p in enumerate(compute.top_n(result, 20)):
        ch = metrics["change_by_ticker"].get(p.ticker)
        for v in p.via:
            if v.fund_id not in via_ids_seen:
                via_ids_seen.append(v.fund_id)
        rows.append({
            "rank": i + 1,
            "ticker": p.ticker,
            "company": _company(p.name),
            "pct": f"{p.pct_of_total:.2f}%",
            "amount": f"¥{p.amount_jpy:,.0f}",
            "via_ids": [v.fund_id for v in p.via],
            "dup": p.is_multi_fund,
            "rank_change": (history.arrow(ch.delta)
                            if ch and metrics["prev_ym"] else ""),
        })

    legend = []
    for fid in via_ids_seen:
        label = next((v.fund_name for p in result.positions for v in p.via
                      if v.fund_id == fid), fid)
        legend.append({"id": fid, "label": label})

    top10_tone, top10_note = "flat", None
    if metrics["prev_top10_pct"] is not None:
        d = metrics["top10_pct"] - metrics["prev_top10_pct"]
        top10_note = f"前月比 {d:+.1f}pt"
        top10_tone = "up" if d > 0 else ("down" if d < 0 else "flat")

    summary = [
        {"label": "上位10社で", "value": f"{metrics['top10_pct']:.1f}%",
         "tone": top10_tone, "note": top10_note},
        {"label": "重複保有の銘柄（上位10社中）",
         "value": f"{metrics['dup10_n']}社",
         "tone": "flat", "note": f"合計 {metrics['dup10_pct']:.1f}%"},
        {"label": metrics["ai_label"], "value": f"{metrics['ai_pct']:.1f}%",
         "tone": "flat", "note": "分類は手動（fund_map.yml）"},
    ]

    return {
        "title": "わたしの資産推移｜中身の分解",
        "subtitle": subtitle,
        "account": f"@{X_ACCOUNT}",
        "total": f"¥{result.total_jpy:,.0f}",
        "coverage": f"{result.coverage_pct:.1f}%",
        "warning": _image_warning(result, names, sample),
        "legend": legend,
        "fund_colors": render.fund_colors([f["id"] for f in legend]),
        "rows": rows,
        "summary": summary,
        "footer_note": "※記録・情報共有目的であり投資助言ではありません",
    }


def _company(name: str | None) -> str:
    if not name:
        return ""
    return str(name).replace(" Inc.", "").replace(" Corp.", "").strip()


def _image_warning(result, names: dict, sample=False) -> str:
    """画像に出す注意書き。ファンドIDではなく表示名で出す。"""
    def label(fid: str) -> str:
        return names.get(fid, fid).split("（")[0]

    bits = []
    if sample:
        bits.append("⚠ サンプルデータ（実際の構成比ではありません）")
    if result.unresolved:
        bits.append("未分解＝要手動確認: "
                    + "・".join(u.fund_name for u in result.unresolved))
    if result.stale_funds:
        bits.append("前回キャッシュ使用: "
                    + "・".join(label(f) for f in result.stale_funds))
    if result.verify_funds:
        bits.append("構成銘柄が手動メンテ: "
                    + "・".join(label(f) for f in result.verify_funds))
    return "　/　".join(bits)


# --------------------------------------------------------------------------
# 出力
# --------------------------------------------------------------------------

def _payload(result, metrics, ym, holdings_asof, cons, sample=False) -> dict:
    return {
        "ym": ym,
        "generated_at": now_jst().strftime("%Y-%m-%d %H:%M JST"),
        "holdings_as_of": holdings_asof,
        "is_sample": sample,
        "total_jpy": result.total_jpy,
        "coverage_pct": round(result.coverage_pct, 3),
        "attributed_jpy": round(result.attributed_jpy),
        "uncovered_jpy": round(result.uncovered_jpy),
        "unresolved": [
            {"fund_id": u.fund_id, "fund_name": u.fund_name,
             "value_jpy": round(u.value_jpy), "reason": u.reason,
             "status": "要手動確認"}
            for u in result.unresolved],
        "proxies": result.proxies,
        "stale_funds": result.stale_funds,
        "verify_required_funds": result.verify_funds,
        "fund_coverage_pct": {k: round(v, 3)
                              for k, v in result.fund_coverage.items()},
        "sources": {
            fid: {"source": fc.source, "as_of": fc.as_of,
                  "proxy_of": fc.proxy_of, "stale": fc.stale,
                  "count": len(fc.items), "error": fc.error}
            for fid, fc in cons.items()},
        "metrics": {
            "top10_pct": round(metrics["top10_pct"], 3),
            "multi_fund_top10_count": metrics["dup10_n"],
            "multi_fund_top10_pct": round(metrics["dup10_pct"], 3),
            "multi_fund_all_count": metrics["dup_all_n"],
            "multi_fund_all_pct": round(metrics["dup_all_pct"], 3),
            "ai_megatech_pct": round(metrics["ai_pct"], 3),
            "prev_ym": metrics["prev_ym"],
            "sectors": ({k: round(v, 3) for k, v in metrics["sectors"].items()}
                        if metrics["sectors"] else None),
        },
        "positions": [
            {"rank": i + 1, "ticker": p.ticker, "name": p.name,
             "sector": p.sector,
             "amount_jpy": round(p.amount_jpy),
             "pct_of_total": round(p.pct_of_total, 4),
             "fund_count": p.fund_count,
             "via": [{"fund_id": v.fund_id, "fund_name": v.fund_name,
                      "amount_jpy": round(v.amount_jpy),
                      "weight_pct": round(v.weight_pct, 4)}
                     for v in p.via]}
            for i, p in enumerate(result.positions)],
    }


def _notes(result, metrics, cons, ym, violations, tofu_chars, font_used,
           ok_png, names, sample=False) -> str:
    def label(fid: str) -> str:
        return f"{names.get(fid, fid)}（{fid}）" if fid in names else str(fid)

    L = [f"# ルックスルー分解 {ym} メモ", ""]
    if sample:
        L += ["> ⚠ **サンプルデータでの実行**です。構成比は実際のものではありません。", ""]

    L += ["## 全体", "",
          f"- 総資産: ¥{result.total_jpy:,.0f}",
          f"- 個別銘柄まで分解できた割合: **{result.coverage_pct:.2f}%**",
          f"- 分解後の銘柄数: {len(result.positions)}",
          f"- 上位10社の合計比率: {metrics['top10_pct']:.2f}%",
          f"- 上位10社のうち2本以上のファンド経由: "
          f"{metrics['dup10_n']}社（合計 {metrics['dup10_pct']:.2f}%）",
          f"- 全体で2本以上のファンド経由: "
          f"{metrics['dup_all_n']}社（合計 {metrics['dup_all_pct']:.2f}%）",
          f"- {metrics['ai_label']}: {metrics['ai_pct']:.2f}%", ""]

    # 要手動確認
    L += ["## 要手動確認（推測では埋めていません）", ""]
    if result.unresolved:
        for u in result.unresolved:
            L.append(f"- **{u.fund_name}**（{u.fund_id}）: {u.reason} "
                     f"／ 評価額 ¥{u.value_jpy:,.0f}")
    if result.verify_funds:
        L.append("- 手動メンテのため定期確認が要る: "
                 + "、".join(label(f) for f in result.verify_funds))
    if result.stale_funds:
        L.append("- 取得に失敗し前回キャッシュを使用（stale）: "
                 + "、".join(label(f) for f in result.stale_funds))
    if not (result.unresolved or result.verify_funds or result.stale_funds):
        L.append("- なし（すべて当日取得できました）")
    L.append("")

    # 代用
    L += ["## 代用したデータ", ""]
    if result.proxies:
        for p in result.proxies:
            L.append(f"- {p['fund_name']} → **{p['proxy_of']}** の構成で代用"
                     f"（{p['reason']}）")
    else:
        L.append("- なし")
    L.append("")

    # ファンド別カバレッジ
    L += ["## ファンド別の構成比カバレッジ", "",
          "| ファンド | 構成比合計 | 銘柄数 | 出所 |", "|---|---:|---:|---|"]
    for fid, cov in result.fund_coverage.items():
        fc = cons.get(fid)
        src = (fc.source if fc and fc.source else (fc.error if fc else "—"))
        n = len(fc.items) if fc else 0
        L.append(f"| {names.get(fid, fid)} | {cov:.2f}% | {n} | {src} |")
    L.append("")

    # 前月比
    L += [f"## 前月比（{metrics['prev_ym'] or '前月データなし'}）", ""]
    if metrics["prev_ym"]:
        L += ["| 順位 | 銘柄 | 前月 | 変動 | 実質比率 | 前月差 |",
              "|---:|---|---:|---:|---:|---:|"]
        for c in metrics["changes"]:
            L.append(f"| {c.rank} | {c.ticker} | "
                     f"{c.prev_rank if c.prev_rank else '—'} | "
                     f"{history.arrow(c.delta)} | {c.pct:.2f}% | "
                     f"{f'{c.pct_delta:+.2f}pt' if c.pct_delta is not None else '—'} |")
    else:
        L.append("- 前月のスナップショットがないため比較していません（初回）。")
    L.append("")

    # 重複保有の内訳
    L += ["## 重複保有（上位10社）の経由内訳", ""]
    _, _, dup = compute.multi_fund_in_top_n(result, 10)
    if dup:
        for p in dup:
            L.append(f"- {compute.via_breakdown_text(p)}")
    else:
        L.append("- 上位10社に重複保有はありませんでした。")
    L.append("")

    # セクター
    if metrics["sectors"]:
        L += ["## セクター別の実質比率", ""]
        for k, v in list(metrics["sectors"].items())[:12]:
            L.append(f"- {k}: {v:.2f}%")
        L.append("")

    # 生成物チェック
    L += ["## 生成物チェック", "",
          f"- 画像生成: {'OK' if ok_png else '失敗（HTMLのみ出力）'}",
          f"- 使用フォント: {font_used or '未判定'}",
          f"- 豆腐（□）: {'なし' if not tofu_chars else '⚠ ' + ''.join(tofu_chars)}"]
    if violations:
        L.append("- 投稿文の要確認:")
        for name, probs in violations.items():
            for p in probs:
                L.append(f"  - {name}: {p}")
    else:
        L.append("- 投稿文: 方針チェック・文字数ともに問題なし")
    L.append("")
    return "\n".join(L)


def _check_tofu(ctx) -> tuple[bool, list[str], str]:
    try:
        return fontcheck.check_texts(render.collect_texts(ctx))
    except fontcheck.FontNotFoundError as e:
        print(f"::warning::豆腐チェックを実行できません: {e}")
        return True, [], ""


# --------------------------------------------------------------------------
# サンプルデータ
# --------------------------------------------------------------------------

def _sample_constituents(fund_ids: list[str]) -> dict:
    """tests/fixtures のサンプル構成比を読む（動作確認専用・実データではない）。"""
    raw = load_yaml(SAMPLE_FIXTURE, default=None)
    if not raw:
        raise FileNotFoundError(f"サンプルデータがありません: {SAMPLE_FIXTURE}")
    out = {}
    for fid in fund_ids:
        spec = raw.get("funds", {}).get(fid)
        if not spec:
            out[fid] = compute.FundConstituents(
                fund_id=fid, error="サンプルデータに未定義（要手動確認）")
            continue
        items = tuple(
            compute.Constituent(ticker=i["ticker"],
                                weight_pct=float(i["weight_pct"]),
                                name=i.get("name"), sector=i.get("sector"))
            for i in spec.get("items", []))
        out[fid] = compute.FundConstituents(
            fund_id=fid, items=items, as_of=str(raw.get("as_of", "")),
            source="SAMPLE", proxy_of=spec.get("proxy_of"),
            proxy_reason=spec.get("proxy_reason"),
            verify_required=bool(spec.get("verify_required")))
    return out


if __name__ == "__main__":
    sys.exit(main())
