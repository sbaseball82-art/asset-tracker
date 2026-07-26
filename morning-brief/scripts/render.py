# -*- coding: utf-8 -*-
"""描画基盤：共通部品（キャンバス・ヘッダ・チャート・数字カード・ブロック）と
ピクセル実測検証、テンプレートへのディスパッチ。

レイアウト本体は templates.py（T1〜T6）にあり、どのテンプレートにも
同じ story（CardSpec相当の辞書）を流し込める。旧版のスタンス欄・
同時報道数の表示は廃止したまま。

文字あふれは描画後にピクセル実測で検証し、NGなら story_builder.shorten()
で生成側の文章を短縮して再描画する（フォント縮小や枠外はみ出しに逃げない）。
"""
from __future__ import annotations
import datetime as dt
import re as _re
import unicodedata

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

try:
    import matplotlib_fontja  # noqa: F401  Py3.12対応の日本語フォント
except Exception:
    try:
        import japanize_matplotlib  # noqa: F401
    except Exception:
        print("[warn] 日本語フォントパッケージ未検出。文字化けの可能性があります。")

from matplotlib import font_manager as _fm
_noto = [f.name for f in _fm.fontManager.ttflist if "Noto Sans CJK JP" in f.name]
if _noto:
    plt.rcParams["font.family"] = ["Noto Sans CJK JP"] + list(plt.rcParams["font.family"])

# パレット（ブランド固定色）
BG = "#0e1726"; GOLD = "#d8b56a"; BLUE = "#6aa6e8"; INK = "#eef2f8"
DIM = "#8fa0b8"; GRN = "#5fd0a0"; RED = "#e8807f"; LINE = "#2a3650"
CARDBG = "#1a2740"; PANEL = "#131f33"
W, H = 1080, 1350

PT2PX = 100 / 72
CJK_ADV = 1.02

# 本文の折返し幅（全角換算ユニット）
BODY_UNITS = (W - 112 - 84) / (16.5 * PT2PX * CJK_ADV)


def _units(s: str) -> float:
    return sum(1.0 if unicodedata.east_asian_width(c) in "FWA" else 0.55 for c in s)


# 数値・英字の連なりは1トークンとして扱い、途中で改行しない
_TOKEN_RE = _re.compile(r"[0-9A-Za-z.%+\-=&σ]+|.")


def _wrap(text: str, width_units: float) -> list[str]:
    lines, cur, w = [], "", 0.0
    for tok in _TOKEN_RE.findall(text):
        tw = _units(tok)
        if w + tw > width_units and cur:
            if tok in tuple("、。」』）！？"):   # 行頭禁則
                cur += tok
                lines.append(cur); cur, w = "", 0.0
                continue
            lines.append(cur); cur, w = "", 0.0
        cur += tok; w += tw
    if cur:
        lines.append(cur)
    return lines or [""]


def _canvas():
    fig = plt.figure(figsize=(10.8, 13.5), dpi=100)
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W); ax.set_ylim(0, H)
    ax.invert_yaxis(); ax.axis("off")
    return fig, ax


def _header(ax, badge: str, date_str: str, accent: str = GOLD):
    ax.text(64, 78, "MORNING BRIEF", color=GOLD, fontsize=30,
            fontweight="bold", va="center")
    ax.text(64, 124, "きょう深掘りする1枚", color=DIM, fontsize=15, va="center")
    bw = max(120, int(_units(badge) * 22 + 56))
    ax.add_patch(FancyBboxPatch((W - 64 - bw, 56), bw, 42,
                 boxstyle="round,pad=0,rounding_size=12",
                 facecolor=accent, alpha=0.16, lw=1.2, edgecolor=accent))
    ax.text(W - 64 - bw / 2, 77, badge, color=accent, fontsize=16,
            fontweight="bold", ha="center", va="center")
    ax.text(W - 64, 124, date_str, color=DIM, fontsize=14, ha="right", va="center")
    ax.plot([64, W - 64], [150, 150], color=LINE, lw=2)


