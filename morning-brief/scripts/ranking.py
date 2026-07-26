# -*- coding: utf-8 -*-
"""記事スコアリングと同一トピックの重複排除。

score = 0.35 * min(|z|,4)/4
      + 0.25 * min(出来高比,3)/3
      + 0.20 * 媒体一致数（独立媒体数の正規化）
      + 0.10 * SNS熱量（Reddit/HN スコアの正規化）
      + 0.10 * 保有関連度（VTI/S&P500/QQQ 構成比への寄与の近似）
（＋当日が経済カレンダー該当日ならボーナス加点）

重複排除: 見出しの文字バイグラムTF-IDFコサイン類似度（閾値0.6）で
クラスタリングし、同一トピックは代表1件（独立媒体数はクラスタ全体で数える）。
sklearn を使わない軽量実装。
"""
from __future__ import annotations
import math
import re
from collections import Counter


# ── TF-IDF（文字バイグラム）─────────────────────────────
def _bigrams(text: str) -> Counter:
    t = re.sub(r"\s+", "", text.lower())
    return Counter(t[i:i + 2] for i in range(len(t) - 1)) if len(t) > 1 else Counter()


def tfidf_cosine_clusters(titles: list[str], threshold: float) -> list[list[int]]:
    """タイトル群をコサイン類似度 >= threshold でグリーディにクラスタリング。"""
    grams = [_bigrams(t) for t in titles]
    n = len(titles)
    df = Counter()
    for g in grams:
        df.update(g.keys())
    idf = {k: math.log((1 + n) / (1 + v)) + 1 for k, v in df.items()}
    vecs = [{k: c * idf[k] for k, c in g.items()} for g in grams]
    norms = [math.sqrt(sum(v * v for v in vec.values())) or 1.0 for vec in vecs]

    def cos(i: int, j: int) -> float:
        a, b = vecs[i], vecs[j]
        if len(b) < len(a):
            a, b = b, a
        return sum(v * b.get(k, 0.0) for k, v in a.items()) / (norms[i] * norms[j])

    clusters: list[list[int]] = []
    for i in range(n):
        for cl in clusters:
            if cos(i, cl[0]) >= threshold:
                cl.append(i)
                break
        else:
            clusters.append([i])
    return clusters


def independent_outlets(headlines: list[dict], threshold: float) -> tuple[int, list[dict]]:
    """同一トピックを報じた独立媒体数と、代表見出しを返す。

    見出しは既に銘柄（＝トピック）でひも付いているため、媒体数は
    全見出しの独立媒体名で数える（日英の表記差でクラスタが割れても
    過小カウントしない）。代表見出しは最大クラスタから取る。
    """
    if not headlines:
        return 0, []
    outlets = {h["outlet"] for h in headlines if h.get("outlet")}
    clusters = tfidf_cosine_clusters([h["title"] for h in headlines], threshold)
    biggest = max(clusters, key=len)
    reps = [headlines[i] for i in biggest[:3]]
    return max(len(outlets), 1), reps


# ── スコアリング ─────────────────────────────────────────
def score_candidates(candidates: list[dict], buzz: dict, primary: dict,
                     cfg: dict, tag_bonus: dict[str, float] | None = None) -> list[dict]:
    """レイヤ1の異常検知候補にレイヤ3の話題度・保有関連度を合成して採点する。

    tag_bonus: 話題タグ -> 学習ボーナス（learner.topic_bonuses の出力）。
    過去にViewsが伸びた話題タグを優先する（上限は learner 側でクリップ済み）。
    """
    from story_builder import SECTOR
    from themes import tag_for_sector

    w = cfg["scoring"]["weights"]
    thr = cfg["scoring"]["dedup_cosine_threshold"]
    rel = cfg.get("holdings_relevance") or {}
    cal_bonus = cfg["scoring"].get("calendar_bonus", 0.0) if primary.get("calendar") else 0.0
    global_bonus = cfg["scoring"].get("global_bonus", 0.0)
    tag_bonus = tag_bonus or {}

    for c in candidates:
        m = c["metrics"]
        tk = c["ticker"]
        heads = (buzz.get("headlines") or {}).get(tk, [])
        n_media, reps = independent_outlets(heads, thr)
        sns = (buzz.get("sns") or {}).get(tk, 0.0)
        langs = {h.get("lang") for h in heads}
        tag = tag_for_sector(SECTOR.get(tk, "index"))

        parts = {
            "z":        w["z"] * min(abs(m["zscore"]), 4.0) / 4.0,
            "volume":   w["volume"] * (min(m["vol_ratio"], 3.0) / 3.0
                                       if m["vol_ratio"] else 0.0),
            "media":    w["media"] * min(n_media, 6) / 6.0,
            "sns":      w["sns"] * sns,
            "holdings": w["holdings"] * float(rel.get(tk, 0.2)),
            "calendar": cal_bonus,
            # 日英両方の媒体が報じていれば加点（グローバル一致）
            "global":   global_bonus if {"ja", "en"} <= langs else 0.0,
            # 過去にViewsが伸びた話題タグへの学習ボーナス
            "learn":    float(tag_bonus.get(tag, 0.0)),
        }
        c["topic_tag"] = tag
        c["n_media"] = n_media           # 内部スコア用（画像には表示しない）
        c["headlines"] = reps
        c["sns_heat"] = round(sns, 3)
        c["score_parts"] = {k: round(v, 4) for k, v in parts.items()}
        c["score"] = round(sum(parts.values()), 4)

    candidates.sort(key=lambda c: -c["score"])
    return _dedup_same_topic(candidates, thr)


def _dedup_same_topic(candidates: list[dict], thr: float) -> list[dict]:
    """同一トピック（例: SMHと^SOX、NVDAとSMH等の同因連動）を代表1件に束ねる。

    見出しクラスタが同じ、または片方の代表見出しともう片方の代表見出しの
    コサイン類似度が閾値以上なら同一トピックとみなし、スコア上位を残す。
    """
    kept: list[dict] = []
    for c in candidates:
        dup = False
        for k in kept:
            t1 = [h["title"] for h in c.get("headlines", [])]
            t2 = [h["title"] for h in k.get("headlines", [])]
            if t1 and t2:
                cl = tfidf_cosine_clusters([t1[0], t2[0]], thr)
                if len(cl) == 1:
                    dup = True
            # 見出しが無い場合はセクター連動（ETFと構成指数）だけ束ねる
            elif {c["ticker"], k["ticker"]} <= {"SMH", "^SOX"}:
                dup = True
            if dup:
                k.setdefault("merged", []).append(c["ticker"])
                break
        if not dup:
            kept.append(c)
    return kept
