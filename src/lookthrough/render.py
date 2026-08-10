# -*- coding: utf-8 -*-
"""
render.py
=========
ルックスルー結果を「ASSET LOG」デザインの1枚画像(1180×1450)にする。

デザイン仕様
------------
- 背景 #0B1220 / 左右余白 64px
- ヘッダー: 白太字42px + グレー20px サブ + 右上に青のアカウント名 + 罫線 #1E2A42
- 総資産ブロック: グレー小見出し + 白・等幅64px
- 実質保有TOP20の表: カード #111A2E / 角丸16px
  2本以上のファンド経由の行は左端に黄色(#E0B45C)の縦線を入れる
- サマリーカード3枚: #16203A / 角丸14px / 数値44px
- フッター: 左に免責、右に金色の「ASSET LOG」

日本語は Noto Sans JP（無ければ Noto Sans CJK JP）。
描画後に src.common.fontcheck で豆腐（□）の有無を検査する。
"""

from __future__ import annotations

from pathlib import Path

from src.common.render import render_png

WIDTH, HEIGHT = 1180, 1450

# 経由ファンドを表す色ドット。ファンドIDに順番に割り当てる。
DOT_COLORS = ["#4A9EFF", "#E0B45C", "#6EE7A8", "#F08A8A", "#B79BFF",
              "#7FD4C1", "#F5A97F", "#9FB3D9", "#D98BC4", "#8FD46E",
              "#C9A227"]

_CSS = f"""
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  width:{WIDTH}px; height:{HEIGHT}px; background:#0B1220; color:#FFFFFF;
  font-family:'Noto Sans JP','Noto Sans CJK JP','Hiragino Sans',sans-serif;
  padding:40px 64px 30px; display:flex; flex-direction:column; overflow:hidden;
}}
.num {{ font-variant-numeric:tabular-nums; font-feature-settings:'tnum' 1; }}

header {{ display:flex; justify-content:space-between; align-items:flex-start; }}
.h-title {{ font-size:42px; font-weight:700; letter-spacing:.01em;
  line-height:1.15; }}
.h-sub {{ font-size:20px; color:#8B96AB; margin-top:9px; line-height:1.3; }}
.h-acct {{ font-size:20px; color:#4A9EFF; font-weight:700; }}
.rule {{ height:1px; background:#1E2A42; margin:16px 0 0; }}

.totals {{ display:flex; justify-content:space-between; align-items:flex-end;
  margin-top:16px; }}
.t-label {{ font-size:18px; color:#8B96AB; line-height:1.3; }}
.t-value {{ font-size:64px; font-weight:700; line-height:1.0; margin-top:6px; }}
.t-right {{ text-align:right; }}
.t-cov {{ font-size:30px; font-weight:700; margin-top:6px; line-height:1.1; }}
/* 構成比の基準日は常に出す。古いときは金色で強調する。 */
.t-asof {{ font-size:15px; color:#8B96AB; margin-top:5px; line-height:1.3; }}
.t-asof.old {{ color:#E0B45C; font-weight:700; }}

/* 警告と凡例は最大2行に抑える（表の行数を圧迫させないため） */
.warn {{ margin-top:11px; font-size:15px; color:#E0B45C; line-height:1.4;
  max-height:42px; overflow:hidden; }}

.legend {{ display:flex; flex-wrap:wrap; gap:5px 16px; margin-top:11px;
  font-size:14px; color:#8B96AB; line-height:1.35; max-height:44px;
  overflow:hidden; }}
.legend span {{ display:inline-flex; align-items:center; gap:6px; }}
.dot {{ width:9px; height:9px; border-radius:50%; display:inline-block;
  flex:none; }}

.card {{ background:#111A2E; border-radius:16px; padding:12px 18px;
  margin-top:12px; }}
.thead, .row {{ display:grid;
  grid-template-columns:42px 1fr 92px 116px 162px; align-items:center;
  column-gap:10px; }}
.thead {{ font-size:14px; color:#8B96AB; padding:0 0 7px 11px;
  line-height:1.3; border-bottom:1px solid #1E2A42; }}
.row {{ font-size:21px; line-height:1.15; padding:6.5px 0 6.5px 8px;
  border-left:3px solid transparent;
  border-bottom:1px solid rgba(30,42,66,.55); }}
.row.dup {{ border-left-color:#E0B45C; }}
.row:last-child {{ border-bottom:none; }}
.r-rank {{ font-size:16px; color:#8B96AB; }}
.r-name {{ font-weight:700; white-space:nowrap; overflow:hidden;
  text-overflow:ellipsis; }}
.r-name .co {{ font-size:14px; color:#8B96AB; font-weight:400; margin-left:8px; }}
.r-dots {{ display:flex; gap:4px; }}
.r-pct {{ text-align:right; font-weight:700; }}
.r-amt {{ text-align:right; color:#8B96AB; font-size:19px; }}
.r-chg {{ font-size:13px; margin-left:6px; color:#8B96AB; font-weight:400; }}

.summary {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px;
  margin-top:12px; }}
.s-card {{ background:#16203A; border-radius:14px; padding:14px 18px; }}
.s-label {{ font-size:16px; color:#8B96AB; line-height:1.3; }}
.s-value {{ font-size:44px; font-weight:700; margin-top:6px; line-height:1.05; }}
.s-note {{ font-size:13px; color:#8B96AB; margin-top:5px; line-height:1.3; }}
.up {{ color:#6EE7A8; }} .down {{ color:#F08A8A; }} .flat {{ color:#FFFFFF; }}

footer {{ margin-top:auto; padding-top:12px; display:flex;
  justify-content:space-between; align-items:flex-end; }}
.f-note {{ font-size:16px; color:#8B96AB; }}
.f-brand {{ font-size:20px; font-weight:700; color:#E0B45C;
  letter-spacing:.08em; }}
"""


