# -*- coding: utf-8 -*-
"""
make_slide.py
=============
data.json と events.json から、Xに投稿する1枚スライド(PNG)を生成する。

出力: slide/slide.png (1080x1080)
依存: playwright (chromium)
  pip install playwright && playwright install chromium
"""

import json
from datetime import datetime
from pathlib import Path

DATA = Path("data.json")
EVENTS = Path("events.json")
OUT_HTML = Path("slide/slide.html")
OUT_PNG = Path("slide/slide.png")

from config import PORTFOLIO_TITLE, X_ACCOUNT


def yen(n):
    try:
        return f"¥{int(round(n)):,}"
    except Exception:
        return "—"

def signed_yen(n):
    if n is None:
        return "—"
    s = "+" if n >= 0 else "−"
    return f"{s}¥{abs(int(round(n))):,}"

def signed_pct(p):
    if p is None:
        return "—"
    s = "+" if p >= 0 else "−"
    return f"{s}{abs(p):.2f}%"

def cls(v):
    if v is None:
        return "flat"
    return "up" if v >= 0 else "down"


def build_html(data: dict, events: dict) -> str:
    total = data.get("total_jpy", 0)
    comp = data.get("comparisons", {}) or {}

    # 比較カード(前日/先週/先月/年初来)
    labels = [("前日比", "day"), ("先週比", "week"),
              ("先月比", "month"), ("年初来", "ytd")]
    comp_cards = ""
    for label, key in labels:
        c = comp.get(key)
        if c:
            pct_v = c.get("change_pct")
            jpy_v = c.get("change_jpy")
        else:
            pct_v = jpy_v = None
        comp_cards += f"""
        <div class="cmp {cls(pct_v)}">
          <div class="cmp-label">{label}</div>
          <div class="cmp-pct">{signed_pct(pct_v)}</div>
          <div class="cmp-jpy">{signed_yen(jpy_v)}</div>
        </div>"""

    # 保有明細(ETF + 投信)
    def holding_rows(items, is_etf):
        rows = ""
        for v in items:
            change = v.get("change_pct")
            if is_etf:
                price = f"${v['curr_price']:,.2f}"
                sub = f"{v['shares']}株 / 前日 ${v['prev_price']:,.2f}"
            else:
                price = f"{v['curr_nav']:,.0f}円"
                sub = f"{v['units']:,}口"
            rows += f"""
            <div class="hold">
              <div class="hold-main">
                <span class="hold-name">{v['name']}</span>
                <span class="hold-chg {cls(change)}">{signed_pct(change)}</span>
              </div>
              <div class="hold-sub">
                <span>{price} ・ {sub}</span>
                <span class="hold-jpy">{yen(v['curr_jpy'])}</span>
              </div>
            </div>"""
        return rows

    etf_items = list(data.get("etf", {}).values())
    fund_items = list(data.get("fund", {}).values())

    date_str = data.get("date", "")
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        date_disp = f"{d.year}年{d.month}月{d.day}日"
    except Exception:
        date_disp = date_str

    day_pct = (comp.get("day") or {}).get("change_pct")

    return f"""<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Zen+Kaku+Gothic+New:wght@400;500;700;900&family=Roboto+Mono:wght@500;700&display=swap');
* {{ margin:0; padding:0; box-sizing:border-box; }}
:root {{
  --bg:#0d1117; --panel:#161b22; --panel2:#1c2230;
  --line:#2a3242; --txt:#e6edf3; --dim:#8b98a9;
  --up:#3fb950; --down:#f85149; --accent:#58a6ff; --gold:#e3b341;
}}
body {{
  width:1080px; height:1080px; background:
    radial-gradient(900px 500px at 85% -8%, rgba(88,166,255,.10), transparent 60%),
    radial-gradient(700px 500px at -5% 110%, rgba(227,179,65,.08), transparent 55%),
    var(--bg);
  color:var(--txt); font-family:'Zen Kaku Gothic New',sans-serif;
  padding:48px 56px 40px; display:flex; flex-direction:column;
  overflow:hidden;
}}
.mono {{ font-family:'Roboto Mono',monospace; }}
.up {{ color:var(--up); }} .down {{ color:var(--down); }} .flat {{ color:var(--dim); }}

header {{ display:flex; justify-content:space-between; align-items:flex-end;
  border-bottom:2px solid var(--line); padding-bottom:22px; }}
.title {{ font-size:38px; font-weight:900; letter-spacing:.02em; }}
.date {{ font-size:22px; color:var(--dim); margin-top:6px; }}
.acct {{ font-size:20px; color:var(--accent); font-weight:700; }}

.total-wrap {{ margin:24px 0 20px; display:flex; align-items:baseline; gap:26px; }}
.total-label {{ font-size:24px; color:var(--dim); }}
.total {{ font-size:70px; font-weight:900; letter-spacing:-.01em; }}
.total-day {{ font-size:30px; font-weight:700; }}

.cmps {{ display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:22px; }}
.cmp {{ background:var(--panel); border:1px solid var(--line); border-radius:16px;
  padding:16px 14px; text-align:center; }}
.cmp.up {{ border-color:rgba(63,185,80,.35); }}
.cmp.down {{ border-color:rgba(248,81,73,.35); }}
.cmp-label {{ font-size:19px; color:var(--dim); margin-bottom:6px; }}
.cmp-pct {{ font-size:32px; font-weight:900; }}
.cmp-jpy {{ font-size:17px; margin-top:3px; opacity:.85; }}

.cols {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; flex:1; }}
.panel {{ background:var(--panel); border:1px solid var(--line);
  border-radius:18px; padding:20px 20px 12px; }}
.panel-h {{ font-size:21px; font-weight:700; margin-bottom:10px;
  display:flex; align-items:center; gap:10px; }}
.panel-h::before {{ content:''; width:8px; height:22px; border-radius:3px;
  background:var(--accent); }}
.panel.fund .panel-h::before {{ background:var(--gold); }}

.hold {{ padding:9px 0; border-bottom:1px solid var(--line); }}
.hold:last-child {{ border-bottom:none; }}
.hold-main {{ display:flex; justify-content:space-between; align-items:center; }}
.hold-name {{ font-size:20px; font-weight:500; }}
.hold-chg {{ font-size:20px; font-weight:700; }}
.hold-sub {{ display:flex; justify-content:space-between;
  font-size:16px; color:var(--dim); margin-top:2px; }}
.hold-jpy {{ font-weight:700; color:var(--txt); }}

footer {{ margin-top:18px; text-align:center; font-size:15px; color:var(--dim); }}
</style></head><body>
  <header>
    <div>
      <div class="title">{PORTFOLIO_TITLE}</div>
      <div class="date">{date_disp} 終値ベース ・ USD/JPY {data.get('usdjpy','—')}</div>
    </div>
    <div class="acct">@{X_ACCOUNT}</div>
  </header>

  <div class="total-wrap">
    <span class="total-label">総資産</span>
    <span class="total mono">{yen(total)}</span>
    <span class="total-day mono {cls(day_pct)}">{signed_pct(day_pct)}</span>
  </div>

  <div class="cmps">{comp_cards}</div>

  <div class="cols">
    <div class="panel etf">
      <div class="panel-h">米国ETF</div>
      {holding_rows(etf_items, True)}
    </div>
    <div class="panel fund">
      <div class="panel-h">投資信託</div>
      {holding_rows(fund_items, False)}
    </div>
  </div>

  <footer>※本投稿は記録・情報共有目的であり投資助言ではありません</footer>
</body></html>"""


def main():
    data = json.load(open(DATA, encoding="utf-8")) if DATA.exists() else {}
    events = json.load(open(EVENTS, encoding="utf-8")) if EVENTS.exists() else {"events": []}

    html = build_html(data, events)
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
        page.wait_for_timeout(1200)  # フォント読込待ち
        raw = page.screenshot(clip={"x":0,"y":0,"width":1080,"height":1080})
        browser.close()
    Image.open(io.BytesIO(raw)).convert("RGB").resize(
        (1080, 1080), Image.LANCZOS).save(OUT_PNG)
    print(f"🖼️  {OUT_PNG} を生成しました")


if __name__ == "__main__":
    main()
