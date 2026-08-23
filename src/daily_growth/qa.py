# -*- coding: utf-8 -*-
"""
qa.py
=====
生成物の自動QA。**ここを通らなかったものは投稿素材として扱わない。**

見るもの
--------
ファイル: 5本ぶん揃っているか / 画像が1投稿1枚で独立しているか / 画像サイズ
数値    : 総資産・USD/JPY が data.json と一致するか、恒等式が成り立つか、
          本文と画像の数字がすべて source_values で裏づけられるか
単位    : 比率は % / 寄与・差分は %pt
文章    : 全角165字 / 免責 / 禁止語 / DRAMならシクリカル / ハッシュタグ
画像    : 豆腐（□）/ キャンバスからのはみ出し / 通し番号（01・1/5・①）
重複    : 前日の5本との類似度 / 同一デザインの連続使用

結果は qa.json に落とす。errors が1件でもあれば ok=false。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from src.common.textcheck import zenkaku_len
from src.daily_growth import compose as C
from src.daily_growth import history as H
from src.daily_growth import render as R

# 恒等式の許容誤差（表示は丸めるので円単位で少しだけ許す）
TOLERANCE_JPY = 1.0
# 比率の合計の許容誤差（%）
TOLERANCE_PCT = 0.6


@dataclass
class Result:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: dict = field(default_factory=dict)

    def error(self, msg: str) -> None:
        self.errors.append(msg)
        self.ok = False

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "errors": self.errors,
                "warnings": self.warnings, "checks": self.checks}


# --------------------------------------------------------------------------
# 個別チェック
# --------------------------------------------------------------------------

def check_files(posts: list[dict], out_dir: Path, expected: int,
                res: Result) -> None:
    if len(posts) != expected:
        res.error(f"投稿候補が{len(posts)}本しかありません（{expected}本必要）")
    digests: dict[str, str] = {}
    for p in posts:
        png, txt = Path(p["image"]), Path(p["text_file"])
        if not txt.exists():
            res.error(f"本文ファイルがありません: {txt.name}")
        if not png.exists():
            res.error(f"画像がありません: {png.name}")
            continue
        digest = hashlib.sha256(png.read_bytes()).hexdigest()
        if digest in digests:
            res.error(f"画像が他の投稿と同一です: {png.name} / {digests[digest]}")
        digests[digest] = png.name
    res.checks["files"] = {"posts": len(posts), "unique_images": len(digests)}


def check_image_size(post: dict, design: dict, res: Result) -> None:
    want = R.design_size(design)
    png = Path(post["image"])
    if not png.exists():
        return
    try:
        from PIL import Image
        with Image.open(png) as im:
            got = im.size
    except Exception as e:  # noqa: BLE001
        res.warn(f"{png.name}: 画像サイズを確認できません（{e}）")
        return
    if got != want:
        res.error(f"{png.name}: 画像サイズが{got}です（{want}のはず）")


def check_text(post: dict, limit: float, res: Result) -> None:
    text = post["text"]
    tid = post["topic_id"]
    for p in C.validate_text(text, limit=limit,
                             disclaimer=post.get("disclaimer", "asset")):
        res.error(f"{tid}: {p}")
    head = [ln for ln in text.split("\n") if ln.strip()][:2]
    if len("".join(head)) < 10:
        res.error(f"{tid}: 1〜2行目だけで意味が通りません")


def check_numbers(post: dict, res: Result) -> None:
    """本文・画像の数字が source_values で裏づけられているかを見る。

    ここが落ちるのは「どこから来たか説明できない数字」が入ったとき。
    金融数値を推測で作らせないための最後の砦。
    """
    values = {k: C.Val(v["raw"], v["text"])
              for k, v in (post.get("source_values") or {}).items()}
    # 図の数字は formatter が facts から作る。基準日は check_date で別に照合する。
    extra = list(post.get("literals") or []) + [str(post.get("asof") or "")]
    bad = C.unverified_numbers(post["text"], values, extra)
    if bad:
        res.error(f'{post["topic_id"]}: 出どころが不明な数字（本文）: {", ".join(bad)}')
    img_text = " ".join(post.get("image_texts") or [])
    bad_img = C.unverified_numbers(img_text, values, extra)
    if bad_img:
        res.error(f'{post["topic_id"]}: 出どころが不明な数字（画像）: '
                  f'{", ".join(sorted(set(bad_img)))}')


def check_units(post: dict, res: Result) -> None:
    """寄与・差分に % を使っていないか（%pt でなければならない）。"""
    for key, v in (post.get("source_values") or {}).items():
        text = v.get("text", "")
        if key.endswith(("_pt", "diff", "_diff")) and "%" in text \
                and "%pt" not in text:
            res.error(f'{post["topic_id"]}: 差分・寄与に%ptを使っていません: '
                      f'{key}={text}')
        if key.endswith("_pct") and "%pt" in text:
            res.error(f'{post["topic_id"]}: 比率に%ptを使っています: {key}={text}')


def check_serial(post: dict, res: Result) -> None:
    hits = C.serial_markers(post.get("image_texts") or [])
    if hits:
        res.error(f'{post["topic_id"]}: 画像に通し番号らしき表記があります: '
                  f'{", ".join(sorted(set(hits)))}')


def check_date(post: dict, data_date: str, res: Result) -> None:
    if post.get("asof") != data_date:
        res.error(f'{post["topic_id"]}: 画像の基準日{post.get("asof")}が'
                  f'data.jsonの{data_date}と違います')
    year = data_date[:4]
    for t in post.get("image_texts") or []:
        for token in str(t).split():
            if len(token) >= 4 and token[:4].isdigit() and token[:4] != year \
                    and "-" in token:
                res.warn(f'{post["topic_id"]}: 画像に別の年の日付があります: {token}')


def check_dram(post: dict, res: Result) -> None:
    text = post["text"] + " " + " ".join(post.get("image_texts") or [])
    if any(k in text for k in C.CYCLICAL_TRIGGERS) and \
            C.CYCLICAL_WORD not in post["text"]:
        res.error(f'{post["topic_id"]}: メモリ／DRAMの話なのに'
                  f'「{C.CYCLICAL_WORD}」がありません')


def check_facts(post: dict, f: dict, res: Result) -> None:
    """総資産・USD/JPY・恒等式が facts と一致しているか。"""
    sv = post.get("source_values") or {}
    if "total" in sv and isinstance(sv["total"].get("raw"), (int, float)):
        raw = float(sv["total"]["raw"])
        # total は「総資産」または「増減額」のどちらかに使われる
        if abs(raw - f["total_jpy"]) > TOLERANCE_JPY and \
                post.get("topic_id", "").startswith("dg0") and \
                "総資産" in sv["total"]["text"]:
            res.error(f'{post["topic_id"]}: 総資産がdata.jsonと一致しません')
    if "usdjpy" in sv and f.get("usdjpy") is not None:
        if abs(float(sv["usdjpy"]["raw"]) - float(f["usdjpy"])) > 0.01:
            res.error(f'{post["topic_id"]}: USD/JPYがdata.jsonと一致しません')
    # 価格要因＋為替要因＝総資産の前日比
    if {"price", "fx", "total"} <= set(sv):
        try:
            price = float(sv["price"]["raw"])
            fx = float(sv["fx"]["raw"])
            total = float(sv["total"]["raw"])
        except (TypeError, ValueError):
            return
        if abs(price + fx - total) > TOLERANCE_JPY:
            res.error(f'{post["topic_id"]}: 価格要因＋為替要因が'
                      f'前日比と一致しません')


def check_figure(post: dict, res: Result) -> None:
    """図の合計・比率の整合。比率の合計が100%を超えたら止める。"""
    fig = post.get("figure") or {}
    if fig.get("kind") == "progress" and not 0.0 <= fig.get("ratio", 0) <= 1.0:
        res.error(f'{post["topic_id"]}: 進捗率が0〜100%の外です')
    if fig.get("kind") == "bars":
        pcts = []
        for it in fig.get("items", []):
            t = str(it.get("text", ""))
            if t.endswith("%") and "%pt" not in t:
                try:
                    pcts.append(float(t.rstrip("%").lstrip("+")))
                except ValueError:
                    pass
        if len(pcts) >= 2 and all(v >= 0 for v in pcts) and \
                sum(pcts) > 100 + TOLERANCE_PCT:
            res.error(f'{post["topic_id"]}: 比率の合計が100%を超えています'
                      f'（{sum(pcts):.1f}%）')


def check_overflow(post: dict, res: Result) -> None:
    ov = (post.get("render_report") or {}).get("overflow_px")
    if ov:
        res.error(f'{post["topic_id"]}: 画像の中身がキャンバスから'
                  f'{ov}pxはみ出しています')


def check_tofu(posts: list[dict], res: Result) -> None:
    texts: list[str] = []
    for p in posts:
        texts += list(p.get("image_texts") or [])
    if not texts:
        return
    try:
        from src.common.fontcheck import check_texts
        ok, missing, font = check_texts(texts)
    except Exception as e:  # noqa: BLE001
        res.warn(f"豆腐チェックを実行できません（{e}）")
        return
    res.checks["font"] = font
    if not ok:
        res.error(f'画像に豆腐（□）になる文字があります: {"".join(missing)}')


def check_rotation(posts: list[dict], today: date, entries: list[dict],
                   rotation: dict, res: Result) -> None:
    prev = H.previous_day_texts(today, entries)
    limit = float(rotation.get("prev_day_similarity", 0.72))
    for p in posts:
        sim = H.max_similarity(p["text"], prev)
        if sim >= limit:
            res.error(f'{p["topic_id"]}: 前日の投稿と似すぎています'
                      f'（類似度{sim:.2f}）')
    texts = [p["text"] for p in posts]
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            sim = H.similarity(texts[i], texts[j])
            if sim >= limit:
                res.error(f'{posts[i]["topic_id"]}と{posts[j]["topic_id"]}が'
                          f'似すぎています（類似度{sim:.2f}）')

    designs = [p["design_id"] for p in posts]
    if len(set(designs)) != len(designs):
        res.error("同じ日に同じデザインを重複して使っています")
    max_days = int(rotation.get("design_max_consecutive_days", 3))
    for d in set(designs):
        if H.design_blocked(d, today, entries, max_days):
            res.error(f"デザイン{d}が{max_days}日連続になります")

    topics = [p["topic_id"] for p in posts]
    if len(set(topics)) != len(topics):
        res.error("同じ日に同じ話題を重複して使っています")
    reuse = int(rotation.get("topic_reuse_days", 14))
    for t in topics:
        if H.topic_blocked(t, today, entries, reuse):
            res.error(f"話題{t}を{reuse}日以内に使っています")


# --------------------------------------------------------------------------
# まとめ
# --------------------------------------------------------------------------

def run(posts: list[dict], f: dict, today: date, entries: list[dict],
        designs: dict[str, dict], out_dir: Path, expected: int,
        char_limit: float, rotation: dict) -> Result:
    res = Result()
    res.checks["date"] = f.get("data_date")
    res.checks["total_jpy"] = f.get("total_jpy")
    res.checks["usdjpy"] = f.get("usdjpy")
    res.checks["char_limit"] = char_limit

    check_files(posts, out_dir, expected, res)
    for p in posts:
        design = designs.get(p["design_id"], {})
        check_image_size(p, design, res)
        check_text(p, char_limit, res)
        check_numbers(p, res)
        check_units(p, res)
        check_serial(p, res)
        check_date(p, str(f.get("data_date")), res)
        check_dram(p, res)
        check_facts(p, f, res)
        check_figure(p, res)
        check_overflow(p, res)
    check_tofu(posts, res)
    check_rotation(posts, today, entries, rotation, res)

    res.checks["posts"] = [
        {"topic_id": p["topic_id"], "design_id": p["design_id"],
         "zenkaku": round(zenkaku_len(p["text"]), 1),
         "image": Path(p["image"]).name} for p in posts]
    return res
