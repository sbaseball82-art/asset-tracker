# -*- coding: utf-8 -*-
"""
topics.py
=========
ネタプール（``data/daily_growth_topics.yml``）の読み込みと、
その日の事実から「実際に書ける候補」を組み立てる。

考え方
------
- YAML は **文言とメタ情報だけ**（hook / numbers / view / 画像見出し / 重み）。
- 数字は必ず Python 側の builder が ``Val`` として作る。
  YAML に数値を直書きできないので、文言を編集しても数字は壊れない。
- ``requires`` に挙げた事実キーが1つでも欠けていたら **候補にしない**。
  「取れなかったから推測で埋める」を構造的に不可能にする。
- ``builder`` が None の話題は「データ源が無いと分かっている話題」。
  候補には出ないが、summary.md に理由つきで残す（隠さない）。
"""

from __future__ import annotations

from pathlib import Path

from src.common.util import REPO_ROOT, load_yaml
from src.daily_growth import compose as C
from src.daily_growth.compose import Draft, Val, fill

TOPICS_PATH = REPO_ROOT / "data" / "daily_growth_topics.yml"


def load_topics(path: Path = TOPICS_PATH) -> list[dict]:
    data = load_yaml(path, default={"topics": []}) or {}
    return data.get("topics", []) or []


def find_duplicates(topics: list[dict]) -> list[str]:
    problems, seen = [], set()
    for t in topics:
        tid = t.get("id", "")
        if tid in seen:
            problems.append(f"ID重複: {tid}")
        seen.add(tid)
        if not t.get("builder"):
            # データ源が無いと宣言した話題。理由を書き残すことだけ求める
            if not t.get("blocked_reason"):
                problems.append(f"blocked_reasonがありません: {tid}")
            continue
        if t["builder"] not in BUILDERS:
            problems.append(f"未定義のbuilder: {tid} -> {t['builder']}")
        for key in ("hook", "view", "headline"):
            if not t.get(key):
                problems.append(f"{key}がありません: {tid}")
        if not t.get("designs"):
            problems.append(f"designsがありません: {tid}")
    return problems


# --------------------------------------------------------------------------
# 図（画像に載せる1つの図）の作り方
# --------------------------------------------------------------------------

def _bars(items: list[dict], signed: bool = False) -> dict:
    """items: [{label, value(float), text}] → 横棒。幅は最大値基準。"""
    peak = max((abs(i["value"]) for i in items), default=0) or 1.0
    return {"kind": "bars", "signed": signed, "items": [
        {"label": i["label"], "text": i["text"],
         "ratio": abs(i["value"]) / peak,
         "tone": "up" if i["value"] > 0 else ("down" if i["value"] < 0 else "flat")}
        for i in items]}


def _compare(left: dict, right: dict, note: str = "") -> dict:
    return {"kind": "compare", "left": left, "right": right, "note": note}


def _progress(ratio: float, left: str, right: str, note: str = "") -> dict:
    return {"kind": "progress", "ratio": max(0.0, min(1.0, ratio)),
            "left": left, "right": right, "note": note}


def _table(columns: list[str], rows: list[list[str]],
           align: list[str] | None = None) -> dict:
    return {"kind": "table", "columns": columns, "rows": rows,
            "align": align or ["left"] + ["right"] * (len(columns) - 1)}


def _spark(points: list[float], left: str, right: str, note: str = "") -> dict:
    return {"kind": "sparkline", "points": points, "left": left,
            "right": right, "note": note}


def _R(values: dict, *, surprise: float, figure: dict, hero: dict,
       kicker: str, notes: list[str] | None = None) -> dict:
    return {"values": values, "surprise": surprise, "figure": figure,
            "hero": hero, "kicker": kicker, "notes": notes or []}


def _dir_word(v: float, up: str = "増えました", down: str = "減りました",
              flat: str = "ほぼ動きませんでした") -> str:
    return up if v > 0 else (down if v < 0 else flat)


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def _date_val(s: str) -> Val:
    return Val(str(s), str(s))


# --------------------------------------------------------------------------
# builder 群
# --------------------------------------------------------------------------
# それぞれ「今日の事実」から values / 図 / surprise を作る。
# 書けない日は None を返す（＝その話題は今日の候補から消える）。

def b_daily_move(f: dict, p: dict) -> dict | None:
    day, contrib = f["day"], f["contributions"]
    top = contrib[0]
    z = (f.get("volatility") or {}).get("z")
    values = {
        "total": C.jpy_man(f["total_jpy"]),
        "day_pct": C.pct_signed(day["change_pct"]),
        "day_jpy": C.jpy_signed(day["market_jpy"]),
        "top_label": top["label"],
        "top_pt": C.pt_signed(top["contrib_pt"]),
        "second_label": contrib[1]["label"],
        "second_pt": C.pt_signed(contrib[1]["contrib_pt"]),
        "direction": _dir_word(day["market_jpy"]),
        "date": _date_val(f["data_date"]),
    }
    figure = _bars([{"label": r["label"], "value": r["contrib_pt"],
                     "text": C.pt_signed(r["contrib_pt"]).text}
                    for r in contrib[:5]], signed=True)
    return _R(values,
              surprise=_clamp(abs(z) / 2.5) if z is not None
              else _clamp(abs(day["change_pct"]) / 1.5),
              figure=figure,
              hero={"label": "総資産", "value": values["total"].text,
                    "delta": f'{values["day_pct"].text}（{values["day_jpy"].text}）',
                    "tone": "up" if day["market_jpy"] > 0 else "down"},
              kicker="前日比の内訳",
              notes=["寄与は総資産に対する%pt。合計が前日比になります"])


