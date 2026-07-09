# -*- coding: utf-8 -*-
"""
make_allocation_slide.py
========================
data.json から資産割合スライド(2枚目)を生成する。
 - 左: ETF vs 投資信託 の大分類ドーナツ
 - 右: 全銘柄別ドーナツ
出力: slide/allocation.png (1080x1080)
"""

import json
import math
from datetime import datetime
from pathlib import Path

from config import PORTFOLIO_TITLE, X_ACCOUNT

DATA = Path("data.json")
OUT_HTML = Path("slide/allocation.html")
OUT_PNG = Path("slide/allocation.png")

# 銘柄ごとの色パレット(ETF系=青緑、投信系=金茶でグラデ)
PALETTE = [
    "#58a6ff", "#3fb950", "#56d4dd", "#79c0ff",  # ETF寄り
    "#e3b341", "#f0883e", "#db61a2", "#bc8cff",   # 投信寄り
]


def yen(n):
    try:
        return f"¥{int(round(n)):,}"
    except Exception:
        return "—"


def donut_svg(segments, size=300, stroke=46):
    """segments: [(label, value, color)] からSVGドーナツを生成。"""
    total = sum(v for _, v, _ in segments) or 1
    r = (size - stroke) / 2
    cx = cy = size / 2
    circ = 2 * math.pi * r
    offset = 0.0
    arcs = ""
    for label, value, color in segments:
        frac = value / total
        dash = frac * circ
        gap = circ - dash
        # -90度start(12時方向)、時計回り
        arcs += (
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
            f'stroke="{color}" stroke-width="{stroke}" '
            f'stroke-dasharray="{dash:.3f} {gap:.3f}" '
            f'stroke-dashoffset="{-offset:.3f}" '
            f'transform="rotate(-90 {cx} {cy})"/>'
        )
        offset += dash
    return (f'<svg viewBox="0 0 {size} {size}" '
            f'xmlns="http://www.w3.org/2000/svg">{arcs}</svg>')


def legend_rows(segments, total):
    rows = ""
    for label, value, color in segments:
        pct = value / total * 100 if total else 0
        rows += f"""
        <div class="lg">
          <span class="dot" style="background:{color}"></span>
          <span class="lg-name">{label}</span>
          <span class="lg-pct">{pct:.1f}%</span>
          <span class="lg-jpy">{yen(value)}</span>
        </div>"""
    return rows


