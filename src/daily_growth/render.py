# -*- coding: utf-8 -*-
"""
render.py
=========
カード（compose が作った素材）を1枚の画像にする。

方針
----
- **数字はすべてプログラムが実データから描く**。画像生成AIは使わない。
- 素材イラスト（ロケット・札束・コイン・炎・人物・盾）を置かない。
  出すのは文字・罫線・棒・折れ線だけ。
- 1投稿1枚。通し番号（01 / 1/5 / ①）は入れない。
- iPhone の X タイムラインで読める文字サイズにする（本文16px相当以上）。

デザインは data/daily_growth_designs.yml のプールから選ばれる。
theme（配色）と layout（骨格）の組み合わせで、毎日同じ見た目にならない
ようにしている。
"""

from __future__ import annotations

from pathlib import Path

from src.common.render import render_png
from src.common.util import REPO_ROOT, load_yaml

DESIGNS_PATH = REPO_ROOT / "data" / "daily_growth_designs.yml"

DEFAULT_SIZE = (1180, 1450)

# ASSET LOG の配色（既存の画像と揃える）
THEMES = {
    "dark": {
        "bg": "#0B1220", "panel": "#111A2E", "card": "#16203A",
        "line": "#1E2A42", "ink": "#FFFFFF", "dim": "#8B96AB",
        "accent": "#4A9EFF", "gold": "#E0B45C",
        "up": "#6EE7A8", "down": "#F08A8A",
        "font": "'Noto Sans JP','Noto Sans CJK JP','Hiragino Sans',sans-serif",
    },
    "light": {
        "bg": "#F4F1EA", "panel": "#FFFFFF", "card": "#ECE7DC",
        "line": "#D6CFC0", "ink": "#14202E", "dim": "#6C7787",
        "accent": "#1B5FA8", "gold": "#9A7526",
        "up": "#1C7A4F", "down": "#B03A3A",
        "font": "'Noto Sans JP','Noto Sans CJK JP','Hiragino Sans',sans-serif",
    },
    "paper": {
        "bg": "#FAF7F0", "panel": "#FFFFFF", "card": "#F2EDE2",
        "line": "#CFC7B6", "ink": "#1A1A1A", "dim": "#6E6A78",
        "accent": "#2A5D8F", "gold": "#8A6A20",
        "up": "#1C7A4F", "down": "#B03A3A",
        "font": "'Roboto Mono','Noto Sans JP','Noto Sans CJK JP',monospace",
    },
}


def load_designs(path: Path = DESIGNS_PATH) -> dict[str, dict]:
    data = load_yaml(path, default={"designs": []}) or {}
    return {d["id"]: d for d in (data.get("designs") or [])}


def design_size(design: dict) -> tuple[int, int]:
    return (int(design.get("width", DEFAULT_SIZE[0])),
            int(design.get("height", DEFAULT_SIZE[1])))


def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _tone_class(tone: str) -> str:
    return {"up": "up", "down": "down"}.get(tone, "flat")


# --------------------------------------------------------------------------
# 図
# --------------------------------------------------------------------------

def _fig_bars(fig: dict) -> str:
    rows = ""
    for it in fig["items"]:
        w = max(3.0, float(it["ratio"]) * 100.0)
        rows += (
            f'<div class="bar-row">'
            f'<div class="bar-label">{_esc(it["label"])}</div>'
            f'<div class="bar-track"><div class="bar-fill {_tone_class(it["tone"])}"'
            f' style="width:{w:.1f}%"></div></div>'
            f'<div class="bar-value num {_tone_class(it["tone"])}">{_esc(it["text"])}</div>'
            f'</div>')
    return f'<div class="bars">{rows}</div>'


def _fig_compare(fig: dict) -> str:
    def block(side: dict, cls: str) -> str:
        note = (f'<div class="cmp-note">{_esc(side["note"])}</div>'
                if side.get("note") else "")
        return (f'<div class="cmp {cls}">'
                f'<div class="cmp-label">{_esc(side["label"])}</div>'
                f'<div class="cmp-value num {_tone_class(side.get("tone", "flat"))}">'
                f'{_esc(side["value"])}</div>{note}</div>')
    note = (f'<div class="fig-note">{_esc(fig["note"])}</div>'
            if fig.get("note") else "")
    return (f'<div class="compare">{block(fig["left"], "left")}'
            f'<div class="cmp-div"></div>{block(fig["right"], "right")}</div>{note}')


