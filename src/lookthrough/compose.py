# -*- coding: utf-8 -*-
"""
compose.py
==========
ルックスルー結果から X の投稿文を組み立てる。

守る方針（アカウント共通・厳守）
------------------------------
- 煽らない／断定しない。一人称の推測形（「〜だと思います」「〜に見えます」）
- 数値には「公表ベースの概算」である旨を添える
- 個別銘柄を推奨しない
- メモリ・DRAM に触れるときは必ず「シクリカル」を添える
- 末尾は必ず「※記録・情報共有目的であり投資助言ではありません」
- 1行目と2行目だけで意味が通る（Xのプレビューで切られる前提）
- 画像が無くてもテキスト単体で成立する
- ハッシュタグは末尾のみ2〜3個

文字数は全角換算（半角=0.5）で数える。src.common.textcheck を使う。
"""

from __future__ import annotations

import re

from src.common.textcheck import zenkaku_len

DISCLAIMER = "※記録・情報共有目的であり投資助言ではありません"
# 概算である旨は「必ず」添える。文字数が厳しい投稿でも落とさないよう、
# 末尾の定型（tail）に入れて必須扱いにしている。
APPROX_TAIL = "※公表データからの概算"
APPROX_NOTE = "数値は各運用会社の公表データをもとにした概算です。"

# 断定・予測・推奨にあたる表現。生成物にこれが出たら不合格にする。
FORBIDDEN = [
    "必ず", "確実に", "間違いなく", "断言", "保証",
    "買い時", "売り時", "買うべき", "売るべき", "仕込み時",
    "おすすめ", "オススメ", "推奨します",
    "上がるでしょう", "下がるでしょう", "上昇するでしょう", "下落するでしょう",
    "底打ち", "天井打ち", "反発局面", "急騰確定", "暴落する",
    "儲かります", "勝てます",
]

# メモリ・DRAM に言及したら必ず添える語
CYCLICAL_TRIGGERS = ("DRAM", "メモリ", "半導体メモリ")
CYCLICAL_WORD = "シクリカル"

HASHTAG_POOL = ["#資産推移", "#米国株", "#ETF", "#インデックス投資"]


def man_yen(jpy: float) -> str:
    """円を「約3,318万円」形式にする（概算であることを表に出す）。"""
    return f"約{jpy / 10000:,.0f}万円"


def pct(v: float, digits: int = 1) -> str:
    return f"{v:.{digits}f}%"


# --------------------------------------------------------------------------
# 本文の組み立て
# --------------------------------------------------------------------------

def build_posts(m: dict, limits=(100, 150, 165)) -> dict[int, str]:
    """文字数上限ごとの投稿文を作る。 {100: "...", 150: "...", ...}"""
    return {lim: _assemble(m, lim) for lim in limits}


def _heads(m: dict) -> list[list[str]]:
    """1〜2行目の候補（長い順）。どれも2行だけで意味が通るようにする。"""
    total = man_yen(m["total_jpy"])
    top10 = pct(m["top10_pct"])
    dup_n = m["multi_fund_count_top10"]
    return [
        [f"{total}を、ETFと投信の中身の個別銘柄まで分解してみました。",
         f"上位10社だけで全体の{top10}、うち{dup_n}社は複数のファンドから重複して持っていました。"],
        [f"{total}を、保有ファンドの中身まで分解してみました。",
         f"上位10社で全体の{top10}、うち{dup_n}社が重複保有でした。"],
        [f"{total}の中身を個別銘柄まで分解しました。",
         f"上位10社で{top10}、うち{dup_n}社が重複保有です。"],
    ]


def _options(m: dict) -> list[str]:
    """追加ブロックを優先度順に返す。入るところまで前から入れる。

    先頭ほど大事。「分けているつもりが実は重なっている」という着地を
    最優先にしている（このアカウントの投稿で一番効く型のため）。
    """
    dup_all_n = m["multi_fund_count_all"]
    dup_all_pct = pct(m["multi_fund_pct_all"])
    fund_n = m["fund_count"]

    blocks = [
        f"{fund_n}本に分けているつもりでしたが、"
        f"中を開けると重なる銘柄が{dup_all_n}社、合わせて{dup_all_pct}ありました。",

        "高配当が下げを和らげる日は多いのですが、"
        "二重に持っている分はその効きが弱くなるように見えます。",
    ]

    if m.get("top1"):
        t = m["top1"]
        blocks.append(f"いちばん多いのは{t['ticker']}で、実質{pct(t['pct'])}。"
                      f"{t['via_text']}という内訳に見えます。")

    if m.get("rank_note"):
        blocks.append(m["rank_note"])

    # 余った枠に入る短い締め（前の行が入らなかったときの受け皿）
    blocks.append("分けているつもりでも、中身は思ったより重なるのだと思います。")
    return blocks


def _tail(m: dict, limit: int) -> list[str]:
    tags = HASHTAG_POOL[:2] if limit <= 100 else HASHTAG_POOL[:3]
    return [APPROX_TAIL, DISCLAIMER, " ".join(tags)]


