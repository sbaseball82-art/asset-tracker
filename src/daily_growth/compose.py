# -*- coding: utf-8 -*-
"""
compose.py
==========
facts.py が出した「事実」から、投稿文と画像用のカード素材を組み立てる。

守る方針（CLAUDE.md と共通。ここでも機械的に検査する）
-------------------------------------------------------
- 数字は **必ず** ``Val`` 経由で入れる。テンプレへ直に数値を書かない。
  ``Val`` に通した値だけが source_values に残り、QAで照合できる。
  （＝AIが「それらしい数字」を書き足せない構造にする）
- 断定・予測・煽りをしない。禁止語は lookthrough と共通のものを再利用する。
- メモリ／DRAM に触れたら「シクリカル」を必ず入れる。
- 末尾に免責。資産投稿と報道ベース投稿で文言を出し分ける。
- 全角換算 165字以内（config.yml の daily_growth.char_limit）。
- 1〜2行目だけで意味が通る（Xのプレビューで切られる前提）。

このモジュールも純粋関数だけにする（I/O・ネットワークを入れない）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.common.textcheck import zenkaku_len
from src.lookthrough.compose import APPROX_TAIL
from src.lookthrough.compose import CYCLICAL_TRIGGERS, CYCLICAL_WORD
from src.lookthrough.compose import DISCLAIMER as DISCLAIMER_ASSET
from src.lookthrough.compose import FORBIDDEN as _BASE_FORBIDDEN

DISCLAIMER_NEWS = "※報道ベースの概算。投資助言ではありません"

# 依頼仕様で明示された煽り表現を、既存の禁止語に足す
FORBIDDEN = list(dict.fromkeys(list(_BASE_FORBIDDEN) + [
    "爆益", "爆損", "暴落", "暴騰", "急騰確定", "ヤバい", "やばい",
    "絶対", "必勝", "今すぐ買", "今すぐ売", "狙い目", "鉄板",
]))

# 画像に入れてはいけない通し番号（01 / 1/5 / ①）
_SERIAL_PATTERNS = (
    re.compile(r"[①-⑳➀-➉]"),
    re.compile(r"(?<![\d.,])\d\s*/\s*5(?![\d.,%])"),
    # ゼロ埋め2桁（01〜09）。日付(2026-08-17)や時刻(08:30)は除く
    re.compile(r"(?<![\d.,/:\-])0[1-9](?![\d.,%/:\-])"),
)


# --------------------------------------------------------------------------
# 数値の入れ物
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Val:
    """投稿に出す数値。raw（元の値）と text（表示文字列）を必ず対にする。

    QA はこの text を「唯一の正」として、本文・画像の数字を照合する。
    """
    raw: float | int | str
    text: str

    def __str__(self) -> str:  # テンプレの {key} で text が入る
        return self.text


def jpy_man(v: float, digits: int = 0) -> Val:
    """円 →「約3,469万円」。1万円未満は「約9,137円」。"""
    if abs(v) < 10_000:
        return Val(v, f"約{v:,.0f}円")
    return Val(v, f"約{v / 10_000:,.{digits}f}万円")


def jpy_signed(v: float, digits: int = 1) -> Val:
    """円の増減 →「+1.5万円」「-6.3万円」。1万円未満は円のまま。"""
    sign = "+" if v >= 0 else "-"
    a = abs(v)
    if a < 10_000:
        return Val(v, f"{sign}{a:,.0f}円")
    return Val(v, f"{sign}{a / 10_000:,.{digits}f}万円")


def oku(v: float) -> Val:
    """円 →「3億円」（マイルストーンの表示用）。"""
    if v >= 100_000_000 and v % 100_000_000 == 0:
        return Val(v, f"{v / 100_000_000:,.0f}億円")
    if v >= 10_000:
        return Val(v, f"{v / 10_000:,.0f}万円")
    return Val(v, f"{v:,.0f}円")


def pct(v: float, digits: int = 2) -> Val:
    """比率そのもの（%）。"""
    return Val(v, f"{v:.{digits}f}%")


def pct_signed(v: float, digits: int = 2) -> Val:
    return Val(v, f"{v:+.{digits}f}%")


def pt_signed(v: float, digits: int = 2) -> Val:
    """差分・寄与は必ず %pt（CLAUDE.md「単位を混同しない」）。"""
    return Val(v, f"{v:+.{digits}f}%pt")


def pt_abs(v: float, digits: int = 2) -> Val:
    return Val(v, f"{v:.{digits}f}%pt")


def num(v: float, unit: str = "", digits: int = 0) -> Val:
    return Val(v, f"{v:,.{digits}f}{unit}")


def as_text(v) -> str:
    return v.text if isinstance(v, Val) else str(v)


# --------------------------------------------------------------------------
# 生成物
# --------------------------------------------------------------------------

@dataclass
class Draft:
    topic_id: str
    category: str
    builder: str
    hook: str
    text: str
    values: dict[str, Val]
    card: dict
    surprise: float = 0.0
    timeliness: float = 0.5
    relevance: float = 1.0
    clarity: float = 0.8
    designs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    literals: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def source_values(self) -> dict:
        return {k: {"raw": v.raw, "text": v.text} for k, v in self.values.items()}


# --------------------------------------------------------------------------
# テンプレ差し込み
# --------------------------------------------------------------------------

def fill(template: str, values: dict) -> str:
    """{key} を values の text で埋める。足りなければ ValueError。"""
    class _M(dict):
        def __missing__(self, k):  # noqa: D105
            raise ValueError(f"テンプレの差し込み値が不足: {{{k}}}")
    return str(template).format_map(_M({k: as_text(v) for k, v in values.items()}))


# --------------------------------------------------------------------------
# 本文の組み立て
# --------------------------------------------------------------------------

def build_text(hook: str, numbers: list[str], view: str, tags: list[str],
               limit: float = 165.0, disclaimer: str = "asset",
               cyclical: bool = False) -> str:
    """「強い冒頭 → 具体的数字 → 自分の観察 → 免責 → タグ」で組む。

    入りきらないときは、数字行を後ろから削り、それでも駄目なら観察を落とす。
    免責とタグは絶対に削らない。
    """
    tail = _tail(tags, disclaimer)
    numbers = [n for n in numbers if n]

    for n_keep in range(len(numbers), 0, -1):
        for with_view in (True, False):
            body = numbers[:n_keep] + ([view] if (with_view and view) else [])
            text = _join(hook, body, tail)
            if cyclical:
                text = ensure_cyclical(text)
            if zenkaku_len(text) <= limit:
                return text
    text = _join(hook, numbers[:1], tail)
    return ensure_cyclical(text) if cyclical else text


def _tail(tags: list[str], disclaimer: str) -> list[str]:
    tags = [t for t in tags if t][:3]
    if disclaimer == "news":
        lines = [DISCLAIMER_NEWS]
    else:
        lines = [APPROX_TAIL, DISCLAIMER_ASSET]
    if tags:
        lines.append(" ".join(tags))
    return lines


def _join(hook: str, body: list[str], tail: list[str]) -> str:
    parts = [hook]
    if body:
        parts += [""] + body
    parts += [""] + tail
    return re.sub(r"\n{3,}", "\n\n", "\n".join(parts)).strip()


def ensure_cyclical(text: str) -> str:
    """メモリ／DRAM に触れているのに「シクリカル」が無ければ補う。"""
    if not any(k in text for k in CYCLICAL_TRIGGERS) or CYCLICAL_WORD in text:
        return text
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if any(k in line for k in CYCLICAL_TRIGGERS):
            lines[i] = line.rstrip("。") + f"。メモリは{CYCLICAL_WORD}な業種だと思っています。"
            break
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 検査
# --------------------------------------------------------------------------

_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_TAG_RE = re.compile(r"#\S+")


def allowed_numbers(values: dict, extra: list[str] | None = None) -> set[str]:
    """source_values の表示文字列から「出てよい数字」の集合を作る。"""
    out: set[str] = set()
    texts = [as_text(v) for v in values.values()] + list(extra or [])
    for t in texts:
        out.update(_NUM_RE.findall(t))
    return out


# 数量を表す単位。この直前の数字は「データの数字」とみなして裏づけを求める
_DATA_UNITS = "%円万億兆倍pt"
_HANDLE_RE = re.compile(r"@\S+")


def unverified_numbers(text: str, values: dict,
                       extra: list[str] | None = None) -> list[str]:
    """文中の数字のうち、source_values に裏付けが無いものを返す。

    ここが空でないということは「どこから来たか説明できない数字」が
    紛れ込んでいるということなので、投稿素材として扱わない。
    （例: テンプレに手書きされた「上位10社で72%」）

    次のものは対象外にする。数え上げの言い回しや識別子であって、
    投稿する金融数値ではないため。
      - 銘柄名・ハンドルに含まれる数字（S&P500 / NASDAQ100 / @xxx）
      - 「1日」「2番目」のような1桁の数え上げ（単位が付かないもの）
    """
    allowed = allowed_numbers(values, extra)
    body = _HANDLE_RE.sub("", _TAG_RE.sub("", text))
    out: list[str] = []
    for m in _NUM_RE.finditer(body):
        tok = m.group(0)
        before = body[m.start() - 1] if m.start() > 0 else ""
        after = body[m.end()] if m.end() < len(body) else ""
        if (before.isascii() and before.isalpha()) or \
                (after.isascii() and after.isalpha() and after not in "pt"):
            continue  # 識別子の一部（NASDAQ100 など）
        if len(tok) == 1 and after not in _DATA_UNITS:
            continue  # 1桁の数え上げ
        if tok in allowed:
            continue
        out.append(tok)
    return out


def string_leaves(obj) -> list[str]:
    """入れ子の dict / list から文字列だけを取り出す。

    図（figure）に入っている数字を「裏づけ済み」として扱うために使う。
    図の数字は必ず上の Val 系フォーマッタが facts から作っているので、
    QAの照合対象は YAML 由来の文言（本文・見出し・注記）に絞れる。
    """
    out: list[str] = []
    if isinstance(obj, dict):
        for v in obj.values():
            out += string_leaves(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out += string_leaves(v)
    elif isinstance(obj, str):
        out.append(obj)
    return out


def serial_markers(texts: list[str]) -> list[str]:
    """画像に入れてはいけない通し番号（01 / 1/5 / ①）を拾う。"""
    hits: list[str] = []
    for t in texts:
        for pat in _SERIAL_PATTERNS:
            hits += pat.findall(str(t))
    return hits


def validate_text(text: str, limit: float = 165.0,
                  disclaimer: str = "asset") -> list[str]:
    """投稿文が方針に反していないかを検査する。違反の一覧（空なら合格）。"""
    problems: list[str] = []

    need = DISCLAIMER_NEWS if disclaimer == "news" else DISCLAIMER_ASSET
    if need not in text:
        problems.append("免責文が入っていません")
    if "概算" not in text:
        problems.append("数値が概算である旨が入っていません")

    for word in FORBIDDEN:
        if word in text:
            problems.append(f"断定・推奨・煽りにあたる表現:「{word}」")

    if any(k in text for k in CYCLICAL_TRIGGERS) and CYCLICAL_WORD not in text:
        problems.append("メモリ／DRAMに触れているのに「シクリカル」がありません")

    tags = _TAG_RE.findall(text)
    if not 2 <= len(tags) <= 3:
        problems.append(f"ハッシュタグは2〜3個にしてください（現在{len(tags)}個）")
    elif tags:
        last = text.strip().split("\n")[-1]
        if not all(t in last for t in tags):
            problems.append("ハッシュタグが本文の途中に入っています")

    lines = [ln for ln in text.split("\n") if ln.strip()]
    if len(lines) < 2:
        problems.append("1行目と2行目で意味が通る構成になっていません")

    n = zenkaku_len(text)
    if n > limit:
        problems.append(f"文字数超過: {n:.1f}/{limit}（全角換算）")
    return problems
