# -*- coding: utf-8 -*-
"""
validation.py
=============
取得した構成銘柄が「まともなデータか」を検証する。純粋関数のみ・要テスト。

壊れたレスポンス（10銘柄しか返らないVTI、全部0%のCSVなど）を
掴んだまま投稿の数字を作ってしまうのを防ぐのが目的。

FANG+ のように厳しい制約があるものは fund_map.yml の validation: に
ルールを書く。ルールに反したsourceは採用せず、次のpriorityへ進む。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.lookthrough.compute import normalize_ticker


@dataclass
class ValidationResult:
    """検証結果。ok=False なら、そのsourceは採用しない。"""

    ok: bool
    problems: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)     # 前回から増えた銘柄
    removed: list[str] = field(default_factory=list)   # 前回から消えた銘柄

    @property
    def changed(self) -> bool:
        """銘柄の入替が起きたか（四半期リバランス等）。"""
        return bool(self.added or self.removed)

    @property
    def diff_count(self) -> int:
        return max(len(self.added), len(self.removed))

    def diff_text(self) -> str:
        if not self.changed:
            return "入替なし"
        parts = []
        if self.added:
            parts.append(f"追加: {', '.join(self.added)}")
        if self.removed:
            parts.append(f"除外: {', '.join(self.removed)}")
        return " / ".join(parts)


def validate_constituents(items, rules: dict | None,
                          previous_tickers: list[str] | None = None,
                          min_constituents: int | None = None
                          ) -> ValidationResult:
    """構成銘柄を検証する。

    Args:
        items: Constituent の並び。
        rules: fund_map.yml の validation: セクション。None なら件数チェックのみ。
        previous_tickers: 前回採用した銘柄（入替判定に使う）。初回は None。
        min_constituents: 最低件数。これを下回ったら失敗扱い。

    Returns:
        ValidationResult。ok=False なら次のpriorityへ進む。
    """
    problems: list[str] = []
    rules = rules or {}
    n = len(items)

    if n == 0:
        return ValidationResult(ok=False, problems=["構成銘柄が0件"])

    # --- 最低件数（壊れたレスポンスを弾く） ---
    if min_constituents is not None and n < min_constituents:
        problems.append(f"件数が少なすぎます: {n}件（最低 {min_constituents}件）")

    # --- ちょうどN件（FANG+ のような固定銘柄数の指数） ---
    exact = rules.get("exact_count")
    if exact is not None and n != int(exact):
        problems.append(f"銘柄数が{n}件で、想定の{exact}件と違います")

    # --- 構成比の範囲（等ウェイト指数の確認） ---
    wr = rules.get("weight_range")
    if wr:
        lo, hi = float(wr[0]), float(wr[1])
        outliers = [f"{c.ticker} {c.weight_pct:.2f}%"
                    for c in items if not lo <= c.weight_pct <= hi]
        if outliers:
            problems.append(
                f"構成比が{lo}〜{hi}%の範囲外: {', '.join(outliers[:5])}"
                + (f" ほか{len(outliers) - 5}件" if len(outliers) > 5 else ""))

    # --- 構成比の合計が明らかにおかしくないか ---
    total = sum(c.weight_pct for c in items)
    if total <= 0:
        problems.append("構成比の合計が0です")
    elif total > 100.5:
        problems.append(f"構成比の合計が{total:.2f}%で100%を超えています")

    # --- 前回との差分（入替の検出と、入れ替わりすぎの検出） ---
    added: list[str] = []
    removed: list[str] = []
    if previous_tickers:
        now = {normalize_ticker(c.ticker) for c in items}
        prev = {normalize_ticker(t) for t in previous_tickers}
        added = sorted(now - prev)
        removed = sorted(prev - now)
        max_diff = rules.get("max_member_diff")
        if max_diff is not None:
            diff = max(len(added), len(removed))
            if diff > int(max_diff):
                problems.append(
                    f"前回から{diff}銘柄も入れ替わっています"
                    f"（許容 {max_diff}銘柄）: "
                    f"追加 {', '.join(added) or 'なし'} / "
                    f"除外 {', '.join(removed) or 'なし'}")

    return ValidationResult(ok=not problems, problems=problems,
                            added=added, removed=removed)
