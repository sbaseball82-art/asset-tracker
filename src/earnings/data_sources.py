# -*- coding: utf-8 -*-
"""
data_sources.py
===============
決算実況用のデータ取得。

方針（依頼書 2-4 / 3-3）:
- 予想EPS/実績: Finnhub 無料枠を第一候補。FINNHUB_API_KEY が無い・
  取得失敗の場合は None を返し、テンプレ側で「要手動入力」と表示する。
  **推測値は絶対に埋めない。**
- 株価騰落率: 既存の取得系（yfinance）を流用。失敗時は None。
- すべてリトライ3回。
"""

import json
import os
import urllib.parse
import urllib.request

from src.common.util import retry


def _finnhub_get(path: str, params: dict) -> dict | None:
    key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not key:
        return None
    params = {**params, "token": key}
    url = f"https://finnhub.io/api/v1/{path}?{urllib.parse.urlencode(params)}"

    def _fetch():
        req = urllib.request.Request(url, headers={"User-Agent": "asset-tracker"})
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode("utf-8"))

    return retry(_fetch, tries=3, wait=5, label=f"Finnhub {path}")


def get_earnings_estimates(ticker: str, date_from: str, date_to: str) -> dict:
    """{eps_estimate, eps_actual, revenue_estimate, revenue_actual, hour}
    取得できない項目は None（→表示は「要手動入力」）。"""
    out = {"eps_estimate": None, "eps_actual": None,
           "revenue_estimate": None, "revenue_actual": None, "hour": None}
    data = _finnhub_get("calendar/earnings",
                        {"from": date_from, "to": date_to, "symbol": ticker})
    if not data:
        return out
    for row in data.get("earningsCalendar", []):
        if row.get("symbol") == ticker:
            out["eps_estimate"] = row.get("epsEstimate")
            out["eps_actual"] = row.get("epsActual")
            out["revenue_estimate"] = row.get("revenueEstimate")
            out["revenue_actual"] = row.get("revenueActual")
            out["hour"] = row.get("hour")
            break
    return out


def get_price_change_pct(ticker: str) -> float | None:
    """直近終値の前日比(%)。取得失敗は None（→「要手動入力」）。"""
    def _fetch():
        import yfinance as yf
        df = yf.download(tickers=ticker, period="7d", interval="1d",
                         auto_adjust=False, progress=False)
        closes = df["Close"].dropna()
        if hasattr(closes, "iloc") and len(closes) >= 2:
            last = float(closes.iloc[-1])
            prev = float(closes.iloc[-2])
            return round((last / prev - 1) * 100, 2)
        raise ValueError("終値が2日分取れませんでした")

    return retry(_fetch, tries=3, wait=5, label=f"株価({ticker})")