def b_quiet_day(f: dict, p: dict) -> dict | None:
    q = f["quiet"]
    if not q["is_quiet"]:
        return None
    etfs = [h for h in f["holdings"] if h["kind"] == "ETF"
            and h["change_pct"] is not None]
    values = {
        "total": C.jpy_man(f["total_jpy"]),
        "day_pct": C.pct_signed(f["day"]["change_pct"]),
        "day_jpy": C.jpy_signed(f["day"]["market_jpy"]),
        "max_pct": C.pct(q["max_abs_pct"]),
        "count": C.num(len(etfs), "本"),
        "date": _date_val(f["data_date"]),
    }
    figure = _bars([{"label": h["label"], "value": h["change_pct"],
                     "text": C.pct_signed(h["change_pct"]).text} for h in etfs],
                   signed=True)
    return _R(values, surprise=0.55, figure=figure,
              hero={"label": "総資産", "value": values["total"].text,
                    "delta": values["day_pct"].text, "tone": "flat"},
              kicker="動かなかった日の記録",
              notes=["ETFの値動き（前営業日比）"])


def b_fx_decomp(f: dict, p: dict) -> dict | None:
    d = f["fx_decomp"]
    share = d["fx_share_pct"] or 0.0
    if share < float(p.get("min_share", 0)):
        return None
    if p.get("require_opposite") and not d["opposite"]:
        return None
    values = {
        "price": C.jpy_signed(d["price_jpy"]),
        "fx": C.jpy_signed(d["fx_jpy"]),
        "total": C.jpy_signed(d["total_jpy"]),
        "fx_share": C.pct(share, 0),
        "usdjpy": C.num(f["usdjpy"], "円", 2),
        "total_assets": C.jpy_man(f["total_jpy"]),
        "price_word": _dir_word(d["price_jpy"], "プラス", "マイナス", "横ばい"),
        "fx_word": _dir_word(d["fx_jpy"], "プラス", "マイナス", "横ばい"),
        "date": _date_val(f["data_date"]),
    }
    figure = _compare(
        {"label": "株価の値動き", "value": values["price"].text,
         "tone": "up" if d["price_jpy"] > 0 else "down", "note": "同じ為替で比較"},
        {"label": "為替の影響", "value": values["fx"].text,
         "tone": "up" if d["fx_jpy"] > 0 else "down",
         "note": f'USD/JPY {values["usdjpy"].text}'},
        note=f'合計＝総資産の前日比 {values["total"].text}')
    surprise = 0.9 if d["opposite"] else _clamp(share / 100 + 0.2)
    return _R(values, surprise=surprise, figure=figure,
              hero={"label": "総資産の前日比", "value": values["total"].text,
                    "delta": f'株価{values["price"].text} ／ 為替{values["fx"].text}',
                    "tone": "up" if d["total_jpy"] > 0 else "down"},
              kicker="値動きと為替の分解",
              notes=["株価要因＋為替要因＝総資産の前日比（入金なしの日）"])


def b_reversal(f: dict, p: dict) -> dict | None:
    r = f.get("reversal")
    if not r or not r["flipped"]:
        return None
    values = {
        "prev_pct": C.pct_signed(r["prev_pct"]),
        "today_pct": C.pct_signed(r["today_pct"]),
        "prev_date": _date_val(r["prev_date"]),
        "total": C.jpy_man(f["total_jpy"]),
        "day_jpy": C.jpy_signed(f["day"]["market_jpy"]),
        "date": _date_val(f["data_date"]),
    }
    figure = _compare(
        {"label": f'前日 {r["prev_date"]}', "value": values["prev_pct"].text,
         "tone": "up" if r["prev_pct"] > 0 else "down", "note": "入金除外"},
        {"label": f'当日 {f["data_date"]}', "value": values["today_pct"].text,
         "tone": "up" if r["today_pct"] > 0 else "down", "note": "入金除外"},
        note="連日で符号が反転しました")
    return _R(values, surprise=0.8, figure=figure,
              hero={"label": "総資産", "value": values["total"].text,
                    "delta": values["today_pct"].text,
                    "tone": "up" if r["today_pct"] > 0 else "down"},
              kicker="前日と逆に動いた日",
              notes=["いずれも入金を除いた増減率"])


