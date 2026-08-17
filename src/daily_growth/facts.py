# -*- coding: utf-8 -*-
"""
facts.py
========
data.json（と任意で data/lookthrough.json）から、投稿に使ってよい
**事実だけ** を取り出す。

このモジュールの約束（CLAUDE.md「絶対に守ること」1に対応）
-----------------------------------------------------------
- **純粋関数だけ**。ネットワーク・ファイル読み書きを入れない。
- 取れない値は 0 でも平均値でも前日値でも埋めない。**キー自体を作らない**。
  「キーが無い＝その話題は今日は作れない」という意味にする。
- 事実はすべて data.json の値の四則演算だけで作る。外挿・推定はしない。

呼び出し側（topics.py / compose.py）は ``requires`` に必要なキーを宣言し、
揃っていない話題はそもそも候補に入れない。
"""

from __future__ import annotations

import math
import statistics
from datetime import date

# 高配当グループとグロースグループ（ETFのみ。投信は基準日がずれるため混ぜない）
HIGH_YIELD_ETFS = ("VYM", "HDV")
GROWTH_ETFS = ("QQQ", "VTI")

# マイルストーン（円）。金額は目標であって予測ではない。
MILESTONES = (50_000_000, 100_000_000, 300_000_000)

# 「何も起きなかった日」とみなす閾値
QUIET_TOTAL_PCT = 0.10
QUIET_HOLDING_PCT = 0.50


def _d(s) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def _f(v):
    """数値に変換できないもの（None・空文字）は None のまま返す。"""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct(part: float, whole: float) -> float | None:
    if not whole:
        return None
    return part / whole * 100.0


# --------------------------------------------------------------------------
# 保有一覧
# --------------------------------------------------------------------------

def holdings_of(data: dict) -> list[dict]:
    """ETF・投信をまとめた保有一覧。data.json に無い項目は入れない。"""
    out: list[dict] = []
    for key, v in (data.get("etf") or {}).items():
        jpy, prev = _f(v.get("curr_jpy")), _f(v.get("prev_jpy"))
        if jpy is None:
            continue
        out.append({
            "key": key, "label": key, "name": v.get("name", key), "kind": "ETF",
            "jpy": jpy, "prev_jpy": prev, "change_pct": _f(v.get("change_pct")),
            "price": _f(v.get("curr_price")), "asof": data.get("date"),
        })
    for code, v in (data.get("fund") or {}).items():
        jpy, prev = _f(v.get("curr_jpy")), _f(v.get("prev_jpy"))
        if jpy is None:
            continue
        out.append({
            "key": code, "label": v.get("name", code), "name": v.get("name", code),
            "kind": "投資信託", "jpy": jpy, "prev_jpy": prev,
            "change_pct": _f(v.get("change_pct")),
            "price": _f(v.get("curr_nav")), "asof": v.get("curr_date"),
        })
    return out


# --------------------------------------------------------------------------
# 本体
# --------------------------------------------------------------------------

def build(data: dict, today: date, lookthrough: dict | None = None) -> dict:
    """data.json から事実の辞書を作る。取れない項目はキーを作らない。"""
    f: dict = {}
    if not data:
        return f

    data_date = _d(data.get("date"))
    total = _f(data.get("total_jpy"))
    if data_date is None or not total:
        return f

    f["data_date"] = data_date.isoformat()
    f["age_days"] = (today - data_date).days
    f["total_jpy"] = total
    f["updated_at"] = data.get("updated_at")

    usdjpy = _f(data.get("usdjpy"))
    if usdjpy:
        f["usdjpy"] = usdjpy

    hs = holdings_of(data)
    if hs:
        f["holdings"] = hs
        f["holding_count"] = len(hs)
        _add_weights(f, hs, total)
        _add_contributions(f, hs)
        _add_cushion(f, data)
        _add_lag(f, data, data_date)
        _add_dram(f, data, total)

    _add_windows(f, data)
    _add_fx(f, data, hs, usdjpy)
    _add_history(f, data, total, data_date)
    _add_milestones(f, total)
    _add_quiet(f, hs)
    _add_lookthrough(f, lookthrough)
    return f


# --------------------------------------------------------------------------
# 構成比・集中度
# --------------------------------------------------------------------------

def _add_weights(f: dict, hs: list[dict], total: float) -> None:
    ranked = sorted(hs, key=lambda h: h["jpy"], reverse=True)
    for h in ranked:
        h["weight_pct"] = _pct(h["jpy"], total)
    f["ranked_holdings"] = ranked
    f["top_holding"] = ranked[0]
    f["concentration"] = {
        "top1_pct": _pct(ranked[0]["jpy"], total),
        "top3_pct": _pct(sum(h["jpy"] for h in ranked[:3]), total),
        "top1_label": ranked[0]["label"],
        "etf_pct": _pct(sum(h["jpy"] for h in hs if h["kind"] == "ETF"), total),
    }