def _footer(ax):
    ax.plot([64, W - 64], [H - 76, H - 76], color=LINE, lw=1.5)
    ax.text(64, H - 46, "報道ベースの要約・数値は概算。投資助言ではありません。",
            color=DIM, fontsize=12.5, va="center")
    ax.text(W - 64, H - 46, "ASSET LOG", color=GOLD, fontsize=13,
            fontweight="bold", ha="right", va="center")


def _headline(ax, story: dict, cy: float, text: str | None = None) -> float:
    lines = _wrap(text or story["headline"], 14)[:2]
    hfs = 38 if len(lines) == 1 else 33
    for i, ln in enumerate(lines):
        t = ax.text(W / 2, cy + i * (hfs * 1.5), ln, color=INK, fontsize=hfs,
                    fontweight="bold", ha="center", va="center")
        t.set_gid(f"maxx:{W - 40}")
    return cy + len(lines) * (hfs * 1.5) + 6


def _conclusion(ax, story: dict, cy: float, color: str) -> float:
    t = ax.text(W / 2, cy, story["conclusion"], color=color, fontsize=19,
                fontweight="bold", ha="center", va="center")
    t.set_gid(f"maxx:{W - 40}")
    return cy + 40


def _chart(fig, rect, series: dict, story: dict) -> bool:
    """主役チャート：当事者の直近6ヶ月＋イベント日▲▼と変動率注記。"""
    if not series or len(series.get("closes", [])) < 30:
        return False
    x, y, w, h = rect
    ax = fig.add_axes([x / W, 1 - (y + h) / H, w / W, h / H])
    ax.set_facecolor(PANEL)
    dates = [dt.date.fromisoformat(d) for d in series["dates"]][-126:]
    closes = series["closes"][-126:]
    color = GRN if closes[-1] >= closes[0] else RED
    ax.plot(dates, closes, color=color, lw=2.4, solid_capstyle="round", zorder=3)
    ax.fill_between(dates, closes, min(closes), color=color, alpha=0.13, zorder=2)

    ev_col = RED if story["event_pct"] < 0 else GRN
    marker = "▼" if story["event_pct"] < 0 else "▲"
    ax.annotate(f"{marker} {story.get('event_label') or format(story['event_pct'], '+.1f') + '%'}",
                xy=(dates[-1], closes[-1]),
                xytext=(-10, 18 if story["event_pct"] < 0 else -26),
                textcoords="offset points", ha="right", color=ev_col,
                fontsize=16, fontweight="bold", zorder=5)
    ax.scatter([dates[-1]], [closes[-1]], s=46, color=ev_col, zorder=4)

    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.grid(axis="y", color=LINE, lw=0.8, alpha=0.6)
    ax.tick_params(colors=DIM, labelsize=11, length=0)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-m月"))
    ax.margins(x=0.02, y=0.2)
    pct6m = (closes[-1] - closes[0]) / closes[0] * 100
    ax.text(0.02, 0.95, f"{story['name']}・直近6ヶ月", transform=ax.transAxes,
            color=INK, fontsize=14.5, fontweight="bold", va="top")
    ax.text(0.98, 0.95, f"6ヶ月 {pct6m:+.1f}%", transform=ax.transAxes,
            color=(GRN if pct6m >= 0 else RED), fontsize=13.5,
            fontweight="bold", va="top", ha="right")
    return True


def story_tiles(story: dict) -> list[dict]:
    return [{"label": n["label"], "value": n["value"], "sub": n.get("sub", ""),
             "color": (GRN if str(n["value"]).startswith("+") else
                       RED if str(n["value"]).startswith("-") else INK)}
            for n in story["numbers"]]


