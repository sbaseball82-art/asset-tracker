# -*- coding: utf-8 -*-
"""
投稿文の組み立てと検査のテスト。

守るのは次の点。
  - 全角換算165字以内（src/common/textcheck.py の zenkaku_len を使う）
  - 免責が必ず入る（資産投稿／報道ベースで文言が違う）
  - 禁止語・煽り表現が入らない
  - DRAM・メモリに触れたら「シクリカル」が入る
  - source_values に無い数字が本文に紛れ込まない
"""

import pytest

from src.common.textcheck import zenkaku_len
from src.daily_growth import compose as C

TAGS = ["#資産推移", "#米国株"]


def build(hook="総資産約3,469万円。前日比+0.04%でした。",
          numbers=None, view="数字より内訳を見るほうが意味がある気がしています。",
          **kw) -> str:
    return C.build_text(hook, numbers or ["いちばん効いたのはVTIで+0.12%ptでした。"],
                        view, TAGS, **kw)


# --------------------------------------------------------------------------
# 文字数
# --------------------------------------------------------------------------

def test_165字に収まる():
    assert zenkaku_len(build()) <= 165


def test_長い素材でも165字を超えない():
    numbers = [f"とても長い数字の行その{i}。" * 3 for i in range(4)]
    text = C.build_text("非常に長い書き出しの行です。" * 3, numbers,
                        "非常に長い観察の行です。" * 3, TAGS, limit=165)
    assert zenkaku_len(text) <= 165


def test_上限を変えられる():
    assert zenkaku_len(build(limit=120)) <= 120


def test_zenkaku_lenは半角を05字として数える():
    assert zenkaku_len("あい") == 2.0
    assert zenkaku_len("ab") == 1.0


# --------------------------------------------------------------------------
# 構成
# --------------------------------------------------------------------------

def test_免責とハッシュタグは削られない():
    text = C.build_text("あ" * 150, ["い" * 50], "う" * 50, TAGS, limit=165)
    assert C.DISCLAIMER_ASSET in text
    assert "#資産推移" in text


def test_概算である旨が入る():
    assert "概算" in build()


def test_報道ベースの免責に切り替えられる():
    text = build(disclaimer="news")
    assert C.DISCLAIMER_NEWS in text
    assert C.DISCLAIMER_ASSET not in text


def test_ハッシュタグは末尾のみ():
    text = build()
    assert text.strip().split("\n")[-1].startswith("#")


def test_1行目と2行目で意味が通る():
    lines = [ln for ln in build().split("\n") if ln.strip()]
    assert len(lines) >= 2
    assert "総資産" in lines[0]


# --------------------------------------------------------------------------
# 検査
# --------------------------------------------------------------------------

def test_正しい投稿文は合格する():
    assert C.validate_text(build(), 165) == []


def test_免責が無いと落ちる():
    text = "総資産の話です。\n数字です。\n#資産推移 #米国株"
    assert any("免責" in p for p in C.validate_text(text, 165))


def test_165字超過で落ちる():
    text = build() + "\n" + "あ" * 200
    assert any("文字数超過" in p for p in C.validate_text(text, 165))


@pytest.mark.parametrize("word", ["必ず", "確実に", "買い時", "爆益", "暴落", "おすすめ"])
def test_禁止語で落ちる(word):
    text = build(view=f"これは{word}だと思います。")
    assert any(word in p for p in C.validate_text(text, 165))


def test_ハッシュタグが多すぎると落ちる():
    text = build() + " #タグ4 #タグ5"
    assert any("ハッシュタグ" in p for p in C.validate_text(text, 165))


# --------------------------------------------------------------------------
# シクリカル
# --------------------------------------------------------------------------

def test_DRAMに触れたらシクリカルが補われる():
    text = C.build_text("保有のDRAMメモリ半導体ETFが+0.69%でした。",
                        ["金額では約9,137円です。"], "小さい枠で持っています。",
                        TAGS, cyclical=True)
    assert "シクリカル" in text
    assert C.validate_text(text, 165) == []


def test_シクリカルが無いDRAM投稿は落ちる():
    text = "保有のDRAMが動きました。\n記録です。\n※公表データからの概算\n" \
           f"{C.DISCLAIMER_ASSET}\n#資産推移 #米国株"
    assert any("シクリカル" in p for p in C.validate_text(text, 165))


# --------------------------------------------------------------------------
# 数字の裏づけ
# --------------------------------------------------------------------------

def test_裏づけのある数字は通る():
    values = {"total": C.jpy_man(34689130), "pct": C.pct_signed(0.04)}
    text = "総資産約3,469万円。前日比+0.04%でした。"
    assert C.unverified_numbers(text, values) == []


def test_出どころが無い数字は検出される():
    values = {"total": C.jpy_man(34689130)}
    text = "総資産約3,469万円。上位10社で72%でした。"
    assert "72" in C.unverified_numbers(text, values)


def test_銘柄名の数字は数値とみなさない():
    values = {"total": C.jpy_man(34689130)}
    assert C.unverified_numbers("SBI・V・S&P500とNASDAQ100の話です。", values) == []


def test_1桁の数え上げは数値とみなさない():
    assert C.unverified_numbers("1年前の自分と2番目の銘柄の話です。", {}) == []


def test_ハッシュタグの数字は無視する():
    assert C.unverified_numbers("記録です。\n#資産推移100", {}) == []


# --------------------------------------------------------------------------
# 単位
# --------------------------------------------------------------------------

def test_寄与はptで表す():
    assert C.pt_signed(0.1234).text == "+0.12%pt"
    assert C.pct_signed(0.1234).text == "+0.12%"
    assert C.pt_signed(-0.07).text == "-0.07%pt"


def test_金額の表示():
    assert C.jpy_man(34689130).text == "約3,469万円"
    assert C.jpy_signed(15326).text == "+1.5万円"
    assert C.jpy_signed(-9137).text == "-9,137円"
    assert C.oku(300000000).text == "3億円"


# --------------------------------------------------------------------------
# 通し番号
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["01", "1/5", "①", "投稿 03"])
def test_通し番号を検出する(bad):
    assert C.serial_markers([bad])


@pytest.mark.parametrize("ok", ["2026-08-17", "08:30", "+0.04%", "約3,469万円",
                                "159.40円", "-0.31%"])
def test_通常の表記は通し番号とみなさない(ok):
    assert C.serial_markers([ok]) == []


# --------------------------------------------------------------------------
# テンプレ
# --------------------------------------------------------------------------

def test_差し込み値が足りなければ落ちる():
    with pytest.raises(ValueError):
        C.fill("{total}と{missing}", {"total": C.jpy_man(100000)})


def test_Valはtextで差し込まれる():
    assert C.fill("{total}です", {"total": C.jpy_man(34689130)}) == "約3,469万円です"
