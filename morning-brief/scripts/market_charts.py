# -*- coding: utf-8 -*-
"""カードに載せるマーケットチャート・統計タイルのデータ取得と描画。

- fetch_market_data(): yfinance で主要指数・関連銘柄の6ヶ月終値を一括取得。
  一部失敗はその銘柄だけ欠落、全滅なら {} を返す（呼び出し側がフォールバック）。
- story_instrument(): 見出しのキーワード → 関連インストゥルメント(ticker, 表示名)。
- draw_price_chart(): ダークテーマの折れ線（面塗り・最新値注釈・騰落バッジ）。
- フォールバックのビジュアル（数字パネル・概念図）は news_visuals.py 側にある。
"""
from __future__ import annotations
import datetime as dt

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

INK = "#eef2f8"; DIM = "#8fa0b8"; LINE = "#2a3650"
ACCENT = "#4fd1c5"   # 添付サンプル準拠のティール
UP = "#5fd0a0"; DOWN = "#e8807f"; PANEL = "#131f33"

# 取得対象（カードのタイル・チャートで使う基本セット）
UNIVERSE = {
    "^GSPC":  "S&P500",
    "^IXIC":  "ナスダック総合",
    "^DJI":   "NYダウ",
    "^N225":  "日経平均",
    "^SOX":   "半導体指数(SOX)",
    "^TNX":   "米10年金利",
    "JPY=X":  "ドル円",
    "MU":     "マイクロン(MU)",
    "NVDA":   "エヌビディア(NVDA)",
}

# 見出しキーワード → 関連インストゥルメント（上から先勝ち）
TOPIC_MAP = [
    (("メモリ", "キオクシア", "DRAM", "NAND", "HBM", "サンディスク", "SanDisk",
      "マイクロン", "Micron", "SK hynix", "ハイニックス"), "MU"),
    (("エヌビディア", "NVIDIA", "Nvidia"), "NVDA"),
    (("半導体", "TSMC", "チップ", "chip", "semiconductor", "AMD", "SOX"), "^SOX"),
    (("日経", "東京株", "日本株", "TOPIX", "Nikkei"), "^N225"),
    (("ドル円", "円安", "円高", "円相場", "為替", "yen"), "JPY=X"),
    (("金利", "国債", "FRB", "Fed", "利上げ", "利下げ", "Treasury", "yield"), "^TNX"),
    (("ナスダック", "Nasdaq", "AI", "人工知能", "ハイテク", "tech"), "^IXIC"),
    (("ダウ", "Dow"), "^DJI"),
]
DEFAULT_TICKER = "^GSPC"


def story_instrument(title: str) -> tuple[str, str]:
    for keys, tk in TOPIC_MAP:
        if any(k.lower() in title.lower() for k in keys):
            return tk, UNIVERSE[tk]
    return DEFAULT_TICKER, UNIVERSE[DEFAULT_TICKER]


def fetch_market_data() -> dict:
    """UNIVERSE の6ヶ月日足終値を取得。銘柄ごとに失敗耐性、全滅なら {}。"""
    try:
        import yfinance as yf
        raw = yf.download(tickers=list(UNIVERSE), period="6mo", interval="1d",
                          progress=False, auto_adjust=True, group_by="ticker")
    except Exception as e:
        print(f"[warn] yfinance 取得失敗: {e}")
        return {}

    out = {}
    for tk in UNIVERSE:
        try:
            ser = raw[tk]["Close"].dropna()
            if len(ser) < 10:
                continue
            out[tk] = {
                "dates": [d.to_pydatetime() if hasattr(d, "to_pydatetime") else d
                          for d in ser.index],
                "closes": [float(v) for v in ser.values],
            }
        except Exception:
            continue
    print(f"[ok] マーケットデータ: {len(out)}/{len(UNIVERSE)} 銘柄")
    return out


def daily_move(market: dict, tk: str) -> dict | None:
    s = market.get(tk)
    if not s or len(s["closes"]) < 2:
        return None
    last, prev = s["closes"][-1], s["closes"][-2]
    return {"last": last, "prev": prev,
            "pct": (last - prev) / prev * 100 if prev else 0.0}


def _fmt_value(tk: str, v: float) -> str:
    if tk == "JPY=X":
        return f"{v:,.2f}"
    if tk == "^TNX":
        return f"{v:.2f}%"
    return f"{v:,.0f}"


def draw_price_chart(fig, rect_px: tuple, W: int, H: int,
                     market: dict, ticker: str, label: str) -> bool:
    """rect_px=(x,y,w,h) ピクセル指定でチャートを描く。データ無しなら False。"""
    s = market.get(ticker)
    if not s or len(s["closes"]) < 10:
        return False
    x, y, w, h = rect_px
    ax = fig.add_axes([x / W, 1 - (y + h) / H, w / W, h / H])
    ax.set_facecolor(PANEL)

    dates, closes = s["dates"], s["closes"]
    color = UP if closes[-1] >= closes[0] else DOWN
    ax.plot(dates, closes, color=color, lw=2.4, solid_capstyle="round", zorder=3)
    ax.fill_between(dates, closes, min(closes), color=color, alpha=0.14, zorder=2)

    # 最新値マーカー＋注釈
    ax.scatter([dates[-1]], [closes[-1]], s=42, color=color, zorder=4)
    move = daily_move(market, ticker)
    pct6m = (closes[-1] - closes[0]) / closes[0] * 100
    ax.annotate(_fmt_value(ticker, closes[-1]),
                xy=(dates[-1], closes[-1]), xytext=(-8, 14),
                textcoords="offset points", ha="right",
                color=INK, fontsize=15, fontweight="bold", zorder=5)

    # 枠・目盛（最小限）
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.grid(axis="y", color=LINE, lw=0.8, alpha=0.6)
    ax.tick_params(colors=DIM, labelsize=11, length=0)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-m月"))
    ax.margins(x=0.02, y=0.18)

    # 左上: ラベル / 右上: 6ヶ月騰落
    ax.text(0.02, 0.94, f"{label}・直近6ヶ月", transform=ax.transAxes,
            color=INK, fontsize=14.5, fontweight="bold", va="top")
    ax.text(0.98, 0.94, f"6ヶ月 {pct6m:+.1f}%", transform=ax.transAxes,
            color=(UP if pct6m >= 0 else DOWN), fontsize=13.5,
            fontweight="bold", va="top", ha="right")
    return True
