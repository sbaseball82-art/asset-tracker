# -*- coding: utf-8 -*-
"""ニュース内容を分析して描く「わかりやすい図・表・イラスト」ライブラリ。

カードのビジュアルは次の優先順で選ぶ（媒体数のような報道メタ情報は使わない）:
  1. 見出しトピックに関連する実マーケットチャート（market_charts.draw_price_chart）
  2. 見出しから数字が取れる → 「数字で見る」パネル（大型スタット/比較バー）
  3. どちらも適さない → トピック別の概念イラスト（需給ギャップ・金利シーソー・
     AI投資連鎖・期待と結果マトリクス等。ニュースの構造を1枚で理解させる図解）

すべて matplotlib のみで描画し、ネットワーク無しでも必ず描ける。
"""
from __future__ import annotations
import re

import matplotlib
matplotlib.use("Agg")
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

INK = "#eef2f8"; DIM = "#8fa0b8"; LINE = "#2a3650"; PANEL = "#131f33"
ACCENT = "#4fd1c5"; GOLD = "#d8b56a"; BLUE = "#6aa6e8"
UP = "#5fd0a0"; RED = "#e8807f"; BOX = "#22304d"


# ─────────────────────────────────────────────
# 共通部品（0..1 の axes 座標で描く）
# ─────────────────────────────────────────────
def _panel_ax(fig, rect_px, W, H, title=None):
    x, y, w, h = rect_px
    ax = fig.add_axes([x / W, 1 - (y + h) / H, w / W, h / H])
    ax.set_facecolor(PANEL)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.axis("off")
    if title:
        ax.text(0.03, 0.94, title, color=INK, fontsize=14.5,
                fontweight="bold", va="top")
    return ax


def _box(ax, x, y, w, h, label, sub=None, color=BOX, tcolor=INK, fs=15):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0.008,rounding_size=0.02",
                 facecolor=color, lw=0, mutation_aspect=0.5))
    cy = y + h / 2 + (0.045 if sub else 0)
    ax.text(x + w / 2, cy, label, color=tcolor, fontsize=fs,
            fontweight="bold", ha="center", va="center")
    if sub:
        ax.text(x + w / 2, cy - 0.09, sub, color=DIM, fontsize=11.5,
                ha="center", va="center")


def _arrow(ax, x1, y1, x2, y2, color=DIM, lw=2.6):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2),
                 arrowstyle="-|>", mutation_scale=18, color=color, lw=lw))


# ─────────────────────────────────────────────
# 1) 数字で見るパネル（見出しから抽出した数字の可視化）
# ─────────────────────────────────────────────
# 「1兆5000億円」のような兆・億の複合表記を最優先で1トークンとして拾う
_NUM_CTX = re.compile(
    r"([+\-▲▼]?\d+(?:\.\d+)?兆(?:\d+(?:\.\d+)?億)?円?)"
    r"|([+\-▲▼]?\d+(?:\.\d+)?\s*(?:%|％|兆円|億円|万円|万人|円|ドル|ポイント|pt|倍))")


def _context_label(title: str, start: int) -> str:
    """数値の直前の文脈を、区切り(、。・空白等)から数値までの語で切り出す。"""
    head = title[:start]
    seg = re.split(r"[、。・「」\s]", head)[-1]
    return (seg[-10:] or "見出しより").strip() or "見出しより"


def _leading_value(raw: str) -> float:
    m = re.match(r"[+\-▲▼]?(\d+(?:\.\d+)?)兆(?:(\d+(?:\.\d+)?)億)?", raw)
    if m:  # 兆・億の複合は億円換算（1兆5000億 → 15000）
        v = float(m.group(1)) * 10000 + float(m.group(2) or 0)
    else:
        m2 = re.match(r"[+\-▲▼]?(\d+(?:\.\d+)?)", raw)
        v = float(m2.group(1)) if m2 else 0.0
    return -v if raw[:1] in "-▲▼" else v


def _unit_of(raw: str) -> str:
    if "兆" in raw or "億円" in raw:
        return "円(大口)"
    m = re.search(r"(%|％|万円|万人|円|ドル|ポイント|pt|倍)$", raw)
    return m.group(1) if m else "他"


def extract_facts(title: str) -> list[dict]:
    """見出しから (文脈ラベル, 数値, 単位) を抽出。数値表記は原文のまま保持する。"""
    facts = []
    for m in _NUM_CTX.finditer(title.replace(",", "")):
        raw = (m.group(1) or m.group(2)).replace(" ", "")
        facts.append({"label": _context_label(title.replace(",", ""), m.start()),
                      "value": _leading_value(raw),
                      "raw": raw, "unit": _unit_of(raw)})
    return facts[:3]


