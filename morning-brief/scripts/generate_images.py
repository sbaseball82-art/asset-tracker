# -*- coding: utf-8 -*-
"""毎朝5枚のニュースカード画像を生成する（チャート付き・まとめ無し）。

構成（1ニュース=1枚 × 5枚）:
  ヘッダー → 見出し（文末保証つき自動折返し） → 関連マーケットチャート
  → 統計タイル3枚 → ❶何が起きた/❷どう見るか → スタンス → フッター

文字切れを構造的に防ぐ2段構え:
  1. fit_text(): 全角/半角の実効幅で折り返し、行数超過時は「文の区切り」まで
     戻して省略（…）。文の途中でぶつ切りにならない。
  2. validate_card(): 描画後に全テキストのピクセル範囲を実測し、キャンバスから
     はみ出していないか検査。NGならフォントを縮小して再描画（最大3段階）。
"""
from __future__ import annotations
import re
import unicodedata

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

# 日本語フォント（japanize-matplotlibはPy3.12で動かないため後継のfontja）
try:
    import matplotlib_fontja  # noqa
except Exception:
    try:
        import japanize_matplotlib  # noqa
    except Exception:
        print("[warn] 日本語フォントパッケージ未検出。文字化けの可能性があります。")

# 太字ウェイトを持つ Noto Sans CJK があれば優先（IPAexはboldが無く疑似太字になるため）。
# 本番Actionsでは fonts-noto-cjk をインストールして使う。無ければfontjaのIPAexで動く。
from matplotlib import font_manager as _fm
_noto = [f.name for f in _fm.fontManager.ttflist if "Noto Sans CJK JP" in f.name]
if _noto:
    plt.rcParams["font.family"] = ["Noto Sans CJK JP"] + list(plt.rcParams["font.family"])
    print("[ok] フォント: Noto Sans CJK JP（太字対応）")

from explainer import build_explainer
from market_charts import (story_instrument, daily_move, draw_price_chart,
                           draw_topic_bars, _fmt_value)

BG = "#0e1726"; PANEL = "#131f33"; CARD = "#1a2740"
INK = "#eef2f8"; DIM = "#8fa0b8"; LINE = "#2a3650"
GOLD = "#d8b56a"; ACCENT = "#4fd1c5"; BLUE = "#6aa6e8"
UP = "#5fd0a0"; RED = "#e8807f"; STANCEBG = "#20233a"
W, H = 1080, 1350

STANCES = [
    "予想は当てず、指数で淡々と継続。",
    "個社は追わず、束（指数）で持って眺める。",
    "読めないものは読まない。積立は自動で継続。",
    "上げの日も下げの日も、やることは同じ。",
    "主役は当てない。全員（指数）を持てば主役は手の中。",
]

EVERGREEN = [
    ("時間を味方にする",
     "相場の底や天井を当て続けた人は歴史上ほぼいない",
     "上昇の大部分は少数の「最良の日」に集中する。市場に居続けた人だけがそれを取れる"),
    ("分散は無料の保険",
     "未来の主役セクターや国は、事前には誰にも分からない",
     "値動きの色が違う資産を混ぜるほど、資産全体の曲線はなだらかになる"),
    ("最高益は天井の罠",
     "シクリカル銘柄は好況の頂点で利益もPERの見た目も最高になる",
     "業績ピークのとき、株価はすでに次の下りを織り込み始めることがある"),
    ("暴落は予定に入れる",
     "10%程度の調整はおおむね毎年、大きな下落も数年に一度は起きてきた",
     "急落を「想定内」にできれば、狼狽売りという最大の失敗を避けられる"),
    ("複利は静かに効く",
     "リターンがリターンを生む構造は、時間が長いほど加速する",
     "1日の±1%より、10年続けたかどうかが資産の桁を決める"),
]


# ─────────────────────────────────────────────
# テキストフィットエンジン（文字切れの構造的防止・その1）
# ─────────────────────────────────────────────
PT2PX = 100 / 72          # dpi=100 のとき 1pt = 1.389px
CJK_ADV = 1.02            # 全角1文字の送り幅 ≒ fontsize×1.02（IPAex/Noto実測+余裕）


def units_for(width_px: float, fontsize_pt: float) -> float:
    """幅 width_px に fontsize_pt で入る全角換算文字数（安全側に切り下げ）。"""
    return width_px / (fontsize_pt * PT2PX * CJK_ADV)


def _char_w(ch: str) -> float:
    """全角=1.0 / 半角=0.55 の実効幅。"""
    return 1.0 if unicodedata.east_asian_width(ch) in "FWA" else 0.55


