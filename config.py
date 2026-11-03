# -*- coding: utf-8 -*-
"""
config.py
=========
銘柄のマスタ情報（名前・ISINなど、めったに変わらないもの）を定義します。

★ 保有数量（追加購入で変わるもの）は holdings.json に分離しました。
  買い増したときは holdings.json の数字だけ編集すればOKです。
"""

import json
import math
from pathlib import Path

# 保有数量を holdings.json から読み込む
_HOLDINGS_FILE = Path(__file__).parent / "holdings.json"
try:
    _h = json.loads(_HOLDINGS_FILE.read_text(encoding="utf-8"))
    _ETF_QTY = _h.get("etf", {})
    _FUND_QTY = _h.get("fund", {})
except (OSError, ValueError) as e:
    raise RuntimeError("holdings.json を読めません。数量を確認してください") from e


# 1. 保有ETF：シンボル -> (表示名, 保有株数)
_ETF_NAMES = {
    "VYM": "VYM 米国高配当ETF",
    "VTI": "VTI 全米株式ETF",
    "HDV": "HDV 米国高配当ETF",
    "QQQ": "QQQ ナスダック100ETF",
    "DRAM": "DRAM メモリ半導体ETF",
}
ETF_HOLDINGS = {
    sym: (name, _ETF_QTY.get(sym, 0))
    for sym, name in _ETF_NAMES.items()
}


# 2. 保有投資信託：協会コード -> (表示名, 保有口数, ISINコード)
_FUND_META = {
    "29313233":     ("ニッセイNASDAQ100",          "JP90C000PDY6"),
    "89311199":     ("SBI・V・S&P500",             "JP90C000J569"),
    "04311181":     ("iFreeNEXT FANG+",            "JP90C000FZD4"),
    "8931224C":     ("SBI S 米国高配当(年4回)",    "JP90C000REE2"),
    "79314186":     ("イノベーションAI", "JP90C000GK01"),
    "89311265":     ("SBI NASDAQ100",              "JP90C000PVT8"),
}
FUND_HOLDINGS = {
    code: (name, _FUND_QTY.get(code, 0), isin)
    for code, (name, isin) in _FUND_META.items()
}


# 個別株はETFと別分類。数量・取得情報も holdings.json から読む。
STOCK_HOLDINGS = _h.get("stocks", {})


def load_stocks():
    """個別株設定を検証する。取得単価・購入日が未設定ならそのまま残す。"""
    try:
        if not isinstance(STOCK_HOLDINGS, dict) or not STOCK_HOLDINGS:
            raise ValueError("missing stocks")
        stocks = {symbol: dict(value) for symbol, value in STOCK_HOLDINGS.items()}
        for symbol, values in stocks.items():
            if not isinstance(symbol, str) or not symbol or values.get("currency") != "USD":
                raise ValueError("invalid symbol/currency")
            qty = values.get("shares")
            if isinstance(qty, bool) or not isinstance(qty, int) or qty < 0:
                raise ValueError("invalid quantity")
            for field in ("purchase_price_usd", "purchase_usdjpy"):
                value = values.get(field)
                if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                          or not math.isfinite(value) or value <= 0):
                    raise ValueError("invalid cost")
            if values.get("purchase_date") is not None:
                from datetime import date
                date.fromisoformat(values["purchase_date"])
    except (ValueError, TypeError):
        raise ValueError("holdings.json の個別株設定が不正です。数量・通貨・取得単価・日付を確認してください") from None
    return stocks


# 3. 市場イベント解説の生成モード（"semi" / "auto" / "manual"）
EVENT_MODE = "semi"

# Xアカウント名（@は不要）
# ★ 実体は config.yml の account.x_handle。ここは既存スクリプト
#   （make_slide.py など）が import してくるための入口として残している。
try:
    from src.common.settings import x_handle as _x_handle
    X_ACCOUNT = _x_handle()
except Exception as e:  # noqa: BLE001
    print(f"config.yml 読込失敗: {e} -> 既定のアカウント名で続行")
    X_ACCOUNT = "your_account"

# ポートフォリオのタイトル
PORTFOLIO_TITLE = "わたしの資産推移"
