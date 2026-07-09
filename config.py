# -*- coding: utf-8 -*-
"""
config.py
=========
銘柄のマスタ情報（名前・ISINなど、めったに変わらないもの）を定義します。

★ 保有数量（追加購入で変わるもの）は holdings.json に分離しました。
  買い増したときは holdings.json の数字だけ編集すればOKです。
"""

import json
from pathlib import Path

# 保有数量を holdings.json から読み込む
_HOLDINGS_FILE = Path(__file__).parent / "holdings.json"
try:
    _h = json.loads(_HOLDINGS_FILE.read_text(encoding="utf-8"))
    _ETF_QTY = _h.get("etf", {})
    _FUND_QTY = _h.get("fund", {})
except Exception as e:
    print(f"holdings.json 読込失敗: {e} -> 数量0で続行")
    _ETF_QTY, _FUND_QTY = {}, {}


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
}
FUND_HOLDINGS = {
    code: (name, _FUND_QTY.get(code, 0), isin)
    for code, (name, isin) in _FUND_META.items()
}


# 3. 市場イベント解説の生成モード（"semi" / "auto" / "manual"）
EVENT_MODE = "semi"

# Xアカウント名（@は不要）
X_ACCOUNT = "your_account"

# ポートフォリオのタイトル
PORTFOLIO_TITLE = "わたしの資産推移"
