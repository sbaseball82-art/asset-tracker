# -*- coding: utf-8 -*-
"""
公開データのパーサを、保存したレスポンス例（fixture）でオフライン検証する。

実データが取れない環境でもパーサの正しさは担保できるようにするのが目的。
運用会社が形式を変えたら、まず新しいレスポンスをここに保存して
このテストを落としてから直す、という順番で使う。
"""

from pathlib import Path

import pytest

from src.lookthrough.constituents import _parse_csv, _parse_json

FIX = Path(__file__).parent / "fixtures" / "sources"


def read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8-sig")


# --------------------------------------------------------------------------
# Vanguard（JSON）
# --------------------------------------------------------------------------

def test_vanguard_jsonから構成銘柄を抜ける():
    items = _parse_json(read("vanguard_vti.json"))
    by = {c.ticker: c for c in items}

    assert by["NVDA"].weight_pct == pytest.approx(6.50)
    assert by["NVDA"].name == "NVIDIA Corp."
    assert by["NVDA"].sector == "Information Technology"
    assert by["MSFT"].weight_pct == pytest.approx(5.80)
    # 構成比の降順に並ぶ
    assert [c.ticker for c in items][:3] == ["NVDA", "MSFT", "AAPL"]


def test_vanguard_現金行は落とす():
    items = _parse_json(read("vanguard_vti.json"))
    assert "CASH" not in {c.ticker for c in items}


def test_vanguard_別クラス株のドット表記を保つ():
    items = _parse_json(read("vanguard_vti.json"))
    assert "BRK.B" in {c.ticker for c in items}


# --------------------------------------------------------------------------
# iShares（CSV・前置きの説明行あり）
# --------------------------------------------------------------------------

IS_COLS = {"ticker": "Ticker", "weight": "Weight (%)",
           "name": "Name", "sector": "Sector"}


def test_ishares_csvは説明行を読み飛ばす():
    items = _parse_csv(read("ishares_hdv.csv"), IS_COLS, skip_until_header=True)
    by = {c.ticker: c for c in items}

    assert by["XOM"].weight_pct == pytest.approx(8.50)
    assert by["XOM"].sector == "Energy"
    assert by["JNJ"].name == "JOHNSON & JOHNSON"
    assert len(items) == 4          # 現金2行を除いた4銘柄


def test_ishares_現金と貨幣行は落とす():
    items = _parse_csv(read("ishares_hdv.csv"), IS_COLS, skip_until_header=True)
    tickers = {c.ticker for c in items}
    assert "XTSLA" not in tickers        # BlackRockのキャッシュファンド
    assert "USD" not in tickers          # マイナス比率の現金行


def test_ヘッダ行が見つからなければ例外():
    with pytest.raises(ValueError, match="ヘッダ行"):
        _parse_csv("説明1\n説明2\n", IS_COLS, skip_until_header=True)


# --------------------------------------------------------------------------
# Invesco（CSV・ヘッダが1行目・数値に空白とカンマ）
# --------------------------------------------------------------------------

INV_COLS = {"ticker": "Holding Ticker", "weight": "Weight",
            "name": "Name", "sector": "Sector"}


def test_invesco_csvから構成銘柄を抜ける():
    items = _parse_csv(read("invesco_qqq.csv"), INV_COLS, skip_until_header=True)
    by = {c.ticker: c for c in items}

    assert by["NVDA"].weight_pct == pytest.approx(9.10)
    assert by["AAPL"].name == "APPLE INC"
    assert by["AMZN"].sector == "Consumer Discretionary"
    assert len(items) == 4          # 現金行を除く


def test_invesco_数値の空白とカンマを処理する():
    items = _parse_csv(read("invesco_qqq.csv"), INV_COLS, skip_until_header=True)
    assert all(c.weight_pct > 0 for c in items)


# --------------------------------------------------------------------------
# Schwab（CSV・%つきの構成比）
# --------------------------------------------------------------------------

SCHWAB_COLS = {"ticker": "Symbol", "weight": "Weight", "name": "Name"}


def test_schwab_csvはパーセント記号つきでも読める():
    items = _parse_csv(read("schwab_schd.csv"), SCHWAB_COLS,
                       skip_until_header=True)
    by = {c.ticker: c for c in items}

    assert by["ABBV"].weight_pct == pytest.approx(4.30)
    assert by["KO"].weight_pct == pytest.approx(4.00)
    assert "CASH" not in by
    assert len(items) == 4


# --------------------------------------------------------------------------
# 共通の挙動
# --------------------------------------------------------------------------

def test_同一ティッカーの重複行は合算される():
    csv_text = "ticker,weight\nAAPL,3.0\nMSFT,2.0\nAAPL,1.5\n"
    items = _parse_csv(csv_text, {"ticker": "ticker", "weight": "weight"})
    by = {c.ticker: c for c in items}
    assert by["AAPL"].weight_pct == pytest.approx(4.5)
    assert len(items) == 2


def test_構成比が数値でない行は落とす():
    csv_text = "ticker,weight\nAAPL,3.0\nBAD,N/A\nWORSE,\n"
    items = _parse_csv(csv_text, {"ticker": "ticker", "weight": "weight"})
    assert [c.ticker for c in items] == ["AAPL"]


def test_構成比がゼロや負の行は落とす():
    csv_text = "ticker,weight\nAAPL,3.0\nZERO,0\nNEG,-1.2\n"
    items = _parse_csv(csv_text, {"ticker": "ticker", "weight": "weight"})
    assert [c.ticker for c in items] == ["AAPL"]
