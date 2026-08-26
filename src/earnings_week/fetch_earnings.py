# -*- coding: utf-8 -*-
"""
fetch_earnings.py
=================
Finnhub の Earnings Calendar から「その週に決算を出す会社」を取る。

    GET https://finnhub.io/api/v1/calendar/earnings?from=&to=&token=

APIキーは環境変数 ``FINNHUB_API_KEY`` から読む。**コードに直書きしない。**

無料枠は 60 req/min。呼び出し間隔を空け、429/5xx は指数バックオフで
リトライする。取れなかったものを推測で埋めることはしない
（EPS予想が null なら null のまま持ち回り、画像には「—」と出る）。
"""

from __future__ import annotations

import os
import time
from datetime import date, timedelta

import requests

API_BASE = "https://finnhub.io/api/v1"

# 無料枠は 60 req/min。少し余裕を持たせる
MIN_INTERVAL_SEC = 1.1
RETRY_WAITS = (2, 4, 8, 16)
TIMEOUT_SEC = 20

_last_call = 0.0


class FinnhubError(RuntimeError):
    """Finnhub からデータを取れなかった。"""


class MissingAPIKey(FinnhubError):
    """APIキーが設定されていない。"""


def api_key(explicit: str | None = None) -> str:
    key = explicit or os.environ.get("FINNHUB_API_KEY", "")
    if not key.strip():
        raise MissingAPIKey(
            "環境変数 FINNHUB_API_KEY が設定されていません。"
            "https://finnhub.io/ でキーを取得し、GitHub の "
            "Settings > Secrets and variables > Actions に FINNHUB_API_KEY として"
            "登録してください（ローカルなら export FINNHUB_API_KEY=...）。")
    return key.strip()


def _throttle() -> None:
    global _last_call
    wait = MIN_INTERVAL_SEC - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def finnhub_get(path: str, params: dict, token: str,
                timeout: int = TIMEOUT_SEC) -> dict | list:
    """Finnhub を叩く。レート制限と一時的な失敗はリトライする。"""
    url = f"{API_BASE}/{path.lstrip('/')}"
    query = dict(params, token=token)
    last_error = ""

    for attempt in range(len(RETRY_WAITS) + 1):
        _throttle()
        try:
            res = requests.get(url, params=query, timeout=timeout)
        except requests.RequestException as exc:
            last_error = f"通信エラー: {exc}"
        else:
            if res.status_code == 200:
                try:
                    return res.json()
                except ValueError as exc:
                    last_error = f"JSONとして読めません: {exc}"
            elif res.status_code in (401, 403):
                raise FinnhubError(
                    f"Finnhub に拒否されました（HTTP {res.status_code}）。"
                    "FINNHUB_API_KEY が正しいか、無料枠で使えるエンドポイントかを"
                    f"確認してください。path={path}")
            elif res.status_code == 429:
                wait = float(res.headers.get("Retry-After") or 0)
                if wait > 0:
                    time.sleep(min(wait, 60))
                last_error = "レート制限（HTTP 429）"
            else:
                last_error = f"HTTP {res.status_code}"

        if attempt < len(RETRY_WAITS):
            print(f"[retry] {path}: {last_error} — "
                  f"{RETRY_WAITS[attempt]}秒待って再試行 "
                  f"({attempt + 1}/{len(RETRY_WAITS)})")
            time.sleep(RETRY_WAITS[attempt])

    raise FinnhubError(f"Finnhub の取得に失敗しました（{path}）: {last_error}")


# ---------------------------------------------------------------- 週


def week_bounds(week_start: date) -> tuple[date, date]:
    """その日を含む週の月曜と金曜を返す。"""
    monday = week_start - timedelta(days=week_start.weekday())
    return monday, monday + timedelta(days=4)


def next_week_start(today: date) -> date:
    """「翌週の月曜」。日曜夜に走らせて翌週分を作るため。"""
    return today + timedelta(days=7 - today.weekday())


# ---------------------------------------------------------------- 取得


def fetch_calendar(start: date, end: date, token: str) -> list[dict]:
    """指定期間の決算カレンダーを取る（絞り込み前の生データ）。"""
    payload = finnhub_get("calendar/earnings",
                          {"from": start.isoformat(), "to": end.isoformat()},
                          token)
    if not isinstance(payload, dict):
        raise FinnhubError(f"想定外の応答です: {type(payload).__name__}")
    rows = payload.get("earningsCalendar") or []
    out = []
    for row in rows:
        symbol = (row.get("symbol") or "").strip().upper()
        day = (row.get("date") or "").strip()
        if not symbol or not day:
            continue
        try:
            parsed = date.fromisoformat(day)
        except ValueError:
            continue
        if not (start <= parsed <= end):
            continue
        out.append({
            "symbol": symbol,
            "date": day,
            "hour": (row.get("hour") or "").strip().lower(),
            "eps_estimate": _num(row.get("epsEstimate")),
            "revenue_estimate": _num(row.get("revenueEstimate")),
            "quarter": row.get("quarter"),
            "year": row.get("year"),
        })
    return out


def _num(value) -> float | None:
    """数値でなければ None。0埋めや平均値での補完はしない。"""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def filter_watchlist(entries: list[dict], watchlist: list[str]) -> list[dict]:
    """watchlist に載っているティッカーだけ残す。"""
    wanted = {s.strip().upper() for s in watchlist if s and s.strip()}
    return [e for e in entries if e["symbol"] in wanted]


def dedupe(entries: list[dict]) -> list[dict]:
    """同じ週に同じ銘柄が複数回出てきたら1つにまとめる。

    予想値が入っているほうを優先し、同条件なら早い日付を採る。
    """
    best: dict[str, dict] = {}
    for e in entries:
        cur = best.get(e["symbol"])
        if cur is None:
            best[e["symbol"]] = e
            continue
        score = (e["eps_estimate"] is not None) + (e["revenue_estimate"] is not None)
        cur_score = (cur["eps_estimate"] is not None) + (cur["revenue_estimate"] is not None)
        if score > cur_score or (score == cur_score and e["date"] < cur["date"]):
            best[e["symbol"]] = e
    return sorted(best.values(), key=lambda e: (e["date"], e["symbol"]))
