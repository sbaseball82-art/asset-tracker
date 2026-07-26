# -*- coding: utf-8 -*-
"""
etf_data.py
===========
ETF構成銘柄（上位10）の取得とキャッシュ。

- 通常は data/cache/etf_constituents.yml のキャッシュを読む
- --refresh 時のみ各社の公開データ取得を試みる（リトライ3回）。
  失敗したら前回キャッシュを使い、stale: true のまま続行する
  （画像に stale 表記が入る）。
- 取得できない値を推測で埋めることはしない。
"""

from pathlib import Path

from src.common.util import REPO_ROOT, load_yaml, retry, save_yaml

CACHE_PATH = REPO_ROOT / "data" / "cache" / "etf_constituents.yml"

# 公開CSV/JSONのエンドポイント（無料・キー不要のもののみ）
_SOURCES = {
    "VYM": "https://investor.vanguard.com/investment-products/etfs/profile/api/VYM/portfolio-holding/stock",
    "VTI": "https://investor.vanguard.com/investment-products/etfs/profile/api/VTI/portfolio-holding/stock",
    "VOO": "https://investor.vanguard.com/investment-products/etfs/profile/api/VOO/portfolio-holding/stock",
}


def load_constituents(refresh: bool = False) -> dict:
    """{etfs: {SYM: {top10:[...]}}, as_of, stale} を返す。"""
    cache = load_yaml(CACHE_PATH, default=None)
    if cache is None:
        raise FileNotFoundError(f"ETF構成キャッシュがありません: {CACHE_PATH}")
    if refresh:
        cache = _try_refresh(cache)
    return cache


def _try_refresh(cache: dict) -> dict:
    import json
    import urllib.request

    updated = 0
    for sym, url in _SOURCES.items():
        def _fetch(u=url):
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as res:
                return json.loads(res.read().decode("utf-8"))

        data = retry(_fetch, tries=3, wait=5, label=f"ETF構成({sym})")
        if data is None:
            continue
        top10 = _parse_vanguard(data)
        if top10:
            cache["etfs"].setdefault(sym, {})["top10"] = top10
            updated += 1

    if updated == len(_SOURCES):
        from datetime import date
        cache["stale"] = False
        cache["as_of"] = date.today().strftime("%Y-%m")
        save_yaml(CACHE_PATH, cache)
        print(f"[ok] ETF構成キャッシュを更新（{updated}本）")
    else:
        print(f"[warn] ETF構成の取得が不完全（{updated}/{len(_SOURCES)}）。"
              "前回キャッシュを stale として使用")
    return cache


def _parse_vanguard(data) -> list[str]:
    """Vanguard APIレスポンスから上位10ティッカーを抜く（形式変更に弱いので防御的に）。"""
    try:
        items = data.get("fund", {}).get("entity", data if isinstance(data, list) else [])
        rows = []
        for it in items:
            tk = it.get("ticker") or it.get("symbol")
            wt = float(it.get("percentWeight") or it.get("weight") or 0)
            if tk:
                rows.append((tk, wt))
        rows.sort(key=lambda x: -x[1])
        return [t for t, _ in rows[:10]]
    except Exception:  # noqa: BLE001
        return []


def overlap(cache: dict, a: str, b: str) -> tuple[int, list[str]]:
    """上位10銘柄ベースの重複数と共通銘柄リスト。"""
    sa = list(cache["etfs"][a]["top10"])
    sb = set(cache["etfs"][b]["top10"])
    common = [t for t in sa if t in sb]
    return len(common), common