def _assemble(m: dict, limit: int) -> str:
    """上限に収まる範囲で、中身がいちばん多くなる組み合わせを選ぶ。

    単純に「入る中でいちばん長い見出し」を採ると、見出しだけで枠を使い切って
    本文が1つも入らないことがある。見出しを短くしてでも本文ブロックを入れた
    ほうが投稿として強いので、候補を全部組んでから選ぶ。
    """
    tail = _tail(m, limit)
    options = _options(m)
    best: tuple[tuple, str] | None = None

    for head in _heads(m):
        if zenkaku_len("\n".join(head + [""] + tail)) > limit:
            continue
        body: list[str] = []
        used: list[int] = []
        for i, block in enumerate(options):
            trial = head + [""] + body + [block] + [""] + tail
            if zenkaku_len("\n".join(trial)) <= limit:
                body.append(block)
                used.append(i)
        parts = head + ([""] + body if body else []) + [""] + tail
        text = "\n".join(parts)
        # 本文が多いほど良い → 優先度の高いブロックを使っているほど良い
        # → 同じなら長いほう（見出しが長い＝情報が多い）
        score = (len(body), -sum(used), zenkaku_len(text))
        if best is None or score > best[0]:
            best = (score, text)

    if best is None:
        # どの見出しも入らない場合（上限が極端に小さい）は最小構成
        return _finalize("\n".join(_heads(m)[-1] + [""] + tail))
    return _finalize(best[1])


def _finalize(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return _ensure_cyclical(text)


def _ensure_cyclical(text: str) -> str:
    """メモリ・DRAM に触れているのに「シクリカル」が無ければ補う。"""
    if any(k in text for k in CYCLICAL_TRIGGERS) and CYCLICAL_WORD not in text:
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if any(k in line for k in CYCLICAL_TRIGGERS):
                lines[i] = line.rstrip("。") + f"。メモリは{CYCLICAL_WORD}な業種だと思います。"
                break
        text = "\n".join(lines)
    return text


def build_reply(m: dict, limit: float = 280) -> str:
    """画像を添える2投稿目。画像の読み方と、データの限界を書く。

    データの但し書き（代用・未取得・カバレッジ）は削らず、
    入りきらないときは重複の例示のほうを減らして収める。
    """
    def compose_with(n_examples: int, notes: list[str]) -> str:
        lines = [
            "画像は実質保有の上位20社です。",
            "左端に黄色の線が付いている銘柄が、2本以上のファンドから重ねて持っているものです。",
            "",
        ]
        dup = (m.get("dup_examples") or [])[:n_examples]
        if dup:
            lines.append("たとえば、")
            lines += [f"・{d}" for d in dup]
            lines.append("")
        lines += [n for n in notes if n]
        lines += ["", APPROX_NOTE, DISCLAIMER]
        return _finalize("\n".join(lines))

    all_notes = [m.get("proxy_note"), m.get("manual_note"),
                 m.get("coverage_note")]
    for n in (3, 2, 1, 0):
        text = compose_with(n, all_notes)
        if zenkaku_len(text) <= limit:
            return text
    return compose_with(0, all_notes)


# --------------------------------------------------------------------------
# 検証
# --------------------------------------------------------------------------

def validate_post(text: str, limit: float | None = None,
                  require_hashtags: bool = True) -> list[str]:
    """投稿文が方針に反していないかを検査する。違反の一覧を返す（空なら合格）。

    Args:
        require_hashtags: 2投稿目（reply）はハッシュタグを付けない方針なので False。
            その場合も「本文途中にタグが混ざっていないか」は見る。
    """
    problems: list[str] = []

    if DISCLAIMER not in text:
        problems.append("免責文が入っていません")

    if "概算" not in text:
        problems.append("数値が概算である旨が入っていません")

    for word in FORBIDDEN:
        if word in text:
            problems.append(f"断定・推奨にあたる表現: 「{word}」")

    if any(k in text for k in CYCLICAL_TRIGGERS) and CYCLICAL_WORD not in text:
        problems.append("メモリ／DRAMに触れているのに「シクリカル」がありません")

    tags = re.findall(r"#\S+", text)
    if require_hashtags and not 2 <= len(tags) <= 3:
        problems.append(f"ハッシュタグは2〜3個にしてください（現在{len(tags)}個）")
    elif tags:
        # ハッシュタグは末尾のみ（最後の行にまとまっていること）
        last = text.strip().split("\n")[-1]
        if not all(t in last for t in tags):
            problems.append("ハッシュタグが本文の途中に入っています")

    lines = [ln for ln in text.split("\n") if ln.strip()]
    if len(lines) < 2:
        problems.append("1行目と2行目で意味が通る構成になっていません")

    if limit is not None and zenkaku_len(text) > limit:
        problems.append(
            f"文字数超過: {zenkaku_len(text):.1f}/{limit}（全角換算）")

    return problems
