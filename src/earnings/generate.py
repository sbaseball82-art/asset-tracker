# -*- coding: utf-8 -*-
"""
generate.py（機能B: 決算日連動 実況テンプレ）
=============================================
3タイミングのテキストを生成する。投稿は人間が行う。

  pre     … T-60分: 予想EPS・売上、注目点、分岐条件、保有への影響度
  post    … 発表直後: 実績 vs 予想、時間外の初動、ガイダンス要旨
  morning … 翌朝7:00: 指数寄与（構成比×騰落率）、資産への反映、翌日の論点

出力: output/earnings/YYYY-MM-DD_TICKER/{pre,post,morning}.txt

使い方:
  python -m src.earnings.generate --ticker MSFT --date 2026-07-28 --phase pre
  （スケジュール実行は src/earnings/scheduler.py が担当）

データが取れない箇所は「要手動入力」と明示する。推測値は埋めない。
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.common import postlog
from src.common.notify import notify
from src.common.textcheck import check_post
from src.common.util import MANUAL, REPO_ROOT, load_yaml, today_jst
from src.earnings import data_sources
from src.earnings.contribution import (effective_holding_pct,
                                       index_contribution,
                                       portfolio_impact_pct)

DISCLAIMER = "※報道ベースの概算。投資助言ではありません"


def _load_context(ticker: str):
    wl = load_yaml(REPO_ROOT / "data" / "watchlist.yml", default={})
    holdings = load_yaml(REPO_ROOT / "data" / "holdings.yml", default={})
    info = (wl.get("tickers", {}) or {}).get(ticker) \
        or (wl.get("macro_events", {}) or {}).get(ticker)
    if info is None:
        raise SystemExit(f"[error] watchlist に {ticker} がありません")
    fund_shares = {str(f["id"]): f["share_pct"]
                   for f in holdings.get("funds", [])}
    return wl, info, fund_shares


def _exposure(info: dict, fund_shares: dict) -> float:
    return effective_holding_pct(fund_shares, info.get("fund_weights", {}) or {})


def _fmt_eps(v) -> str:
    return MANUAL if v is None else f"{v:.2f}ドル"


def _fmt_rev(v) -> str:
    if v is None:
        return MANUAL
    return f"約{v / 1e8:,.0f}億ドル" if v > 1e6 else f"約{v:,.0f}百万ドル"


def _fmt_pct(v) -> str:
    return MANUAL if v is None else f"{v:+.1f}%"


# ------------------------------------------------------------------ pre
def build_pre(ticker: str, date_str: str, info: dict, est: dict,
              exposure: float, is_macro: bool) -> str:
    name = info.get("name_ja", ticker)
    focus = info.get("focus", MANUAL)
    if is_macro:
        return "\n".join([
            f"【まもなく】{name} 発表前の整理",
            "",
            f"・市場予想: {MANUAL}",
            f"・前回値: {MANUAL}",
            f"・注目点: {focus}",
            "",
            "分岐条件（あとで検証します）",
            f"・予想より強ければ → 金利上昇・株は重くなる方向とみています",
            f"・予想より弱ければ → 利下げ観測で株に追い風とみています",
            "",
            "私は結果で売買はせず、数字だけ淡々と記録します。",
            "",
            DISCLAIMER,
        ])
    return "\n".join([
        f"【T-60分】{name}（{ticker}）決算前の整理",
        "",
        f"・予想EPS: {_fmt_eps(est['eps_estimate'])}",
        f"・予想売上高: {_fmt_rev(est['revenue_estimate'])}",
        f"・市場が注目する1点: {focus}",
        f"・私の実効保有比率: 約{exposure:.1f}%（指数経由）",
        "",
        "分岐条件（あとで検証します）",
        "・EPSと売上の両ビート＋ガイダンス上方 → 素直に上とみています",
        "・EPSビートでもガイダンス弱め → 反落パターンを警戒しています",
        "",
        "結果が出ても私は売買しません。数字の答え合わせだけします。",
        "",
        DISCLAIMER,
    ])


# ----------------------------------------------------------------- post
def build_post_phase(ticker: str, date_str: str, info: dict, est: dict,
                     is_macro: bool) -> str:
    name = info.get("name_ja", ticker)
    if is_macro:
        return "\n".join([
            f"【結果】{name}",
            "",
            f"・結果: {MANUAL}",
            f"・市場予想: {MANUAL}",
            f"・直後の反応（先物/為替）: {MANUAL}",
            "",
            f"（解釈: {MANUAL}）",
            "",
            DISCLAIMER,
        ])
    ea, ee = est["eps_actual"], est["eps_estimate"]
    if ea is not None and ee is not None:
        beat = "ビート" if ea >= ee else "ミス"
        eps_line = f"・EPS: {ea:.2f}ドル（予想 {ee:.2f}ドル → {beat}）"
    else:
        eps_line = f"・EPS: {_fmt_eps(ea)}（予想 {_fmt_eps(ee)}）"
    ra, re_ = est["revenue_actual"], est["revenue_estimate"]
    rev_line = f"・売上高: {_fmt_rev(ra)}（予想 {_fmt_rev(re_)}）"
    return "\n".join([
        f"【速報】{name}（{ticker}）決算",
        "",
        eps_line,
        rev_line,
        f"・時間外の初動: {MANUAL}（※時間外の値動きです）",
        f"・ガイダンス要旨: {MANUAL}",
        "",
        "時間外は流動性が薄いので、私は翌日の終値まで判断を保留します。",
        "",
        DISCLAIMER,
    ])


# -------------------------------------------------------------- morning
def build_morning(ticker: str, date_str: str, info: dict,
                  change_pct: float | None, exposure: float,
                  is_macro: bool) -> str:
    name = info.get("name_ja", ticker)
    if is_macro:
        return "\n".join([
            f"【翌朝の整理】{name}後のマーケット",
            "",
            f"・S&P500: {MANUAL} / NASDAQ: {MANUAL}",
            f"・金利・ドル円の反応: {MANUAL}",
            f"・自分の資産への反映: {MANUAL}",
            "",
            f"（解釈: {MANUAL}）",
            "",
            DISCLAIMER,
        ])

    spw = float(info.get("sp500_weight") or 0)
    qqw = float(info.get("qqq_weight") or 0)
    if change_pct is not None:
        contrib = index_contribution(spw, change_pct)
        impact = portfolio_impact_pct(exposure, change_pct)
        chg_s = f"{change_pct:+.1f}%"
        contrib_s = f"約{contrib:+.2f}%pt"
        impact_s = f"約{impact:+.2f}%"
    else:
        chg_s, contrib_s, impact_s = MANUAL, MANUAL, MANUAL

    lines = [
        f"【翌朝の整理】{name}（{ticker}） {chg_s}",
        "",
        f"・S&P500の構成比 約{spw:.1f}% → 指数寄与 {contrib_s}",
    ]
    if qqw:
        lines.append(f"・QQQでは約{qqw:.1f}%組入れ、そのぶん振れが大きい")
    lines += [
        f"・私の実効保有比率は約{exposure:.1f}% → 資産全体への影響は{impact_s}",
        "",
        "1銘柄の決算でも、指数経由だとこの程度に薄まるのだと思います。",
        "だから私は決算で売買せず、翌朝に数字だけ整理しています。",
        "",
        f"・翌日の論点: {info.get('focus', MANUAL)}の市場評価が定まるか",
        "",
        DISCLAIMER,
    ]
    return "\n".join(lines)


# ----------------------------------------------------------------- main
def generate(ticker: str, date_str: str, phase: str,
             dry_run: bool = False) -> Path:
    wl, info, fund_shares = _load_context(ticker)
    is_macro = ticker in (wl.get("macro_events", {}) or {})
    exposure = _exposure(info, fund_shares)

    est = {"eps_estimate": None, "eps_actual": None,
           "revenue_estimate": None, "revenue_actual": None, "hour": None}
    if not is_macro and phase in ("pre", "post"):
        est = data_sources.get_earnings_estimates(ticker, date_str, date_str)

    if phase == "pre":
        text = build_pre(ticker, date_str, info, est, exposure, is_macro)
    elif phase == "post":
        text = build_post_phase(ticker, date_str, info, est, is_macro)
    elif phase == "morning":
        change = None if is_macro else data_sources.get_price_change_pct(ticker)
        text = build_morning(ticker, date_str, info, change, exposure, is_macro)
    else:
        raise SystemExit(f"[error] 不明なphase: {phase}")

    ok, n, warn = check_post(text)
    if not ok:
        print(f"::warning::{ticker} {phase} {warn}")

    out_dir = REPO_ROOT / "output" / "earnings" / f"{date_str}_{ticker}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{phase}.txt"
    out_path.write_text(text, encoding="utf-8")

    if not dry_run:
        postlog.append_row(today_jst().isoformat(), "earnings",
                           f"{date_str}_{ticker}", phase, n, False)
    critical = (phase == "pre")  # T-60分は遅延が致命的
    notify(f"earnings 生成完了: {ticker} {phase} → "
           f"{out_path.relative_to(REPO_ROOT)}"
           + ("\n（要手動入力の欄があります）" if MANUAL in text else ""),
           critical=critical)
    return out_path


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--date", required=True, help="米国現地の発表日 YYYY-MM-DD")
    ap.add_argument("--phase", required=True, choices=["pre", "post", "morning"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    out = generate(args.ticker, args.date, args.phase, dry_run=args.dry_run)
    print(f"[done] {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
