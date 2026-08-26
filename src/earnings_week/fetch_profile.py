# -*- coding: utf-8 -*-
"""
fetch_profile.py
================
企業名・時価総額・ロゴを Finnhub の ``stock/profile2`` から取る。

    GET https://finnhub.io/api/v1/stock/profile2?symbol=AAPL&token=

* プロフィール（名前・時価総額・ロゴURL）は ``cache/profiles.json`` に30日キャッシュ
* ロゴ画像は ``cache/logos/{TICKER}.png`` に30日キャッシュし、**毎回落とし直さない**
* 取れなかったものは None のまま返す。名前を推測したり時価総額を0で埋めたりしない
  （時価総額が無い銘柄は並び順の最後に回る）

``marketCapitalization`` は Finnhub の仕様で **百万USD単位**。
並べ替えにしか使わないので単位変換はしないが、画像には出さない。
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from .fetch_earnings import FinnhubError, finnhub_get

PROFILE_TTL_DAYS = 30
LOGO_TTL_DAYS = 30
LOGO_TIMEOUT_SEC = 15
LOGO_MAX_BYTES = 2_000_000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _age_days(path: Path) -> float:
    stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return (_now() - stamp).total_seconds() / 86400


# ---------------------------------------------------------------- プロフィール


class ProfileCache:
    """cache/profiles.json（symbol → {name, market_cap, logo, fetched_at}）。"""

    def __init__(self, path: Path, ttl_days: int = PROFILE_TTL_DAYS):
        self.path = path
        self.ttl = timedelta(days=ttl_days)
        self.data: dict[str, dict] = {}
        if path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                self.data = {}   # 壊れていたら捨てて取り直す

    def get(self, symbol: str) -> dict | None:
        row = self.data.get(symbol)
        if not row:
            return None
        try:
            fetched = datetime.fromisoformat(row["fetched_at"])
        except (KeyError, ValueError):
            return None
        if _now() - fetched > self.ttl:
            return None
        return row

    def put(self, symbol: str, row: dict) -> None:
        self.data[symbol] = dict(row, fetched_at=_now().isoformat())

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2),
                             encoding="utf-8")


def fetch_profile(symbol: str, token: str) -> dict:
    """1銘柄ぶんのプロフィール。取れなかった項目は None のまま。"""
    payload = finnhub_get("stock/profile2", {"symbol": symbol}, token)
    if not isinstance(payload, dict):
        raise FinnhubError(f"profile2 の応答が想定外です: {symbol}")
    cap = payload.get("marketCapitalization")
    try:
        cap = float(cap) if cap not in (None, "") else None
    except (TypeError, ValueError):
        cap = None
    return {
        "name": (payload.get("name") or "").strip(),
        "market_cap": cap,          # 百万USD（並べ替え用。画像には出さない）
        "logo": (payload.get("logo") or "").strip(),
    }


# ---------------------------------------------------------------- ロゴ


def logo_path(symbol: str, logo_dir: Path) -> Path:
    return logo_dir / f"{symbol}.png"


def ensure_logo(symbol: str, url: str, logo_dir: Path,
                ttl_days: int = LOGO_TTL_DAYS, offline: bool = False) -> Path | None:
    """ロゴをキャッシュに用意して返す。取れなければ None（呼び出し側が代替表示）。"""
    dest = logo_path(symbol, logo_dir)
    if dest.exists() and _age_days(dest) <= ttl_days:
        return dest
    if offline or not url:
        return dest if dest.exists() else None

    try:
        res = requests.get(url, timeout=LOGO_TIMEOUT_SEC,
                           headers={"User-Agent": "asset-tracker/earnings-week"})
        if res.status_code != 200 or not res.content:
            raise OSError(f"HTTP {res.status_code}")
        if len(res.content) > LOGO_MAX_BYTES:
            raise OSError(f"大きすぎます（{len(res.content)} bytes）")

        from io import BytesIO

        from PIL import Image
        with Image.open(BytesIO(res.content)) as img:
            img.load()
            rgba = img.convert("RGBA")
        rgba.thumbnail((320, 320), Image.LANCZOS)
        dest.parent.mkdir(parents=True, exist_ok=True)
        rgba.save(dest, "PNG")
        return dest
    except Exception as exc:  # noqa: BLE001 — ロゴ1つで生成を止めない
        print(f"[logo] {symbol}: 取得できませんでした（{exc}）→ 代替表示にします")
        return dest if dest.exists() else None


# ---------------------------------------------------------------- まとめ


def enrich(entries: list[dict], token: str | None, cache_dir: Path,
           offline: bool = False) -> tuple[list[dict], list[str]]:
    """決算エントリに 企業名・時価総額・ロゴのパス を足す。

    Returns:
        (足したエントリ, ロゴが取れなかったティッカー)
    """
    cache = ProfileCache(cache_dir / "profiles.json")
    logo_dir = cache_dir / "logos"
    missing_logo: list[str] = []
    out: list[dict] = []

    for entry in entries:
        symbol = entry["symbol"]
        row = cache.get(symbol)
        if row is None and not offline and token:
            try:
                row = fetch_profile(symbol, token)
                cache.put(symbol, row)
            except FinnhubError as exc:
                print(f"[profile] {symbol}: 取得できませんでした（{exc}）")
                row = None
        if row is None:
            row = cache.data.get(symbol) or {}   # 期限切れでも在るものは使う

        logo = ensure_logo(symbol, row.get("logo") or "", logo_dir, offline=offline)
        if logo is None:
            missing_logo.append(symbol)
        out.append(dict(entry,
                        name=row.get("name") or "",
                        market_cap=row.get("market_cap"),
                        logo_path=str(logo) if logo else None))
        time.sleep(0)   # 明示的な譲り（throttle は finnhub_get 側）

    cache.save()
    return out, missing_logo


def sort_by_market_cap(entries: list[dict]) -> list[dict]:
    """時価総額の大きい順。取れていない銘柄は最後に回す。"""
    return sorted(entries,
                  key=lambda e: (-(e.get("market_cap") or 0.0), e["symbol"]))
