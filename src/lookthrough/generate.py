# -*- coding: utf-8 -*-
"""
generate.py
===========
ルックスルー分解の実行エントリ。

    python -m src.lookthrough.generate              # 通常（公開データを取得）
    python -m src.lookthrough.generate --offline    # 取得せずキャッシュのみ
    python -m src.lookthrough.generate --sample     # サンプルデータで動作確認
    python -m src.lookthrough.generate --dry-run    # 取得状況とカバレッジだけ見る

出力先: ``output/lookthrough/YYYY-MM/``
  lookthrough.png / post_100.txt / post_150.txt / post_165.txt
  reply.txt / data.json / notes.md

生成を中止する条件（＝実態と違う数字を投稿させないための門）
------------------------------------------------------------
1. ``coverage_policy: required`` のファンドの構成銘柄が取れなかった
2. 分解カバレッジが ``config.yml`` の ``coverage.halt_below`` を下回った

「カバレッジ72%のまま『上位10社で◯%』という投稿文を作る」ことを防ぐ。
中止した場合も notes.md と通知には理由と各ファンドの取得状況を残す。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from src.common import fontcheck, postlog, settings
from src.common.notify import notify
from src.common.textcheck import zenkaku_len
from src.common.util import REPO_ROOT, load_yaml, now_jst
from src.lookthrough import compose, compute, constituents, history, render
from src.lookthrough.constituents import (
    collect, freshness_label, load_fund_map, load_holdings,
)

SAMPLE_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "constituents_sample.yml"


def out_root() -> Path:
    return settings.path_of("output") / "lookthrough"


# --------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="保有ファンドのルックスルー分解")
    ap.add_argument("--offline", action="store_true",
                    help="公開データを取得せず data/cache のみ使う")
    ap.add_argument("--sample", action="store_true",
                    help="サンプル構成データで通しの動作確認をする（実データではない）")
    ap.add_argument("--dry-run", action="store_true",
                    help="投稿文と画像を作らず、取得状況とカバレッジだけ出す")
    ap.add_argument("--ym", default=None, help="出力月（既定は当月 YYYY-MM）")
    ap.add_argument("--allow-tofu", action="store_true",
                    help="豆腐（□）が出ても失敗にしない")
    args = ap.parse_args(argv)

    ym = args.ym or now_jst().strftime("%Y-%m")
    funds, total_jpy, holdings_asof = load_holdings()
    fmap = load_fund_map()

    if args.sample:
        cons = _sample_constituents([f.id for f in funds], fmap)
        print("⚠ サンプルデータで実行しています（実際の構成比ではありません）")
    else:
        cons = collect([f.id for f in funds], offline=args.offline,
                       fund_map=fmap)

    try:
        result = compute.look_through(funds, cons, total_jpy)
    except (compute.ReconciliationError, ValueError) as e:
        print(f"::error::ルックスルー計算に失敗: {e}")
        _notify("halt", f"ルックスルー生成失敗: {e}", critical=True)
        return 1

    names = {f.id: f.name for f in funds}
    eff_cov = result.effective_coverage_pct(settings.exclude_declared())

    # ---- 取得状況の要約（dry-run でも中止時でも同じものを出す） -----------
    status = _status_report(result, cons, names, eff_cov, ym, sample=args.sample)
    print(status)

    if args.dry_run:
        path = _write_report(f"dry_run_{ym}.md", status)
        print(f"\n✅ dry-run: {path}")
        print("   投稿文と画像は生成していません。")
        return 0

    # ---- 生成中止の判定 --------------------------------------------------
    halt = _halt_reason(result, eff_cov, names)
    if halt:
        print(f"::error::{halt}")
        outdir = out_root() / ("sample" if args.sample else ym)
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "notes.md").write_text(
            f"# ルックスルー分解 {ym} — 生成中止\n\n"
            f"> **{halt}**\n\n"
            "実態と違う数字で投稿文を作らないため、生成を中止しました。\n"
            "下の取得状況を見て、`data/manual/` にCSVを置くか、\n"
            "そのファンドを `coverage_policy: excluded` に変えてください。\n\n"
            + status, encoding="utf-8")
        _notify("halt", f"ルックスルー生成中止 {ym}: {halt}", critical=True)
        print(f"   詳細: {outdir / 'notes.md'}")
        return 1

    if eff_cov < settings.coverage_warn_below() * 100:
        print(f"::warning::カバレッジ {eff_cov:.1f}% は目安の "
              f"{settings.coverage_warn_below() * 100:.0f}% を下回っています")

    metrics = _metrics(result, funds, fmap, ym)
    outdir = out_root() / ("sample" if args.sample else ym)
    outdir.mkdir(parents=True, exist_ok=True)

    # ---- 画像 -----------------------------------------------------------
    ctx = _render_ctx(result, metrics, ym, names, cons, eff_cov,
                      sample=args.sample)
    layout: dict = {}
    ok_png = render.render(ctx, outdir / "lookthrough.png", report=layout)
    if layout.get("overflow_px"):
        print(f"::warning::画像の中身が {layout['overflow_px']}px はみ出しています"
              "（表の行数か文言を減らしてください）")

    tofu_ok, tofu_chars, font_used = _check_tofu(ctx)
    if not tofu_ok and not args.allow_tofu:
        print(f"::error::画像に豆腐が出ます（グリフ欠落: {''.join(tofu_chars)}）")
        _notify("halt", f"ルックスルー画像に豆腐: {''.join(tofu_chars)}", critical=True)
        return 1

    # ---- 投稿文 ---------------------------------------------------------
    limits = settings.post_limits()
    posts = compose.build_posts(metrics["post"], limits=limits)
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
    payload = _payload(result, metrics, ym, holdings_asof, cons, eff_cov,
                       sample=args.sample)
    (outdir / "data.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    # 機能②（指数寄与）が読む feed は、十分に分解できたときだけ更新する
    if not args.sample:
        feed_min = settings.coverage_feed_min() * 100
        if eff_cov >= feed_min:
            settings.path_of("feed").write_text(
                json.dumps(payload, ensure_ascii=False, indent=1),
                encoding="utf-8")
        else:
            print(f"::warning::カバレッジ {eff_cov:.1f}% のため "
                  f"{settings.path_of('feed').name} は更新しません")

    # ---- notes.md -------------------------------------------------------
    (outdir / "notes.md").write_text(
        _notes(result, metrics, cons, ym, violations, tofu_chars, font_used,
               ok_png, names, status, sample=args.sample),
        encoding="utf-8")

    # ---- 月次スナップショット（サンプル実行では汚さない） ----------------
    if not args.sample:
        history.save_snapshot(ym, result)
        postlog.append_row(date.today().isoformat(), "ルックスルー", f"lt-{ym}",
                           "画像+本文", int(zenkaku_len(posts[max(limits)])),
                           ok_png)

    print(f"\n✅ 出力: {outdir}")
    if violations:
        print(f"   ⚠ 投稿文の要確認: {len(violations)}件（notes.md 参照）")

    if result.stale_funds:
        _notify("stale", f"ルックスルー {ym}: キャッシュ使用 "
                         f"{len(result.stale_funds)}本")
    for ch in result.changes:
        _notify("constituent_change",
                f"ルックスルー {ym}: {ch['fund_name']} の{ch['note']}")
    _notify("halt", f"ルックスルー生成完了 {ym}: カバレッジ {eff_cov:.1f}% / "
                    f"上位10社 {metrics['top10_pct']:.1f}%", always=True)
    return 0


def _notify(event: str, message: str, critical: bool = False,
            always: bool = False) -> None:
    """config.yml の notify_on に入っている種類だけ通知する。"""
    if always or settings.notify_on(event):
        notify(message, critical=critical)
    else:
        print(f"[notify:skip:{event}] {message}")


def _halt_reason(result, eff_cov: float, names: dict) -> str | None:
    """生成を中止すべき理由。無ければ None。"""
    missing = result.missing_required
    if missing:
        who = "、".join(f"{u.fund_name}（{u.reason}）" for u in missing)
        return f"required 指定のファンドを分解できませんでした: {who}"

    halt_below = settings.coverage_halt_below() * 100
    if eff_cov < halt_below:
        return (f"分解カバレッジが {eff_cov:.1f}% で、下限の "
                f"{halt_below:.0f}% を下回っています")
    return None


def _write_report(filename: str, body: str) -> Path:
    path = settings.path_of("reports") / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# 取得状況の要約
# --------------------------------------------------------------------------

def _status_report(result, cons, names, eff_cov, ym, sample=False) -> str:
    L = [f"## 取得状況 {ym}", ""]
    if sample:
        L += ["> ⚠ サンプルデータでの実行です。実際の構成比ではありません。", ""]

    L += [f"- 総資産: ¥{result.total_jpy:,.0f}",
          f"- 分解カバレッジ（対象外を除く）: **{eff_cov:.2f}%**",
          f"- 分解カバレッジ（総資産に対して）: {result.coverage_pct:.2f}%",
          f"- 分解後の銘柄数: {len(result.positions)}",
          f"- 下限 {settings.coverage_halt_below() * 100:.0f}% / "
          f"警告 {settings.coverage_warn_below() * 100:.0f}%", "",
          "| ファンド | 方針 | 採用source | 件数 | 構成比計 | 鮮度 | 状態 |",
          "|---|---|---|---:|---:|---|---|"]

    for fid, cov in result.fund_coverage.items():
        fc = cons.get(fid)
        name = names.get(fid, fid)
        if fc is None:
            L.append(f"| {name} | — | — | 0 | 0.00% | — | 定義なし |")
            continue
        if fc.is_excluded:
            L.append(f"| {name} | excluded | — | — | — | — | 対象外（意図的） |")
            continue
        state = "OK" if fc.ok else f"NG: {fc.error}"
        if fc.stale:
            state = f"キャッシュ使用（{fc.age_days}日前）"
        fresh = freshness_label(fc.age_days)
        L.append(f"| {name} | {fc.policy} | {fc.source_id or '—'} | "
                 f"{len(fc.items)} | {cov:.2f}% | {fresh} | {state} |")

    # source ごとの試行結果（priority 1 が落ちて下位で拾っている検出用）
    detail = []
    for fid, fc in cons.items():
        if fc.is_excluded or not fc.attempts:
            continue
        for a in fc.attempts:
            detail.append(f"- {names.get(fid, fid)} … {a.summary}")
    if detail:
        L += ["", "### source の試行結果", ""] + detail

    degraded = _degraded(cons)
    if degraded:
        L += ["", "### ⚠ priority 1 が失敗しているファンド", ""]
        L += [f"- {names.get(f, f)}（採用: {s}）" for f, s in degraded]

    return "\n".join(L)


def _degraded(cons) -> list[tuple[str, str]]:
    """priority 1 が失敗し、下位の source で拾っているファンド。"""
    out = []
    for fid, fc in cons.items():
        if fc.is_excluded or not fc.ok or not fc.attempts:
            continue
        first = min(fc.attempts, key=lambda a: a.priority, default=None)
        if first is not None and not first.ok:
            out.append((fid, fc.source_id or "—"))
    return out


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
        # 分解できたファンドの本数（対象外は数えない）
        "fund_count": len(funds) - len(result.excluded),
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
        "changes": changes, "change_by_ticker": change_by_ticker,
        "prev_ym": prev_ym_used, "prev_top10_pct": prev_top10,
        "sectors": compute.sector_breakdown(result),
        "post": post,
    }


def _short_fund(name: str) -> str:
    """「VTI 全米株式ETF」→「VTI」のように、本文で使う短い呼び方にする。"""
    return str(name).split()[0] if name else name


def _via_text(pos) -> str:
    return " + ".join(
        f"{_short_fund(v.fund_name)}経由 {compose.man_yen(v.amount_jpy)}"
        for v in pos.via[:3])


def _via_line(pos) -> str:
    names = [_short_fund(v.fund_name) for v in pos.via]
    via = "と".join(names) if len(names) <= 2 else \
        "、".join(names[:2]) + f"など{len(names)}本"
    return f"{pos.ticker}は{via}の重なりで、合わせて{compose.pct(pos.pct_of_total)}"


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
# 返信文の但し書きは短くする。ファンドごとの代用先や取得の詳細は
# notes.md に全部残してあるので、投稿側は事実が分かれば足りる。
#

def _proxy_note(result) -> str | None:
    if not result.proxies:
        return None
    return (f"投信は中身が公開されていないため、連動対象ETFの構成で"
            f"代用しています（{len(result.proxies)}本）。")


def _manual_note(result) -> str | None:
    """未取得（＝取れなかったもの）だけを書く。対象外は別扱い。"""
    if not result.unresolved:
        return None
    names = "、".join(_short_fund(u.fund_name) for u in result.unresolved)
    pct_ = sum(u.value_jpy for u in result.unresolved) / result.total_jpy * 100
    return (f"{names}は構成銘柄が取れず、集計から外しています"
            f"（総額の{pct_:.1f}%）。")


def _coverage_note(result) -> str | None:
    if result.coverage_pct >= 99.0:
        return None
    return f"個別銘柄まで分解できたのは総資産の{result.coverage_pct:.1f}%です。"


# --------------------------------------------------------------------------
# 画像コンテキスト
# --------------------------------------------------------------------------

def _render_ctx(result, metrics, ym, names, cons, eff_cov, sample=False) -> dict:
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

    asof, asof_warn = _asof_line(cons)
    return {
        "title": "わたしの資産推移｜中身の分解",
        "subtitle": subtitle,
        "account": settings.x_handle(with_at=True),
        "total": f"¥{result.total_jpy:,.0f}",
        "coverage": f"{eff_cov:.1f}%",
        "asof": asof,
        "asof_warn": asof_warn,
        "warning": _image_warning(result, names, sample),
        "legend": legend,
        "fund_colors": render.fund_colors([f["id"] for f in legend]),
        "rows": rows,
        "summary": summary,
        "footer_note": "※記録・情報共有目的であり投資助言ではありません",
    }


def _asof_line(cons) -> tuple[str, bool]:
    """構成比の基準日。古いものがあれば強調表示する。"""
    dates = [fc.as_of for fc in cons.values()
             if fc.ok and not fc.is_excluded and fc.as_of]
    ages = [fc.age_days for fc in cons.values()
            if fc.ok and not fc.is_excluded and fc.age_days is not None]
    oldest = max(ages) if ages else None
    ok_days, _ = settings.freshness_days()
    warn = oldest is not None and oldest > ok_days

    if not dates:
        return "構成比基準日 —", warn
    base = min(dates).replace("-", "/")
    label = f"構成比基準日 {base}"
    if warn:
        label += f"（最古 {oldest}日前）"
    return label, warn


def _company(name: str | None) -> str:
    if not name:
        return ""
    return str(name).replace(" Inc.", "").replace(" Corp.", "").strip()


def _image_warning(result, names: dict, sample=False) -> str:
    """画像に出す注意書き。

    excluded（意図的に対象外にしたもの）は「要手動確認」ではなく
    「分解対象外」として、合計比率つきで淡々と書く。
    """
    def label(fid: str) -> str:
        return names.get(fid, fid).split("（")[0]

    bits = []
    if sample:
        bits.append("⚠ サンプルデータ（実際の構成比ではありません）")
    if result.excluded:
        who = "・".join(_short_fund(e.fund_name) for e in result.excluded)
        pct_ = result.excluded_jpy / result.total_jpy * 100
        bits.append(f"分解対象外：{who}（合計{pct_:.1f}%）")
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

def _payload(result, metrics, ym, holdings_asof, cons, eff_cov,
             sample=False) -> dict:
    return {
        "ym": ym,
        "generated_at": now_jst().strftime("%Y-%m-%d %H:%M JST"),
        "holdings_as_of": holdings_asof,
        "is_sample": sample,
        "total_jpy": result.total_jpy,
        "coverage_pct": round(result.coverage_pct, 3),
        "effective_coverage_pct": round(eff_cov, 3),
        "attributed_jpy": round(result.attributed_jpy),
        "uncovered_jpy": round(result.uncovered_jpy),
        "excluded_jpy": round(result.excluded_jpy),
        "excluded": [
            {"fund_id": e.fund_id, "fund_name": e.fund_name,
             "value_jpy": round(e.value_jpy), "reason": e.reason,
             "status": "分解対象外"}
            for e in result.excluded],
        "unresolved": [
            {"fund_id": u.fund_id, "fund_name": u.fund_name,
             "value_jpy": round(u.value_jpy), "reason": u.reason,
             "policy": u.policy, "status": "要手動確認"}
            for u in result.unresolved],
        "proxies": result.proxies,
        "stale_funds": result.stale_funds,
        "verify_required_funds": result.verify_funds,
        "constituent_changes": result.changes,
        "fund_coverage_pct": {k: round(v, 3)
                              for k, v in result.fund_coverage.items()},
        "sources": {
            fid: {"source_id": fc.source_id, "source": fc.source,
                  "as_of": fc.as_of, "age_days": fc.age_days,
                  "freshness": freshness_label(fc.age_days),
                  "proxy_of": fc.proxy_of, "stale": fc.stale,
                  "policy": fc.policy, "count": len(fc.items),
                  "error": fc.error,
                  "attempts": [
                      {"id": a.id, "priority": a.priority, "ok": a.ok,
                       "count": a.count, "elapsed_ms": a.elapsed_ms,
                       "error": a.error, "problems": list(a.problems)}
                      for a in fc.attempts]}
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
           ok_png, names, status, sample=False) -> str:
    L = [f"# ルックスルー分解 {ym} メモ", ""]
    if sample:
        L += ["> ⚠ **サンプルデータでの実行**です。構成比は実際のものではありません。", ""]

    L += ["## 全体", "",
          f"- 総資産: ¥{result.total_jpy:,.0f}",
          f"- 分解カバレッジ（対象外を除く）: **"
          f"{result.effective_coverage_pct(settings.exclude_declared()):.2f}%**",
          f"- 分解後の銘柄数: {len(result.positions)}",
          f"- 上位10社の合計比率: {metrics['top10_pct']:.2f}%",
          f"- 上位10社のうち2本以上のファンド経由: "
          f"{metrics['dup10_n']}社（合計 {metrics['dup10_pct']:.2f}%）",
          f"- 全体で2本以上のファンド経由: "
          f"{metrics['dup_all_n']}社（合計 {metrics['dup_all_pct']:.2f}%）",
          f"- {metrics['ai_label']}: {metrics['ai_pct']:.2f}%", ""]

    # 分解対象外（意図的）
    if result.excluded:
        L += ["## 分解対象外（意図的・警告ではありません）", ""]
        for e in result.excluded:
            L.append(f"- **{e.fund_name}**（{e.fund_id}）: ¥{e.value_jpy:,.0f}"
                     f" … {e.reason}")
        L += ["", "分解したくなったら `data/fund_map.yml` の "
              "`coverage_policy` を `best_effort` に変え、"
              "`data/manual/` にCSVを置いてください。", ""]

    # 要手動確認（取れなかったもの）
    L += ["## 要手動確認（推測では埋めていません）", ""]
    if result.unresolved:
        for u in result.unresolved:
            L.append(f"- **{u.fund_name}**（{u.fund_id}／{u.policy}）: "
                     f"{u.reason} ／ 評価額 ¥{u.value_jpy:,.0f}")
    if result.verify_funds:
        L.append("- 手動メンテのため定期確認が要る: "
                 + "、".join(f"{names.get(f, f)}（{f}）"
                            for f in result.verify_funds))
    if result.stale_funds:
        L.append("- 取得に失敗し前回キャッシュを使用（stale）: "
                 + "、".join(f"{names.get(f, f)}（{f}）"
                            for f in result.stale_funds))
    if not (result.unresolved or result.verify_funds or result.stale_funds):
        L.append("- なし（すべて当日取得できました）")
    L.append("")

    # 銘柄入替
    if result.changes:
        L += ["## 指数の銘柄入替を検出", ""]
        for ch in result.changes:
            L.append(f"- {ch['fund_name']}: {ch['note']}")
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

    # 取得状況（source・鮮度）
    L += [status, ""]

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

    if metrics["sectors"]:
        L += ["## セクター別の実質比率", ""]
        for k, v in list(metrics["sectors"].items())[:12]:
            L.append(f"- {k}: {v:.2f}%")
        L.append("")

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

def _sample_constituents(fund_ids: list[str], fmap: dict) -> dict:
    """tests/fixtures のサンプル構成比を読む（動作確認専用・実データではない）。

    coverage_policy は本番と同じ fund_map.yml の指定を使う。
    excluded の扱いもサンプル実行で確認できるようにするため。
    """
    raw = load_yaml(SAMPLE_FIXTURE, default=None)
    if not raw:
        raise FileNotFoundError(f"サンプルデータがありません: {SAMPLE_FIXTURE}")
    specs = fmap.get("funds", {})
    out = {}
    for fid in fund_ids:
        spec = specs.get(fid, {}) or {}
        policy = str(spec.get("coverage_policy") or compute.POLICY_REQUIRED)
        if policy == compute.POLICY_EXCLUDED:
            out[fid] = compute.FundConstituents(
                fund_id=fid, policy=policy,
                excluded_reason=" ".join(
                    str(spec.get("excluded_reason") or "").split()),
                error="分解対象外（excluded）")
            continue
        s = raw.get("funds", {}).get(fid)
        if not s:
            out[fid] = compute.FundConstituents(
                fund_id=fid, policy=policy,
                error="サンプルデータに未定義（要手動確認）")
            continue
        items = tuple(
            compute.Constituent(ticker=i["ticker"],
                                weight_pct=float(i["weight_pct"]),
                                name=i.get("name"), sector=i.get("sector"))
            for i in s.get("items", [])) + _sample_tail(s.get("tail"))
        out[fid] = compute.FundConstituents(
            fund_id=fid, items=items, as_of=str(raw.get("as_of", "")),
            source="SAMPLE", source_id="sample", age_days=0, policy=policy,
            proxy_of=spec.get("proxy_for"),
            proxy_reason=spec.get("proxy_reason"),
            verify_required=bool(s.get("verify_required")))
    return out


def _sample_tail(spec: dict | None) -> tuple:
    """サンプル用の「下位銘柄の裾」を作る。

    実際のETFは数百〜数千銘柄あり、上位20件だけではカバレッジが
    50%程度にしかならない。カバレッジ闾値ゲートまで含めて動作確認
    できるように、裾の部分をダミー銘柄で埋める。
    ティッカーは SMPL0001 形式で、実在しないことが一目で分かるようにしている。
    """
    if not spec:
        return ()
    count = int(spec.get("count", 0))
    total = float(spec.get("total_weight", 0.0))
    if count <= 0 or total <= 0:
        return ()
    w = total / count
    prefix = str(spec.get("prefix", "SMPL"))
    return tuple(
        compute.Constituent(ticker=f"{prefix}{i:04d}", weight_pct=w,
                            name="（サンプルの下位銘柄）")
        for i in range(1, count + 1))


if __name__ == "__main__":
    sys.exit(main())