def _tiles(ax, cy: float, tiles: list[dict], big: bool = False) -> float:
    """数字カード。big=True は2倍サイズ(2×2)。ラベルは記事ごとに可変。"""
    if big:
        rows = [tiles[:2], tiles[2:4]]
        th, gap = 150, 16
        for row in [r for r in rows if r]:
            tw = (W - 128 - gap * (len(row) - 1)) / len(row)
            for i, t in enumerate(row):
                x = 64 + i * (tw + gap)
                ax.add_patch(FancyBboxPatch((x, cy), tw, th,
                             boxstyle="round,pad=0,rounding_size=14",
                             facecolor=CARDBG, lw=0))
                ax.text(x + tw / 2, cy + 34, t["label"], color=DIM, fontsize=15,
                        ha="center", va="center")
                ax.text(x + tw / 2, cy + 80, t["value"], color=t.get("color", INK),
                        fontsize=32, fontweight="bold", ha="center", va="center")
                ax.text(x + tw / 2, cy + 122, t.get("sub", ""), color=DIM,
                        fontsize=13, ha="center", va="center")
            cy += th + gap
        return cy + 4
    gap = 16
    tw = (W - 128 - gap * 2) / 3
    th = 112
    for i, t in enumerate(tiles[:3]):
        x = 64 + i * (tw + gap)
        ax.add_patch(FancyBboxPatch((x, cy), tw, th,
                     boxstyle="round,pad=0,rounding_size=14",
                     facecolor=CARDBG, lw=0))
        ax.text(x + tw / 2, cy + 25, t["label"], color=DIM, fontsize=13.5,
                ha="center", va="center")
        ax.text(x + tw / 2, cy + 59, t["value"], color=t.get("color", INK),
                fontsize=23, fontweight="bold", ha="center", va="center")
        ax.text(x + tw / 2, cy + 91, t.get("sub", ""), color=DIM, fontsize=12,
                ha="center", va="center")
    return cy + th + 16


def _block(ax, cy: float, label: str, text: str, max_lines: int,
           label_color=GOLD, line_units: float | None = None) -> float:
    lines = _wrap(text, line_units or BODY_UNITS)[:max_lines]
    pad_top, line_h, pad_bot = 40, 30, 12
    h = pad_top + len(lines) * line_h + pad_bot
    ax.add_patch(FancyBboxPatch((56, cy), W - 112, h,
                 boxstyle="round,pad=0,rounding_size=16", facecolor=CARDBG, lw=0))
    ax.text(84, cy + 24, label, color=label_color, fontsize=15.5,
            fontweight="bold", va="center")
    for i, ln in enumerate(lines):
        t = ax.text(84, cy + pad_top + 12 + i * line_h, ln, color=INK,
                    fontsize=16.5, va="center")
        t.set_gid(f"maxx:{W - 72},ybot:{H - 90}")
    return cy + h + 12


def _validate(fig) -> list[str]:
    """全テキストのピクセル範囲を実測し、はみ出しを列挙（空なら合格）。"""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    fw, fh = fig.canvas.get_width_height()
    bad = []
    for aax in fig.axes:
        for t in aax.texts:
            if not t.get_text().strip():
                continue
            bb = t.get_window_extent(renderer)
            limit_x, limit_ybot = fw + 2, -2
            for part in (t.get_gid() or "").split(","):
                if part.startswith("maxx:"):
                    limit_x = float(part.split(":")[1]) + 2
                elif part.startswith("ybot:"):
                    limit_ybot = fh - float(part.split(":")[1]) - 2
            if (bb.x0 < -2 or bb.y0 < limit_ybot or bb.x1 > limit_x
                    or bb.y1 > fh + 2):
                bad.append(f"'{t.get_text()[:18]}…' x1={bb.x1:.0f}/{limit_x:.0f}")
    return bad


def render_card(story: dict, series: dict | None, date_str: str,
                out_png: str, cfg: dict, template_id: str = "T2",
                theme=None) -> bool:
    """検証つき描画。はみ出しは生成側短縮で解消。3回で直らなければ False（スキップ）。"""
    from story_builder import shorten
    from templates import BUILDERS
    from themes import THEMES
    theme = theme or THEMES["default"]
    build = BUILDERS.get(template_id, BUILDERS["T2"])
    for level in (0, 1, 2, 3):
        if level:
            story = shorten(story, level, cfg)
        fig = build(story, series, date_str, cfg["limits"], theme)
        problems = _validate(fig)
        if not problems:
            fig.savefig(out_png, facecolor=BG)
            plt.close(fig)
            return True
        plt.close(fig)
        print(f"[warn] {template_id} はみ出し{len(problems)}件 → 生成側短縮 level={level + 1} で再描画")
    print(f"[error] {out_png}: 短縮しても検証NGのため、この記事はスキップ")
    return False
