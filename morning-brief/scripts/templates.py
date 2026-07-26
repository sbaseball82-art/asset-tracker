# -*- coding: utf-8 -*-
"""6種のレイアウトテンプレート（日替わりローテーション用）。

すべて ASSET LOG ブランド（ネイビー基調・ゴールドのワードマーク・1080×1350）を
維持しつつ情報の見せ方を変える。全テンプレートは同一インターフェース:

    build(story, series, date_str, lim, theme) -> matplotlib.figure.Figure

story は共通の CardSpec（story_builder.build_story の辞書）で、
テンプレを差し替えても内容が壊れない。深掘り体裁（❶事実❷仕組み❸波及❹反証の
ゲート通過済みコンテンツ・脚注免責）はどのテンプレでも維持する。

| ID | 名称        | 構成                                   | 向いている話題 |
|----|------------|----------------------------------------|---------------|
| T1 | classic    | 大型数字カード2×2＋❶❷❸❹              | 汎用（チャート無しでも成立） |
| T2 | stat_deep  | チャート＋数字カード×3＋❶❷❸❹          | 指標・金利・急変動 |
| T3 | hero_number| 巨大な1つの数字＋補足タイル＋❷❸❹      | 記録更新・大幅変動 |
| T4 | contrast   | 左右2分割（主役 vs 比較対象）＋❷❸❹    | 明暗が割れた日 |
| T5 | timeline   | 6ヶ月の経緯を時系列で縦に＋❷❸❹        | 経緯のあるニュース |
| T6 | qa         | 「なぜ？」→答え(❷)→数字→ただし(❹)     | 疑問形が刺さる話題 |
"""
from __future__ import annotations
import datetime as dt

from matplotlib.patches import FancyBboxPatch

from render import (BG, CARDBG, DIM, GRN, INK, LINE, PANEL, RED, W, H,
                    _block, _canvas, _chart, _conclusion, _footer, _header,
                    _headline, _tiles, _units, _wrap, story_tiles)

# 話題タグ×テンプレートの相性表（候補を絞る。学習が最終選択する）
AFFINITY = {
    "semiconductor": ["T2", "T3", "T4", "T6"],
    "rates":         ["T2", "T3", "T5", "T6"],
    "fx":            ["T2", "T3", "T5"],
    "ai":            ["T2", "T3", "T4", "T6"],
    "earnings":      ["T2", "T3", "T6"],
    "macro":         ["T1", "T2", "T4", "T5"],
    "other":         ["T1", "T2", "T5"],
}
ALL_TEMPLATES = ["T1", "T2", "T3", "T4", "T5", "T6"]


def _blocks_1234(ax, cy, story, lim, theme, skip=()):
    if "fact" not in skip:
        cy = _block(ax, cy, "❶ 事実（What）", story["fact"], lim["fact_lines"],
                    label_color=theme.main)
    if "why" not in skip:
        cy = _block(ax, cy, "❷ 仕組み（Why）", story["why"], lim["why_lines"],
                    label_color=theme.sub)
    if "sowhat" not in skip:
        cy = _block(ax, cy, "❸ 波及（So what）", story["sowhat"],
                    lim["sowhat_lines"], label_color=theme.main)
    if "counter" not in skip:
        cy = _block(ax, cy, "❹ 反証（外れる条件）", story["counter"],
                    lim["counter_lines"], label_color=RED)
    return cy


# ── T1 classic：大型数字カード＋4ブロック（チャート無しでも成立）──
def build_t1(story, series, date_str, lim, theme):
    fig, ax = _canvas()
    _header(ax, story["theme"], date_str, theme.main)
    cy = _headline(ax, story, 196)
    cy = _conclusion(ax, story, cy, theme.sub)
    cy = _tiles(ax, cy + 4, story_tiles(story)[:4], big=True)
    _blocks_1234(ax, cy, story, lim, theme)
    _footer(ax)
    return fig


# ── T2 stat_deep：チャート＋数字カード×3＋4ブロック（基準形）──
def build_t2(story, series, date_str, lim, theme):
    fig, ax = _canvas()
    _header(ax, story["theme"], date_str, theme.main)
    cy = _headline(ax, story, 196)
    n_hl = 1 if cy < 280 else 2
    cy = _conclusion(ax, story, cy, theme.sub)
    tiles = story_tiles(story)
    chart_h = 300 if n_hl == 1 else 258
    if _chart(fig, (72, cy, W - 144, chart_h), series or {}, story):
        cy += chart_h + 20
        cy = _tiles(ax, cy, tiles[:3])
    else:
        cy = _tiles(ax, cy, tiles[:4], big=True)
    _blocks_1234(ax, cy, story, lim, theme)
    _footer(ax)
    return fig


