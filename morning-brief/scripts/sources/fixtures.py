# -*- coding: utf-8 -*-
"""オフライン検証用の決定論的フィクスチャ（--fixtures）。

外部通信ができない開発環境や、受け入れテスト
（「材料が薄い日は0枚」「任意の3日を再現生成」）のための合成データ。
シナリオ日:
  2026-07-22  メモリショック（MU急落・SOX/NVDA連れ安・大商い）
  2026-07-23  金利ショック（米10年金利急伸・株は小反落）
  2026-07-20  静かな日（異常なし → 画像0枚で正常終了の確認用）
上記以外の日付は「静かな日」として生成される。
"""
from __future__ import annotations
import datetime as dt
import math
import random

_ANCHOR = dt.date(2026, 7, 24)   # 系列の最終営業日

# ticker: (基準価格, 日次ボラ%, 基準出来高)
_BASE = {
    "^GSPC": (6300, 0.7, 0), "^IXIC": (20500, 0.9, 0), "^DJI": (44500, 0.6, 0),
    "^SOX": (5600, 1.6, 0), "^TNX": (4.25, 1.2, 0), "JPY=X": (152.0, 0.5, 0),
    "VTI": (310, 0.7, 4e6), "QQQ": (560, 0.9, 3e7), "VYM": (135, 0.5, 1e6),
    "HDV": (122, 0.5, 4e5), "SCHD": (29, 0.5, 1e7), "SMH": (290, 1.6, 8e6),
    "XLE": (92, 1.0, 1.5e7), "XLF": (52, 0.8, 3e7), "XLU": (82, 0.7, 1e7),
    "NVDA": (178, 2.2, 2e8), "MSFT": (505, 1.1, 2e7), "AAPL": (232, 1.2, 5e7),
    "GOOGL": (198, 1.4, 3e7), "AMZN": (228, 1.5, 4e7), "META": (720, 1.6, 1.5e7),
    "TSLA": (320, 3.0, 9e7), "AVGO": (285, 2.0, 2e7), "MU": (128, 2.6, 2.5e7),
    "INTC": (23, 2.2, 5e7), "TSM": (245, 1.8, 1.5e7), "AMD": (165, 2.4, 4e7),
}

# シナリオ: date -> {ticker: (リターン%, 出来高倍率)}
_SHOCKS = {
    dt.date(2026, 7, 22): {
        "MU": (-13.2, 4.2), "^SOX": (-4.1, 1.0), "SMH": (-3.9, 2.6),
        "NVDA": (-3.4, 1.9), "AMD": (-3.0, 1.7), "TSM": (-2.5, 1.5),
        "^GSPC": (-1.1, 1.0), "QQQ": (-1.5, 1.4), "^IXIC": (-1.4, 1.0),
        "^TNX": (0.5, 1.0),
    },
    dt.date(2026, 7, 23): {
        "^TNX": (3.8, 1.0), "^GSPC": (-0.9, 1.0), "^IXIC": (-1.3, 1.0),
        "QQQ": (-1.3, 1.3), "XLF": (1.2, 1.4), "XLU": (-1.6, 1.3),
        "JPY=X": (0.8, 1.0), "MSFT": (-1.5, 1.2), "NVDA": (-1.8, 1.1),
    },
}


def _bdays_until(end: dt.date, n: int) -> list[dt.date]:
    days, d = [], end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= dt.timedelta(days=1)
    return list(reversed(days))


def fixture_market(asof: dt.date) -> dict:
    """全ティッカーの合成日足（asofまで・約260営業日）。決定論的。"""
    end = max(asof, _ANCHOR) if asof > _ANCHOR else asof
    days = _bdays_until(_ANCHOR, 260)
    days = [d for d in days if d <= asof] or days[:70]
    out = {}
    for tk, (base, vol_pct, base_vol) in _BASE.items():
        rng = random.Random(f"mb-fixture-{tk}")
        closes, volumes = [], []
        price = base * 0.9
        for d in days:
            shock = _SHOCKS.get(d, {}).get(tk)
            r = (shock[0] / 100 if shock
                 else rng.gauss(0.0004, vol_pct / 100))
            price *= (1 + r)
            closes.append(round(price, 4))
            vmul = shock[1] if shock else max(0.4, rng.lognormvariate(0, 0.25))
            volumes.append(int(base_vol * vmul))
        out[tk] = {"dates": [d.isoformat() for d in days],
                   "closes": closes, "volumes": volumes}
    return out


def fixture_buzz(asof: dt.date) -> dict:
    if asof == dt.date(2026, 7, 22):
        mu_heads = [
            {"title": "SK Hynix to expand HBM capacity in 2026, memory stocks slide", "outlet": "Reuters", "url": "https://example.com/reuters-hbm"},
            {"title": "SKハイニックスのHBM増産報道でメモリ株が急落", "outlet": "日本経済新聞", "url": ""},
            {"title": "Micron plunges as HBM supply fears hit chipmakers", "outlet": "Bloomberg", "url": ""},
            {"title": "Memory stocks tumble on oversupply concerns", "outlet": "CNBC", "url": ""},
        ]
        semi_heads = [
            {"title": "Chip stocks fall broadly as memory selloff spreads", "outlet": "MarketWatch", "url": ""},
            {"title": "半導体株が全面安 SOX指数4%下落", "outlet": "Google News", "url": ""},
        ]
        return {"headlines": {"MU": mu_heads, "^SOX": semi_heads,
                              "SMH": semi_heads, "NVDA": semi_heads[:1]},
                "sns": {"MU": 1.0, "NVDA": 0.5, "^SOX": 0.4}}
    if asof == dt.date(2026, 7, 23):
        return {"headlines": {"^TNX": [
            {"title": "10-year Treasury yield jumps after weak auction", "outlet": "Reuters", "url": "https://example.com/reuters-ust"},
            {"title": "米長期金利が急上昇 入札不調で", "outlet": "日本経済新聞", "url": ""},
            {"title": "Treasury yields spike, pressuring tech stocks", "outlet": "Bloomberg", "url": ""},
        ]}, "sns": {"^TNX": 0.6, "QQQ": 0.3}}
    return {"headlines": {}, "sns": {}}


def fixture_primary(asof: dt.date) -> dict:
    out = {"calendar": []}
    if asof == dt.date(2026, 7, 23):
        out["treasury"] = {"date": asof.isoformat(), "y2": 3.92, "y10": 4.46,
                           "y30": 4.88, "source": "米財務省"}
    elif asof == dt.date(2026, 7, 22):
        out["treasury"] = {"date": asof.isoformat(), "y2": 3.88, "y10": 4.31,
                           "y30": 4.74, "source": "米財務省"}
    return out
