# -*- coding: utf-8 -*-
"""レイヤ2：一次情報（記事の数字を埋める source of truth）。

- SEC EDGAR full-text search（キー不要・User-Agent必須）
- 企業IRプレスリリースRSS（config.yaml の ir_feeds）
- FRED API（FRED_API_KEY があるときのみ）
- 米財務省イールドカーブXML（キー不要）
- 経済指標カレンダー（config.yaml。当日該当なら優先度加点の材料）

どの取得元が失敗してもその取得元だけ欠落し、全体は続行する。
単体実行: python scripts/sources/primary.py [--date YYYY-MM-DD]
"""
from __future__ import annotations
import datetime as dt
import os
import re
import xml.etree.ElementTree as ET

try:
    from .http_util import get
except ImportError:          # 単体実行（python scripts/sources/primary.py）用
    from http_util import get


# ── SEC EDGAR ────────────────────────────────────────────
def edgar_recent_filings(query: str, asof: dt.date, days: int = 3) -> list[dict]:
    """EDGAR全文検索。直近days日の該当ファイリング（社名・フォーム・日付）を返す。"""
    start = (asof - dt.timedelta(days=days)).isoformat()
    data = get("https://efts.sec.gov/LATEST/search-index",
               params={"q": query, "dateRange": "custom",
                       "startdt": start, "enddt": asof.isoformat()},
               as_json=True)
    hits = []
    try:
        for h in (data or {}).get("hits", {}).get("hits", [])[:10]:
            src = h.get("_source", {})
            hits.append({
                "company": (src.get("display_names") or [""])[0],
                "form": src.get("file_type") or src.get("form_type", ""),
                "filed": src.get("file_date", ""),
                "source": "SEC EDGAR",
            })
    except Exception:
        pass
    return hits


# ── FRED ─────────────────────────────────────────────────
def fred_latest(series_id: str, asof: dt.date) -> dict | None:
    """FRED系列の最新2観測値（前回差の計算用）。キー未設定なら None。"""
    key = os.environ.get("FRED_API_KEY")
    if not key:
        return None
    data = get("https://api.stlouisfed.org/fred/series/observations",
               params={"series_id": series_id, "api_key": key,
                       "file_type": "json", "sort_order": "desc", "limit": 2,
                       "observation_end": asof.isoformat()},
               as_json=True)
    try:
        obs = [o for o in data["observations"] if o["value"] not in (".", "")]
        if not obs:
            return None
        return {"value": float(obs[0]["value"]), "date": obs[0]["date"],
                "prev": float(obs[1]["value"]) if len(obs) > 1 else None,
                "source": "FRED"}
    except Exception:
        return None


# ── 米財務省イールドカーブ ────────────────────────────────
_TREASURY_URL = ("https://home.treasury.gov/resource-center/data-chart-center/"
                 "interest-rates/pages/xml"
                 "?data=daily_treasury_yield_curve&field_tdr_date_value_month={ym}")


def treasury_yields(asof: dt.date) -> dict | None:
    """asof以前の最新営業日の 2年/10年/30年 利回り（%）。"""
    xml = get(_TREASURY_URL.format(ym=asof.strftime("%Y%m")))
    if not xml:
        return None
    try:
        ns = {"a": "http://www.w3.org/2005/Atom",
              "m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata",
              "d": "http://schemas.microsoft.com/ado/2007/08/dataservices"}
        best = None
        for entry in ET.fromstring(xml).findall(".//a:entry", ns):
            p = entry.find(".//m:properties", ns)
            if p is None:
                continue
            d_el = p.find("d:NEW_DATE", ns)
            if d_el is None or not d_el.text:
                continue
            d = dt.date.fromisoformat(d_el.text[:10])
            if d > asof:
                continue
            row = {"date": d.isoformat(), "source": "米財務省"}
            for tag, k in (("d:BC_2YEAR", "y2"), ("d:BC_10YEAR", "y10"),
                           ("d:BC_30YEAR", "y30")):
                el = p.find(tag, ns)
                if el is not None and el.text:
                    row[k] = float(el.text)
            if best is None or row["date"] > best["date"]:
                best = row
        return best
    except Exception:
        return None


# ── 企業IR RSS ───────────────────────────────────────────
def ir_releases(cfg: dict, tickers: list[str], asof: dt.date) -> dict[str, list[dict]]:
    """対象銘柄のIRプレスリリース（直近3日）。"""
    out: dict[str, list[dict]] = {}
    feeds = cfg.get("ir_feeds") or {}
    for tk in tickers:
        url = feeds.get(tk)
        if not url:
            continue
        text = get(url)
        if not text:
            continue
        try:
            import feedparser
            fp = feedparser.parse(text)
            items = []
            for e in fp.entries[:10]:
                pub = e.get("published_parsed") or e.get("updated_parsed")
                if pub and (asof - dt.date(*pub[:3])).days > 3:
                    continue
                items.append({"title": (e.get("title") or "").strip(),
                              "source": f"{tk} IR"})
            if items:
                out[tk] = items
        except Exception:
            continue
    return out


# ── 経済カレンダー ────────────────────────────────────────
def calendar_events(cfg: dict, asof: dt.date) -> list[str]:
    """当日該当する経済イベント名のリスト（優先度加点＋カード素材）。"""
    cal = cfg.get("calendar") or {}
    events = []
    if asof.isoformat() in [str(d) for d in cal.get("fomc", [])]:
        events.append("FOMC結果公表")
    if asof.isoformat() in [str(d) for d in cal.get("boj", [])]:
        events.append("日銀会合結果")
    if cal.get("nfp_rule") == "first_friday" and asof.weekday() == 4 and asof.day <= 7:
        events.append("米雇用統計")
    return events


def fetch_primary(cfg: dict, asof: dt.date, focus_tickers: list[str]) -> dict:
    """レイヤ2一括取得。取得できたものだけ詰めて返す。"""
    out: dict = {"calendar": calendar_events(cfg, asof)}
    ty = treasury_yields(asof)
    if ty:
        out["treasury"] = ty
    fred = {}
    for sid in (cfg.get("fred_series") or {}):
        v = fred_latest(sid, asof)
        if v:
            fred[sid] = v
    if fred:
        out["fred"] = fred
    ir = ir_releases(cfg, focus_tickers, asof)
    if ir:
        out["ir"] = ir
    return out


if __name__ == "__main__":
    import argparse, json, os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config_loader import load_config
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    a = ap.parse_args()
    asof = dt.date.fromisoformat(a.date) if a.date else dt.date.today()
    print(json.dumps(fetch_primary(load_config(), asof, ["NVDA", "MU"]),
                     ensure_ascii=False, indent=1))