def b_sigma(f: dict, p: dict) -> dict | None:
    v = f.get("volatility")
    if not v or v.get("z") is None:
        return None
    z = v["z"]
    band = float(p.get("band", 1.5))
    if p.get("inside") and abs(z) >= band:
        return None
    if p.get("outside") and abs(z) < band:
        return None
    values = {
        "z": C.num(abs(z), "σ", 2),
        "sigma": C.pct(v["sigma_pct"]),
        "day_pct": C.pct_signed(v["today_pct"]),
        "n": C.num(v["n"], "日"),
        "band": C.num(band, "σ", 1),
        "total": C.jpy_man(f["total_jpy"]),
        "sigma_jpy": C.jpy_man(f["total_jpy"] * v["sigma_pct"] / 100),
        "date": _date_val(f["data_date"]),
    }
    figure = _bars([
        {"label": "今日の変動", "value": abs(v["today_pct"]),
         "text": values["day_pct"].text},
        {"label": f'標準偏差（{v["n"]}日）', "value": v["sigma_pct"],
         "text": values["sigma"].text},
        {"label": "期間の最大", "value": abs(v["max_pct"]),
         "text": C.pct_signed(v["max_pct"]).text},
        {"label": "期間の最小", "value": abs(v["min_pct"]),
         "text": C.pct_signed(v["min_pct"]).text},
    ])
    return _R(values, surprise=_clamp(abs(z) / 2.5) if p.get("outside") else 0.5,
              figure=figure,
              hero={"label": "今日の変動", "value": values["day_pct"].text,
                    "delta": f'{values["z"].text}（標準偏差 {values["sigma"].text}）',
                    "tone": "up" if v["today_pct"] > 0 else "down"},
              kicker="平常時とくらべた大きさ",
              notes=[f'{v["n"]}日ぶんの入金除外リターンから算出'])


def b_contribution(f: dict, p: dict) -> dict | None:
    rows = f["contributions"]
    top = rows[0]
    values = {
        "top_label": top["label"],
        "top_pt": C.pt_signed(top["contrib_pt"]),
        "top_pct": C.pct_signed(top["change_pct"]) if top["change_pct"] is not None
        else C.pct_signed(0.0),
        "top_jpy": C.jpy_signed(top["diff_jpy"]),
        "sum_pt": C.pt_signed(f["price_change_pct"]),
        "second_label": rows[1]["label"],
        "second_pt": C.pt_signed(rows[1]["contrib_pt"]),
        "date": _date_val(f["data_date"]),
    }
    figure = _table(["銘柄", "値動き", "寄与"], [
        [r["label"],
         C.pct_signed(r["change_pct"]).text if r["change_pct"] is not None else "—",
         C.pt_signed(r["contrib_pt"]).text] for r in rows[:6]])
    share = abs(top["contrib_pt"]) / max(
        sum(abs(r["contrib_pt"]) for r in rows), 1e-9)
    return _R(values, surprise=_clamp(share * 1.2), figure=figure,
              hero={"label": "いちばん効いた銘柄", "value": top["label"],
                    "delta": f'{values["top_pt"].text}（{values["top_jpy"].text}）',
                    "tone": "up" if top["contrib_pt"] > 0 else "down"},
              kicker="今日の資産を動かしたもの",
              notes=["寄与は総資産に対する%pt。合計が値動きベースの前日比"])


def b_window(f: dict, p: dict) -> dict | None:
    w = (f.get("windows") or {}).get(p["window"])
    if not w:
        return None
    values = {
        "label": w["label"],
        "base_date": _date_val(w["base_date"]),
        "base": C.jpy_man(w["base_jpy"]),
        "market": C.jpy_signed(w["market_jpy"]),
        "pct": C.pct_signed(w["change_pct"]),
        "total": C.jpy_man(f["total_jpy"]),
        "direction": _dir_word(w["market_jpy"]),
        "date": _date_val(f["data_date"]),
    }
    if "cash_flow_jpy" in w:
        values["flow"] = C.jpy_man(w["cash_flow_jpy"])
        values["gross"] = C.jpy_signed(w["gross_jpy"])
    hist = [r["total_jpy"] for r in (f.get("total_series") or [])
            if str(r["date"]) >= str(w["base_date"])]
    # 折れ線は総資産そのもの（入金の日は段差が出る）。
    # 率は入金除外なので、両者が別物であることを図の注記で明示する。
    figure = (_spark(hist, w["base_date"], f["data_date"],
                     "折れ線は総資産の推移（入金を含む）。"
                     f'{w["label"]}比 {values["pct"].text} は入金を除いた増減です')
              if len(hist) >= 5 else
              _compare({"label": f'{w["label"]}（{w["base_date"]}）',
                        "value": values["base"].text, "tone": "flat", "note": ""},
                       {"label": f'当日（{f["data_date"]}）',
                        "value": values["total"].text,
                        "tone": "up" if w["market_jpy"] > 0 else "down",
                        "note": values["pct"].text}))
    return _R(values, surprise=_clamp(abs(w["change_pct"]) / 4.0),
              figure=figure,
              hero={"label": f'{w["label"]}比（入金除外）',
                    "value": values["pct"].text, "delta": values["market"].text,
                    "tone": "up" if w["market_jpy"] > 0 else "down"},
              kicker=f'{w["label"]}からの変化',
              notes=["入金分を除いた、運用だけの増減です"])


