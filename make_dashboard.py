"""公開の portfolio.json から統合画像(1920×1080)と単体HTMLを生成する。"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

COLORS = {"stocks": "#dfba70", "etf": "#519afa", "fund": "#51d1d0"}
LABELS = {"stocks": "個別株", "etf": "ETF", "fund": "投資信託"}


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def yen(value, signed=False):
    if not number(value):
        return "未確認"
    return f'{"+" if value >= 0 else "−"}¥{abs(round(value)):,}' if signed else f"¥{round(value):,}"


def percent(value, signed=False):
    if not number(value):
        return "—"
    return f"{value:+.2f}%" if signed else f"{value:.1f}%"


def tone(value):
    return "muted" if not number(value) else "positive" if value >= 0 else "negative"


def date_text(value):
    return escape(str(value)[:10]) if value else "未確認"


def updated(value):
    try:
        return datetime.fromisoformat(value).astimezone(timezone(timedelta(hours=9))).strftime("%Y/%m/%d %H:%M JST")
    except (TypeError, ValueError):
        return "未確認"


def history_chart(history):
    records = sorted([r for r in history if number(r.get("total_jpy"))], key=lambda r: r["date"])
    if len(records) < 2:
        return '<div class="chart-empty"><strong>統合履歴を蓄積中</strong><span>2日目から推移を表示します。<br>追加前の資産履歴とは接続しません。</span></div>'
    values = [r["total_jpy"] for r in records]
    lo, hi = min(values), max(values)
    spread = hi - lo or max(abs(hi)*.02, 1)
    lo, hi = lo-spread*.15, hi+spread*.15
    dates = [datetime.fromisoformat(r["date"]).toordinal() for r in records]
    span = dates[-1]-dates[0] or 1
    points = [(85+(d-dates[0])/span*555, 155-(v-lo)/(hi-lo)*130) for d, v in zip(dates, values)]
    grid = ""
    for i in range(3):
        y, value = 155-i*65, lo+(hi-lo)*i/2
        grid += f'<line x1="85" x2="640" y1="{y}" y2="{y}" stroke="#25374e" stroke-dasharray="3 5"/><text x="74" y="{y+5}" text-anchor="end" fill="#96a7bd" font-size="14">{value/10000:,.0f}万</text>'
    path = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    return f'<svg class="history-chart" viewBox="0 0 660 194" role="img" aria-label="資産評価額の推移。入出金を含み、投資利益ではありません。">{grid}<polygon points="85,155 {path} 640,155" fill="#51d1d022"/><polyline points="{path}" fill="none" stroke="#60d9df" stroke-width="3"/><text x="85" y="187" fill="#96a7bd" font-size="14">{date_text(records[0]["date"])}</text><text x="640" y="187" text-anchor="end" fill="#96a7bd" font-size="14">{date_text(records[-1]["date"])}</text></svg>'


def build_html(data):
    from src.portfolio_analysis import analyze

    items = [(kind, sym, row) for kind in LABELS for sym, row in (data.get(kind) or {}).items()]
    total = data.get("total_jpy")
    incomplete = data.get("complete") is False or not number(total)
    stale = sum(bool(row.get("stale")) for _, _, row in items)
    missing = sum(bool(row.get("missing")) or not number(row.get("curr_jpy")) for _, _, row in items)
    fx = data.get("fx") or {}
    degraded = data.get("status") == "degraded" or stale or fx.get("stale")
    status = "取得不足・要確認" if incomplete else "前回価格を含む・要確認" if degraded else "取得データを反映"
    status_color = "warning" if incomplete or degraded else "positive"
    rate = data.get("usdjpy", fx.get("rate"))
    rate_text = f"{rate:,.2f}" if number(rate) else "未確認"
    total_text = "データ不足" if incomplete else yen(total)
    total_label = "総資産評価額：算出保留" if incomplete else "総資産評価額"
    subtitle = f"確認済みの小計 {yen(data.get('known_total_jpy'))}" if incomplete else "公表価格 × 保有数量 ／ 円換算"
    comparisons = ""
    for label, key in (("前日比", "day"), ("先週比", "week"), ("先月比", "month"), ("年初来", "ytd")):
        comp = (data.get("comparisons") or {}).get(key) or {}
        val = comp.get("change_jpy") if not incomplete else None
        pct = comp.get("change_pct") if not incomplete else None
        base = f"基準 {date_text(comp.get('base_date'))}" if number(val) else "比較可能な履歴が不足"
        comparisons += f'<section class="comparison"><div class="cmp-label">{label}<span>{base}</span></div><div class="cmp-value {tone(val)}">{yen(val, True) if number(val) else "データ蓄積中"}<small>{percent(pct, True)}</small></div></section>'
    rows = ""
    for kind, sym, row in items:
        value = row.get("curr_jpy")
        weight = value/total*100 if number(value) and number(total) and total > 0 and not incomplete else None
        qty = row.get("units") if kind == "fund" else row.get("shares")
        quantity = f'{qty:,}{"口" if kind == "fund" else "株"}' if number(qty) else "数量未設定"
        absent = row.get("missing") or not number(value)
        state = "取得失敗" if absent else "前回価格" if row.get("stale") else ""
        change = row.get("change_pct") if not row.get("stale") and not absent else None
        rows += f'''<tr data-symbol="{escape(sym)}"><td><div class="holding-name"><i style="background:{COLORS[kind]}"></i>{escape(row.get('name', sym))}</div><div class="holding-meta">{escape(sym)}<span>{LABELS[kind]} · {quantity}</span></div></td><td class="num">{yen(value)}</td><td class="num">{percent(weight)}<div class="weight-track"><b style="width:{min(max(weight or 0, 0), 100):.2f}%;background:{COLORS[kind]}"></b></div></td><td class="num {tone(change)}">{percent(change, True)}</td><td class="price-date">{date_text(row.get('curr_date'))}<small class="warning">{state}</small></td></tr>'''
    categories, segments = "", ""
    for kind in LABELS:
        vals = [v.get("curr_jpy") for v in (data.get(kind) or {}).values()]
        amount = sum(vals) if all(number(v) for v in vals) else None
        share = amount/total*100 if number(amount) and number(total) and total > 0 and not incomplete else None
        categories += f'<div class="allocation-item"><span><i style="background:{COLORS[kind]}"></i>{LABELS[kind]}</span><strong>{percent(share)}</strong><small>{yen(amount)}</small></div>'
        if share:
            segments += f'<div style="width:{share:.4f}%;background:{COLORS[kind]}"></div>'
    risk = analyze(data)
    largest = risk.get("largest_holding") or {}
    direct = risk.get("direct_usd_exposure") or {}
    dd = risk.get("max_drawdown") or {}
    us = risk.get("us_market_policy") or {}
    largest_text = f"{escape(str(largest.get('symbol', '')))} · {percent(largest.get('pct'))}" if largest else "データ不足"
    sensitivity = f"{yen(direct.get('per_yen_jpy'), True)} / 1円" if number(direct.get("per_yen_jpy")) else "データ不足"
    drawdown = percent(dd.get("pct"), True) if number(dd.get("pct")) else "データ不足"
    us_text = percent(us.get("known_product_weight_pct"))
    overlap = (risk.get("overlap") or {}).get("note", "構成銘柄データ不足のため、重複率は未算出。")
    cost_notes, detail_rows = [], []
    for sym, row in (data.get("stocks") or {}).items():
        if not number(row.get("purchase_price_usd")):
            cost_notes.append(f"{sym}：取得単価・含み益・損益率は未設定")
        else:
            gain = row.get("unrealized_gain_usd")
            gain_text = f"${gain:+,.2f}" if number(gain) else "未確認"
            cost_notes.append(f"{sym}：USD含み益 {gain_text}（{percent(row.get('unrealized_pct'), True)}）")
        quote = f"${row['curr_price']:,.2f}" if number(row.get("curr_price")) else "未確認"
        previous = f"${row['prev_price']:,.2f}" if number(row.get("prev_price")) else "未確認"
        detail_rows.append(f"{sym}：株価 {quote}、前日終値 {previous}、購入日 {row.get('purchase_date') or '未設定'}。円建て含み益 {yen(row.get('unrealized_jpy'))}（取得時為替も必要）")
    dates = sorted({str(row['curr_date'])[:10] for _, _, row in items if row.get('curr_date')})
    dates_text = f"{dates[0]}〜{dates[-1]}" if dates else "未確認"
    notes = list(data.get("warnings", [])) + list(risk.get("notes", [])) + detail_rows
    notes += [str(dd.get("reason", "")), str(dd.get("method", "")), str(us.get("note", ""))]
    details = "".join(f"<li>{escape(str(note))}</li>" for note in notes if note)
    return f'''<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>私の投資ダッシュボード</title><style>{CSS}</style></head><body><main class="dashboard">
<header><div><div class="eyebrow">PERSONAL PORTFOLIO / ASSET LOG</div><h1>私の投資ダッシュボード</h1></div><div class="update"><span class="status {status_color}"><i></i>{status}</span><div>更新 {updated(data.get('updated_at'))}</div></div></header>
<section class="hero"><div class="total"><div class="section-label">{total_label}<span>JPY</span></div><div class="total-value">{total_text}</div><p>{subtitle}</p></div><div class="hero-meta"><div><span>USD / JPY</span><strong>{rate_text}<small>円</small></strong><p>為替基準日 {date_text(fx.get('curr_date'))}{' · 前回値' if fx.get('stale') else ''}</p></div><div><span>保有銘柄</span><strong>{len(items)}<small>銘柄</small></strong><p>個別株・ETF・投資信託</p></div><div><span>価格の状態</span><strong class="quality {status_color}">{missing} 欠損 <b>/</b> {stale} 前回</strong><p>価格基準日 {escape(dates_text)}</p></div></div></section>
<div class="comparisons">{comparisons}</div>
<div class="content-grid"><section class="panel holdings"><div class="panel-heading"><h2>保有資産の内訳</h2><span>評価額・構成比は円換算</span></div><div class="table-wrap"><table><colgroup><col class="name-col"><col class="value-col"><col class="weight-col"><col class="change-col"><col class="date-col"></colgroup><thead><tr><th>銘柄 / 保有数量</th><th class="num">評価額</th><th class="num">構成比</th><th class="num">価格前日比</th><th class="price-date">価格基準日</th></tr></thead><tbody>{rows}</tbody></table></div><div class="cost-note">{escape(' ／ '.join(cost_notes) or '個別株の取得原価は未設定です。')}</div></section>
<aside class="side"><section class="panel chart-panel"><div class="panel-heading"><h2>資産推移</h2><span>入出金を含む評価額</span></div>{history_chart(data.get('history', []))}</section><section class="panel allocation-panel"><div class="panel-heading"><h2>資産クラスの構成</h2><span>ASSET ALLOCATION</span></div><div class="allocation-bar">{segments}</div><div class="allocation-rows">{categories}</div></section><section class="panel risk-panel"><div class="panel-heading"><h2>リスクの確認</h2><span>保有データからの分析</span></div><div class="risk-metrics"><div><span>最大の保有商品</span><strong>{largest_text}</strong></div><div><span>直接USD資産の為替感応度</span><strong>{sensitivity}</strong></div><div><span>米国市場を主対象とする商品</span><strong>{us_text}</strong></div><div><span>概算最大下落率（記録期間）</span><strong>{drawdown}</strong></div></div><p class="risk-note">{escape(str(overlap))}</p></section></aside></div>
<footer><p>期間比較は数量変化による推定入出金を除いた概算。価格前日比は各商品の現地通貨建て。配当・税・手数料は含みません。</p><p>※公表データからの概算。記録・情報共有目的であり投資助言ではありません。DRAMはシクリカル資産です。</p></footer></main><details class="extra-details"><summary>データの注意点・計算の前提・個別株の詳細</summary><ul>{details}</ul><p>米国商品の比率は商品分類であり、実質的な国別構成比ではありません。為替感応度は直接USD保有のみで、投信内部の為替効果を含みません。</p></details></body></html>'''


CSS = """
*{box-sizing:border-box}html,body{margin:0;background:#07101e;color:#eef3fb}body{font-family:'Noto Sans CJK JP','Noto Sans JP',sans-serif;font-size:16px;font-variant-numeric:tabular-nums}h1,h2,p{margin:0}.dashboard{width:1920px;height:1080px;padding:30px 44px;display:grid;grid-template-rows:64px 118px 92px minmax(0,1fr) 42px;gap:18px;background:radial-gradient(ellipse at 75% -10%,#17325266,transparent 55%),#07101e}header{display:flex;justify-content:space-between;align-items:center}h1{font-size:31px;letter-spacing:.06em}.eyebrow{font-size:11px;color:#dfba70;letter-spacing:.2em;margin-bottom:6px}.update{text-align:right;color:#91a1b7;font-size:14px;line-height:1.8}.status{font-size:14px}.status i{display:inline-block;width:6px;height:6px;border-radius:50%;background:currentColor;margin-right:8px}.hero{display:flex;align-items:center;justify-content:space-between;border-top:1px solid #27374e;border-bottom:1px solid #27374e;padding:12px 0}.section-label{color:#a8b9cd;font-size:15px;letter-spacing:.08em}.section-label span{margin-left:14px;color:#dfba70;font-size:11px}.total-value{font-family:Arial,sans-serif;font-size:57px;font-weight:700;letter-spacing:-1px;line-height:1.05;margin:4px 0}.total p{font-size:12px;color:#8b9cb2}.hero-meta{display:flex;gap:48px}.hero-meta>div{padding-left:30px;border-left:1px solid #25354b}.hero-meta span{display:block;color:#99abc1;font-size:13px}.hero-meta strong{display:block;font-family:Arial,'Noto Sans CJK JP',sans-serif;font-size:32px;font-weight:600;margin:7px 0}.hero-meta small{font-size:15px;font-weight:400;margin-left:8px;color:#a5b7cd}.hero-meta p{font-size:12px;color:#8b9cb2}.hero-meta strong.quality{font-size:23px;line-height:36px}.quality b{font-weight:400;color:#566a84;margin:0 5px}.positive{color:#69ddd0}.negative{color:#f296a2}.warning{color:#dfba70}.muted{color:#92a4bd}.comparisons{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}.comparison{background:linear-gradient(115deg,#122137,#0d182a);border:1px solid #22334b;border-radius:10px;padding:14px 20px}.cmp-label{display:flex;align-items:center;justify-content:space-between;font-size:14px;color:#bccbdf}.cmp-label span{font-size:11px;color:#8b9cb2}.cmp-value{font-family:Arial,'Noto Sans CJK JP',sans-serif;font-weight:600;font-size:29px;display:flex;justify-content:space-between;align-items:baseline;margin-top:7px}.cmp-value small{font-size:21px;font-weight:400}.content-grid{display:grid;grid-template-columns:minmax(0,1.62fr) minmax(0,1fr);gap:18px;min-height:0}.panel{border:1px solid #22334b;border-radius:12px;background:linear-gradient(140deg,#101e32dd,#0b1627ee);min-width:0}.panel-heading{height:53px;padding:0 20px;display:flex;align-items:center;justify-content:space-between;gap:12px}h2{font-size:18px;font-weight:600;letter-spacing:.04em}.panel-heading>span{font-size:11px;color:#8599b2}.holdings{display:flex;flex-direction:column;min-height:0}.table-wrap{padding:0 20px;flex:1}table{width:100%;border-collapse:collapse;table-layout:fixed}.name-col{width:39%}.value-col{width:20%}.weight-col{width:12%}.change-col{width:15%}.date-col{width:14%}th{font-size:12px;font-weight:500;color:#8197b2;text-align:left;height:34px;border-bottom:1px solid #2a3b53}td{height:40px;border-bottom:1px solid #1d2b40;font-size:16px}.num{text-align:right;padding-right:16px;font-family:Arial,'Noto Sans CJK JP',sans-serif}.holding-name{font-size:14px;line-height:20px;white-space:nowrap}.holding-name i,.allocation-item i{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:9px;vertical-align:middle}.holding-meta{font-size:10px;color:#7f94af;line-height:16px;padding-left:15px}.holding-meta span{margin-left:15px}.price-date{text-align:right;font-size:12px;color:#98abc4}.price-date small{font-size:10px;display:block;line-height:13px}.weight-track{width:44px;height:2px;background:#28384f;margin:4px 0 0 auto}.weight-track b{display:block;height:2px}.cost-note{margin:8px 20px 12px;padding:8px 10px;background:#1d2532;border-left:2px solid #dfba70;font-size:11px;color:#d0bea0;line-height:1.6}.side{display:grid;grid-template-rows:234px 156px minmax(0,1fr);gap:14px;min-height:0}.chart-panel .panel-heading{height:43px}.history-chart{display:block;width:100%;height:180px;padding:0 12px}.chart-empty{height:178px;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#90a4be;gap:14px}.chart-empty strong{font-weight:500;font-size:19px}.chart-empty span{font-size:13px;text-align:center;line-height:1.8}.allocation-panel .panel-heading{height:44px}.allocation-bar{display:flex;height:8px;border-radius:4px;overflow:hidden;background:#25354b;margin:0 20px 12px;gap:2px}.allocation-rows{display:flex;padding:0 20px;gap:20px}.allocation-item{flex:1;font-size:12px}.allocation-item>span{display:block;color:#96aac3}.allocation-item strong{display:block;font-family:Arial,sans-serif;font-size:23px;margin:6px 0}.allocation-item small{font-family:Arial,sans-serif;font-size:12px;color:#91a5bf}.risk-panel .panel-heading{height:43px}.risk-metrics{display:grid;grid-template-columns:1fr 1.25fr;gap:5px 16px;padding:0 20px}.risk-metrics span{display:block;font-size:10px;color:#8ca1bc;line-height:1.6}.risk-metrics strong{font-size:17px;line-height:1.8;font-weight:500;color:#e1c48d;white-space:nowrap}.risk-note{font-size:11px;color:#8ca1bc;margin:7px 20px 10px;line-height:1.6}footer{font-size:11px;color:#7c90ab;line-height:1.8;padding-top:4px;border-top:1px solid #22334b}.extra-details{max-width:1832px;margin:16px auto 32px;padding:20px;border:1px solid #22334b;border-radius:8px;color:#9aafca;font-size:14px;line-height:1.8}.extra-details summary{cursor:pointer}.extra-details li{margin-bottom:8px}.extra-details p{margin-top:12px}
@media(max-width:1100px){.dashboard{width:100%;height:auto;min-height:100vh;padding:24px;grid-template-rows:auto;gap:18px}header{align-items:flex-start;gap:16px}h1{font-size:24px}.update{font-size:11px}.eyebrow{font-size:9px}.hero{gap:20px;align-items:flex-start}.total-value{font-size:42px}.hero-meta{gap:20px;flex-wrap:wrap}.hero-meta>div{padding-left:15px}.hero-meta strong{font-size:24px}.hero-meta strong.quality{font-size:18px}.content-grid{grid-template-columns:1fr}.side{grid-template-columns:1fr 1fr;grid-template-rows:auto}.chart-panel{grid-column:1/-1}.risk-panel{min-height:210px}.allocation-panel{min-height:180px}.comparisons{grid-template-columns:repeat(2,1fr)}.table-wrap{padding:0 16px}td{height:46px}.cost-note{margin-top:14px}.extra-details{margin:0 24px 24px}.risk-metrics{grid-template-columns:1fr}.risk-metrics>div{display:flex;justify-content:space-between;align-items:center}.risk-metrics strong{font-size:14px}}
@media(max-width:600px){.dashboard{padding:18px 14px;gap:15px}header{display:block}.update{text-align:left;display:flex;justify-content:space-between;gap:8px;margin-top:10px}.status{font-size:11px}h1{font-size:23px}.hero{display:block;padding:16px 0}.total-value{font-size:44px}.hero-meta{margin-top:20px;display:grid;grid-template-columns:1fr 1fr;gap:14px}.hero-meta>div{padding-left:12px}.hero-meta>div:last-child{grid-column:1/-1;display:grid;grid-template-columns:1fr 1fr;align-items:center}.hero-meta>div:last-child p{grid-column:1/-1}.hero-meta strong.quality{margin:0;font-size:17px}.hero-meta strong{font-size:27px;margin:4px 0}.hero-meta p{font-size:10px}.comparison{padding:12px}.cmp-label{font-size:13px}.cmp-label span{display:none}.cmp-value{font-size:20px;flex-direction:column;gap:4px}.cmp-value small{font-size:16px}.comparisons{gap:10px}.content-grid{gap:15px}.panel-heading{padding:0 14px}.panel-heading>span{font-size:9px}h2{font-size:16px}.table-wrap{padding:0 12px}thead{display:none}table,tbody{display:block;width:100%}tr{display:grid;grid-template-columns:1fr 1fr;gap:4px;padding:11px 0;border-bottom:1px solid #22334b}td{display:block;height:auto;min-height:0;border:none;padding:0!important}.holding-name{font-size:13px;white-space:normal}.holding-meta{font-size:10px;padding-left:15px}.holding-meta span{margin-left:5px}.num{font-size:17px}td:first-child{grid-column:1/-1;margin-bottom:5px}td:nth-child(2){text-align:left}td:nth-child(2):before{content:'評価額 ';color:#8ca1bc;font:10px sans-serif}td:nth-child(3):before{content:'構成比 ';color:#8ca1bc;font:10px sans-serif}.weight-track{display:none}td:nth-child(4){text-align:left;font-size:13px}td:nth-child(4):before{content:'価格前日比 ';color:#8ca1bc;font:10px sans-serif}.price-date{font-size:11px}.price-date small{display:inline;margin-left:5px}.cost-note{margin:12px;font-size:11px}.side{grid-template-columns:1fr;gap:15px}.chart-panel{grid-column:auto;padding-bottom:12px}.allocation-panel{min-height:156px}.risk-panel{min-height:225px}.risk-metrics span{font-size:11px}.risk-metrics strong{font-size:15px}.risk-note{font-size:12px}.history-chart{padding:0;height:auto}footer{font-size:10px;line-height:1.9}.extra-details{margin:0 14px 20px;font-size:12px}}
"""


def render(html, out_dir):
    from playwright.sync_api import sync_playwright
    from src.common.fontcheck import check_texts
    from src.common.render import _launch_chromium

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_html = out_dir / "dashboard.html"
    out_html.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        browser = _launch_chromium(p)
        page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        page.route("http://**/*", lambda route: route.abort())
        page.route("https://**/*", lambda route: route.abort())
        page.set_content(html, wait_until="load")
        page.evaluate("document.fonts.ready")
        ok, missing, _ = check_texts([page.locator(".dashboard").inner_text()])
        if not ok:
            browser.close()
            raise RuntimeError(f"日本語フォントの欠落文字: {missing}")
        bounds = page.evaluate("""() => {
          const root = document.querySelector('.dashboard').getBoundingClientRect();
          return [...document.querySelectorAll('.dashboard *')].filter(el => {
            const b = el.getBoundingClientRect(); return b.width && b.height &&
              (b.left < root.left-1 || b.right > root.right+1 || b.top < root.top-1 || b.bottom > root.bottom+1);
          }).map(el => el.tagName + '.' + el.className);
        }""")
        if bounds:
            browser.close()
            raise RuntimeError(f"ダッシュボードが1920×1080を超えています: {bounds}")
        page.locator(".dashboard").screenshot(path=str(out_dir / "dashboard.png"))
        browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("portfolio.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("slide"))
    parser.add_argument("--html-only", action="store_true")
    args = parser.parse_args()
    html = build_html(json.loads(args.data.read_text(encoding="utf-8")))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.html_only:
        (args.output_dir / "dashboard.html").write_text(html, encoding="utf-8")
    else:
        render(html, args.output_dir)
    print("統合ダッシュボードを生成しました。")


if __name__ == "__main__":
    main()