def _fig_progress(fig: dict) -> str:
    w = float(fig["ratio"]) * 100.0
    note = (f'<div class="fig-note">{_esc(fig["note"])}</div>'
            if fig.get("note") else "")
    return (f'<div class="prog">'
            f'<div class="prog-ends"><span>{_esc(fig["left"])}</span>'
            f'<span>{_esc(fig["right"])}</span></div>'
            f'<div class="prog-track"><div class="prog-fill" style="width:{w:.1f}%">'
            f'</div></div></div>{note}')


def _fig_table(fig: dict) -> str:
    cols = fig["columns"]
    align = fig.get("align") or ["left"] * len(cols)
    th = "".join(f'<th class="{align[i]}">{_esc(c)}</th>'
                 for i, c in enumerate(cols))
    trs = ""
    for row in fig["rows"]:
        trs += "<tr>" + "".join(
            f'<td class="{align[i]} {"num" if align[i] == "right" else ""}">'
            f'{_esc(v)}</td>' for i, v in enumerate(row)) + "</tr>"
    return (f'<table class="fig-table"><thead><tr>{th}</tr></thead>'
            f'<tbody>{trs}</tbody></table>')


def _fig_sparkline(fig: dict) -> str:
    pts = [float(v) for v in fig["points"]]
    w, h, pad = 1000, 300, 14
    lo, hi = min(pts), max(pts)
    if hi == lo:
        hi = lo + 1
    n = max(len(pts) - 1, 1)
    coords = " ".join(
        f"{pad + i * (w - 2 * pad) / n:.1f},"
        f"{pad + (h - 2 * pad) * (1 - (v - lo) / (hi - lo)):.1f}"
        for i, v in enumerate(pts))
    area = f"{pad},{h - pad} {coords} {w - pad},{h - pad}"
    note = (f'<div class="fig-note">{_esc(fig["note"])}</div>'
            if fig.get("note") else "")
    return (f'<div class="spark">'
            f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
            f'<polygon points="{area}" class="spark-area"/>'
            f'<polyline points="{coords}" class="spark-line"/></svg>'
            f'<div class="spark-ends"><span>{_esc(fig["left"])}</span>'
            f'<span>{_esc(fig["right"])}</span></div></div>{note}')


_FIGURES = {"bars": _fig_bars, "compare": _fig_compare,
            "progress": _fig_progress, "table": _fig_table,
            "sparkline": _fig_sparkline}


def figure_html(fig: dict) -> str:
    fn = _FIGURES.get(fig.get("kind", ""))
    if fn is None:
        raise ValueError(f"未対応の図: {fig.get('kind')}")
    return f'<div class="figure">{fn(fig)}</div>'


# --------------------------------------------------------------------------
# CSS
# --------------------------------------------------------------------------

