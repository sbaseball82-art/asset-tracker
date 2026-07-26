# -*- coding: utf-8 -*-
"""
render.py
=========
ASSET LOG デザインの画像レンダラ（make_slide.py のデザインを共通化）。

対応フォーマット:
  - table     : 見出し + 表
  - checklist : 見出し + チェックリスト
  - line      : 見出し + 折れ線グラフ（外部ライブラリ不使用のSVG描画）

出力は 1600x900 PNG（返信欄に添える画像として16:9）。
データが前回キャッシュ由来のときは stale 表記を右下に小さく入れる。
"""

import io
from pathlib import Path

_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Zen+Kaku+Gothic+New:wght@400;500;700;900&family=Roboto+Mono:wght@500;700&display=swap');
* { margin:0; padding:0; box-sizing:border-box; }
:root {
  --bg:#0d1117; --panel:#161b22; --line:#2a3242;
  --txt:#e6edf3; --dim:#8b98a9; --accent:#58a6ff; --gold:#e3b341;
  --up:#3fb950; --down:#f85149;
}
body {
  width:1600px; height:900px; background:
    radial-gradient(1100px 600px at 85% -8%, rgba(88,166,255,.10), transparent 60%),
    radial-gradient(900px 600px at -5% 110%, rgba(227,179,65,.08), transparent 55%),
    var(--bg);
  color:var(--txt); font-family:'Zen Kaku Gothic New',sans-serif;
  padding:52px 64px 40px; display:flex; flex-direction:column; overflow:hidden;
}
.mono { font-family:'Roboto Mono',monospace; }
header { display:flex; justify-content:space-between; align-items:flex-end;
  border-bottom:2px solid var(--line); padding-bottom:20px; }
.title { font-size:42px; font-weight:900; letter-spacing:.02em; }
.sub { font-size:22px; color:var(--dim); margin-top:8px; }
.acct { font-size:22px; color:var(--accent); font-weight:700; }
.content { flex:1; margin-top:28px; overflow:hidden; }
table { width:100%; border-collapse:collapse; }
th { font-size:24px; color:var(--dim); font-weight:700; text-align:left;
  padding:12px 18px; border-bottom:2px solid var(--line); }
td { font-size:26px; padding:13px 18px; border-bottom:1px solid var(--line); }
th.num, td.num { text-align:right; font-family:'Roboto Mono',monospace; }
tr.hl td { color:var(--gold); font-weight:700; }
.check { font-size:28px; padding:14px 8px; border-bottom:1px solid var(--line);
  display:flex; gap:18px; align-items:baseline; }
.check .box { color:var(--accent); font-weight:900; }
.check .date { color:var(--gold); font-family:'Roboto Mono',monospace;
  min-width:130px; }
.check .note { color:var(--dim); font-size:22px; margin-left:auto; }
footer { margin-top:20px; display:flex; justify-content:space-between;
  font-size:17px; color:var(--dim); }