# ── T3 hero_number：巨大な1つの数字を中央に、周囲に補足──
def build_t3(story, series, date_str, lim, theme):
    fig, ax = _canvas()
    _header(ax, story["theme"], date_str, theme.main)
    cy = _headline(ax, story, 196)
    two_line_hl = cy > 280
    cy = _conclusion(ax, story, cy, theme.sub)

    hero = story.get("event_label") or f"{story['event_pct']:+.1f}%"
    col = RED if story["event_pct"] < 0 else GRN
    hh = 210 if two_line_hl else 250
    ax.add_patch(FancyBboxPatch((64, cy), W - 128, hh,
                 boxstyle="round,pad=0,rounding_size=18", facecolor=PANEL, lw=0))
    ax.text(W / 2, cy + 40, f"{story['name']}・前日比", color=DIM,
            fontsize=17, ha="center", va="center")
    t = ax.text(W / 2, cy + hh / 2 + 12, hero, color=col,
                fontsize=76 if two_line_hl else 88,
                fontweight="bold", ha="center", va="center")
    t.set_gid(f"maxx:{W - 70}")
    sub = next((n for n in story["numbers"] if "z=" in str(n.get("sub", ""))), None)
    ax.text(W / 2, cy + hh - 32, (sub["sub"] if sub else story["event_date"]),
            color=DIM, fontsize=15, ha="center", va="center")
    cy += hh + 18
    cy = _tiles(ax, cy, story_tiles(story)[1:4])
    _blocks_1234(ax, cy, story, lim, theme,
                 skip=("fact",) if two_line_hl else ())
    _footer(ax)
    return fig


# ── T4 contrast：左右2分割（主役 vs 比較対象）──
def _contrast_partner(story):
    main_lbl = f"{story['name']} 日次"
    for n in story["numbers"]:
        if n["label"].endswith("日次") and n["label"] != main_lbl:
            return n
    return story["numbers"][-1]


def build_t4(story, series, date_str, lim, theme):
    fig, ax = _canvas()
    _header(ax, story["theme"], date_str, theme.main)
    cy = _headline(ax, story, 196)
    cy = _conclusion(ax, story, cy, theme.sub)

    partner = _contrast_partner(story)
    main_val = story.get("event_label") or f"{story['event_pct']:+.1f}%"
    pw = (W - 128 - 20) / 2
    ph = 240
    panels = [
        (64, story["name"], main_val,
         RED if story["event_pct"] < 0 else GRN, "きょうの主役"),
        (64 + pw + 20, partner["label"].replace(" 日次", ""), str(partner["value"]),
         RED if str(partner["value"]).startswith("-") else GRN, "比較対象（同日）"),
    ]
    for x, name, val, col, cap in panels:
        ax.add_patch(FancyBboxPatch((x, cy), pw, ph,
                     boxstyle="round,pad=0,rounding_size=16",
                     facecolor=PANEL, lw=0))
        ax.text(x + pw / 2, cy + 36, cap, color=DIM, fontsize=13.5,
                ha="center", va="center")
        t = ax.text(x + pw / 2, cy + 80, name, color=INK, fontsize=20,
                    fontweight="bold", ha="center", va="center")
        t.set_gid(f"maxx:{x + pw}")
        t = ax.text(x + pw / 2, cy + 155, val, color=col, fontsize=46,
                    fontweight="bold", ha="center", va="center")
        t.set_gid(f"maxx:{x + pw}")
        marker = "▼" if val.startswith("-") else "▲"
        ax.text(x + pw / 2, cy + 208, marker, color=col, fontsize=18,
                ha="center", va="center")
    cy += ph + 18
    cy = _block(ax, cy, "❶ 事実（What）", story["fact"], lim["fact_lines"],
                label_color=theme.main)
    _blocks_1234(ax, cy, story, lim, theme, skip=("fact",))
    _footer(ax)
    return fig