# --------------------------------------------------------------------------
# 寄与（%pt）
# --------------------------------------------------------------------------

def _add_contributions(f: dict, hs: list[dict]) -> None:
    """各銘柄が総資産の前日比に何%pt効いたか。

    分母は「前日評価額の合計（為替は当日レートで揃えたもの）」。
    data.json の day_change_pct と同じ土俵なので足し上げると一致する。
    """
    if any(h["prev_jpy"] is None for h in hs):
        return
    prev_total = sum(h["prev_jpy"] for h in hs)
    if not prev_total:
        return
    rows = []
    for h in hs:
        rows.append({**h, "diff_jpy": h["jpy"] - h["prev_jpy"],
                     "contrib_pt": (h["jpy"] - h["prev_jpy"]) / prev_total * 100})
    rows.sort(key=lambda r: abs(r["contrib_pt"]), reverse=True)
    f["prev_total_jpy"] = prev_total
    f["contributions"] = rows
    f["price_change_pct"] = (sum(r["diff_jpy"] for r in rows) / prev_total) * 100
    f["price_change_jpy"] = sum(r["diff_jpy"] for r in rows)


# --------------------------------------------------------------------------
# 高配当 vs グロース（ETFのみ。投信は基準日がずれるので混ぜない）
# --------------------------------------------------------------------------

def _add_cushion(f: dict, data: dict) -> None:
    etf = data.get("etf") or {}

    def avg(keys):
        vals = [_f(etf[k].get("change_pct")) for k in keys if k in etf]
        vals = [v for v in vals if v is not None]
        return statistics.fmean(vals) if vals else None

    hi, gr = avg(HIGH_YIELD_ETFS), avg(GROWTH_ETFS)
    if hi is None or gr is None:
        return
    members = {k: _f(etf[k].get("change_pct"))
               for k in HIGH_YIELD_ETFS + GROWTH_ETFS if k in etf}
    f["cushion"] = {
        "high_yield_pct": hi, "growth_pct": gr, "diff_pt": hi - gr,
        "members": members,
        "high_yield_keys": [k for k in HIGH_YIELD_ETFS if k in etf],
        "growth_keys": [k for k in GROWTH_ETFS if k in etf],
    }
    vym, hdv = members.get("VYM"), members.get("HDV")
    if vym is not None and hdv is not None:
        f["hy_split"] = {"VYM": vym, "HDV": hdv, "diff_pt": vym - hdv,
                         "opposite": (vym > 0 > hdv) or (hdv > 0 > vym)}


# --------------------------------------------------------------------------
# ETFと投信の反映日ズレ
# --------------------------------------------------------------------------

def _add_lag(f: dict, data: dict, data_date: date) -> None:
    dates = [_d(v.get("curr_date")) for v in (data.get("fund") or {}).values()]
    dates = [d for d in dates if d]
    if not dates:
        return
    fund_date = max(dates)
    f["lag"] = {
        "etf_date": data_date.isoformat(),
        "fund_date": fund_date.isoformat(),
        "days": (data_date - fund_date).days,
        "fund_count": len(dates),
    }


def _add_dram(f: dict, data: dict, total: float) -> None:
    v = (data.get("etf") or {}).get("DRAM")
    if not v:
        return
    jpy, chg = _f(v.get("curr_jpy")), _f(v.get("change_pct"))
    if jpy is None or chg is None:
        return
    f["dram"] = {"change_pct": chg, "jpy": jpy, "weight_pct": _pct(jpy, total),
                 "price": _f(v.get("curr_price"))}


# --------------------------------------------------------------------------
# 期間比較（入金と運用を分ける）
# --------------------------------------------------------------------------

_WINDOW_LABEL = {"day": "前日", "week": "先週", "month": "先月", "ytd": "運用開始"}


def _add_windows(f: dict, data: dict) -> None:
    comps = data.get("comparisons") or {}
    out = {}
    for key, c in comps.items():
        base = _f(c.get("base_jpy"))
        market = _f(c.get("change_jpy"))
        gross = _f(c.get("gross_change_jpy"))
        flow = _f(c.get("cash_flow_jpy"))
        if base is None or market is None:
            continue
        row = {
            "key": key, "label": _WINDOW_LABEL.get(key, key),
            "base_date": c.get("base_date"), "base_jpy": base,
            "market_jpy": market, "change_pct": _f(c.get("change_pct")),
        }
        if gross is not None and flow is not None:
            row.update({"gross_jpy": gross, "cash_flow_jpy": flow,
                        "flow_share_pct": _pct(abs(flow),
                                               abs(flow) + abs(market))})
        out[key] = row
    if out:
        f["windows"] = out
    if "day" in out:
        f["day"] = out["day"]
        f["day_change_pct"] = out["day"]["change_pct"]
        f["day_change_jpy"] = out["day"]["market_jpy"]
    # 週と月で符号が逆かどうか（「月間リターンが週間と逆」）
    w, m = out.get("week"), out.get("month")
    if w and m and w["market_jpy"] and m["market_jpy"]:
        if (w["market_jpy"] > 0) != (m["market_jpy"] > 0):
            f["window_conflict"] = {"week": w, "month": m}