def _css(design: dict) -> str:
    t = THEMES[design.get("theme", "dark")]
    w, h = design_size(design)
    layout = design.get("layout", "stack")
    dashed = "dashed" if layout == "receipt" else "solid"
    hero = {"cover": 132, "hero_first": 120, "receipt": 78,
            "figure_first": 72, "editorial": 84}.get(layout, 96)
    head = {"cover": 74, "editorial": 58, "receipt": 42}.get(layout, 52)
    return f"""
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  width:{w}px; height:{h}px; background:{t['bg']}; color:{t['ink']};
  font-family:{t['font']}; padding:56px 64px 40px;
  display:flex; flex-direction:column; overflow:hidden;
}}
.num {{ font-variant-numeric:tabular-nums; font-feature-settings:'tnum' 1; }}
.up {{ color:{t['up']}; }} .down {{ color:{t['down']}; }} .flat {{ color:{t['ink']}; }}

header {{ display:flex; justify-content:space-between; align-items:flex-start;
  padding-bottom:18px; border-bottom:2px {dashed} {t['line']}; }}
.kicker {{ font-size:24px; font-weight:700; color:{t['accent']};
  letter-spacing:.06em; }}
.asof {{ font-size:20px; color:{t['dim']}; margin-top:8px; }}
.acct {{ font-size:20px; color:{t['dim']}; font-weight:700; text-align:right; }}

main {{ flex:1; display:flex; flex-direction:column;
  justify-content:space-evenly; gap:18px; padding:8px 0; }}

.headline {{ font-size:{head}px; font-weight:700; line-height:1.28;
  letter-spacing:.01em; }}

.hero {{ }}
.hero-label {{ font-size:24px; color:{t['dim']}; }}
.hero-value {{ font-size:{hero}px; font-weight:700; line-height:1.02;
  margin-top:10px; letter-spacing:-.01em; }}
.hero-delta {{ font-size:28px; margin-top:16px; color:{t['dim']}; }}

.figure {{ background:{t['panel']}; border-radius:18px;
  padding:30px 32px; }}
.fig-note {{ font-size:20px; color:{t['dim']}; margin-top:20px;
  line-height:1.45; }}

.bars {{ display:flex; flex-direction:column; gap:20px; }}
.bar-row {{ display:grid; grid-template-columns:250px 1fr 190px;
  align-items:center; column-gap:20px; }}
.bar-label {{ font-size:24px; white-space:nowrap; overflow:hidden;
  text-overflow:ellipsis; }}
.bar-track {{ height:22px; background:{t['card']}; border-radius:11px; }}
.bar-fill {{ height:22px; border-radius:11px; background:{t['accent']}; }}
.bar-fill.up {{ background:{t['up']}; }} .bar-fill.down {{ background:{t['down']}; }}
.bar-value {{ font-size:28px; font-weight:700; text-align:right; }}

.compare {{ display:grid; grid-template-columns:1fr 2px 1fr; align-items:stretch;
  column-gap:28px; }}
.cmp {{ padding:8px 4px; }}
.cmp-div {{ background:{t['line']}; }}
.cmp-label {{ font-size:23px; color:{t['dim']}; line-height:1.35; }}
.cmp-value {{ font-size:60px; font-weight:700; margin-top:14px;
  line-height:1.05; }}
.cmp-note {{ font-size:21px; color:{t['dim']}; margin-top:14px; }}

.prog {{ }}
.prog-ends {{ display:flex; justify-content:space-between; font-size:26px;
  color:{t['dim']}; margin-bottom:16px; }}
.prog-track {{ height:34px; background:{t['card']}; border-radius:17px; }}
.prog-fill {{ height:34px; border-radius:17px; background:{t['gold']}; }}

.fig-table {{ width:100%; border-collapse:collapse; }}
.fig-table th {{ font-size:21px; color:{t['dim']}; font-weight:700;
  padding:0 8px 14px; border-bottom:1px solid {t['line']}; }}
.fig-table td {{ font-size:27px; padding:15px 8px;
  border-bottom:1px {dashed} {t['line']}; }}
.fig-table tr:last-child td {{ border-bottom:none; }}
.left {{ text-align:left; }} .right {{ text-align:right; }}

.spark svg {{ width:100%; height:300px; display:block; }}
.spark-line {{ fill:none; stroke:{t['accent']}; stroke-width:5;
  vector-effect:non-scaling-stroke; }}
.spark-area {{ fill:{t['accent']}; opacity:.13; stroke:none; }}
.spark-ends {{ display:flex; justify-content:space-between; font-size:21px;
  color:{t['dim']}; margin-top:14px; }}

.notes {{ display:flex; flex-direction:column; gap:12px; }}
.note {{ font-size:22px; color:{t['dim']}; line-height:1.5; }}
.assumption {{ border-left:5px solid {t['gold']};
  padding:8px 0 8px 20px; font-size:22px; color:{t['dim']}; line-height:1.5; }}

footer {{ margin-top:auto; padding-top:22px; display:flex;
  justify-content:space-between; align-items:flex-end;
  border-top:1px {dashed} {t['line']}; }}
.f-note {{ font-size:19px; color:{t['dim']}; }}
.f-brand {{ font-size:21px; font-weight:700; color:{t['gold']};
  letter-spacing:.10em; }}
"""