# ── T5 timeline：6ヶ月の経緯を時系列で──
def _timeline_rows(story, series):
    rows = []
    if series and len(series.get("closes", [])) >= 30:
        dates = [dt.date.fromisoformat(d) for d in series["dates"]][-126:]
        closes = series["closes"][-126:]
        hi_i = max(range(len(closes)), key=lambda i: closes[i])
        lo_i = min(range(len(closes)), key=lambda i: closes[i])
        pct = lambda v: (v - closes[0]) / closes[0] * 100  # noqa: E731
        rows.append((dates[0].strftime("%-m/%-d"), "6ヶ月前の水準", "起点", INK))
        for i, cap in sorted([(hi_i, "期間高値"), (lo_i, "期間安値")]):
            rows.append((dates[i].strftime("%-m/%-d"), cap,
                         f"{pct(closes[i]):+.1f}%",
                         GRN if closes[i] >= closes[0] else RED))
        ev = story.get("event_label") or f"{story['event_pct']:+.1f}%"
        rows.append((dates[-1].strftime("%-m/%-d"),
                     f"きょう：{story['theme']}シグナル", ev,
                     RED if story["event_pct"] < 0 else GRN))
    else:
        for n in story["numbers"][:4]:
            col = (GRN if str(n["value"]).startswith("+") else
                   RED if str(n["value"]).startswith("-") else INK)
            rows.append((n.get("asof", "")[-5:], n["label"], str(n["value"]), col))
    return rows


def build_t5(story, series, date_str, lim, theme):
    fig, ax = _canvas()
    _header(ax, story["theme"], date_str, theme.main)
    cy = _headline(ax, story, 196)
    cy = _conclusion(ax, story, cy, theme.sub)

    rows = _timeline_rows(story, series)
    panel_h = 64 + len(rows) * 70
    ax.add_patch(FancyBboxPatch((64, cy), W - 128, panel_h,
                 boxstyle="round,pad=0,rounding_size=16", facecolor=PANEL, lw=0))
    ax.text(96, cy + 34, f"{story['name']}・直近6ヶ月のあゆみ", color=INK,
            fontsize=15.5, fontweight="bold", va="center")
    lx = 150
    y0 = cy + 76
    ax.plot([lx, lx], [y0, y0 + (len(rows) - 1) * 70], color=LINE, lw=2.5)
    for i, (d, label, val, col) in enumerate(rows):
        yy = y0 + i * 70
        ax.scatter([lx], [yy], s=52, color=col, zorder=4)
        ax.text(lx - 26, yy, d, color=DIM, fontsize=13.5, ha="right", va="center")
        t = ax.text(lx + 30, yy, label, color=INK, fontsize=16.5, va="center")
        t.set_gid(f"maxx:{W - 300}")
        ax.text(W - 100, yy, val, color=col, fontsize=19, fontweight="bold",
                ha="right", va="center")
    cy += panel_h + 18
    _blocks_1234(ax, cy, story, lim, theme)
    _footer(ax)
    return fig


# ── T6 qa：「なぜ？」→答え→ただし（反証）──
def build_t6(story, series, date_str, lim, theme):
    fig, ax = _canvas()
    _header(ax, story["theme"], date_str, theme.main)
    a = abs(story["event_pct"])
    mv = ("急落" if a >= 8 else "大幅安" if a >= 4 else "下落") if story["event_pct"] < 0 \
        else ("急騰" if a >= 8 else "大幅高" if a >= 4 else "上昇")
    q = f"なぜ{story['name']}は{mv}したのか？"
    cy = _headline(ax, story, 196, text=q)
    cy = _conclusion(ax, story, cy, theme.sub)
    cy = _block(ax, cy + 4, "Ａ. 答え（仕組み）", story["why"], lim["why_lines"],
                label_color=theme.sub)
    cy = _tiles(ax, cy + 4, story_tiles(story)[:3])
    if _chart(fig, (72, cy, W - 144, 170), series or {}, story):
        cy += 170 + 20
    cy = _block(ax, cy, "❶ 事実（What）", story["fact"], lim["fact_lines"],
                label_color=theme.main)
    cy = _block(ax, cy, "❸ 波及（So what）", story["sowhat"], lim["sowhat_lines"],
                label_color=theme.main)
    _block(ax, cy, "ただし（外れる条件）", story["counter"], lim["counter_lines"],
           label_color=RED)
    _footer(ax)
    return fig


BUILDERS = {
    "T1": build_t1, "T2": build_t2, "T3": build_t3,
    "T4": build_t4, "T5": build_t5, "T6": build_t6,
}
