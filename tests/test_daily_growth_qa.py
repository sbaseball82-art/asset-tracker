# -*- coding: utf-8 -*-
"""
自動QAのテスト。

QAは「生成できたか」ではなく「投稿素材として出してよいか」を見る門なので、
落とすべきものを確実に落とすことをテストで固定する。
"""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from src.daily_growth import compose as C
from src.daily_growth import facts, history as H, qa, render

TODAY = date(2026, 8, 17)
FIXTURE = Path(__file__).parent / "fixtures" / "daily_growth_data.json"
ROTATION = {"topic_reuse_days": 14, "hook_avoid_days": 30,
            "design_max_consecutive_days": 3, "hook_similarity": 0.80,
            "prev_day_similarity": 0.72}


@pytest.fixture(scope="module")
def f() -> dict:
    return facts.build(json.loads(FIXTURE.read_text(encoding="utf-8")), TODAY)


def make_post(tmp_path: Path, index: int = 1, topic_id: str = "dg001",
              design_id: str = "dark_financial_report",
              text: str | None = None, image_texts: list[str] | None = None,
              source_values: dict | None = None, asof: str = "2026-08-17",
              write_image: bool = True, size=(1180, 1450)) -> dict:
    body = text or (
        "総資産約3,469万円。前日比+0.04%でした。\n\n"
        "いちばん効いたのはVTIで+0.12%ptでした。\n\n"
        "※公表データからの概算\n"
        f"{C.DISCLAIMER_ASSET}\n#資産推移 #米国株")
    png = tmp_path / f"post_{index}.png"
    txt = tmp_path / f"post_{index}.txt"
    txt.write_text(body, encoding="utf-8")
    if write_image:
        _write_png(png, size, index)
    return {
        "index": index, "topic_id": topic_id, "category": "daily_move",
        "design_id": design_id, "hook": body.split("\n")[0], "text": body,
        "zenkaku": 100.0, "asof": asof,
        "source_values": source_values if source_values is not None else {
            "total": {"raw": 34689130.0, "text": "約3,469万円"},
            "day_pct": {"raw": 0.04, "text": "+0.04%"},
            "top_pt": {"raw": 0.12, "text": "+0.12%pt"}},
        "literals": [], "figure": {"kind": "bars", "items": []},
        "image": str(png), "text_file": str(txt),
        "image_texts": image_texts if image_texts is not None else [
            "前日比の内訳", "基準日 2026-08-17", "総資産", "約3,469万円"],
        "render_report": {}, "rendered": True, "score": 0.8,
        "score_parts": {},
    }


def _write_png(path: Path, size, seed: int) -> None:
    from PIL import Image
    im = Image.new("RGB", size, (11, 18, 32))
    im.putpixel((0, 0), (seed, seed, seed))   # 画像ごとに中身を変える
    im.save(path)


def run(posts, f, entries=None, designs=None, expected=None, tmp_path=None):
    return qa.run(posts, f, TODAY, entries or [],
                  designs if designs is not None else render.load_designs(),
                  tmp_path or Path("."), expected or len(posts), 165.0, ROTATION)


def five(tmp_path, f) -> list[dict]:
    designs = ["dark_financial_report", "light_editorial", "receipt",
               "versus", "milestone"]
    heads = ["総資産の内訳を並べてみました。", "為替の影響を分けて数えました。",
             "高配当とグロースを比べています。", "反映日のズレを確かめました。",
             "目標までの距離を測りました。"]
    bodies = ["いちばん効いた銘柄を書いています。", "株価と為替に分けた行です。",
              "ふたつのETFを比べた行です。", "基準日の違いを書いた行です。",
              "残りの金額を書いた行です。"]
    return [make_post(tmp_path, i + 1, f"dg{i:03d}", designs[i],
                      text=f"{heads[i]}\n\n{bodies[i]}\n\n※公表データからの概算\n"
                           f"{C.DISCLAIMER_ASSET}\n#資産推移 #米国株",
                      size=render.design_size(render.load_designs()[designs[i]]))
            for i in range(5)]


# --------------------------------------------------------------------------
# 正常系
# --------------------------------------------------------------------------

def test_正しい5本は合格する(tmp_path, f):
    res = run(five(tmp_path, f), f, tmp_path=tmp_path)
    assert res.ok, res.errors


def test_qa_jsonに落とせる形になっている(tmp_path, f):
    d = run(five(tmp_path, f), f, tmp_path=tmp_path).to_dict()
    json.dumps(d, ensure_ascii=False)
    assert set(d) == {"ok", "errors", "warnings", "checks"}