def wrap_jp(text: str, width_units: float) -> list[str]:
    """実効幅ベースの折り返し（禁則は簡易: 行頭の句読点を前行末に送る）。"""
    lines, cur, cur_w = [], "", 0.0
    for ch in text:
        w = _char_w(ch)
        if cur_w + w > width_units and cur:
            if ch in "、。」』）］！？":   # 行頭禁則
                cur += ch
                lines.append(cur); cur, cur_w = "", 0.0
                continue
            lines.append(cur); cur, cur_w = "", 0.0
        cur += ch; cur_w += w
    if cur:
        lines.append(cur)
    return lines or [""]


def fit_text(text: str, width_units: float, max_lines: int) -> list[str]:
    """max_lines に必ず収める。超過時は文の区切りまで戻して省略する。

    優先順: ①「。」で終わる位置まで戻す ②「、」まで戻して… ③単純カット+…
    どの経路でも「文字が中途半端に切れて終わる」ことはない。
    """
    text = re.sub(r"\s+", " ", text).strip()
    lines = wrap_jp(text, width_units)
    if len(lines) <= max_lines:
        return lines

    budget = ""
    for ln in lines[:max_lines]:
        budget += ln
    # ① 文末（。）で終われるならそこまで
    k = budget.rfind("。")
    if k >= len(budget) * 0.45:
        return wrap_jp(budget[:k + 1], width_units)[:max_lines]
    # ② 読点まで戻して省略
    k = budget.rfind("、")
    if k >= len(budget) * 0.55:
        return wrap_jp(budget[:k] + "…", width_units)[:max_lines]
    # ③ 末尾2文字を落として省略記号（…が幅超過しない余白を確保）
    return wrap_jp(budget[:-2] + "…", width_units)[:max_lines]


# ─────────────────────────────────────────────
# 描画部品
# ─────────────────────────────────────────────
def _canvas():
    fig = plt.figure(figsize=(10.8, 13.5), dpi=100)
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W); ax.set_ylim(0, H)
    ax.invert_yaxis(); ax.axis("off")
    return fig, ax


def _header(ax, rank: int, total: int, region: str, date_str: str, fs: float):
    ax.text(64, 84, "MORNING BRIEF", color=GOLD, fontsize=30 * fs,
            fontweight="bold", va="center")
    ax.text(64, 134, f"世界のマーケットニュース {rank}/{total}", color=INK,
            fontsize=19 * fs, va="center")
    # 地域バッジ
    badge_col = ACCENT if region == "海外" else BLUE
    ax.add_patch(FancyBboxPatch((W - 200, 60), 136, 44,
                 boxstyle="round,pad=0,rounding_size=12",
                 facecolor=badge_col, alpha=0.18, lw=1.2, edgecolor=badge_col))
    badge = f"{region}発" if region in ("海外", "国内") else region
    ax.text(W - 132, 82, badge, color=badge_col, fontsize=16 * fs,
            fontweight="bold", ha="center", va="center")
    ax.text(W - 64, 134, date_str, color=DIM, fontsize=14 * fs,
            ha="right", va="center")
    ax.plot([64, W - 64], [166, 166], color=LINE, lw=2)


def _footer(ax, note: str, fs: float):
    ax.plot([64, W - 64], [H - 78, H - 78], color=LINE, lw=1.5)
    ax.text(64, H - 48, note, color=DIM, fontsize=12.5 * fs, va="center")
    ax.text(W - 64, H - 48, "ASSET LOG", color=GOLD, fontsize=13 * fs,
            fontweight="bold", ha="right", va="center")


def _stat_tiles(ax, cy: int, tiles: list, fs: float) -> int:
    """tiles: [(label, value, sub, color)] 最大3枚を横並び。"""
    n = len(tiles)
    if n == 0:
        return cy
    gap = 16
    tw = (W - 128 - gap * (n - 1)) / n
    th = 118
    for i, (label, value, sub, col) in enumerate(tiles):
        x = 64 + i * (tw + gap)
        ax.add_patch(FancyBboxPatch((x, cy), tw, th,
                     boxstyle="round,pad=0,rounding_size=14",
                     facecolor=CARD, lw=0))
        ax.text(x + tw / 2, cy + 26, label, color=DIM, fontsize=13.5 * fs,
                ha="center", va="center")
        ax.text(x + tw / 2, cy + 62, value, color=col, fontsize=24 * fs,
                fontweight="bold", ha="center", va="center")
        ax.text(x + tw / 2, cy + 94, sub, color=DIM, fontsize=12.5 * fs,
                ha="center", va="center")
    return cy + th + 18


