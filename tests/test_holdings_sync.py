# -*- coding: utf-8 -*-
"""
holdings.json と data.json の整合性テスト。

守りたい失敗は2つある。どちらも「気づかないまま古い数字で投稿する」事故になる。

1. **買い増しが日次生成物に反映されていない**
   holdings.json を編集しても、日次パイプライン(fetch_prices.py)が
   走らないかぎり data.json の口数は古いままになる。とくに
   holdings.json を作業ブランチにだけ置いて main にマージし忘れると、
   GitHub Actions は main を checkout するため**永久に反映されない**。
   data.json 側の口数と突き合わせればこの状態を機械的に検出できる。

2. **銘柄の行が増減する**
   holdings.json のキーと config.py のマスタがズレると、
   知らないうちに集計対象から落ちる／二重に出る。

計算そのもの(按分・寄与)のテストではなく、
「今出ている数字が今の保有と一致しているか」を見るテスト。
"""

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOLDINGS_PATH = REPO_ROOT / "holdings.json"
DATA_PATH = REPO_ROOT / "data.json"

# 円換算は round() の丸めがあるため、1円のズレは許容する。
JPY_TOLERANCE = 2


@pytest.fixture(scope="module")
def holdings():
    return json.loads(HOLDINGS_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def data():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# holdings.json 単体の健全性
# --------------------------------------------------------------------------

def test_holdings_jsonが読める(holdings):
    assert "etf" in holdings and "fund" in holdings


def test_数量は非負の整数(holdings):
    for section in ("etf", "fund"):
        for key, qty in holdings[section].items():
            assert isinstance(qty, int), f"{section}.{key} が整数でない: {qty!r}"
            assert qty >= 0, f"{section}.{key} が負: {qty}"


def test_銘柄がconfigのマスタと一致する(holdings):
    """行の増減・キーのタイポを検出する。

    holdings.json にだけ在る銘柄は集計されず、config.py にだけ在る銘柄は
    数量0で扱われる。どちらも黙って進むので、ここで落とす。
    """
    from config import ETF_HOLDINGS, FUND_HOLDINGS

    assert set(holdings["etf"]) == set(ETF_HOLDINGS), (
        f"ETFの銘柄がconfig.pyと一致しない: "
        f"holdings のみ={set(holdings['etf']) - set(ETF_HOLDINGS)} / "
        f"config のみ={set(ETF_HOLDINGS) - set(holdings['etf'])}"
    )
    assert set(holdings["fund"]) == set(FUND_HOLDINGS), (
        f"投信の銘柄がconfig.pyと一致しない: "
        f"holdings のみ={set(holdings['fund']) - set(FUND_HOLDINGS)} / "
        f"config のみ={set(FUND_HOLDINGS) - set(holdings['fund'])}"
    )


# --------------------------------------------------------------------------
# data.json が「今の保有」を反映しているか
# --------------------------------------------------------------------------

def test_data_jsonの株数がholdingsと一致する(holdings, data):
    ズレ = {
        sym: (v.get("shares"), holdings["etf"].get(sym))
        for sym, v in data["etf"].items()
        if v.get("shares") != holdings["etf"].get(sym)
    }
    assert not ズレ, (
        f"data.json の株数が holdings.json と違う (data, holdings)={ズレ}。"
        " holdings.json を編集したあと日次パイプラインが走っていない可能性がある。"
        " main にマージされているかを確認すること"
        " (Actions は main を checkout する)"
    )


def test_data_jsonの口数がholdingsと一致する(holdings, data):
    ズレ = {
        code: (v.get("units"), holdings["fund"].get(code))
        for code, v in data["fund"].items()
        if v.get("units") != holdings["fund"].get(code)
    }
    assert not ズレ, (
        f"data.json の口数が holdings.json と違う (data, holdings)={ズレ}。"
        " holdings.json を編集したあと日次パイプラインが走っていない可能性がある。"
        " main にマージされているかを確認すること"
        " (Actions は main を checkout する)"
    )


# --------------------------------------------------------------------------
# data.json 内部の検算（口数 × 価格 = 評価額 になっているか）
# --------------------------------------------------------------------------

def test_投信の評価額が口数と基準価額から再現できる(data):
    for code, v in data["fund"].items():
        期待 = round(v["curr_nav"] / 10000 * v["units"])
        assert abs(v["curr_jpy"] - 期待) <= JPY_TOLERANCE, (
            f"{code} の評価額が口数×基準価額と合わない: "
            f"data={v['curr_jpy']:,} / 再計算={期待:,}"
        )


def test_ETFの評価額が株数と株価から再現できる(data):
    usdjpy = data["usdjpy"]
    for sym, v in data["etf"].items():
        期待 = round(v["curr_price"] * usdjpy * v["shares"])
        assert abs(v["curr_jpy"] - 期待) <= JPY_TOLERANCE, (
            f"{sym} の評価額が株数×株価×USDJPYと合わない: "
            f"data={v['curr_jpy']:,} / 再計算={期待:,}"
        )


def test_総資産が各銘柄の合計と一致する(data):
    合計 = sum(v["curr_jpy"] for v in data["etf"].values()) \
        + sum(v["curr_jpy"] for v in data["fund"].values())
    assert data["total_jpy"] == 合計, (
        f"total_jpy={data['total_jpy']:,} だが内訳の合計は {合計:,}"
    )


def test_履歴の最終日が総資産と一致する(data):
    最終 = data["history"][-1]
    assert 最終["date"] == data["date"], (
        f"history の最終日 {最終['date']} が data.date {data['date']} と違う"
    )
    assert 最終["total_jpy"] == data["total_jpy"], (
        f"history の最終日の総資産 {最終['total_jpy']:,} が "
        f"total_jpy {data['total_jpy']:,} と違う"
    )


def test_買い増しは相場変動として計上されない(data):
    """前日比は cash_flow を差し引いた「相場だけの変動」であること。

    買い増した日に前日比が拠出額ぶん跳ねると、投稿する騰落率が嘘になる。
    build_comparisons が拠出を引いているかを、生の増減との関係で検算する。
    """
    day = (data.get("comparisons") or {}).get("day")
    if not day:
        pytest.skip("comparisons.day が無い(履歴が1日分しかない)")
    assert day["change_jpy"] == day["gross_change_jpy"] - day["cash_flow_jpy"], (
        "前日比が拠出を差し引いていない: "
        f"change={day['change_jpy']:,} / gross={day['gross_change_jpy']:,} "
        f"/ cash_flow={day['cash_flow_jpy']:,}"
    )
