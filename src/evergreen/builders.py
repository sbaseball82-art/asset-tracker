# -*- coding: utf-8 -*-
"""
builders.py
===========
保存版トピックの中身（表/チェックリスト/折れ線の描画スペックと、
post.txt に差し込む計算値）を組み立てる。

戻り値: (title, subtitle, spec, values, stale, stale_asof)
  spec   … src/common/render.py に渡す描画スペック
  values … post/ammo テンプレの {placeholder} に差し込む計算値
"""

from datetime import date, timedelta

from src.common.util import REPO_ROOT, load_yaml
from src.evergreen import etf_data


def build(topic: dict, today: date) -> tuple[str, str, dict, dict, bool, str]:
    builder = topic.get("builder", "static")
    if builder == "static":
        return _build_static(topic)
    if builder == "etf_overlap":
        return _build_etf_overlap(topic)
    if builder == "checklist_earnings":
        return _build_checklist_earnings(topic, today)
    if builder == "line_sim":
        return _build_line_sim(topic)
    raise ValueError(f"未対応builder: {builder}")


# ---------------------------------------------------------------- static
def _build_static(topic: dict):
    fmt = topic["format"]
    if fmt == "checklist":
        cl = topic["checklist"]
        return cl["title"], cl.get("subtitle", ""), {"items": cl["items"]}, {}, False, ""
    tbl = topic["table"]
    spec = {"columns": tbl["columns"], "rows": tbl["rows"]}
    return tbl["title"], tbl.get("subtitle", ""), spec, {}, False, ""


# ------------------------------------------------------------ etf_overlap
def _build_etf_overlap(topic: dict):
    params = topic.get("params", {})
    etfs = params["etfs"]
    refresh = bool(params.get("refresh"))
    cache = etf_data.load_constituents(refresh=refresh)
    stale = bool(cache.get("stale", True))
    asof = str(cache.get("as_of", ""))

    values, rows = {}, []
    for i, a in enumerate(etfs):
        for b in etfs[i + 1:]:
            n, common = etf_data.overlap(cache, a, b)
            values[f"overlap_{a}_{b}"] = n
            label_a = "FANG+" if a == "FANGPLUS" else a
            label_b = "FANG+" if b == "FANGPLUS" else b
            rows.append({
                "cells": [f"{label_a} × {label_b}", f"{n} / 10",
                          " ".join(common[:6]) + ("…" if len(common) > 6 else "")],
                "highlight": n >= 7,
            })
    spec = {
        "columns": [{"label": "組み合わせ"}, {"label": "上位10銘柄の重複", "num": True},
                    {"label": "共通銘柄"}],
        "rows": rows,
    }
    subtitle = f"上位10銘柄ベースの概算 / as of {asof}"
    note = params.get("note")
    if note:
        subtitle += f" / {note}"
    return topic["theme"], subtitle, spec, values, stale, asof


# ---------------------------------------------------- checklist_earnings
def _build_checklist_earnings(topic: dict, today: date):
    params = topic.get("params", {})
    days_ahead = int(params.get("days_ahead", 21))
    cal = load_yaml(REPO_ROOT / "data" / "earnings_calendar.yml",
                    default={"events": []})
    wl = load_yaml(REPO_ROOT / "data" / "watchlist.yml", default={})
    names = {k: v.get("name_ja", k)
             for k, v in {**wl.get("tickers", {}), **wl.get("macro_events", {})}.items()}

    end = today + timedelta(days=days_ahead)
    items = []
    for ev in sorted(cal.get("events", []), key=lambda e: e["date"]):
        d = date.fromisoformat(str(ev["date"]))
        if today <= d <= end:
            tk = ev["ticker"]
            jst = str(ev.get("announce_jst", ""))[5:16].replace("-", "/")
            items.append({
                "date": d.strftime("%m/%d"),
                "label": f"{names.get(tk, tk)}（{tk}） {ev.get('session', '')}",
                "note": f"日本時間 {jst}頃" if jst else "",
            })
    values = {"count": len(items), "days_ahead": days_ahead}
    subtitle = (f"{today.strftime('%Y/%m/%d')}時点 / 今後{days_ahead}日 / "
                "日時は日本時間・概算（変更されることがあります）")
    return "決算・イベント日程チェックリスト", subtitle, {"items": items}, values, False, ""


# ---------------------------------------------------------------- line_sim
def _build_line_sim(topic: dict):
    p = topic["params"]
    mode = p["mode"]
    if mode == "reinvest_diff":
        return _sim_reinvest(topic, p)
    if mode == "dca_vs_lump":
        return _sim_dca(topic, p)
    raise ValueError(f"未対応シミュレーション: {mode}")


def _sim_reinvest(topic: dict, p: dict):
    principal = float(p["principal"])
    years = int(p["years"])
    g = float(p["growth_pct"]) / 100
    y = float(p["yield_pct"]) / 100

    with_r, without_r, cash = [principal], [principal], 0.0
    for _ in range(years):
        with_r.append(with_r[-1] * (1 + g + y))       # 分配も再投資
        cash += without_r[-1] * y                     # 分配は受取（非再投資）
        without_r.append(without_r[-1] * (1 + g))
    man = 10000
    values = {
        "with_final": round(with_r[-1] / man),
        "without_final": round(without_r[-1] / man),
        "cash_total": round(cash / man),
        "diff_pct": round((with_r[-1] / (without_r[-1] + cash) - 1) * 100),
    }
    spec = {
        "series": [
            {"label": "再投資あり", "values": [v / man for v in with_r]},
            {"label": "再投資なし(元本のみ)", "values": [v / man for v in without_r]},
        ],
        "x_labels": [f"{i}年" for i in range(0, years + 1, max(years // 10, 1))],
    }
    subtitle = (f"概算シミュレーション / 元本{principal / man:.0f}万円・"
                f"成長{p['growth_pct']}%・分配{p['yield_pct']}%・税引前")
    return topic["theme"], subtitle, spec, values, False, ""


def _sim_dca(topic: dict, p: dict):
    principal = float(p["principal"])
    years = int(p["years"])
    g = float(p["growth_pct"]) / 100

    lump = [principal]
    for _ in range(years):
        lump.append(lump[-1] * (1 + g))

    # 分割: 初年度に12分割で投入（年内均等投入＝平均半年運用の近似）
    vals = [0.0]
    v = principal * (1 + g / 2)             # 1年目末
    vals.append(v)
    for _ in range(years - 1):
        v *= (1 + g)
        vals.append(v)
    man = 10000
    values = {
        "lump_final": round(lump[-1] / man),
        "dca_final": round(vals[-1] / man),
        "lump_win_pct": 68,  # 過去データの通説値（報道ベースの概算・出典明記して使う）
    }
    spec = {
        "series": [
            {"label": "一括投資", "values": [v / man for v in lump]},
            {"label": "12ヶ月分割", "values": [v / man for v in vals]},
        ],
        "x_labels": [f"{i}年" for i in range(0, years + 1, max(years // 10, 1))],
    }
    subtitle = (f"概算シミュレーション / {principal / man:.0f}万円・"
                f"年率{p['growth_pct']}%想定・税引前")
    return topic["theme"], subtitle, spec, values, False, ""
