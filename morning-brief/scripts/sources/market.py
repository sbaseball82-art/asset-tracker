# -*- coding: utf-8 -*-
"""レイヤ1：市場の実際の動き（最優先シグナル・APIキー不要）。

yfinance で config.yaml のティッカーの日次終値・出来高を取得し、
- 当日リターンの z-score（直近60営業日のリターン分布に対して）
- 出来高比（当日出来高 / 20日平均）
を算出する。「実際に価格が動いた」銘柄だけが深掘り候補になる。

単体実行: python scripts/sources/market.py [--date YYYY-MM-DD]
"""
from __future__ import annotations
import datetime as dt
import math
import statistics


def all_tickers(cfg: dict) -> dict[str, str]:
    """ticker -> 日本語表示名"""
    out: dict[str, str] = {}
    for group in ("indices", "etfs", "stocks", "watch"):
        out.update(cfg["tickers"].get(group) or {})
    return out


def ticker_kind(cfg: dict, tk: str) -> str:
    for group in ("indices", "etfs", "stocks", "watch"):
        if tk in (cfg["tickers"].get(group) or {}):
            return "index" if group == "indices" else ("etf" if group == "etfs" else "stock")
    return "stock"


def fetch_market(cfg: dict, asof: dt.date) -> dict:
    """全ティッカーの約1年の日足を取得し asof 以前に切り詰める。

    返り値: {ticker: {"dates": [date...], "closes": [...], "volumes": [...]}}
    一部銘柄の失敗はその銘柄だけ欠落。全滅なら {}。
    """
    names = all_tickers(cfg)
    try:
        import yfinance as yf
        raw = yf.download(tickers=list(names), period="1y", interval="1d",
                          progress=False, auto_adjust=True, group_by="ticker",
                          threads=True)
    except Exception as e:
        print(f"[warn] yfinance 取得失敗: {e}")
        return {}

    out = {}
    for tk in names:
        try:
            df = raw[tk].dropna(subset=["Close"])
            dates = [d.date() for d in df.index]
            keep = [i for i, d in enumerate(dates) if d <= asof]
            if len(keep) < 70:   # z-scoreに60営業日必要
                continue
            out[tk] = {
                "dates": [dates[i].isoformat() for i in keep],
                "closes": [float(df["Close"].iloc[i]) for i in keep],
                "volumes": [float(df["Volume"].iloc[i] or 0) for i in keep],
            }
        except Exception:
            continue
    print(f"[ok] レイヤ1 マーケットデータ: {len(out)}/{len(names)} 銘柄")
    return out


def metrics(series: dict, cfg: dict) -> dict | None:
    """当日リターン・z-score・出来高比・6ヶ月騰落などを計算する。"""
    closes, volumes = series["closes"], series["volumes"]
    if len(closes) < 70:
        return None
    look = cfg["anomaly"]["z_lookback_days"]
    vdays = cfg["anomaly"]["vol_avg_days"]

    rets = [(closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(1, len(closes)) if closes[i - 1]]
    ret1d = rets[-1]
    hist = rets[-(look + 1):-1]          # 当日を除く直近60本
    mu = statistics.fmean(hist)
    sd = statistics.pstdev(hist)
    z = (ret1d - mu) / sd if sd > 1e-9 else 0.0

    vhist = [v for v in volumes[-(vdays + 1):-1] if v > 0]
    vol_ratio = (volumes[-1] / statistics.fmean(vhist)) if vhist and volumes[-1] > 0 else None

    n6m = min(len(closes) - 1, 126)      # 約6ヶ月
    ret6m = (closes[-1] - closes[-1 - n6m]) / closes[-1 - n6m]

    return {
        "last": closes[-1], "prev": closes[-2],
        "ret1d_pct": ret1d * 100, "zscore": z,
        "vol_ratio": vol_ratio,
        "ret6m_pct": ret6m * 100,
        "asof": series["dates"][-1],
    }


def find_anomalies(market: dict, cfg: dict,
                   require_asof: str | None = None) -> list[dict]:
    """z-score・出来高比の閾値を超えた「実際に動いた」銘柄を返す。

    require_asof を渡すと、最終バーがその日付でない銘柄（休場・更新遅れの
    古いデータ）は候補から除外する。週末や祝日に前日分を重複生成しないための安全弁。
    """
    names = all_tickers(cfg)
    out = []
    for tk, series in market.items():
        if require_asof and series["dates"][-1] != require_asof:
            continue
        m = metrics(series, cfg)
        if not m:
            continue
        kind = ticker_kind(cfg, tk)
        hit_z = abs(m["zscore"]) >= cfg["anomaly"]["min_abs_z"]
        hit_v = (kind == "stock" and m["vol_ratio"] is not None
                 and m["vol_ratio"] >= cfg["anomaly"]["min_vol_ratio"])
        if not (hit_z or hit_v):
            continue
        out.append({
            "ticker": tk, "name": names.get(tk, tk), "kind": kind,
            "metrics": m,
        })
    out.sort(key=lambda c: -abs(c["metrics"]["zscore"]))
    return out


def _fmt_value(tk: str, v: float) -> str:
    if tk == "JPY=X":
        return f"{v:,.2f}円"
    if tk == "^TNX":
        return f"{v:.2f}%"
    if v >= 1000:
        return f"{v:,.0f}"
    return f"{v:,.2f}"


if __name__ == "__main__":
    import argparse, json, os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config_loader import load_config
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    a = ap.parse_args()
    cfg = load_config()
    asof = dt.date.fromisoformat(a.date) if a.date else dt.date.today()
    mkt = fetch_market(cfg, asof)
    print(json.dumps(find_anomalies(mkt, cfg), ensure_ascii=False, indent=1, default=str))