# --------------------------------------------------------------------------
# 為替
# --------------------------------------------------------------------------

def _add_fx(f: dict, data: dict, hs: list[dict], usdjpy: float | None) -> None:
    if not usdjpy:
        return
    usd_jpy_assets = sum(h["jpy"] for h in hs if h["kind"] == "ETF")
    if usd_jpy_assets:
        # 株価が動かないと仮定したときの為替感応度。仮定を明示して使う。
        f["fx_sim"] = {
            "usd_assets_jpy": usd_jpy_assets,
            "usdjpy": usdjpy,
            "per_yen_jpy": usd_jpy_assets / usdjpy,
            "yen10_jpy": usd_jpy_assets / usdjpy * 10,
            "yen10_pct": _pct(usd_jpy_assets / usdjpy * 10,
                              _f(data.get("total_jpy")) or 0) or 0.0,
        }

    # 前日比の「価格要因」と「為替要因」への分解。
    # 恒等式: 価格要因 + 為替要因 = 総資産の前日比（入金がない日に限る）
    day = (data.get("comparisons") or {}).get("day") or {}
    flow = _f(day.get("cash_flow_jpy"))
    base = _f(day.get("base_jpy"))
    price_jpy = _f(data.get("day_change_jpy"))
    total_change = _f(day.get("change_jpy"))
    prev_total = None
    if hs and all(h["prev_jpy"] is not None for h in hs):
        prev_total = sum(h["prev_jpy"] for h in hs)
    if (flow == 0 and base and price_jpy is not None
            and total_change is not None and prev_total):
        fx_jpy = prev_total - base
        f["fx_decomp"] = {
            "price_jpy": price_jpy,
            "fx_jpy": fx_jpy,
            "total_jpy": total_change,
            "base_jpy": base,
            "fx_share_pct": _pct(abs(fx_jpy), abs(price_jpy) + abs(fx_jpy)),
            "opposite": (price_jpy > 0 > fx_jpy) or (fx_jpy > 0 > price_jpy),
        }


# --------------------------------------------------------------------------
# 履歴（過去最高・変動の大きさ・入金履歴）
# --------------------------------------------------------------------------

def _add_history(f: dict, data: dict, total: float, data_date: date) -> None:
    hist = [h for h in (data.get("history") or [])
            if _d(h.get("date")) and _f(h.get("total_jpy"))]
    if not hist:
        return
    hist.sort(key=lambda h: str(h["date"]))
    f["history_days"] = len(hist)
    f["history_from"] = str(hist[0]["date"])[:10]
    f["total_series"] = [{"date": str(h["date"])[:10],
                          "total_jpy": _f(h["total_jpy"])} for h in hist]

    past = [h for h in hist if str(h["date"])[:10] < data_date.isoformat()]
    if past:
        peak = max(past, key=lambda h: _f(h["total_jpy"]))
        peak_jpy = _f(peak["total_jpy"])
        f["record"] = {
            "prev_high_jpy": peak_jpy,
            "prev_high_date": str(peak["date"])[:10],
            "is_new_high": total >= peak_jpy,
            "gap_jpy": total - peak_jpy,
            "gap_pct": _pct(total - peak_jpy, peak_jpy),
            "days_since_high": (data_date - _d(peak["date"])).days,
        }

    # 入金除外の日次リターン列（前日の総資産に対する、入金を除いた増減）
    rets: list[tuple[str, float]] = []
    for prev, cur in zip(hist, hist[1:]):
        p, c = _f(prev["total_jpy"]), _f(cur["total_jpy"])
        cf = _f(cur.get("cash_flow_jpy")) or 0.0
        if not p:
            continue
        rets.append((str(cur["date"])[:10], (c - cf - p) / p * 100))
    if len(rets) >= 20:
        vals = [r for _, r in rets]
        sigma = statistics.pstdev(vals)
        today_r = rets[-1][1] if rets[-1][0] == data_date.isoformat() else None
        f["volatility"] = {
            "n": len(vals), "sigma_pct": sigma,
            "mean_pct": statistics.fmean(vals),
            "max_pct": max(vals), "min_pct": min(vals),
            "today_pct": today_r,
            "z": (today_r / sigma) if (today_r is not None and sigma) else None,
        }
    if len(rets) >= 2 and rets[-1][0] == data_date.isoformat():
        prev_r, today_r = rets[-2][1], rets[-1][1]
        f["reversal"] = {
            "prev_date": rets[-2][0], "prev_pct": prev_r, "today_pct": today_r,
            "flipped": (prev_r > 0 > today_r) or (today_r > 0 > prev_r),
        }

    # 1年前の自分（±10日以内に実データがあるときだけ）
    for h in hist:
        d = _d(h["date"])
        age = (data_date - d).days
        if 355 <= age <= 375:
            past = _f(h["total_jpy"])
            f["year_ago"] = {
                "date": d.isoformat(), "days": age, "total_jpy": past,
                "diff_jpy": total - past, "diff_pct": _pct(total - past, past),
            }
            break

    flows = [(str(h["date"])[:10], _f(h.get("cash_flow_jpy")) or 0.0)
             for h in hist]
    buys = [(d, v) for d, v in flows if v > 0]
    if buys:
        last_d, last_v = buys[-1]
        f["flows"] = {
            "last_date": last_d, "last_jpy": last_v,
            "days_since": (data_date - _d(last_d)).days,
            "count": len(buys),
            "sum_all_jpy": sum(v for _, v in buys),
            "sum_30d_jpy": sum(v for d, v in buys
                               if (data_date - _d(d)).days <= 30),
        }

    # 実績ペース（1日あたりの総資産の増減。入金を含む「見たままの実績」）
    span = (data_date - _d(hist[0]["date"])).days
    if span >= 30:
        first = _f(hist[0]["total_jpy"])
        f["pace"] = {"days": span, "from_date": str(hist[0]["date"])[:10],
                     "from_jpy": first,
                     "per_day_jpy": (total - first) / span}