def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def fund_colors(fund_ids: list[str]) -> dict[str, str]:
    return {fid: DOT_COLORS[i % len(DOT_COLORS)]
            for i, fid in enumerate(fund_ids)}


def _short_name(name: str, limit: int = 12) -> str:
    n = str(name)
    return n if len(n) <= limit else n[:limit - 1] + "…"


def build_html(ctx: dict) -> str:
    """画像のHTMLを組み立てる。ctx は generate.py が作る描画用データ。"""
    colors = ctx["fund_colors"]

    legend = "".join(
        f'<span><i class="dot" style="background:{colors.get(f["id"], "#8B96AB")}"></i>'
        f'{_esc(_short_name(f["label"]))}</span>'
        for f in ctx["legend"])

    rows = ""
    for r in ctx["rows"]:
        dots = "".join(
            f'<i class="dot" style="background:{colors.get(v, "#8B96AB")}"></i>'
            for v in r["via_ids"])
        chg = (f'<span class="r-chg">{_esc(r["rank_change"])}</span>'
               if r.get("rank_change") else "")
        company = (f'<span class="co">{_esc(_short_name(r["company"], 18))}</span>'
                   if r.get("company") else "")
        rows += (
            f'<div class="row{" dup" if r["dup"] else ""}">'
            f'<div class="r-rank num">{r["rank"]}</div>'
            f'<div class="r-name">{_esc(r["ticker"])}{company}</div>'
            f'<div class="r-dots">{dots}</div>'
            f'<div class="r-pct num">{_esc(r["pct"])}{chg}</div>'
            f'<div class="r-amt num">{_esc(r["amount"])}</div>'
            f'</div>')

    cards = ""
    for c in ctx["summary"]:
        note = (f'<div class="s-note">{_esc(c["note"])}</div>'
                if c.get("note") else "")
        cards += (f'<div class="s-card"><div class="s-label">{_esc(c["label"])}</div>'
                  f'<div class="s-value num {c.get("tone", "flat")}">'
                  f'{_esc(c["value"])}</div>{note}</div>')

    warn = (f'<div class="warn">{_esc(ctx["warning"])}</div>'
            if ctx.get("warning") else "")

    return f"""<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">
<style>{_CSS}</style></head><body>
  <header>
    <div>
      <div class="h-title">{_esc(ctx["title"])}</div>
      <div class="h-sub">{_esc(ctx["subtitle"])}</div>
    </div>
    <div class="h-acct">{_esc(ctx["account"])}</div>
  </header>
  <div class="rule"></div>

  <div class="totals">
    <div>
      <div class="t-label">総資産</div>
      <div class="t-value num">{_esc(ctx["total"])}</div>
    </div>
    <div class="t-right">
      <div class="t-label">個別銘柄まで分解できた割合</div>
      <div class="t-cov num">{_esc(ctx["coverage"])}</div>
      <div class="t-asof{' old' if ctx.get('asof_warn') else ''}">
        {_esc(ctx.get("asof", ""))}</div>
    </div>
  </div>
  {warn}

  <div class="legend">{legend}</div>

  <div class="card">
    <div class="thead">
      <div>#</div><div>銘柄</div><div>経由</div>
      <div style="text-align:right">実質比率</div>
      <div style="text-align:right">実質金額</div>
    </div>
    {rows}
  </div>

  <div class="summary">{cards}</div>

  <footer>
    <span class="f-note">{_esc(ctx["footer_note"])}</span>
    <span class="f-brand">ASSET LOG</span>
  </footer>
</body></html>"""


def collect_texts(ctx: dict) -> list[str]:
    """豆腐チェックの対象になる、画像に描く文字列をすべて集める。"""
    texts = [ctx["title"], ctx["subtitle"], ctx["account"], ctx["total"],
             ctx["coverage"], ctx.get("asof") or "", ctx.get("warning") or "",
             ctx["footer_note"],
             "総資産", "個別銘柄まで分解できた割合", "銘柄", "経由",
             "実質比率", "実質金額", "ASSET LOG"]
    for f in ctx["legend"]:
        texts.append(_short_name(f["label"]))
    for r in ctx["rows"]:
        texts += [r["ticker"], _short_name(r.get("company") or "", 18),
                  r["pct"], r["amount"], r.get("rank_change") or ""]
    for c in ctx["summary"]:
        texts += [c["label"], c["value"], c.get("note") or ""]
    return [t for t in texts if t]


def render(ctx: dict, out_png: Path, report: dict | None = None) -> bool:
    return render_png(build_html(ctx), Path(out_png),
                      width=WIDTH, height=HEIGHT, report=report)