def draw_number_panel(fig, rect_px, W, H, title: str) -> bool:
    """見出し中の数字を大型スタット/比較バーで可視化。

    数字が2つ以上あるときだけ使う（1つだけならパネルが間延びし、
    トピック概念図のほうがニュースの理解に役立つため呼び出し側で図解に回す）。
    """
    facts = extract_facts(title)
    if len(facts) < 2:
        return False
    ax = _panel_ax(fig, rect_px, W, H, "数字で見るこのニュース")

    same_unit = len(facts) >= 2 and len({f["unit"] for f in facts}) == 1
    if same_unit:
        # 同一単位の複数数字 → 横棒で比較
        vals = [abs(f["value"]) for f in facts]
        vmax = max(vals) or 1
        y0 = 0.66
        for i, f in enumerate(facts):
            y = y0 - i * 0.22
            bw = 0.55 * vals[i] / vmax
            neg = f["value"] < 0 or f["raw"].startswith(("-", "▲", "▼"))
            col = RED if neg else ACCENT
            ax.add_patch(FancyBboxPatch((0.20, y - 0.055), max(bw, 0.02), 0.11,
                         boxstyle="round,pad=0.004,rounding_size=0.012",
                         facecolor=col, lw=0, mutation_aspect=0.5))
            ax.text(0.185, y, f["label"], color=DIM, fontsize=12.5,
                    ha="right", va="center")
            ax.text(0.20 + max(bw, 0.02) + 0.015, y, f["raw"], color=INK,
                    fontsize=16, fontweight="bold", ha="left", va="center")
    else:
        # 大型スタットとして中央に並べる
        n = len(facts)
        for i, f in enumerate(facts):
            cx = (i + 0.5) / n
            neg = f["value"] < 0 or f["raw"].startswith(("-", "▲", "▼"))
            col = RED if neg else ACCENT
            ax.text(cx, 0.52, f["raw"], color=col, fontsize=min(44, 30 + 8 // n),
                    fontweight="bold", ha="center", va="center")
            ax.text(cx, 0.30, f["label"], color=DIM, fontsize=13,
                    ha="center", va="center")
    ax.text(0.03, 0.06, "※見出しに含まれる数値の整理（報道ベース）",
            color=DIM, fontsize=11, va="center")
    return True


# ─────────────────────────────────────────────
# 2) トピック別 概念イラスト（ニュースの構造を図解）
# ─────────────────────────────────────────────
def _diagram_memory(ax):
    """需給ギャップ概念図（供給は直線的・需要は加速的に伸びる）。"""
    xs = [0.14 + i * 0.14 for i in range(5)]
    demand = [0.34, 0.40, 0.50, 0.64, 0.82]
    supply = [0.32, 0.36, 0.41, 0.46, 0.52]
    ax.plot(xs, demand, color=RED, lw=3, solid_capstyle="round")
    ax.plot(xs, supply, color=BLUE, lw=3, solid_capstyle="round")
    ax.fill_between(xs, supply, demand, color=RED, alpha=0.10)
    ax.text(xs[-1] + 0.02, demand[-1], "需要", color=RED, fontsize=14,
            fontweight="bold", va="center")
    ax.text(xs[-1] + 0.02, supply[-1], "供給", color=BLUE, fontsize=14,
            fontweight="bold", va="center")
    _arrow(ax, xs[-1] - 0.045, supply[-1] + 0.025, xs[-1] - 0.045,
           demand[-1] - 0.025, color=GOLD)
    ax.text(xs[-1] - 0.075, (demand[-1] + supply[-1]) / 2, "ギャップ",
            color=GOLD, fontsize=12.5, fontweight="bold", ha="right", va="center")
    ax.text(0.5, 0.12, "AI需要が供給を上回るほど価格・業績に追い風（概念図）",
            color=DIM, fontsize=12, ha="center")


def _diagram_semi(ax):
    """半導体＝相場の体温計（連鎖図）。"""
    _box(ax, 0.06, 0.42, 0.22, 0.22, "半導体株", "SOX指数")
    _box(ax, 0.40, 0.62, 0.22, 0.20, "ハイテク株", "ナスダック")
    _box(ax, 0.40, 0.22, 0.22, 0.20, "AI関連", "電力・クラウド")
    _box(ax, 0.74, 0.42, 0.20, 0.22, "相場全体", "リスク選好")
    _arrow(ax, 0.28, 0.56, 0.40, 0.70)
    _arrow(ax, 0.28, 0.50, 0.40, 0.34)
    _arrow(ax, 0.62, 0.70, 0.76, 0.58)
    _arrow(ax, 0.62, 0.32, 0.76, 0.48)
    ax.text(0.5, 0.06, "半導体の急変は他セクターへ波及しやすい「体温計」",
            color=DIM, fontsize=12, ha="center")


def _diagram_rates(ax):
    """金利シーソー図。"""
    ax.plot([0.18, 0.82], [0.62, 0.34], color=INK, lw=4, solid_capstyle="round")
    ax.add_patch(FancyBboxPatch((0.47, 0.20), 0.06, 0.16,
                 boxstyle="round,pad=0.004,rounding_size=0.012",
                 facecolor=BOX, lw=0, mutation_aspect=0.5))
    _box(ax, 0.08, 0.62, 0.24, 0.20, "金利 ↑", "債券利回り", color="#2c3a5c", tcolor=GOLD)
    _box(ax, 0.70, 0.14, 0.24, 0.20, "株価 ↓", "特に高PER株", color="#2c3a5c", tcolor=RED)
    ax.text(0.5, 0.88, "金利と株価はシーソーの関係になりやすい",
            color=INK, fontsize=14, fontweight="bold", ha="center")
    ax.text(0.5, 0.06, "利下げ観測なら逆向き（株に追い風）。ただし理由次第で例外も多い",
            color=DIM, fontsize=12, ha="center")


def _diagram_fx(ax):
    """円相場の影響フロー図。"""
    _box(ax, 0.38, 0.58, 0.24, 0.24, "円安", "ドル/円 上昇", color="#2c3a5c", tcolor=GOLD, fs=17)
    _box(ax, 0.05, 0.16, 0.27, 0.24, "米国資産", "円換算 プラス", tcolor=UP)
    _box(ax, 0.37, 0.16, 0.26, 0.24, "輸出企業", "採算 プラス", tcolor=UP)
    _box(ax, 0.68, 0.16, 0.27, 0.24, "輸入コスト", "家計 マイナス", tcolor=RED)
    _arrow(ax, 0.44, 0.58, 0.22, 0.42)
    _arrow(ax, 0.50, 0.58, 0.50, 0.42)
    _arrow(ax, 0.56, 0.58, 0.78, 0.42)
    ax.text(0.5, 0.05, "円高なら矢印の効果は反転する", color=DIM, fontsize=12, ha="center")


def _diagram_rally(ax):
    """最高値更新の階段図。"""
    for i in range(5):
        x = 0.10 + i * 0.16
        h = 0.16 + i * 0.12
        ax.add_patch(FancyBboxPatch((x, 0.16), 0.12, h,
                     boxstyle="round,pad=0.004,rounding_size=0.012",
                     facecolor=(ACCENT if i == 4 else BOX), lw=0,
                     mutation_aspect=0.5))
    ax.text(0.82, 0.16 + 0.64 + 0.06, "今回", color=ACCENT, fontsize=13,
            fontweight="bold", ha="center")
    ax.text(0.5, 0.90, "最高値は「終わり」ではなく更新されてきた", color=INK,
            fontsize=14, fontweight="bold", ha="center")
    ax.text(0.5, 0.05, "高値更新は強いトレンドの証拠とされることが多い（ただし短期調整はある）",
            color=DIM, fontsize=11.5, ha="center")


def _diagram_selloff(ax):
    """下落の「よくある規模」目安表。"""
    rows = [("調整（-10%前後）", "おおむね毎年ある", ACCENT),
            ("弱気相場（-20%超）", "数年に一度", GOLD),
            ("暴落（-30%超）", "10年に一度ほど", RED)]
    ax.text(0.5, 0.90, "下落の「よくある規模」目安", color=INK, fontsize=14.5,
            fontweight="bold", ha="center")
    for i, (a, b, c) in enumerate(rows):
        y = 0.66 - i * 0.20
        ax.add_patch(FancyBboxPatch((0.06, y - 0.075), 0.88, 0.15,
                     boxstyle="round,pad=0.004,rounding_size=0.015",
                     facecolor=BOX, lw=0, mutation_aspect=0.5))
        ax.text(0.10, y, a, color=c, fontsize=14, fontweight="bold", va="center")
        ax.text(0.90, y, b, color=INK, fontsize=13.5, ha="right", va="center")
    ax.text(0.5, 0.05, "急落は「もし」ではなく「いつ」の世界。想定内にしておく",
            color=DIM, fontsize=12, ha="center")


def _diagram_earnings(ax):
    """決算: 期待と結果のマトリクス。"""
    ax.text(0.5, 0.92, "株価は「結果」より「事前予想との差」で動く", color=INK,
            fontsize=14, fontweight="bold", ha="center")
    _box(ax, 0.10, 0.48, 0.36, 0.26, "好決算 × 期待超え", "素直に上昇", tcolor=UP)
    _box(ax, 0.54, 0.48, 0.36, 0.26, "好決算 × 期待通り", "出尽くしで下落も", tcolor=GOLD)
    _box(ax, 0.10, 0.14, 0.36, 0.26, "悪決算 × 想定内", "悪材料出尽くしで上昇も", tcolor=GOLD)
    _box(ax, 0.54, 0.14, 0.36, 0.26, "悪決算 × 想定外", "大きく下落", tcolor=RED)


def _diagram_macro(ax):
    """経済指標→金融政策→市場のフロー。"""
    _box(ax, 0.05, 0.36, 0.25, 0.32, "経済指標", "雇用・CPI等", fs=16)
    _box(ax, 0.38, 0.36, 0.24, 0.32, "FRBの判断", "利上げ/利下げ", fs=16)
    _box(ax, 0.70, 0.36, 0.25, 0.32, "株・債券", "が織り込む", fs=16)
    _arrow(ax, 0.30, 0.52, 0.38, 0.52)
    _arrow(ax, 0.62, 0.52, 0.70, 0.52)
    ax.text(0.5, 0.82, "強い指標→利上げ観測→株に逆風／弱い指標→その逆", color=INK,
            fontsize=13.5, fontweight="bold", ha="center")
    ax.text(0.5, 0.16, "1回の数字で判断は変えない（速報値は改定されることも多い）",
            color=DIM, fontsize=12, ha="center")


def _diagram_ai(ax):
    """AI投資の産業連鎖図。"""
    _box(ax, 0.04, 0.34, 0.20, 0.34, "AI投資", "巨大テック", fs=16)
    _box(ax, 0.30, 0.34, 0.19, 0.34, "半導体", "GPU", fs=16)
    _box(ax, 0.55, 0.34, 0.19, 0.34, "メモリ", "HBM", fs=16)
    _box(ax, 0.79, 0.34, 0.17, 0.34, "電力", "データセンター", fs=16)
    _arrow(ax, 0.24, 0.51, 0.30, 0.51)
    _arrow(ax, 0.49, 0.51, 0.55, 0.51)
    _arrow(ax, 0.74, 0.51, 0.79, 0.51)
    ax.text(0.5, 0.82, "1つのAIニュースがチェーン全体の株価に波及する", color=INK,
            fontsize=14.5, fontweight="bold", ha="center")
    ax.text(0.5, 0.16, "収益化（ROI）の検証はこれから。期待剥落の調整リスクも併記",
            color=DIM, fontsize=12, ha="center")


def _diagram_default(ax):
    """ニュースとの向き合い方フロー。"""
    _box(ax, 0.06, 0.36, 0.24, 0.32, "ニュース", "見出しの印象", fs=16)
    _box(ax, 0.38, 0.36, 0.24, 0.32, "株価", "多くは織り込み済み", fs=16)
    _box(ax, 0.70, 0.36, 0.24, 0.32, "自分", "方針は変えない", tcolor=ACCENT, fs=16)
    _arrow(ax, 0.30, 0.52, 0.38, 0.52)
    _arrow(ax, 0.62, 0.52, 0.70, 0.52)
    ax.text(0.5, 0.84, "ニュースは「知る」ためのもの、「動く」ためのものではない",
            color=INK, fontsize=13.5, fontweight="bold", ha="center")
    ax.text(0.5, 0.16, "翌日には織り込まれていることも多い", color=DIM,
            fontsize=12, ha="center")


DIAGRAMS = {
    "memory": ("メモリ需給の構図（概念図）", _diagram_memory),
    "semi": ("半導体ニュースの波及構造", _diagram_semi),
    "rates": ("金利と株価の関係", _diagram_rates),
    "fx": ("円相場が効く場所", _diagram_fx),
    "rally": ("最高値更新の見方", _diagram_rally),
    "selloff": ("下落の規模感を整理", _diagram_selloff),
    "earnings": ("決算で株価が動く仕組み", _diagram_earnings),
    "macro": ("経済指標が市場に効く経路", _diagram_macro),
    "ai": ("AI投資の連鎖", _diagram_ai),
    "fab": ("AI投資の連鎖", _diagram_ai),
    "ipo": ("ニュースとの向き合い方", _diagram_default),
    "default": ("ニュースとの向き合い方", _diagram_default),
}


def draw_topic_diagram(fig, rect_px, W, H, topic_id: str) -> None:
    title, fn = DIAGRAMS.get(topic_id, DIAGRAMS["default"])
    ax = _panel_ax(fig, rect_px, W, H)
    ax.text(0.03, 0.97, title, color=INK, fontsize=14.5, fontweight="bold",
            va="top")
    # 図本体はタイトル下の領域に描く（0..1のまま各関数がレイアウト）
    fn(ax)