def _add_milestones(f: dict, total: float) -> None:
    nxt = next((m for m in MILESTONES if m > total), None)
    if nxt is None:
        return
    f["milestone"] = {
        "target_jpy": float(nxt),
        "progress_pct": _pct(total, nxt),
        "remaining_jpy": nxt - total,
    }
    pace = f.get("pace")
    if pace and pace["per_day_jpy"] > 0:
        days = (nxt - total) / pace["per_day_jpy"]
        if math.isfinite(days):
            f["milestone"]["days_at_pace"] = days
            f["milestone"]["years_at_pace"] = days / 365.0
            f["milestone"]["pace_days"] = pace["days"]
            f["milestone"]["pace_per_day_jpy"] = pace["per_day_jpy"]


def _add_quiet(f: dict, hs: list[dict]) -> None:
    day_pct = f.get("day_change_pct")
    chgs = [abs(h["change_pct"]) for h in hs
            if h["kind"] == "ETF" and h["change_pct"] is not None]
    if day_pct is None or not chgs:
        return
    f["quiet"] = {
        "is_quiet": abs(day_pct) < QUIET_TOTAL_PCT and max(chgs) < QUIET_HOLDING_PCT,
        "max_abs_pct": max(chgs),
        "day_pct": day_pct,
    }


def _add_lookthrough(f: dict, lookthrough: dict | None) -> None:
    """ルックスルー結果があるときだけ企業別分解を可能にする。

    無い／カバレッジ不足のときはキーを作らない＝その話題は生成しない。
    """
    if not lookthrough:
        return
    positions = lookthrough.get("positions") or lookthrough.get("top") or []
    coverage = _f(lookthrough.get("coverage_pct"))
    if coverage is None:
        coverage = _f(lookthrough.get("coverage"))
        if coverage is not None and coverage <= 1.0:
            coverage *= 100
    if not positions or coverage is None:
        return
    f["lookthrough"] = {
        "coverage_pct": coverage,
        "asof": lookthrough.get("asof") or lookthrough.get("generated_at"),
        "positions": positions[:10],
    }


# --------------------------------------------------------------------------
# 鮮度チェック
# --------------------------------------------------------------------------

def staleness(f: dict, halt_days: int, warn_days: int) -> tuple[str, str]:
    """('ok'|'warn'|'halt', 説明) を返す。data.json が古いまま作らせない。"""
    if "age_days" not in f:
        return "halt", "data.json から日付と総資産が読めませんでした"
    age = f["age_days"]
    if age < 0:
        return "halt", f"data.json の日付が未来です（{f['data_date']}）"
    if age > halt_days:
        return "halt", (f"data.json が古すぎます（{f['data_date']} / {age}日前）。"
                        "価格取得が止まっている可能性があります")
    if age > warn_days:
        return "warn", f"data.json は{age}日前（{f['data_date']}）のデータです"
    return "ok", ""