def b_flow_vs_market(f: dict, p: dict) -> dict | None:
    w = (f.get("windows") or {}).get(p["window"])
    if not w or "cash_flow_jpy" not in w or w["cash_flow_jpy"] <= 0:
        return None
    if p.get("market_must_win") and abs(w["market_jpy"]) <= w["cash_flow_jpy"]:
        return None
    values = {
        "label": w["label"],
        "flow": C.jpy_man(w["cash_flow_jpy"]),
        "market": C.jpy_signed(w["market_jpy"]),
        "gross": C.jpy_signed(w["gross_jpy"]),
        "flow_share": C.pct(w["flow_share_pct"], 0),
        "bigger": "入金" if w["cash_flow_jpy"] > abs(w["market_jpy"]) else "運用",
        "base_date": _date_val(w["base_date"]),
        "total": C.jpy_man(f["total_jpy"]),
        "date": _date_val(f["data_date"]),
    }
    figure = _compare(
        {"label": "入金で増えた分", "value": values["flow"].text,
         "tone": "flat", "note": "自分で足したお金"},
        {"label": "運用で増えた分", "value": values["market"].text,
         "tone": "up" if w["market_jpy"] > 0 else "down",
         "note": "市場の値動き"},
        note=f'合計 {values["gross"].text}（{w["base_date"]}比）')
    ratio = min(w["cash_flow_jpy"], abs(w["market_jpy"])) / max(
        w["cash_flow_jpy"], abs(w["market_jpy"]), 1e-9)
    return _R(values, surprise=_clamp(0.4 + (1 - ratio) * 0.5), figure=figure,
              hero={"label": f'{w["label"]}からの増減', "value": values["gross"].text,
                    "delta": f'入金 {values["flow"].text} ／ 運用 {values["market"].text}',
                    "tone": "up" if w["gross_jpy"] > 0 else "down"},
              kicker="増えた理由の内訳",
              notes=["入金は自分で足したお金なので、運用成績ではありません"])


def b_window_conflict(f: dict, p: dict) -> dict | None:
    c = f.get("window_conflict")
    if not c:
        return None
    w, m = c["week"], c["month"]
    values = {
        "week_pct": C.pct_signed(w["change_pct"]),
        "month_pct": C.pct_signed(m["change_pct"]),
        "week_jpy": C.jpy_signed(w["market_jpy"]),
        "month_jpy": C.jpy_signed(m["market_jpy"]),
        "week_base": _date_val(w["base_date"]),
        "month_base": _date_val(m["base_date"]),
        "total": C.jpy_man(f["total_jpy"]),
        "date": _date_val(f["data_date"]),
    }
    figure = _compare(
        {"label": f'先週比（{w["base_date"]}〜）', "value": values["week_pct"].text,
         "tone": "up" if w["market_jpy"] > 0 else "down",
         "note": values["week_jpy"].text},
        {"label": f'先月比（{m["base_date"]}〜）', "value": values["month_pct"].text,
         "tone": "up" if m["market_jpy"] > 0 else "down",
         "note": values["month_jpy"].text},
        note="どちらも入金除外")
    return _R(values, surprise=0.85, figure=figure,
              hero={"label": "先週比と先月比", "value": values["week_pct"].text,
                    "delta": f'先月比は {values["month_pct"].text}', "tone": "flat"},
              kicker="期間で符号が逆になった日",
              notes=["切り取る期間で見え方が変わります"])


def b_record(f: dict, p: dict) -> dict | None:
    r = f.get("record")
    if not r:
        return None
    if p.get("require_new") and not r["is_new_high"]:
        return None
    if p.get("require_gap") and r["is_new_high"]:
        return None
    values = {
        "total": C.jpy_man(f["total_jpy"]),
        "prev_high": C.jpy_man(r["prev_high_jpy"]),
        "prev_high_date": _date_val(r["prev_high_date"]),
        "gap": C.jpy_signed(r["gap_jpy"]),
        "gap_pct": C.pct_signed(r["gap_pct"]),
        "days": C.num(r["days_since_high"], "日"),
        "date": _date_val(f["data_date"]),
    }
    figure = _compare(
        {"label": f'これまでの最高（{r["prev_high_date"]}）',
         "value": values["prev_high"].text, "tone": "flat", "note": ""},
        {"label": f'当日（{f["data_date"]}）', "value": values["total"].text,
         "tone": "up" if r["gap_jpy"] > 0 else "down",
         "note": f'{values["gap"].text}（{values["gap_pct"].text}）'})
    return _R(values, surprise=0.9 if r["is_new_high"] else
              _clamp(abs(r["gap_pct"]) / 6.0), figure=figure,
              hero={"label": "総資産", "value": values["total"].text,
                    "delta": f'これまでの最高比 {values["gap"].text}',
                    "tone": "up" if r["gap_jpy"] > 0 else "down"},
              kicker="過去の最高値との比較",
              notes=["入金も含んだ、口座の見た目の金額です"])


def b_weights(f: dict, p: dict) -> dict | None:
    ranked = f["ranked_holdings"]
    values = {
        "total": C.jpy_man(f["total_jpy"]),
        "top_label": ranked[0]["label"],
        "top_pct": C.pct(ranked[0]["weight_pct"], 1),
        "top_jpy": C.jpy_man(ranked[0]["jpy"]),
        "second_label": ranked[1]["label"],
        "second_pct": C.pct(ranked[1]["weight_pct"], 1),
        "count": C.num(len(ranked), "本"),
        "date": _date_val(f["data_date"]),
    }
    figure = _bars([{"label": h["label"], "value": h["weight_pct"],
                     "text": C.pct(h["weight_pct"], 1).text}
                    for h in ranked[:6]])
    return _R(values, surprise=0.3, figure=figure,
              hero={"label": "いちばん大きい保有", "value": ranked[0]["label"],
                    "delta": f'{values["top_pct"].text}（{values["top_jpy"].text}）',
                    "tone": "flat"},
              kicker="保有比率ランキング",
              notes=[f'{values["count"].text}の合計 {values["total"].text}'])