def _block(ax, cy: int, label: str, lines: list[str], fs: float,
           label_color=GOLD, bg=CARD, bar=False) -> int:
    pad_top, line_h, pad_bot = 44, 33, 18
    h = pad_top + len(lines) * line_h + pad_bot
    ax.add_patch(FancyBboxPatch((56, cy), W - 112, h,
                 boxstyle="round,pad=0,rounding_size=16", facecolor=bg, lw=0))
    if bar:
        ax.add_patch(FancyBboxPatch((56, cy), 10, h,
                     boxstyle="round,pad=0,rounding_size=3", facecolor=GOLD, lw=0))
    ax.text(84, cy + 26, label, color=label_color, fontsize=16 * fs,
            fontweight="bold", va="center")
    for i, ln in enumerate(lines):
        t = ax.text(84, cy + pad_top + 12 + i * line_h, ln, color=INK,
                    fontsize=17.5 * fs, va="center")
        t.set_gid(f"maxx:{W - 56 - 16}")   # パネル右端-余白 を超えたら検証NG
    return cy + h + 14


# 本文ブロックの実効幅（x=84開始、パネル右端56+16px余白）
BLOCK_TEXT_PX = (W - 56 - 16) - 84


# ─────────────────────────────────────────────
# 検証（文字切れの構造的防止・その2）
# ─────────────────────────────────────────────
def validate_card(fig) -> list[str]:
    """全テキストのピクセル範囲を実測し、キャンバス外・パネル外へのはみ出しを列挙。

    gid="maxx:<px>" が付いたテキストは、キャンバスだけでなく指定x(パネル右端)も
    超えてはならない。描画結果そのものを検査するため、折返し計算のバグや
    フォント差があっても文字切れ・はみ出しを出荷前に必ず検出できる。
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    fw, fh = fig.canvas.get_width_height()
    bad = []
    for aax in fig.axes:
        for t in aax.texts:
            if not t.get_text().strip():
                continue
            bb = t.get_window_extent(renderer)
            limit_x = fw + 2
            gid = t.get_gid() or ""
            if gid.startswith("maxx:"):
                limit_x = float(gid.split(":")[1]) + 2
            if bb.x0 < -2 or bb.y0 < -2 or bb.x1 > limit_x or bb.y1 > fh + 2:
                bad.append(f"はみ出し: '{t.get_text()[:20]}…' x1={bb.x1:.0f} 上限={limit_x:.0f}")
    return bad


def _render_validated(build_fn, out: str):
    """fontscale を 1.0→0.92→0.84 と下げながら、検証に通るまで再描画して保存。"""
    for fs in (1.0, 0.92, 0.84):
        fig = build_fn(fs)
        problems = validate_card(fig)
        if not problems:
            fig.savefig(out, facecolor=BG)
            plt.close(fig)
            return
        print(f"[warn] fontscale={fs} で {len(problems)} 件のはみ出し → 縮小して再試行")
        for p in problems[:3]:
            print("   ", p)
        plt.close(fig)
    # 最終手段: 最小スケールで必ず保存（画像ゼロ枚は絶対に避ける）
    fig = build_fn(0.8)
    fig.savefig(out, facecolor=BG)
    plt.close(fig)
    print(f"[warn] {out}: 検証NGのまま最小スケールで保存（要目視確認）")


# ─────────────────────────────────────────────
# カード本体
# ─────────────────────────────────────────────
def news_card(rank: int, total: int, story: dict, date_str: str, out: str,
              stance: str, market: dict, all_stories: list):
    """1ニュース=1枚。見出し＋関連チャート＋統計タイル＋解説2ブロック。"""
    ex = build_explainer(story["title"])
    ticker, tk_label = story_instrument(story["title"])
    region = story.get("region", "国内")

    def build(fs: float):
        fig, ax = _canvas()
        _header(ax, rank, total, region, date_str, fs)

        # 見出し（最大3行・文末保証・実効ピクセル幅で折返し）
        cy = 206
        tfs = 29 * fs
        title_lines = fit_text(story["title"], units_for(W - 128, tfs), 3)
        for i, ln in enumerate(title_lines):
            t = ax.text(W / 2, cy + i * (tfs * 1.62), ln, color=INK, fontsize=tfs,
                        fontweight="bold", ha="center", va="center")
            t.set_gid(f"maxx:{W - 40}")
        cy += len(title_lines) * (tfs * 1.62) + 12
        ax.text(W / 2, cy, f"{story['n_sources']}メディアが同時報道",
                color=ACCENT, fontsize=15 * fs, ha="center", va="center",
                fontweight="bold")
        cy += 42

        # 関連チャート（データ無しなら話題度バーにフォールバック）
        chart_rect = (72, cy, W - 144, 360)
        drew = draw_price_chart(fig, chart_rect, W, H, market, ticker, tk_label)
        if not drew:
            draw_topic_bars(fig, chart_rect, W, H, all_stories, rank - 1)
        cy += 360 + 24

        # 統計タイル（関連銘柄・S&P500・ドル円の前日比。無い分は話題データで補完）
        tiles = []
        for tk2, lbl2 in ((ticker, tk_label), ("^GSPC", "S&P500"), ("JPY=X", "ドル円")):
            if any(t[0] == lbl2 for t in tiles):
                continue
            mv = daily_move(market, tk2)
            if mv:
                col = UP if mv["pct"] >= 0 else RED
                tiles.append((lbl2, f"{mv['pct']:+.2f}%",
                              _fmt_value(tk2, mv["last"]), col))
        while len(tiles) < 3:
            fillers = [("同時報道", f"{story['n_sources']}媒体", "話題度の目安", ACCENT),
                       ("話題順位", f"#{rank}", "本日のニュース", GOLD),
                       ("配信地域", region, "ニュース発", BLUE)]
            tiles.append(fillers[len(tiles) % 3])
        cy = _stat_tiles(ax, cy, tiles[:3], fs)

        # 解説（各2行・文末保証つき・実効ピクセル幅で折返し）
        wu = units_for(BLOCK_TEXT_PX, 17.5 * fs)
        cy = _block(ax, cy, "❶ 何が起きた", fit_text(_what_happened(story, ex), wu, 2), fs)
        cy = _block(ax, cy, "❷ どう見るか（リスクまで）",
                    fit_text(ex["影響"] + "。" + ex["注意"] + "。", wu, 2), fs,
                    label_color=BLUE)
        _block(ax, cy, "自分のスタンス", [stance], fs, bg=STANCEBG, bar=True)
        _footer(ax, "報道ベースの要約・チャートは終値ベース。投資助言ではありません。", fs)
        return fig

    _render_validated(build, out)


def _what_happened(story: dict, ex: dict) -> str:
    nums = ex.get("数字") or []
    if nums:
        return f"見出しのポイントは「{'・'.join(nums)}」。{ex['背景']}。"
    return f"{ex['背景']}。"


def evergreen_card(idx: int, rank: int, total: int, date_str: str, out: str,
                   stance: str, market: dict):
    """ニュース全滅時のフォールバック（投資の原則＋S&P500チャート）。"""
    title, p1, p2 = EVERGREEN[idx % len(EVERGREEN)]

    def build(fs: float):
        fig, ax = _canvas()
        _header(ax, rank, total, "原則", date_str, fs)
        cy = 226
        ax.text(W / 2, cy, f"“{title}”", color=GOLD, fontsize=38 * fs,
                fontweight="bold", ha="center", va="center")
        cy += 76
        chart_rect = (72, cy, W - 144, 360)
        if not draw_price_chart(fig, chart_rect, W, H, market, "^GSPC", "S&P500"):
            # データ皆無の日は原則の要点を「表」として描く
            ax.add_patch(FancyBboxPatch((72, cy), W - 144, 360,
                         boxstyle="round,pad=0,rounding_size=16",
                         facecolor=PANEL, lw=0))
            rows = [(t[0], t[1]) for t in EVERGREEN]
            for i, (nm, ds) in enumerate(rows):
                yy = cy + 44 + i * 62
                ax.text(104, yy, f"{i+1}. {nm}", color=INK, fontsize=17 * fs,
                        fontweight="bold", va="center")
                ax.text(104, yy + 26, fit_text(ds, 50, 1)[0], color=DIM,
                        fontsize=13 * fs, va="center")
        cy += 360 + 26
        wu = units_for(BLOCK_TEXT_PX, 17.5 * fs)
        cy = _block(ax, cy, "❶ どういうことか", fit_text(p1 + "。", wu, 2), fs)
        cy = _block(ax, cy, "❷ なぜ大事か", fit_text(p2 + "。", wu, 2), fs,
                    label_color=BLUE)
        _block(ax, cy, "自分のスタンス", [stance], fs, bg=STANCEBG, bar=True)
        _footer(ax, "個人の記録・情報共有であり投資助言ではありません。", fs)
        return fig

    _render_validated(build, out)
