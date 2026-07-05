# -*- coding: utf-8 -*-
"""毎朝5枚のカード画像を生成する（イラストなし・深掘り解説型）。

構成（1ニュース=1枚で深く解説）：
  1〜4枚目: 話題ニュース TOP4。各カードは
            見出し → ❶何が起きた(数字) → ❷背景 → ❸市場への影響
            → ❹リスク・注意 → 用語メモ → 自分のスタンス
  5枚目   : 今朝のまとめ（TOP4一覧＋スタンス）
ニュース不足・取得失敗時は「投資の原則」深掘りカードに自動フォールバック。
"""
from __future__ import annotations
import textwrap
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
# 日本語フォント登録。japanize-matplotlibはPython 3.12以降で動かない
# （distutils依存）ため、後継フォークのmatplotlib-fontjaを使う。
try:
    import matplotlib_fontja  # noqa
except Exception:
    try:
        import japanize_matplotlib  # noqa
    except Exception:
        print("[warn] 日本語フォントパッケージ未検出。文字化けの可能性があります。")
from explainer import build_explainer

BG="#0e1726"; GOLD="#d8b56a"; BLUE="#6aa6e8"; INK="#eef2f8"; DIM="#8fa0b8"
GRN="#5fd0a0"; RED="#e8807f"; LINE="#2a3650"; CARDBG="#1a2740"; STANCEBG="#20233a"
W,H = 1080,1350

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
     "上昇の大部分は少数の「最良の日」に集中する。市場に居続けた人だけがそれを取れる",
     "タイミング売買は「最良の日」を逃すリスクと隣り合わせ。降りると拾えない",
     "機会損失＝投資しなかったことで得られなかった利益のこと"),
    ("分散は無料の保険",
     "未来の主役セクターや国は、事前には誰にも分からない",
     "値動きの色が違う資産を混ぜるほど、資産全体の曲線はなだらかになる",
     "集中投資は上振れも下振れも大きい。生活と心を守るのが分散の役割",
     "相関＝資産同士の連動度。低いほど分散の効果が高い"),
    ("最高益は天井の罠",
     "シクリカル銘柄は好況の頂点で利益もPERの見た目も最高になる",
     "業績ピークのとき、株価はすでに次の下りを織り込み始めることがある",
     "「絶好調だから買う」が高値掴みになりやすい典型パターン",
     "シクリカル＝景気や市況で業績が大きく循環する銘柄群（メモリ・海運等）"),
    ("暴落は予定に入れる",
     "10%程度の調整はおおむね毎年、大きな下落も数年に一度は起きてきた",
     "急落を「想定内」にできれば、狼狽売りという最大の失敗を避けられる",
     "攻めすぎた金額は暴落時に続かない。続けられる金額設計がすべて",
     "ドローダウン＝直近高値からの下落率。心の耐久力の目安になる"),
    ("複利は静かに効く",
     "リターンがリターンを生む構造は、時間が長いほど加速する",
     "1日の±1%より、10年続けたかどうかが資産の桁を決める",
     "途中でやめると複利は止まる。退屈こそインデックス投資の正解",
     "複利＝利益を再投資して、元本を増やしながら増える仕組み"),
]

def _canvas():
    fig = plt.figure(figsize=(10.8,13.5), dpi=100); fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0,0,1,1]); ax.set_xlim(0,W); ax.set_ylim(0,H)
    ax.invert_yaxis(); ax.axis("off")
    return fig, ax

def _header(ax, subtitle, date_str):
    ax.text(64, 84, "MORNING BRIEF", color=GOLD, fontsize=31, fontweight="bold", va="center")
    ax.text(64, 136, subtitle, color=INK, fontsize=20, va="center")
    ax.text(W-64, 66, "@your_account", color=DIM, fontsize=15, ha="right", va="center")
    ax.text(W-64, 94, "ASSET LOG", color=GOLD, fontsize=16, ha="right", va="center", fontweight="bold")
    ax.text(W-64, 122, date_str, color=DIM, fontsize=14, ha="right", va="center")
    ax.plot([64, W-64], [168,168], color=LINE, lw=2)

def _footer(ax, note):
    ax.plot([64, W-64], [H-84, H-84], color=LINE, lw=1.5)
    ax.text(64, H-52, note, color=DIM, fontsize=13.5, va="center")

def _block(ax, cy, label, lines, label_color=GOLD, bg=CARDBG, bar=False):
    pad_top, line_h, pad_bot = 46, 34, 20
    h = pad_top + len(lines)*line_h + pad_bot
    ax.add_patch(FancyBboxPatch((56,cy), W-112, h,
        boxstyle="round,pad=0,rounding_size=16", facecolor=bg, lw=0))
    if bar:
        ax.add_patch(FancyBboxPatch((56,cy), 10, h,
            boxstyle="round,pad=0,rounding_size=3", facecolor=GOLD, lw=0))
    ax.text(84, cy+28, label, color=label_color, fontsize=17, fontweight="bold", va="center")
    for i, ln in enumerate(lines):
        ax.text(84, cy+pad_top+12+i*line_h, ln, color=INK, fontsize=18.5, va="center")
    return cy + h + 12