def b_concentration(f: dict, p: dict) -> dict | None:
    c = f["concentration"]
    values = {
        "total": C.jpy_man(f["total_jpy"]),
        "top1_label": c["top1_label"],
        "top1": C.pct(c["top1_pct"], 1),
        "top3": C.pct(c["top3_pct"], 1),
        "etf": C.pct(c["etf_pct"], 1),
        "count": C.num(f["holding_count"], "本"),
        "date": _date_val(f["data_date"]),
    }
    figure = _progress(c["top3_pct"] / 100, "上位3本", values["top3"].text,
                       f'いちばん大きい {c["top1_label"]} だけで {values["top1"].text}')
    return _R(values, surprise=0.3, figure=figure,
              hero={"label": "上位3本の占める割合", "value": values["top3"].text,
                    "delta": f'{values["count"].text}に分散しているつもりでした',
                    "tone": "flat"},
              kicker="分散のつもりが、実は",
              notes=["評価額ベース。ファンドの中身の重複は含みません"])


def b_cushion(f: dict, p: dict) -> dict | None:
    c = f.get("cushion")
    if not c:
        return None
    if p.get("require_growth_down") and c["growth_pct"] >= 0:
        return None
    if p.get("require_flip") and not (c["growth_pct"] < 0 <= c["high_yield_pct"]):
        return None
    values = {
        "high": C.pct_signed(c["high_yield_pct"]),
        "growth": C.pct_signed(c["growth_pct"]),
        "diff": C.pt_signed(c["diff_pt"]),
        "high_names": "・".join(c["high_yield_keys"]),
        "growth_names": "・".join(c["growth_keys"]),
        "verdict": "効いていた" if c["diff_pt"] > 0 else "効かなかった",
        "date": _date_val(f["data_date"]),
    }
    figure = _bars([{"label": k, "value": v, "text": C.pct_signed(v).text}
                    for k, v in c["members"].items()], signed=True)
    return _R(values, surprise=_clamp(0.35 + abs(c["diff_pt"]) / 2.0),
              figure=figure,
              hero={"label": "高配当 − グロース", "value": values["diff"].text,
                    "delta": f'高配当 {values["high"].text} ／ グロース {values["growth"].text}',
                    "tone": "up" if c["diff_pt"] > 0 else "down"},
              kicker="クッションになったのか",
              notes=["同じ日付で比べられるETFのみ（投信は基準日がずれるため除外）"])


def b_hy_split(f: dict, p: dict) -> dict | None:
    s = f.get("hy_split")
    if not s or not s["opposite"]:
        return None
    values = {
        "vym": C.pct_signed(s["VYM"]),
        "hdv": C.pct_signed(s["HDV"]),
        "diff": C.pt_signed(s["diff_pt"]),
        "date": _date_val(f["data_date"]),
    }
    figure = _compare(
        {"label": "VYM", "value": values["vym"].text,
         "tone": "up" if s["VYM"] > 0 else "down", "note": "米国高配当ETF"},
        {"label": "HDV", "value": values["hdv"].text,
         "tone": "up" if s["HDV"] > 0 else "down", "note": "米国高配当ETF"},
        note=f'差は {values["diff"].text}')
    return _R(values, surprise=0.75, figure=figure,
              hero={"label": "同じ「高配当」の2本", "value": values["diff"].text,
                    "delta": f'VYM {values["vym"].text} ／ HDV {values["hdv"].text}',
                    "tone": "flat"},
              kicker="名前は同じでも中身は別",
              notes=["前営業日比。どちらも米国高配当ETFです"])


def b_lag(f: dict, p: dict) -> dict | None:
    lag = f.get("lag")
    if not lag or lag["days"] < 1:
        return None
    fund_jpy = sum(h["jpy"] for h in f["holdings"] if h["kind"] == "投資信託")
    values = {
        "days": C.num(lag["days"], "日"),
        "etf_date": _date_val(lag["etf_date"]),
        "fund_date": _date_val(lag["fund_date"]),
        "fund_count": C.num(lag["fund_count"], "本"),
        "fund_jpy": C.jpy_man(fund_jpy),
        "fund_pct": C.pct(fund_jpy / f["total_jpy"] * 100, 1),
        "total": C.jpy_man(f["total_jpy"]),
        "date": _date_val(f["data_date"]),
    }
    figure = _compare(
        {"label": "ETFの基準日", "value": lag["etf_date"], "tone": "flat",
         "note": "前営業日の終値"},
        {"label": "投資信託の基準日", "value": lag["fund_date"], "tone": "flat",
         "note": f'{values["fund_count"].text}／{values["fund_pct"].text}'},
        note=f'ズレは {values["days"].text}')
    return _R(values, surprise=0.6, figure=figure,
              hero={"label": "反映日のズレ", "value": values["days"].text,
                    "delta": f'ETF {lag["etf_date"]} ／ 投信 {lag["fund_date"]}',
                    "tone": "flat"},
              kicker="同じ日の資産ではない",
              notes=["投信の基準価額は公表が遅れるため、当日分はまだ入りません"])


