# -*- coding: utf-8 -*-
"""
週次・米国決算カレンダー画像（src/earnings_week）のテスト。

いちばん確かめたいのは「**取れなかった値を埋めていない**」こと。
EPS予想が null の行が 0 や前週の値ではなく「—」になること、
対象0社の週に画像を作らず DATA WAIT で止まることを検査する。
"""

import json
from datetime import date
from pathlib import Path

import pytest

from src.earnings_week import fetch_earnings as fe
from src.earnings_week import main as ew_main
from src.earnings_week import qa, render
from src.earnings_week.render import Company

REPO_ROOT = Path(__file__).resolve().parents[1]
THEME = json.loads((REPO_ROOT / "config" / "theme.json").read_text(encoding="utf-8"))
SAMPLE = json.loads(
    (REPO_ROOT / "tests" / "fixtures" / "earnings_week_sample.json").read_text(
        encoding="utf-8"))


def _sample_companies(n: int) -> list[Company]:
    return [Company(symbol=c["symbol"], name=c["name"], date=c["date"],
                    hour=c["hour"], eps_estimate=c["epsEstimate"],
                    revenue_estimate=c["revenueEstimate"],
                    market_cap=c["marketCapitalization"])
            for c in SAMPLE["companies"][:n]]


# ------------------------------------------------------------ 表記


def test_eps_missing_is_dash_not_zero():
    """取れなかった EPS予想を 0 や平均で埋めない。"""
    assert render.fmt_eps(None) == "—"
    assert render.fmt_eps(0) == "0.00"        # 0 は「0という予想」であって欠損ではない
    assert render.fmt_eps(2.414) == "2.41"
    assert render.fmt_eps(-1.5) == "-1.50"


def test_revenue_formatting():
    assert render.fmt_revenue(None) == "—"
    assert render.fmt_revenue(98_500_000_000) == "98.5B"
    assert render.fmt_revenue(1_234_000_000_000) == "1.23T"
    assert render.fmt_revenue(785_000_000) == "785M"


def test_timing_label_unknown_is_not_guessed():
    """hour が空/未知のとき「引け後」と決めつけない。"""
    assert render.timing_label("bmo", THEME) == "寄付前"
    assert render.timing_label("amc", THEME) == "引け後"
    assert render.timing_label("dmh", THEME) == "場中"
    assert render.timing_label("", THEME) == "時間未定"
    assert render.timing_label(None, THEME) == "時間未定"
    assert render.timing_label("xxx", THEME) == "時間未定"


def test_timing_style_modes():
    """バッジの様式は theme.json から引く（引け後だけ塗り、他は枠線）。"""
    assert render.timing_style("amc", THEME)["mode"] == "solid"
    assert render.timing_style("bmo", THEME)["mode"] == "outline"
    assert render.timing_style("dmh", THEME)["mode"] == "outline"
    assert render.timing_style(None, THEME) == THEME["timing_styles"][""]
    for style in THEME["timing_styles"].values():
        if style["mode"] == "solid":
            assert "text" in style        # 塗りには必ず文字色を持たせる


def test_dark_logo_gets_a_white_pad():
    """暗い透過ロゴは背景に埋もれるので白パッドを敷く（それ以外は敷かない）。"""
    from PIL import Image
    dark = Image.new("RGBA", (40, 40), (10, 10, 12, 255))
    bright = Image.new("RGBA", (40, 40), (240, 120, 60, 255))
    threshold = THEME["logo"]["dark_luminance_threshold"]
    assert render.mean_luminance(dark) < threshold
    assert render.mean_luminance(bright) > threshold
    # 完全な透過は「明るい」扱い（判定対象の画素が無いため落ちないこと）
    assert render.mean_luminance(Image.new("RGBA", (8, 8), (0, 0, 0, 0))) == 255.0


def test_day_heading_and_range():
    assert render.fmt_day_heading(date(2026, 8, 31), THEME) == "8/31 (月)"
    assert render.fmt_range(date(2026, 8, 31), date(2026, 9, 4)) == "2026/08/31 - 09/04"
    assert render.fmt_range(date(2026, 12, 28), date(2027, 1, 1)) == \
        "2026/12/28 - 2027/01/01"
    assert render.output_stem(date(2026, 8, 31)) == "earnings_20260831"
    assert render.output_stem(date(2026, 8, 31)).isascii()


def test_group_by_day_sorts_by_market_cap_within_day():
    comps = _sample_companies(5)
    grouped = render.group_by_day(comps)
    assert [d for d, _ in grouped] == [date(2026, 8, 31), date(2026, 9, 1)]
    assert [c.symbol for c in grouped[1][1]] == ["NVDA", "GOOGL", "AMZN"]


