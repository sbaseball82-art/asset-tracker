"""統合画像の欠損表示・12銘柄・外部通信なしの表示を確認する。"""
import copy
from pathlib import Path

import pytest
from make_dashboard import build_html, render


@pytest.fixture
def dashboard_data():
    data = {"date": "2026-10-30", "updated_at": "2026-10-30T07:11:00+09:00", "usdjpy": 150.,
            "fx": {"curr_date": "2026-10-29", "rate": 150.}, "complete": True, "status": "ok",
            "stocks": {}, "etf": {}, "fund": {}, "comparisons": {}, "history": []}
    groups = {"stocks": [("FTNT", "Fortinet")],
              "etf": [(s, s+" 米国ETF") for s in ("VTI", "QQQ", "VYM", "HDV", "DRAM")],
              "fund": [(str(i), name) for i, name in enumerate(("ニッセイNASDAQ100", "SBI・V・S&P500", "iFreeNEXT FANG+", "SBI S 米国高配当(年4回)", "イノベーションAI", "SBI NASDAQ100"))]}
    for kind, holdings in groups.items():
        for i, (sym, name) in enumerate(holdings):
            data[kind][sym] = {"name": name, "curr_jpy": 100000+i*120000, "prev_jpy": 99000+i*120000,
                               "change_pct": .37, "curr_date": "2026-10-29", "shares": 7,
                               "units": 10000, "purchase_price_usd": None}
    data["total_jpy"] = sum(row["curr_jpy"] for kind in groups for row in data[kind].values())
    return data


def test_all_twelve_holdings_unset_cost_and_offline_html(dashboard_data):
    html = build_html(dashboard_data)
    assert html.count('data-symbol="') == 12
    assert "取得単価・含み益・損益率は未設定" in html
    assert "データ蓄積中" in html
    assert "2026/10/30 07:11 JST" in html
    assert "https://" not in html and "@import" not in html


def test_missing_quote_not_zero_or_partial_total(dashboard_data):
    data = copy.deepcopy(dashboard_data)
    data.update(total_jpy=None, known_total_jpy=1000000, complete=False)
    data["stocks"]["FTNT"].update(curr_jpy=None, missing=True, curr_date=None)
    html = build_html(data)
    assert "総資産評価額：算出保留" in html
    assert "確認済みの小計 ¥1,000,000" in html
    assert 'data-symbol="FTNT"' in html and "取得失敗" in html
    assert "0.0%" not in html


def test_stale_quote_and_insufficient_history_are_explicit(dashboard_data):
    dashboard_data["stocks"]["FTNT"].update(stale=True, change_pct=12.5)
    html = build_html(dashboard_data)
    assert "前回価格を含む・要確認" in html and "+12.50%" not in html
    assert "統合履歴を蓄積中" in html and "追加前の資産履歴とは接続しません" in html


def test_names_are_escaped(dashboard_data):
    dashboard_data["stocks"]["FTNT"]["name"] = '<script>alert("test")</script>'
    html = build_html(dashboard_data)
    assert '<script>alert("test")</script>' not in html
    assert "&lt;script&gt;" in html


@pytest.mark.skipif(not __import__('os').environ.get('DASHBOARD_RENDER_TESTS'), reason='DASHBOARD_RENDER_TESTS=1でChromiumの描画も検証')
def test_png_size_mobile_layout_and_glyphs(dashboard_data, tmp_path):
    from PIL import Image
    from playwright.sync_api import sync_playwright
    from src.common.render import _launch_chromium
    render(build_html(dashboard_data), tmp_path)
    assert Image.open(tmp_path / 'dashboard.png').size == (1920, 1080)
    with sync_playwright() as p:
        browser = _launch_chromium(p)
        for width in (390, 768):
            page = browser.new_page(viewport={'width': width, 'height': 844})
            page.set_content((tmp_path / 'dashboard.html').read_text(encoding='utf-8'))
            assert page.evaluate('document.documentElement.scrollWidth') <= width
            assert page.locator('tbody tr').count() == 12
            assert page.locator('.holding-name').first.evaluate('e => parseFloat(getComputedStyle(e).fontSize)') >= 13
            page.close()
        browser.close()