def b_dram(f: dict, p: dict) -> dict | None:
    d = f.get("dram")
    if not d:
        return None
    values = {
        "dram_pct": C.pct_signed(d["change_pct"]),
        "dram_jpy": C.jpy_man(d["jpy"]),
        "weight": C.pct(d["weight_pct"], 2),
        "total": C.jpy_man(f["total_jpy"]),
        "date": _date_val(f["data_date"]),
    }
    others = [h for h in f["holdings"]
              if h["kind"] == "ETF" and h["key"] != "DRAM"
              and h["change_pct"] is not None]
    figure = _bars(
        [{"label": "DRAM", "value": d["change_pct"],
          "text": values["dram_pct"].text}] +
        [{"label": h["label"], "value": h["change_pct"],
          "text": C.pct_signed(h["change_pct"]).text} for h in others],
        signed=True)
    peak = max((abs(h["change_pct"]) for h in others), default=0.0)
    return _R(values, surprise=_clamp(abs(d["change_pct"]) / max(peak * 2, 1.0)),
              figure=figure,
              hero={"label": "DRAM メモリ半導体ETF", "value": values["dram_pct"].text,
                    "delta": f'保有比率 {values["weight"].text}',
                    "tone": "up" if d["change_pct"] > 0 else "down"},
              kicker="シクリカルな値動きの記録",
              notes=["メモリはシクリカル（景気循環型）な業種です"])


def b_fx_sim(f: dict, p: dict) -> dict | None:
    s = f.get("fx_sim")
    if not s:
        return None
    move = float(p.get("move_yen", 10))
    impact = s["per_yen_jpy"] * move
    values = {
        "usdjpy": C.num(s["usdjpy"], "円", 2),
        "usd_assets": C.jpy_man(s["usd_assets_jpy"]),
        "per_yen": C.jpy_man(s["per_yen_jpy"]),
        "move": C.num(move, "円"),
        "impact": C.jpy_man(impact),
        "impact_pct": C.pct(impact / f["total_jpy"] * 100, 1),
        "after": C.jpy_man(f["total_jpy"] - impact),
        "total": C.jpy_man(f["total_jpy"]),
        "date": _date_val(f["data_date"]),
    }
    figure = _compare(
        {"label": f'現在（USD/JPY {s["usdjpy"]:.2f}）', "value": values["total"].text,
         "tone": "flat", "note": ""},
        {"label": f'{move:.0f}円の円高になった場合', "value": values["after"].text,
         "tone": "down", "note": f'{values["impact_pct"].text} 相当'},
        note="株価が動かないと仮定した単純計算です")
    return _R(values, surprise=0.3, figure=figure,
              hero={"label": f'{move:.0f}円の円高で動く金額',
                    "value": values["impact"].text,
                    "delta": f'総資産の {values["impact_pct"].text}', "tone": "down"},
              kicker="為替だけを動かした試算",
              notes=["株価を固定した仮定の計算で、予想ではありません"])


def b_milestone(f: dict, p: dict) -> dict | None:
    total = f["total_jpy"]
    target = float(p.get("target_jpy") or (f.get("milestone") or {}).get("target_jpy") or 0)
    if not target or target <= total:
        return None
    values = {
        "total": C.jpy_man(total),
        "target": C.oku(target),
        "progress": C.pct(total / target * 100, 1),
        "remaining": C.jpy_man(target - total),
        "date": _date_val(f["data_date"]),
    }
    notes = ["進捗は総資産÷目標額。到達時期の見通しではありません"]
    pace = f.get("pace")
    if p.get("with_pace") and pace and pace["per_day_jpy"] > 0:
        days = (target - total) / pace["per_day_jpy"]
        values["per_day"] = C.jpy_man(pace["per_day_jpy"])
        values["pace_days"] = C.num(pace["days"], "日")
        values["days_left"] = C.num(round(days), "日")
        values["years_left"] = C.num(days / 365, "年", 1)
        notes = ["直近の実績ペースがそのまま続くと仮定した単純計算です",
                 "相場も入金も変わるので、見通しではありません"]
    elif p.get("with_pace"):
        return None
    figure = _progress(total / target, values["total"].text, values["target"].text,
                       f'進捗 {values["progress"].text}／残り {values["remaining"].text}')
    return _R(values, surprise=0.25, figure=figure,
              hero={"label": f'{values["target"].text}までの進捗',
                    "value": values["progress"].text,
                    "delta": f'残り {values["remaining"].text}', "tone": "flat"},
              kicker="目標までの距離", notes=notes)