def test_fallback_color_is_deterministic():
    palette = THEME["fallback_palette"]
    first = render.fallback_color("AAPL", palette)
    assert first == render.fallback_color("AAPL", palette)
    assert first in palette


# ------------------------------------------------------------ 配置


@pytest.mark.parametrize("n_cards,n_days", [(1, 1), (3, 2), (6, 3), (8, 4),
                                            (10, 5), (12, 5)])
def test_plan_layout_fits(n_cards, n_days):
    """どの密度でも本文の高さに収まる（12社でも溢れない）。"""
    plan = render.plan_layout(n_cards, n_days, 1080, THEME)
    total = (n_days * (plan.heading_h + plan.heading_gap)
             + (n_days - 1) * plan.section_gap
             + (n_cards - n_days) * plan.card_gap
             + n_cards * plan.card_h)
    assert plan.fits
    assert total <= 1080 + 0.5
    assert plan.ticker_size >= plan.name_size     # ティッカーが最も大きい


def test_plan_layout_uses_taller_rows_when_sparse():
    """少ない週は行を広げる（詰めた見た目のまま余白だけ増やさない）。"""
    dense = render.plan_layout(12, 5, 1080, THEME)
    sparse = render.plan_layout(3, 2, 1080, THEME)
    assert sparse.card_h > dense.card_h
    assert sparse.ticker_size > dense.ticker_size


# ------------------------------------------------------------ 品質検査


def test_missing_glyphs_detects_tofu():
    from src.earnings_week import fonts
    font = fonts.load(30)
    assert qa.missing_glyphs("今週の米国決算 AAPL 引け後 EPS予想 —", font) == []
    assert "�" in qa.missing_glyphs("A�B", font)


def test_overflow_and_overlap_are_detected():
    inside = qa.TextBox("A", (10, 10, 50, 30), (0, 0, 100, 100), "a")
    outside = qa.TextBox("B", (10, 10, 120, 30), (0, 0, 100, 100), "b")
    assert qa.check_overflow([inside]) == []
    assert qa.check_overflow([outside])
    assert qa.check_overlap([inside, qa.TextBox("C", (200, 200, 210, 210),
                                                (0, 0, 300, 300), "c")]) == []
    assert qa.check_overlap([inside, qa.TextBox("C", (20, 15, 60, 25),
                                                (0, 0, 300, 300), "c")])


@pytest.mark.parametrize("n", [1, 2, 5, 8, 12])
def test_render_passes_qa_at_every_density(n):
    """1社でも12社でも、豆腐・はみ出し・重なりなく描けること。"""
    comps = _sample_companies(n)
    start, end = date(2026, 8, 31), date(2026, 9, 4)
    result = render.render_week(comps, start, end, THEME, others=0)
    qa.verify(result.image, result.report,
              (THEME["canvas"]["width"], THEME["canvas"]["height"]))
    assert result.image.size == (1180, 1450)
    assert result.report.companies == n


@pytest.mark.parametrize("symbol", ["QCOM", "JPM", "PYPL", "GOOGL"])
def test_tickers_with_descenders_stay_inside_the_card(symbol):
    """Q や J のように下に伸びる字を含むティッカーでも枠からはみ出さない。

    級数は掲載社数から決まるため、一番詰まった12社の週で検査する。
    （実際にこれで QCOM がはみ出す不具合を見つけた）
    """
    comps = _sample_companies(12)
    comps[0] = Company(symbol=symbol, name="Qualcomm Incorporated Holdings plc",
                       date=comps[0].date, hour="amc", eps_estimate=None,
                       revenue_estimate=57_200_000_000, market_cap=999_999)
    result = render.render_week(comps, date(2026, 8, 31), date(2026, 9, 4), THEME)
    qa.verify(result.image, result.report, (1180, 1450))


def test_rendered_text_shows_dash_for_missing_eps():
    """EPS予想が null の TSM の行に「—」が出ており、数字を作っていない。"""
    comps = [c for c in _sample_companies(12) if c.symbol == "TSM"]
    assert comps[0].eps_estimate is None
    result = render.render_week(comps, date(2026, 8, 31), date(2026, 9, 4), THEME)
    est = [b.text for b in result.report.boxes if b.label.startswith("est:")]
    assert est and "EPS予想 —" in est[0]