.stale { color:var(--down); opacity:.8; }
"""


def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _table_html(spec: dict) -> str:
    cols = spec["columns"]          # [{label, num?}]
    rows = spec["rows"]             # [{cells:[...], highlight?}]
    th = "".join(
        f'<th class="{"num" if c.get("num") else ""}">{_esc(c["label"])}</th>'
        for c in cols)
    trs = ""
    for r in rows:
        tds = "".join(
            f'<td class="{"num" if cols[i].get("num") else ""}">{_esc(v)}</td>'
            for i, v in enumerate(r["cells"]))
        trs += f'<tr class="{"hl" if r.get("highlight") else ""}">{tds}</tr>'
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def _checklist_html(spec: dict) -> str:
    items = ""
    for it in spec["items"]:        # [{date?, label, note?}]
        date = f'<span class="date">{_esc(it["date"])}</span>' if it.get("date") else ""
        note = f'<span class="note">{_esc(it["note"])}</span>' if it.get("note") else ""
        items += (f'<div class="check"><span class="box">□</span>{date}'
                  f'<span>{_esc(it["label"])}</span>{note}</div>')
    return items


def _line_html(spec: dict) -> str:
    """外部ライブラリなしのSVG折れ線。series: [{label, values:[y...]}], x_labels"""
    series = spec["series"]
    x_labels = spec.get("x_labels", [])
    w, h, pad_l, pad_b, pad_t = 1460, 620, 110, 60, 30
    all_v = [v for s in series for v in s["values"]]
    vmin, vmax = min(all_v), max(all_v)
    if vmax == vmin:
        vmax = vmin + 1
    n = max(len(s["values"]) for s in series)

    def pt(i, v):
        x = pad_l + i * (w - pad_l - 30) / max(n - 1, 1)
        y = pad_t + (h - pad_t - pad_b) * (1 - (v - vmin) / (vmax - vmin))
        return f"{x:.1f},{y:.1f}"

    colors = ["#58a6ff", "#e3b341", "#3fb950", "#f85149"]
    lines, legends = "", ""
    for si, s in enumerate(series):
        c = colors[si % len(colors)]
        pts = " ".join(pt(i, v) for i, v in enumerate(s["values"]))
        lines += f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="4"/>'
        legends += (f'<span style="color:{c};font-size:24px;margin-right:36px;">'
                    f'━ {_esc(s["label"])}</span>')
    # 横軸ラベルとYレンジ
    xl = ""
    for i, lb in enumerate(x_labels):
        x = pad_l + i * (w - pad_l - 30) / max(len(x_labels) - 1, 1)
        xl += (f'<text x="{x:.0f}" y="{h - 18}" fill="#8b98a9" font-size="20"'
               f' text-anchor="middle">{_esc(lb)}</text>')
    ymax_t = f'<text x="{pad_l - 14}" y="{pad_t + 8}" fill="#8b98a9" font-size="20" text-anchor="end">{vmax:,.0f}</text>'
    ymin_t = f'<text x="{pad_l - 14}" y="{h - pad_b}" fill="#8b98a9" font-size="20" text-anchor="end">{vmin:,.0f}</text>'
    grid = (f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{h - pad_b}" stroke="#2a3242" stroke-width="2"/>'
            f'<line x1="{pad_l}" y1="{h - pad_b}" x2="{w - 20}" y2="{h - pad_b}" stroke="#2a3242" stroke-width="2"/>')
    return (f'<div style="margin-bottom:10px;">{legends}</div>'
            f'<svg width="{w}" height="{h}">{grid}{lines}{ymax_t}{ymin_t}{xl}</svg>')


def build_html(title: str, subtitle: str, format_: str, spec: dict,
               account: str = "", note: str = "", stale: bool = False,
               stale_asof: str = "") -> str:
    if format_ == "table":
        body = _table_html(spec)
    elif format_ == "checklist":
        body = _checklist_html(spec)
    elif format_ == "line":
        body = _line_html(spec)
    else:
        raise ValueError(f"未対応フォーマット: {format_}")

    stale_html = (f'<span class="stale">※前回キャッシュのデータ '
                  f'(stale: true / {_esc(stale_asof)})</span>') if stale else "<span></span>"
    return f"""<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">
<style>{_CSS}</style></head><body>
  <header>
    <div>
      <div class="title">{_esc(title)}</div>
      <div class="sub">{_esc(subtitle)}</div>
    </div>
    <div class="acct">{_esc(account)}</div>
  </header>
  <div class="content">{body}</div>
  <footer>
    <span>{_esc(note or "※報道／公表ベースの概算。投資助言ではありません")}</span>
    {stale_html}
  </footer>
</body></html>"""


def render_png(html: str, out_png: Path) -> bool:
    """HTML→PNG。playwright/chromium が無い環境では False を返して続行させる。"""
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    out_html = out_png.with_suffix(".html")
    out_html.write_text(html, encoding="utf-8")
    try:
        from playwright.sync_api import sync_playwright
        from PIL import Image
    except ImportError as e:
        print(f"[warn] 画像レンダリング不可（{e}）。HTMLのみ出力: {out_html}")
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1600, "height": 900},
                                    device_scale_factor=2)
            page.goto(out_html.resolve().as_uri())
            page.wait_for_timeout(1200)  # フォント読込待ち
            raw = page.screenshot(clip={"x": 0, "y": 0, "width": 1600, "height": 900})
            browser.close()
        Image.open(io.BytesIO(raw)).convert("RGB").resize(
            (1600, 900), Image.LANCZOS).save(out_png)
        print(f"🖼️  {out_png}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 画像レンダリング失敗（{e}）。HTMLのみ出力: {out_html}")
        return False