def b_daily_life(f: dict, p: dict) -> dict | None:
    v = f.get("volatility")
    if not v:
        return None
    total = f["total_jpy"]
    sigma_jpy = total * v["sigma_pct"] / 100
    values = {
        "total": C.jpy_man(total),
        "sigma_jpy": C.jpy_man(sigma_jpy),
        "sigma": C.pct(v["sigma_pct"]),
        "max_jpy": C.jpy_man(total * v["max_pct"] / 100),
        "min_jpy": C.jpy_man(abs(total * v["min_pct"] / 100)),
        "n": C.num(v["n"], "日"),
        "day_jpy": C.jpy_signed(f["day"]["market_jpy"]),
        "date": _date_val(f["data_date"]),
    }
    figure = _bars([
        {"label": "1日の平均的な振れ幅", "value": sigma_jpy,
         "text": values["sigma_jpy"].text},
        {"label": "期間中いちばん増えた日", "value": total * v["max_pct"] / 100,
         "text": values["max_jpy"].text},
        {"label": "期間中いちばん減った日", "value": abs(total * v["min_pct"] / 100),
         "text": values["min_jpy"].text},
        {"label": "今日の増減", "value": abs(f["day"]["market_jpy"]),
         "text": values["day_jpy"].text},
    ])
    return _R(values, surprise=0.35, figure=figure,
              hero={"label": "1日で動く金額（標準偏差）",
                    "value": values["sigma_jpy"].text,
                    "delta": f'総資産 {values["total"].text} に対して {values["sigma"].text}',
                    "tone": "flat"},
              kicker="この規模の口座の1日",
              notes=[f'直近{v["n"]}日の入金除外リターンから算出'])


def b_buy_history(f: dict, p: dict) -> dict | None:
    fl = f.get("flows")
    if not fl:
        return None
    values = {
        "last_date": _date_val(fl["last_date"]),
        "last_jpy": C.jpy_man(fl["last_jpy"]),
        "days_since": C.num(fl["days_since"], "日"),
        "count": C.num(fl["count"], "回"),
        "sum_all": C.jpy_man(fl["sum_all_jpy"]),
        "sum_30d": C.jpy_man(fl["sum_30d_jpy"]),
        "total": C.jpy_man(f["total_jpy"]),
        "from_date": _date_val(f["history_from"]),
        "date": _date_val(f["data_date"]),
    }
    figure = _compare(
        {"label": f'記録期間の入金（{f["history_from"]}〜）',
         "value": values["sum_all"].text, "tone": "flat",
         "note": f'{values["count"].text}'},
        {"label": "直近の買い増し", "value": values["last_jpy"].text,
         "tone": "flat", "note": f'{fl["last_date"]}（{values["days_since"].text}前）'})
    return _R(values, surprise=_clamp(0.7 - fl["days_since"] * 0.06),
              figure=figure,
              hero={"label": "直近の買い増し", "value": values["last_jpy"].text,
                    "delta": f'{fl["last_date"]}／{values["days_since"].text}前',
                    "tone": "flat"},
              kicker="入金の記録",
              notes=["入金は運用成績ではないので分けて記録しています"])


def b_checkback(f: dict, p: dict) -> dict | None:
    c = f.get("checkback")
    if not c:
        return None
    values = {
        "past_date": _date_val(c["date"]),
        "past_total": C.jpy_man(c["total_jpy"]),
        "total": C.jpy_man(f["total_jpy"]),
        "diff": C.jpy_signed(f["total_jpy"] - c["total_jpy"]),
        "diff_pct": C.pct_signed((f["total_jpy"] - c["total_jpy"])
                                 / c["total_jpy"] * 100),
        "days": C.num(c["age_days"], "日"),
        "direction": _dir_word(f["total_jpy"] - c["total_jpy"]),
        "date": _date_val(f["data_date"]),
    }
    figure = _compare(
        {"label": f'{c["date"]} の投稿時点', "value": values["past_total"].text,
         "tone": "flat", "note": ""},
        {"label": f'当日（{f["data_date"]}）', "value": values["total"].text,
         "tone": "up" if f["total_jpy"] > c["total_jpy"] else "down",
         "note": f'{values["diff"].text}（{values["diff_pct"].text}）'},
        note=f'{values["days"].text}後の答え合わせ')
    return _R(values, surprise=0.7, figure=figure,
              hero={"label": f'{values["days"].text}前と今',
                    "value": values["diff"].text, "delta": values["diff_pct"].text,
                    "tone": "up" if f["total_jpy"] > c["total_jpy"] else "down"},
              kicker="過去の投稿の答え合わせ",
              notes=["過去に投稿した数字と、同じ基準で並べています"])


def b_year_ago(f: dict, p: dict) -> dict | None:
    y = f.get("year_ago")
    if not y:
        return None
    values = {
        "past_date": _date_val(y["date"]),
        "past_total": C.jpy_man(y["total_jpy"]),
        "total": C.jpy_man(f["total_jpy"]),
        "diff": C.jpy_signed(y["diff_jpy"]),
        "diff_pct": C.pct_signed(y["diff_pct"]),
        "days": C.num(y["days"], "日"),
        "direction": _dir_word(y["diff_jpy"]),
        "date": _date_val(f["data_date"]),
    }
    figure = _compare(
        {"label": f'{y["date"]}', "value": values["past_total"].text,
         "tone": "flat", "note": "1年前の記録"},
        {"label": f'{f["data_date"]}', "value": values["total"].text,
         "tone": "up" if y["diff_jpy"] > 0 else "down",
         "note": f'{values["diff"].text}（{values["diff_pct"].text}）'})
    return _R(values, surprise=0.6, figure=figure,
              hero={"label": "1年前との差", "value": values["diff"].text,
                    "delta": values["diff_pct"].text,
                    "tone": "up" if y["diff_jpy"] > 0 else "down"},
              kicker="1年前の自分と比較",
              notes=["入金も含んだ、口座の見た目の金額の差です"])