def test_sample_render_is_marked_as_sample():
    """ダミーデータの画像が本物の決算日として読まれないよう SAMPLE を出す。"""
    comps = _sample_companies(3)
    plain = render.render_week(comps, date(2026, 8, 31), date(2026, 9, 4), THEME)
    marked = render.render_week(comps, date(2026, 8, 31), date(2026, 9, 4), THEME,
                                sample=True)
    assert THEME["text"]["sample_badge"] not in [b.text for b in plain.report.boxes]
    texts = [b.text for b in marked.report.boxes]
    assert THEME["text"]["sample_badge"] in texts
    assert any(THEME["text"]["sample_note"] in t for t in texts)
    qa.verify(marked.image, marked.report, (1180, 1450))


def test_disclaimer_is_always_drawn():
    result = render.render_week(_sample_companies(3), date(2026, 8, 31),
                                date(2026, 9, 4), THEME)
    texts = [b.text for b in result.report.boxes]
    assert THEME["text"]["disclaimer"] in texts
    assert "投資助言ではありません" in THEME["text"]["disclaimer"]


# ------------------------------------------------------------ 取得


def test_week_bounds_and_next_week():
    assert fe.week_bounds(date(2026, 9, 2)) == (date(2026, 8, 31), date(2026, 9, 4))
    assert fe.next_week_start(date(2026, 8, 30)) == date(2026, 8, 31)   # 日曜→翌月曜
    assert fe.next_week_start(date(2026, 8, 26)) == date(2026, 8, 31)


def test_filter_and_dedupe():
    rows = [
        {"symbol": "AAPL", "date": "2026-09-01", "eps_estimate": None,
         "revenue_estimate": None},
        {"symbol": "AAPL", "date": "2026-09-02", "eps_estimate": 2.4,
         "revenue_estimate": 1.0},
        {"symbol": "ZZZZ", "date": "2026-09-02", "eps_estimate": 1.0,
         "revenue_estimate": None},
    ]
    kept = fe.filter_watchlist(rows, ["AAPL"])
    assert {r["symbol"] for r in kept} == {"AAPL"}
    merged = fe.dedupe(kept)
    assert len(merged) == 1 and merged[0]["eps_estimate"] == 2.4


def test_fetch_calendar_drops_rows_outside_range(monkeypatch):
    payload = {"earningsCalendar": [
        {"symbol": "AAPL", "date": "2026-09-01", "hour": "amc",
         "epsEstimate": 2.41, "revenueEstimate": 9.85e10},
        {"symbol": "OUT", "date": "2026-09-30", "hour": "bmo",
         "epsEstimate": 1.0, "revenueEstimate": None},
        {"symbol": "", "date": "2026-09-01"},
    ]}
    monkeypatch.setattr(fe, "finnhub_get", lambda *a, **k: payload)
    rows = fe.fetch_calendar(date(2026, 8, 31), date(2026, 9, 4), "dummy")
    assert [r["symbol"] for r in rows] == ["AAPL"]
    assert rows[0]["eps_estimate"] == 2.41


def test_missing_api_key_is_an_error(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    with pytest.raises(fe.MissingAPIKey):
        fe.api_key()


def test_empty_week_raises_data_wait(monkeypatch):
    """APIが空を返した週はダミーで作らず DATA WAIT。"""
    monkeypatch.setenv("FINNHUB_API_KEY", "dummy")
    monkeypatch.setattr(fe, "fetch_calendar", lambda *a, **k: [])
    with pytest.raises(ew_main.DataWait):
        ew_main.collect_live(date(2026, 8, 31), THEME, offline=True)


def test_no_watchlist_match_raises_data_wait(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "dummy")
    monkeypatch.setattr(fe, "fetch_calendar", lambda *a, **k: [
        {"symbol": "NOTINLIST", "date": "2026-09-01", "hour": "amc",
         "eps_estimate": None, "revenue_estimate": None}])
    with pytest.raises(ew_main.DataWait):
        ew_main.collect_live(date(2026, 8, 31), THEME, offline=True)


def test_watchlist_file_is_loadable():
    tickers = ew_main.load_watchlist()
    assert 50 <= len(tickers) <= 120
    assert len(set(tickers)) == len(tickers)
    assert all(t == t.upper() for t in tickers)


def test_sample_run_writes_only_to_sample_dir(tmp_path):
    """--sample は本番の出力先に触れない。"""
    code = ew_main.main(["--sample", "--out-dir", str(tmp_path / "out"),
                         "--qa-dir", str(tmp_path / "qa")])
    assert code == ew_main.EXIT_OK
    assert (tmp_path / "out" / "sample" / "earnings_20260831.png").exists()
    assert (tmp_path / "out" / "sample" / "earnings_20260831.jpg").exists()
    thumb = tmp_path / "qa" / "sample" / "earnings_20260831_thumb.png"
    assert thumb.exists()
    from PIL import Image
    with Image.open(thumb) as img:
        assert img.width == THEME["qa"]["thumbnail_width"]
