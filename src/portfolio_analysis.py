"""無料・ローカルの分析。構成銘柄・ヘッジ情報がない部分は推測しない。"""
from __future__ import annotations

import math
from datetime import date


# 既存マスタの商品分類。企業の所在地・実質国別構成比ではない。
US_MARKET_PRODUCTS = {
    "VTI", "VYM", "HDV", "QQQ", "FTNT", "29313233", "89311199",
    "04311181", "8931224C", "89311265",
}
USD_LISTED_PRODUCTS = {"VTI", "VYM", "HDV", "QQQ", "DRAM", "FTNT"}
NASDAQ_PRODUCTS = {"QQQ", "29313233", "89311265"}


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _drawdown(data):
    """推定拠出を除いた日末入出金モデル。厳密な TWR・配当込み収益ではない。"""
    result = {
        "pct": None, "reason": "連続した統合履歴を蓄積中",
        "method": "数量変更の推定拠出を除外した概算指数（日末入出金、配当・税を除く）",
    }
    history = data.get("history") or []
    if len(history) < 2:
        return result
    previous_date = None
    for row in history:
        try:
            row_date = date.fromisoformat(row["date"])
        except (KeyError, TypeError, ValueError):
            result["reason"] = "履歴の日付が不正"
            return result
        if previous_date is not None and (row_date - previous_date).days != 1:
            result["reason"] = "履歴に欠落・日付の重複あり"
            return result
        previous_date = row_date
        if row.get("complete") is not True or row.get("stale") is not False:
            result["reason"] = "欠損・旧価格・未検証の履歴を含むため算出保留"
            return result
        if (not _finite(row.get("total_jpy")) or row["total_jpy"] <= 0
                or not _finite(row.get("cash_flow_jpy"))):
            result["reason"] = "評価額または資金流出入の記録不足"
            return result
    if history[-1]["date"] != data.get("date") or history[-1]["total_jpy"] != data.get("total_jpy"):
        result["reason"] = "履歴が現在の評価額と一致しない"
        return result
    index = peak = 1.0
    maximum = 0.0
    for previous, current in zip(history, history[1:]):
        factor = (current["total_jpy"] - current["cash_flow_jpy"]) / previous["total_jpy"]
        if not _finite(factor) or factor <= 0:
            result["reason"] = "推定拠出で収益率を検算できない期間あり"
            return result
        index *= factor
        if not math.isfinite(index):
            result["reason"] = "履歴の計算値が不正"
            return result
        peak = max(peak, index)
        maximum = min(maximum, index / peak - 1.0)
    result.update(pct=round(maximum * 100, 2), reason="統合履歴期間内・拠出調整後の概算")
    return result


def analyze(data: dict) -> dict:
    """集中・限定的な為替感応度・履歴上の下落率。I/O・売買判断なし。"""
    rows = [(kind, symbol, row) for kind in ("etf", "fund", "stocks")
            for symbol, row in (data.get(kind) or {}).items()]
    symbols = {symbol for _, symbol, row in rows if _finite(row.get("curr_jpy")) and row["curr_jpy"] > 0}
    groups = []
    nasdaq = sorted(symbols & NASDAQ_PRODUCTS)
    if len(nasdaq) > 1:
        groups.append({"label": "NASDAQ100連動商品の重複", "symbols": nasdaq})
    broad = sorted(symbols & {"VTI", "89311199", "QQQ", "29313233", "89311265", "04311181"})
    if "VTI" in broad and len(broad) > 1:
        groups.append({"label": "全米株と大型株・NASDAQ系の重複候補", "symbols": broad})
    overlap_note = "構成銘柄の最新データ不足：実質重複率は未算出"
    if groups:
        overlap_note = "NASDAQ系・全米株に重複候補。実質重複率はデータ不足"
    result = {
        "largest_holding": None, "category_weights_pct": None, "direct_usd_exposure": None,
        "us_market_policy": {
            "known_product_weight_pct": None, "unknown_weight_pct": None,
            "note": "米国市場を主対象とする商品の配分。企業の国別比率ではありません",
        },
        "overlap": {"groups": groups, "underlying_overlap_pct": None, "note": overlap_note},
        "max_drawdown": {"pct": None, "reason": "現在の全資産評価額が未確定", "method": "拠出調整後の概算"},
        "notes": [],
    }
    total = data.get("total_jpy")
    valid = (bool(rows) and data.get("complete") is not False and _finite(total) and total > 0
             and all(_finite(row.get("curr_jpy")) and row["curr_jpy"] >= 0 for _, _, row in rows))
    if not valid or abs(sum(row["curr_jpy"] for _, _, row in rows) - total) > 1:
        result["notes"] = ["欠損・集計不一致のため構成比と感応度は未算出", overlap_note]
        return result
    _, symbol, largest = max(rows, key=lambda item: item[2]["curr_jpy"])
    result["largest_holding"] = {
        "symbol": symbol, "name": largest.get("name", symbol),
        "pct": round(largest["curr_jpy"] / total * 100, 2),
    }
    result["category_weights_pct"] = {
        category: round(sum(row["curr_jpy"] for kind, _, row in rows if kind == category) / total * 100, 2)
        for category in ("etf", "fund", "stocks")
    }
    known_us = sum(row["curr_jpy"] for _, symbol, row in rows if symbol in US_MARKET_PRODUCTS)
    result["us_market_policy"].update(
        known_product_weight_pct=round(known_us / total * 100, 2),
        unknown_weight_pct=round((total - known_us) / total * 100, 2),
    )
    direct = [(symbol, row) for kind, symbol, row in rows if kind in ("etf", "stocks")
              and (row.get("currency") == "USD" or (symbol in USD_LISTED_PRODUCTS and row.get("currency", "USD") == "USD"))]
    rate = data.get("usdjpy")
    if _finite(rate) and rate > 0:
        value = sum(row["curr_jpy"] for _, row in direct)
        result["direct_usd_exposure"] = {
            "value_jpy": value, "weight_pct": round(value / total * 100, 2),
            "per_yen_jpy": round(value / rate),
            "note": "USD建て直接保有のみ・株価固定。投信内部の為替・ヘッジ効果は未算出",
        }
    result["max_drawdown"] = _drawdown(data)
    result["notes"] = [
        f"最大保有商品 {symbol}：{result['largest_holding']['pct']:.1f}%（中身の企業集中は未算出）",
        overlap_note,
        "米国市場への依存は商品分類で確認。実効国別比率は構成データ不足",
        "為替感応度は直接USD保有のみ。投信内部の為替影響は含みません",
    ]
    if any(row.get("stale") for _, _, row in rows) or (data.get("fx") or {}).get("stale"):
        result["notes"].insert(0, "旧価格を含むため現在の分析値は参考値")
    return result