# --------------------------------------------------------------------------
# ファイル
# --------------------------------------------------------------------------

def test_5本そろっていないと落ちる(tmp_path, f):
    posts = five(tmp_path, f)[:4]
    res = run(posts, f, expected=5, tmp_path=tmp_path)
    assert not res.ok
    assert any("5本必要" in e for e in res.errors)


def test_画像が無いと落ちる(tmp_path, f):
    posts = five(tmp_path, f)
    Path(posts[0]["image"]).unlink()
    assert not run(posts, f, tmp_path=tmp_path).ok


def test_同じ画像を使い回すと落ちる(tmp_path, f):
    posts = five(tmp_path, f)
    Path(posts[1]["image"]).write_bytes(Path(posts[0]["image"]).read_bytes())
    res = run(posts, f, tmp_path=tmp_path)
    assert any("同一" in e for e in res.errors)


def test_画像サイズが違うと落ちる(tmp_path, f):
    posts = five(tmp_path, f)
    _write_png(Path(posts[0]["image"]), (800, 800), 9)
    res = run(posts, f, tmp_path=tmp_path)
    assert any("画像サイズ" in e for e in res.errors)


# --------------------------------------------------------------------------
# 本文
# --------------------------------------------------------------------------

def test_165字超過で落ちる(tmp_path, f):
    posts = five(tmp_path, f)
    posts[0]["text"] += "あ" * 200
    res = run(posts, f, tmp_path=tmp_path)
    assert any("文字数超過" in e for e in res.errors)


def test_免責が無いと落ちる(tmp_path, f):
    posts = five(tmp_path, f)
    posts[0]["text"] = posts[0]["text"].replace(C.DISCLAIMER_ASSET, "")
    assert not run(posts, f, tmp_path=tmp_path).ok


def test_禁止語で落ちる(tmp_path, f):
    posts = five(tmp_path, f)
    posts[0]["text"] = posts[0]["text"].replace("いちばん効いた銘柄を書いています。",
                                                "ここは買い時だと思います。")
    res = run(posts, f, tmp_path=tmp_path)
    assert any("買い時" in e for e in res.errors)


def test_DRAMなのにシクリカルが無いと落ちる(tmp_path, f):
    posts = five(tmp_path, f)
    posts[0]["text"] = posts[0]["text"].replace("いちばん効いた銘柄を書いています。",
                                                "DRAMが動いた日でした。")
    res = run(posts, f, tmp_path=tmp_path)
    assert any("シクリカル" in e for e in res.errors)


# --------------------------------------------------------------------------
# 数値の安全性
# --------------------------------------------------------------------------

def test_出どころが無い数字は落ちる(tmp_path, f):
    posts = five(tmp_path, f)
    posts[0]["text"] = posts[0]["text"].replace(
        "いちばん効いた銘柄を書いています。", "上位10社で72%を占めていました。")
    res = run(posts, f, tmp_path=tmp_path)
    assert any("出どころが不明" in e for e in res.errors)


def test_画像に出どころが無い数字があると落ちる(tmp_path, f):
    posts = five(tmp_path, f)
    posts[0]["image_texts"] = posts[0]["image_texts"] + ["配当は年12万円でした"]
    res = run(posts, f, tmp_path=tmp_path)
    assert any("出どころが不明" in e and "画像" in e for e in res.errors)


def test_総資産がdata_jsonと違うと落ちる(tmp_path, f):
    post = make_post(tmp_path, source_values={
        "total": {"raw": 99999999.0, "text": "総資産 約9,999万円"}})
    post["text"] = ("総資産 約9,999万円でした。\n\n記録です。\n\n※公表データからの概算\n"
                    f"{C.DISCLAIMER_ASSET}\n#資産推移 #米国株")
    res = run([post], f, tmp_path=tmp_path)
    assert any("総資産" in e for e in res.errors)


def test_USDJPYがdata_jsonと違うと落ちる(tmp_path, f):
    post = make_post(tmp_path, source_values={
        "usdjpy": {"raw": 100.0, "text": "100.00円"}})
    res = run([post], f, tmp_path=tmp_path)
    assert any("USD/JPY" in e for e in res.errors)


def test_価格要因と為替要因の恒等式が崩れると落ちる(tmp_path, f):
    post = make_post(tmp_path, source_values={
        "price": {"raw": 78559.0, "text": "+7.9万円"},
        "fx": {"raw": -63233.0, "text": "-6.3万円"},
        "total": {"raw": 999999.0, "text": "+100.0万円"}})
    res = run([post], f, tmp_path=tmp_path)
    assert any("一致しません" in e for e in res.errors)