def b_lookthrough(f: dict, p: dict) -> dict | None:
    lt = f.get("lookthrough")
    if not lt:
        return None
    pos = lt["positions"]
    top = pos[0]
    values = {
        "coverage": C.pct(lt["coverage_pct"], 1),
        "top_label": str(top.get("ticker") or top.get("name") or ""),
        "top_pct": C.pct(float(top.get("pct") or 0), 2),
        "top_jpy": C.jpy_man(float(top.get("jpy") or 0)),
        "total": C.jpy_man(f["total_jpy"]),
        "count": C.num(len(pos), "社"),
        "date": _date_val(f["data_date"]),
    }
    figure = _table(["銘柄", "実質比率"], [
        [str(r.get("ticker") or r.get("name") or ""),
         C.pct(float(r.get("pct") or 0), 2).text] for r in pos[:6]])
    return _R(values, surprise=0.5, figure=figure,
              hero={"label": "実質でいちばん大きい会社",
                    "value": values["top_label"],
                    "delta": f'{values["top_pct"].text}（{values["top_jpy"].text}）',
                    "tone": "flat"},
              kicker="ファンドの中身まで分解",
              notes=[f'個別銘柄まで分解できた割合 {values["coverage"].text}'])


BUILDERS = {
    "daily_move": b_daily_move,
    "quiet_day": b_quiet_day,
    "fx_decomp": b_fx_decomp,
    "reversal": b_reversal,
    "sigma": b_sigma,
    "contribution": b_contribution,
    "window": b_window,
    "flow_vs_market": b_flow_vs_market,
    "window_conflict": b_window_conflict,
    "record": b_record,
    "weights": b_weights,
    "concentration": b_concentration,
    "cushion": b_cushion,
    "hy_split": b_hy_split,
    "lag": b_lag,
    "dram": b_dram,
    "fx_sim": b_fx_sim,
    "milestone": b_milestone,
    "daily_life": b_daily_life,
    "buy_history": b_buy_history,
    "checkback": b_checkback,
    "year_ago": b_year_ago,
    "lookthrough": b_lookthrough,
}


# --------------------------------------------------------------------------
# 候補づくり
# --------------------------------------------------------------------------

def missing_requirements(topic: dict, f: dict) -> list[str]:
    return [k for k in (topic.get("requires") or []) if k not in f]


def build_draft(topic: dict, f: dict, char_limit: float = 165.0) -> Draft | None:
    """1つの話題から候補を作る。今日のデータで書けなければ None。"""
    builder = BUILDERS.get(topic.get("builder") or "")
    if builder is None or missing_requirements(topic, f):
        return None

    params = dict(topic.get("params") or {})
    result = builder(f, params)
    if result is None:
        return None

    values = result["values"]
    hook = fill(topic["hook"], values)
    numbers = [fill(n, values) for n in (topic.get("numbers") or [])]
    view = fill(topic["view"], values)
    text = C.build_text(
        hook=hook, numbers=numbers, view=view,
        tags=topic.get("tags") or ["#資産推移", "#米国株"],
        limit=char_limit, disclaimer=topic.get("disclaimer", "asset"),
        cyclical=bool(topic.get("cyclical")))

    card = {
        "kicker": result["kicker"],
        "headline": fill(topic["headline"], values),
        "hero": result["hero"],
        "figure": result["figure"],
        "notes": result["notes"] + [n for n in (topic.get("notes") or [])],
        "asof": f["data_date"],
    }
    return Draft(
        topic_id=topic["id"], category=topic.get("category", "other"),
        builder=str(topic.get("builder") or ""), hook=hook, text=text, values={k: v for k, v in values.items()
                                      if isinstance(v, Val)},
        card=card, surprise=float(result["surprise"]),
        timeliness=float(topic.get("timeliness", 0.5)),
        relevance=float(topic.get("relevance", 1.0)),
        clarity=float(topic.get("clarity", 0.8)),
        designs=list(topic.get("designs") or []),
        notes=result["notes"],
        literals=C.string_leaves(result["figure"]))


def build_all(topics: list[dict], f: dict,
              char_limit: float = 165.0) -> tuple[list[Draft], list[dict]]:
    """(作れた候補, 作れなかった話題と理由) を返す。"""
    drafts: list[Draft] = []
    skipped: list[dict] = []
    for t in topics:
        if not t.get("builder"):
            skipped.append({"id": t["id"], "title": t.get("title", ""),
                            "reason": t.get("blocked_reason",
                                            "データ源がないため生成対象外")})
            continue
        missing = missing_requirements(t, f)
        if missing:
            skipped.append({"id": t["id"], "title": t.get("title", ""),
                            "reason": f'必要なデータがありません: {", ".join(missing)}'})
            continue
        d = build_draft(t, f, char_limit)
        if d is None:
            skipped.append({"id": t["id"], "title": t.get("title", ""),
                            "reason": "今日のデータでは条件を満たしません"})
            continue
        drafts.append(d)
    return drafts, skipped
