# -*- coding: utf-8 -*-
"""
compute.py
==========
ルックスルー（保有ファンドを構成銘柄まで分解する）計算の中核。

このモジュールは **純粋関数のみ** で構成する（I/O・ネットワーク禁止）。
理由は、ここが投稿の数値そのものになるため、検算テストで固めたいから。

計算式
------
    実質保有額(銘柄) = Σ_ファンド ( ファンド評価額 × ファンド内での構成比 / 100 )
    実質保有比率(銘柄) = 実質保有額 ÷ 総資産 × 100

「経由の内訳」(Via) がこの機能の主眼。同じ銘柄を高配当ETFとグロース系の
両方から持っている状態を、金額ベースで可視化する。

推測で埋めないための約束
------------------------
- 構成銘柄が取れなかったファンドは ``unresolved`` に積み、按分しない。
- 構成比の合計が100%に満たないファンド（上位N銘柄しか取れない等）は、
  取れた分だけを按分し、残りを ``uncovered_jpy`` として別枠で持つ。
- したがって次の恒等式が常に成り立つ:

      Σ実質保有額 + uncovered_jpy + unresolved合計 = 総資産
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 構成比の合計がこの値を超えたらデータ異常とみなす（%）
MAX_WEIGHT_SUM = 100.5
# 「ほぼ全構成銘柄が取れている」とみなすしきい値（%）
FULL_COVERAGE_MIN = 99.0


def normalize_ticker(ticker: str) -> str:
    """ティッカーの表記ゆれを吸収する。

    運用会社ごとに ``BRK.B`` / ``BRK-B`` / ``BRK/B`` と揺れるため統一する。
    GOOG と GOOGL のような別クラス株は**別銘柄のまま**にする（意図的）。
    """
    t = str(ticker).strip().upper()
    for sep in ("-", "/", " "):
        t = t.replace(sep, ".")
    while ".." in t:
        t = t.replace("..", ".")
    return t.strip(".")


@dataclass(frozen=True)
class Fund:
    """保有しているファンド1本（holdings.yml の1要素に対応）。"""

    id: str
    name: str
    kind: str          # "etf" | "fund"
    value_jpy: float


@dataclass(frozen=True)
class Constituent:
    """ファンド内の構成銘柄1件。"""

    ticker: str
    weight_pct: float
    name: str | None = None
    sector: str | None = None


@dataclass(frozen=True)
class FundConstituents:
    """あるファンドの構成銘柄一式と、その出所（代用したかどうかを含む）。"""

    fund_id: str
    items: tuple[Constituent, ...] = ()
    as_of: str | None = None
    source: str | None = None
    # 連動対象ETFで代用した場合、その代用先シンボル（例 SBI・V・S&P500 → "VOO"）
    proxy_of: str | None = None
    proxy_reason: str | None = None
    stale: bool = False          # 取得失敗でキャッシュを使った
    verify_required: bool = False  # 手動メンテのため要目視確認
    error: str | None = None     # 取得できなかった理由（あれば unresolved 扱い）

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.items)

    @property
    def coverage_pct(self) -> float:
        """構成比の合計(%)。上位N銘柄しか無い場合は100未満になる。"""
        return sum(c.weight_pct for c in self.items)


@dataclass(frozen=True)
class Via:
    """「どのファンド経由で持っているか」1件分。"""

    fund_id: str
    fund_name: str
    amount_jpy: float
    weight_pct: float   # そのファンド内での構成比


@dataclass
class Position:
    """ルックスルー後の1銘柄。"""

    ticker: str
    name: str | None
    amount_jpy: float
    pct_of_total: float
    via: list[Via] = field(default_factory=list)
    sector: str | None = None

    @property
    def fund_count(self) -> int:
        return len(self.via)

    @property
    def is_multi_fund(self) -> bool:
        """2本以上のファンド経由で持っている（＝重複保有）。"""
        return self.fund_count >= 2


@dataclass
class Unresolved:
    """構成銘柄が取れず、分解できなかったファンド。推測で埋めない。"""

    fund_id: str
    fund_name: str
    value_jpy: float
    reason: str


@dataclass
class LookThroughResult:
    total_jpy: float
    positions: list[Position]
    unresolved: list[Unresolved]
    uncovered_jpy: float                 # 構成比が100%に満たない分の残額
    fund_coverage: dict[str, float]      # fund_id -> 構成比合計(%)
    proxies: list[dict]                  # 代用の記録
    stale_funds: list[str]
    verify_funds: list[str]

    @property
    def attributed_jpy(self) -> float:
        return sum(p.amount_jpy for p in self.positions)

    @property
    def unresolved_jpy(self) -> float:
        return sum(u.value_jpy for u in self.unresolved)

    @property
    def coverage_pct(self) -> float:
        """総資産のうち、個別銘柄まで分解できた割合(%)。"""
        if self.total_jpy <= 0:
            return 0.0
        return self.attributed_jpy / self.total_jpy * 100.0


class ReconciliationError(ValueError):
    """按分の合計が総資産と合わない（計算バグかデータ破損）。"""


def look_through(
    funds: list[Fund],
    constituents: dict[str, FundConstituents],
    total_jpy: float,
    tolerance_pct: float = 1.0,
) -> LookThroughResult:
    """保有ファンド一覧を個別銘柄まで分解する。

    Args:
        funds: 保有ファンド一覧。
        constituents: fund_id -> そのファンドの構成銘柄。欠けていれば未分解扱い。
        total_jpy: 総資産（円）。
        tolerance_pct: 突合の許容誤差(%)。既定1%。

    Raises:
        ReconciliationError: 按分合計＋未按分が総資産と合わない場合。
        ValueError: 構成比の合計が100%を明らかに超えるファンドがある場合。
    """
    acc: dict[str, Position] = {}
    unresolved: list[Unresolved] = []
    uncovered_jpy = 0.0
    fund_coverage: dict[str, float] = {}
    proxies: list[dict] = []
    stale_funds: list[str] = []
    verify_funds: list[str] = []

    for fund in funds:
        fc = constituents.get(fund.id)

        if fc is None or not fc.ok:
            reason = (fc.error if fc is not None and fc.error
                      else "構成銘柄データなし")
            unresolved.append(Unresolved(fund.id, fund.name, fund.value_jpy, reason))
            fund_coverage[fund.id] = 0.0
            continue

        cov = fc.coverage_pct
        if cov > MAX_WEIGHT_SUM:
            raise ValueError(
                f"{fund.id} の構成比合計が {cov:.2f}% で100%を超えています。"
                "データ異常のため中断します"
            )
        fund_coverage[fund.id] = cov

        if fc.proxy_of:
            proxies.append({
                "fund_id": fund.id,
                "fund_name": fund.name,
                "proxy_of": fc.proxy_of,
                "reason": fc.proxy_reason or "",
            })
        if fc.stale:
            stale_funds.append(fund.id)
        if fc.verify_required:
            verify_funds.append(fund.id)

        for c in fc.items:
            amount = fund.value_jpy * c.weight_pct / 100.0
            key = normalize_ticker(c.ticker)
            pos = acc.get(key)
            if pos is None:
                pos = Position(ticker=key, name=c.name, amount_jpy=0.0,
                               pct_of_total=0.0, sector=c.sector)
                acc[key] = pos
            pos.amount_jpy += amount
            # 名前・セクターは先に取れた非空の値を優先（欠損を上書きしない）
            if not pos.name and c.name:
                pos.name = c.name
            if not pos.sector and c.sector:
                pos.sector = c.sector
            pos.via.append(Via(fund.id, fund.name, amount, c.weight_pct))

        # 構成比が100%に届かない分は按分せず、別枠で保持する
        uncovered_jpy += fund.value_jpy * max(0.0, 100.0 - cov) / 100.0

    positions = list(acc.values())
    for p in positions:
        p.pct_of_total = (p.amount_jpy / total_jpy * 100.0) if total_jpy else 0.0
        p.via.sort(key=lambda v: -v.amount_jpy)
    positions.sort(key=lambda p: (-p.amount_jpy, p.ticker))

    result = LookThroughResult(
        total_jpy=total_jpy,
        positions=positions,
        unresolved=unresolved,
        uncovered_jpy=uncovered_jpy,
        fund_coverage=fund_coverage,
        proxies=proxies,
        stale_funds=stale_funds,
        verify_funds=verify_funds,
    )

    _reconcile(result, funds, tolerance_pct)
    return result


def _reconcile(result: LookThroughResult, funds: list[Fund],
               tolerance_pct: float) -> None:
    """按分合計＋未カバー＋未分解 が総資産に一致するかを検算する。"""
    total = result.total_jpy
    if total <= 0:
        raise ReconciliationError("総資産が0以下です")

    # まず holdings 側の合計が総資産と整合しているか
    fund_sum = sum(f.value_jpy for f in funds)
    drift = abs(fund_sum - total) / total * 100.0
    if drift > tolerance_pct:
        raise ReconciliationError(
            f"ファンド評価額の合計 {fund_sum:,.0f}円 が総資産 {total:,.0f}円 と "
            f"{drift:.2f}% ずれています（許容 {tolerance_pct}%）"
        )

    accounted = (result.attributed_jpy + result.uncovered_jpy
                 + result.unresolved_jpy)
    diff_pct = abs(accounted - fund_sum) / fund_sum * 100.0
    if diff_pct > tolerance_pct:
        raise ReconciliationError(
            f"按分の突合に失敗: 按分{result.attributed_jpy:,.0f} + "
            f"未カバー{result.uncovered_jpy:,.0f} + 未分解{result.unresolved_jpy:,.0f} "
            f"= {accounted:,.0f}円 が {fund_sum:,.0f}円 と {diff_pct:.2f}% ずれています"
        )


# --------------------------------------------------------------------------
# 集計指標
# --------------------------------------------------------------------------

def top_n(result: LookThroughResult, n: int = 20) -> list[Position]:
    return result.positions[:n]


def top_n_pct(result: LookThroughResult, n: int = 10) -> float:
    """上位n社の実質比率の合計(%)。"""
    return sum(p.pct_of_total for p in result.positions[:n])


def multi_fund_in_top_n(result: LookThroughResult, n: int = 10
                        ) -> tuple[int, float, list[Position]]:
    """上位n社のうち2本以上のファンド経由の銘柄数・合計比率・その一覧。"""
    hits = [p for p in result.positions[:n] if p.is_multi_fund]
    return len(hits), sum(p.pct_of_total for p in hits), hits


def multi_fund_all(result: LookThroughResult) -> tuple[int, float]:
    """全銘柄のうち2本以上のファンド経由の銘柄数と合計比率(%)。"""
    hits = [p for p in result.positions if p.is_multi_fund]
    return len(hits), sum(p.pct_of_total for p in hits)


def sector_breakdown(result: LookThroughResult) -> dict[str, float] | None:
    """セクター別の実質比率(%)。セクター情報が全く無ければ None。

    推測で埋めないため、セクター不明分は "不明" として明示的に残す。
    """
    if not any(p.sector for p in result.positions):
        return None
    out: dict[str, float] = {}
    for p in result.positions:
        key = p.sector or "不明"
        out[key] = out.get(key, 0.0) + p.pct_of_total
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def group_pct(result: LookThroughResult, tickers: list[str]) -> float:
    """指定ティッカー群の実質比率合計(%)（例: AI・大型ハイテク）。"""
    want = {normalize_ticker(t) for t in tickers}
    return sum(p.pct_of_total for p in result.positions if p.ticker in want)


def via_breakdown_text(pos: Position) -> str:
    """「AVGO = VTI経由◯円 + VYM経由◯円」形式の1行を作る（notes.md 用）。"""
    parts = [f"{v.fund_name}経由 {v.amount_jpy:,.0f}円" for v in pos.via]
    return f"{pos.ticker} = " + " + ".join(parts)