def test_比率の合計が100を超えると落ちる(tmp_path, f):
    post = make_post(tmp_path)
    post["figure"] = {"kind": "bars", "items": [
        {"text": "60.0%"}, {"text": "55.0%"}]}
    res = run([post], f, tmp_path=tmp_path)
    assert any("100%を超え" in e for e in res.errors)


def test_寄与に_ptを使っていないと落ちる(tmp_path, f):
    post = make_post(tmp_path, source_values={
        "top_pt": {"raw": 0.12, "text": "+0.12%"}})
    res = run([post], f, tmp_path=tmp_path)
    assert any("%pt" in e for e in res.errors)


# --------------------------------------------------------------------------
# 画像まわり
# --------------------------------------------------------------------------

def test_通し番号があると落ちる(tmp_path, f):
    posts = five(tmp_path, f)
    posts[0]["image_texts"] = posts[0]["image_texts"] + ["01"]
    res = run(posts, f, tmp_path=tmp_path)
    assert any("通し番号" in e for e in res.errors)


def test_1_5のような表記も落ちる(tmp_path, f):
    posts = five(tmp_path, f)
    posts[0]["image_texts"] = posts[0]["image_texts"] + ["1/5"]
    assert not run(posts, f, tmp_path=tmp_path).ok


def test_基準日がdata_jsonと違うと落ちる(tmp_path, f):
    posts = five(tmp_path, f)
    posts[0]["asof"] = "2026-08-10"
    res = run(posts, f, tmp_path=tmp_path)
    assert any("基準日" in e for e in res.errors)


def test_キャンバスからはみ出すと落ちる(tmp_path, f):
    posts = five(tmp_path, f)
    posts[0]["render_report"] = {"overflow_px": 120}
    res = run(posts, f, tmp_path=tmp_path)
    assert any("はみ出" in e for e in res.errors)


# --------------------------------------------------------------------------
# 重複防止
# --------------------------------------------------------------------------

def test_同じデザインを同日に2枚使うと落ちる(tmp_path, f):
    posts = five(tmp_path, f)
    posts[1]["design_id"] = posts[0]["design_id"]
    res = run(posts, f, tmp_path=tmp_path)
    assert any("同じデザイン" in e for e in res.errors)


def test_デザインの3日連続で落ちる(tmp_path, f):
    posts = five(tmp_path, f)
    entries = [H.make_entry((TODAY - timedelta(days=i)).isoformat(), "dgX",
                            "hook", posts[0]["design_id"], "本文", {}, [])
               for i in (1, 2)]
    res = run(posts, f, entries=entries, tmp_path=tmp_path)
    assert any("連続" in e for e in res.errors)


def test_14日以内の同じ話題で落ちる(tmp_path, f):
    posts = five(tmp_path, f)
    entries = [H.make_entry((TODAY - timedelta(days=3)).isoformat(),
                            posts[0]["topic_id"], "hook", "receipt",
                            "別の本文", {}, [])]
    res = run(posts, f, entries=entries, tmp_path=tmp_path)
    assert any("14日以内" in e for e in res.errors)


def test_前日と似すぎていると落ちる(tmp_path, f):
    posts = five(tmp_path, f)
    entries = [H.make_entry((TODAY - timedelta(days=1)).isoformat(), "dgZ",
                            "hook", "receipt", posts[0]["text"], {}, [])]
    res = run(posts, f, entries=entries, tmp_path=tmp_path)
    assert any("前日" in e for e in res.errors)


def test_同じ日に同じ話題を2本入れると落ちる(tmp_path, f):
    posts = five(tmp_path, f)
    posts[1]["topic_id"] = posts[0]["topic_id"]
    res = run(posts, f, tmp_path=tmp_path)
    assert any("同じ話題" in e for e in res.errors)


# --------------------------------------------------------------------------
# 鮮度（staleデータ）
# --------------------------------------------------------------------------

def test_データが古すぎたら中止(f):
    old = dict(f, age_days=9, data_date="2026-08-08")
    level, msg = facts.staleness(old, 4, 1)
    assert level == "halt" and "古すぎ" in msg


def test_少し古い程度なら警告(f):
    level, _ = facts.staleness(dict(f, age_days=3), 4, 1)
    assert level == "warn"


def test_当日なら正常(f):
    assert facts.staleness(f, 4, 1)[0] == "ok"


def test_未来日付は中止(f):
    assert facts.staleness(dict(f, age_days=-1), 4, 1)[0] == "halt"


def test_データが読めなければ中止():
    assert facts.staleness({}, 4, 1)[0] == "halt"