def build_html(data: dict) -> str:
    etf = data.get("etf", {})
    fund = data.get("fund", {})

    etf_total = sum(v["curr_jpy"] for v in etf.values())
    fund_total = sum(v["curr_jpy"] for v in fund.values())
    total = etf_total + fund_total or 1

    # 左: 大分類
    cat_segs = [
        ("米国ETF", etf_total, "#58a6ff"),
        ("投資信託", fund_total, "#e3b341"),
    ]

    # 右: 全銘柄(評価額の大きい順)
    items = []
    for v in etf.values():
        items.append((v["name"].split()[0], v["curr_jpy"]))  # 短縮名
    for v in fund.values():
        items.append((v["name"], v["curr_jpy"]))
    items.sort(key=lambda x: x[1], reverse=True)
    sym_segs = [(name, jpy, PALETTE[i % len(PALETTE)])
                for i, (name, jpy) in enumerate(items)]

    date_str = data.get("date", "")
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        date_disp = f"{d.year}年{d.month}月{d.day}日"
    except Exception:
        date_disp = date_str

    etf_pct = etf_total / total * 100
    fund_pct = fund_total / total * 100

    return f"""<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Zen+Kaku+Gothic+New:wght@400;500;700;900&family=Roboto+Mono:wght@500;700&display=swap');
* {{ margin:0; padding:0; box-sizing:border-box; }}
:root {{
  --bg:#0d1117; --panel:#161b22; --line:#2a3242;
  --txt:#e6edf3; --dim:#8b98a9; --accent:#58a6ff; --gold:#e3b341;
}}
body {{
  width:1080px; height:1080px; background:
    radial-gradient(900px 500px at 85% -8%, rgba(88,166,255,.10), transparent 60%),
    radial-gradient(700px 500px at -5% 110%, rgba(227,179,65,.08), transparent 55%),
    var(--bg);
  color:var(--txt); font-family:'Zen Kaku Gothic New',sans-serif;
  padding:52px 56px 44px; display:flex; flex-direction:column; overflow:hidden;
}}
.mono {{ font-family:'Roboto Mono',monospace; }}
header {{ display:flex; justify-content:space-between; align-items:flex-end;
  border-bottom:2px solid var(--line); padding-bottom:22px; }}
.title {{ font-size:38px; font-weight:900; }}
.date {{ font-size:22px; color:var(--dim); margin-top:6px; }}
.acct {{ font-size:20px; color:var(--accent); font-weight:700; }}

.total-wrap {{ margin:26px 0 30px; display:flex; align-items:baseline; gap:22px; }}
.total-label {{ font-size:24px; color:var(--dim); }}
.total {{ font-size:64px; font-weight:900; }}

.cols {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; flex:1; }}
.panel {{ background:var(--panel); border:1px solid var(--line);
  border-radius:20px; padding:26px 26px 20px; display:flex; flex-direction:column; }}
.panel-h {{ font-size:23px; font-weight:700; margin-bottom:18px;
  display:flex; align-items:center; gap:10px; }}
.panel-h::before {{ content:''; width:9px; height:24px; border-radius:3px; background:var(--accent); }}
.panel.sym .panel-h::before {{ background:var(--gold); }}

.donut-wrap {{ position:relative; width:300px; height:300px; margin:0 auto 22px; }}
.donut-wrap svg {{ width:100%; height:100%; }}
.donut-center {{ position:absolute; inset:0; display:flex; flex-direction:column;
  align-items:center; justify-content:center; }}
.dc-big {{ font-size:30px; font-weight:900; }}
.dc-sub {{ font-size:15px; color:var(--dim); }}
.donut-wrap.small {{ width:260px; height:260px; }}

.lg {{ display:flex; align-items:center; gap:10px; padding:7px 0;
  border-bottom:1px solid var(--line); font-size:18px; }}
.lg:last-child {{ border-bottom:none; }}
.dot {{ width:14px; height:14px; border-radius:4px; flex:none; }}
.lg-name {{ flex:1; }}
.lg-pct {{ font-weight:700; width:64px; text-align:right; }}
.lg-jpy {{ color:var(--dim); width:120px; text-align:right; font-size:16px; }}

footer {{ margin-top:18px; text-align:center; font-size:15px; color:var(--dim); }}
</style></head><body>
  <header>
    <div>
      <div class="title">{PORTFOLIO_TITLE}｜資産構成</div>
      <div class="date">{date_disp} 時点</div>
    </div>
    <div class="acct">@{X_ACCOUNT}</div>
  </header>

  <div class="total-wrap">
    <span class="total-label">総資産</span>
    <span class="total mono">{yen(total)}</span>
  </div>

  <div class="cols">
    <div class="panel cat">
      <div class="panel-h">資産タイプ別</div>
      <div class="donut-wrap">
        {donut_svg(cat_segs)}
        <div class="donut-center">
          <div class="dc-big">ETF {etf_pct:.0f}%</div>
          <div class="dc-sub">投信 {fund_pct:.0f}%</div>
        </div>
      </div>
      {legend_rows(cat_segs, total)}
    </div>

    <div class="panel sym">
      <div class="panel-h">銘柄別</div>
      <div class="donut-wrap small">
        {donut_svg(sym_segs, size=260, stroke=40)}
      </div>
      {legend_rows(sym_segs, total)}
    </div>
  </div>

  <footer>※評価額ベースの構成比。記録・情報共有目的であり投資助言ではありません</footer>
</body></html>"""


def main():
    data = json.load(open(DATA, encoding="utf-8")) if DATA.exists() else {}
    html = build_html(data)
    OUT_HTML.parent.mkdir(exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"💾 {OUT_HTML}")

    from playwright.sync_api import sync_playwright
    import io
    from PIL import Image
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        # 2倍解像度でレンダリングしてから 1080x1080 へ縮小(スーパーサンプリング)。
        # 高解像描画の鮮明さは保ちつつ、最終出力は 1080x1080(=1.17MP)に抑える。
        # 2160x2160(4.67MP)のままだと iOS Safari / GitHub モバイルの画像デコード上限に
        # 引っかかり、スマホの blob 表示で画像が出ない事象があるため。
        page = browser.new_page(viewport={"width": 1080, "height": 1080},
                                device_scale_factor=2)
        page.goto(OUT_HTML.resolve().as_uri())
        page.wait_for_timeout(1200)
        raw = page.screenshot(clip={"x": 0, "y": 0, "width": 1080, "height": 1080})
        browser.close()
    Image.open(io.BytesIO(raw)).convert("RGB").resize(
        (1080, 1080), Image.LANCZOS).save(OUT_PNG)
    print(f"🖼️  {OUT_PNG} を生成しました")


if __name__ == "__main__":
    main()