# --------------------------------------------------------------------------
# 骨格
# --------------------------------------------------------------------------

FOOTER_NOTE = "※記録・情報共有目的であり投資助言ではありません"
ASSUMPTION_TEXT = "前提を置いた単純計算です。見通しではありません"


def _hero_html(hero: dict) -> str:
    delta = (f'<div class="hero-delta">{_esc(hero["delta"])}</div>'
             if hero.get("delta") else "")
    return (f'<div class="hero"><div class="hero-label">{_esc(hero["label"])}</div>'
            f'<div class="hero-value num {_tone_class(hero.get("tone", "flat"))}">'
            f'{_esc(hero["value"])}</div>{delta}</div>')


def _notes_html(notes: list[str]) -> str:
    if not notes:
        return ""
    items = "".join(f'<div class="note">{_esc(n)}</div>' for n in notes[:2])
    return f'<div class="notes">{items}</div>'


def build_html(card: dict, design: dict, account: str = "") -> str:
    layout = design.get("layout", "stack")
    headline = f'<div class="headline">{_esc(card["headline"])}</div>'
    hero = _hero_html(card["hero"])
    figure = figure_html(card["figure"])
    notes = _notes_html(card.get("notes") or [])
    assumption = (f'<div class="assumption">{ASSUMPTION_TEXT}</div>'
                  if design.get("assumption_band") else "")

    if layout in ("figure_first", "split"):
        body = headline + figure + hero + notes
    elif layout in ("hero_first", "cover"):
        body = hero + headline + figure + notes
    elif layout == "receipt":
        body = headline + hero + figure + notes
    elif layout == "editorial":
        body = headline + hero + figure + notes
    else:  # stack
        body = headline + hero + figure + notes

    return f"""<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">
<style>{_css(design)}</style></head><body>
  <header>
    <div>
      <div class="kicker">{_esc(card["kicker"])}</div>
      <div class="asof">基準日 {_esc(card["asof"])}</div>
    </div>
    <div class="acct">{_esc(account)}</div>
  </header>
  <main>{body}{assumption}</main>
  <footer>
    <span class="f-note">{_esc(FOOTER_NOTE)}</span>
    <span class="f-brand">ASSET LOG</span>
  </footer>
</body></html>"""


def collect_texts(card: dict, account: str = "",
                  design: dict | None = None) -> list[str]:
    """画像に描く文字列をすべて集める（豆腐チェック・通し番号チェック用）。"""
    texts = [card["kicker"], card["headline"], card["asof"], account,
             card["hero"]["label"], card["hero"]["value"],
             card["hero"].get("delta") or "",
             "基準日", FOOTER_NOTE, "ASSET LOG"]
    if design and design.get("assumption_band"):
        texts.append(ASSUMPTION_TEXT)
    texts += list(card.get("notes") or [])
    fig = card["figure"]
    kind = fig.get("kind")
    if kind == "bars":
        for it in fig["items"]:
            texts += [it["label"], it["text"]]
    elif kind == "compare":
        for side in (fig["left"], fig["right"]):
            texts += [side["label"], side["value"], side.get("note") or ""]
        texts.append(fig.get("note") or "")
    elif kind == "progress":
        texts += [fig["left"], fig["right"], fig.get("note") or ""]
    elif kind == "table":
        texts += list(fig["columns"])
        for row in fig["rows"]:
            texts += [str(c) for c in row]
    elif kind == "sparkline":
        texts += [fig["left"], fig["right"], fig.get("note") or ""]
    return [str(t) for t in texts if str(t).strip()]


def render(card: dict, design: dict, out_png: Path, account: str = "",
           report: dict | None = None) -> bool:
    w, h = design_size(design)
    return render_png(build_html(card, design, account), Path(out_png),
                      width=w, height=h, report=report)