def _wrap(text, width):
    return textwrap.wrap(text, width) or [""]

def news_card(rank:int, story:dict, date_str:str, out:str, stance:str):
    """1ニュース=1枚の深掘り解説カード。"""
    ex = build_explainer(story["title"])
    fig, ax = _canvas()
    _header(ax, f"今日の話題ニュース #{rank}（{story['n_sources']}媒体が報道）", date_str)

    cy = 198
    tl = _wrap(story["title"], 17)[:3]
    for i, ln in enumerate(tl):
        ax.text(W/2, cy+20+i*48, ln, color=INK, fontsize=29, fontweight="bold",
                ha="center", va="center")
    cy += len(tl)*48 + 36

    nums = ex["数字"]
    if nums:
        l1 = _wrap("見出しのポイントは「" + "・".join(nums) + "」という数字。", 25)[:2]
    else:
        l1 = _wrap(story["title"] + "、というニュース。", 25)[:2]
    cy = _block(ax, cy, "❶ 何が起きた", l1)
    cy = _block(ax, cy, "❷ 背景を一言で", _wrap(ex["背景"] + "。", 25)[:2])
    cy = _block(ax, cy, "❸ 市場への影響", _wrap(ex["影響"] + "。", 25)[:2])
    cy = _block(ax, cy, "❹ リスク・注意（必読）", _wrap(ex["注意"] + "。", 25)[:2],
                label_color=RED)
    cy = _block(ax, cy, "用語メモ", _wrap(ex["用語"] + "。", 25)[:2], label_color=BLUE)
    _block(ax, cy, "自分のスタンス", [stance], bg=STANCEBG, bar=True)
    _footer(ax, "報道ベースの概算・見出しは要約。解説は一般的な整理です。投資助言ではありません。")
    fig.savefig(out, facecolor=BG); plt.close(fig)

def evergreen_card(idx:int, date_str:str, out:str, stance:str, rank:int|None=None):
    title, p1, p2, p3, yougo = EVERGREEN[idx % len(EVERGREEN)]
    fig, ax = _canvas()
    sub = f"今日の話題ニュース #{rank}（取得不可のため原則解説）" if rank else "今日の投資の原則"
    _header(ax, sub, date_str)
    cy = 212
    ax.text(W/2, cy+14, f"“{title}”", color=GOLD, fontsize=40, fontweight="bold",
            ha="center", va="center")
    cy += 94
    cy = _block(ax, cy, "❶ どういうことか", _wrap(p1 + "。", 25)[:2])
    cy = _block(ax, cy, "❷ なぜ大事か", _wrap(p2 + "。", 25)[:2])
    cy = _block(ax, cy, "❸ ありがちな失敗", _wrap(p3 + "。", 25)[:2], label_color=RED)
    cy = _block(ax, cy, "用語メモ", _wrap(yougo + "。", 25)[:2], label_color=BLUE)
    _block(ax, cy, "自分のスタンス", [stance], bg=STANCEBG, bar=True)
    _footer(ax, "個人の記録・情報共有であり投資助言ではありません。")
    fig.savefig(out, facecolor=BG); plt.close(fig)

def summary_card(stories:list|None, date_str:str, out:str, stance:str):
    fig, ax = _canvas()
    _header(ax, "今朝の話題まとめ", date_str)
    cy = 200
    if stories:
        for i, s in enumerate(stories[:4], 1):
            lines = _wrap(s["title"], 22)[:2]
            hgt = 54 + len(lines)*40 + 16
            ax.add_patch(FancyBboxPatch((56,cy), W-112, hgt,
                boxstyle="round,pad=0,rounding_size=16", facecolor=CARDBG, lw=0))
            ax.text(92, cy+34, f"{i}", color=GOLD, fontsize=28, fontweight="bold", va="center")
            ax.text(138, cy+26, f"{s['n_sources']}媒体が報道", color=DIM, fontsize=13.5, va="center")
            for j, ln in enumerate(lines):
                ax.text(138, cy+56+j*40, ln, color=INK, fontsize=20, va="center")
            cy += hgt + 12
        note = "報道ベースの概算・見出しは要約。個人の記録であり投資助言ではありません。"
    else:
        cy = _block(ax, cy, "本日のニュース", ["休場などの理由で話題ニュースの取得なし",
                                            "こういう日は「何もしない」が正解"])
        note = "個人の記録・情報共有であり投資助言ではありません。"
    cy = max(cy, 1030)
    _block(ax, cy, "自分のスタンス", [stance], bg=STANCEBG, bar=True)
    _footer(ax, note)
    fig.savefig(out, facecolor=BG); plt.close(fig)
