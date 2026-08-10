# -*- coding: utf-8 -*-
"""
health.py
=========
各 source に実アクセスして「生きているか」だけを確かめる。

用途は2つ。
  - scripts/verify_live.py … 本番投入前に1回流して全sourceを確認する
  - scripts/source_health.py … 週1で回し、壊れる前に予兆を捕まえる

分解や投稿文の生成はしない。取得とパースと検証までを行い、
件数・応答時間・エラーを記録する。
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from src.common import settings
from src.lookthrough import constituents as C
from src.lookthrough.compute import POLICY_EXCLUDED
from src.lookthrough.validation import validate_constituents

HISTORY_NAME = "source_health_history.json"


@dataclass
class ProbeResult:
    fund_id: str
    fund_name: str
    source_id: str
    kind: str
    priority: int
    ok: bool
    count: int = 0
    elapsed_ms: int = 0
    error: str | None = None
    problems: list[str] = field(default_factory=list)
    url: str = ""
    policy: str = "required"

    @property
    def key(self) -> str:
        return f"{self.fund_id}/{self.source_id}"

    @property
    def status(self) -> str:
        if self.ok:
            return "OK"
        return "NG"

    @property
    def detail(self) -> str:
        if self.ok:
            return f"{self.count}件"
        return self.error or "; ".join(self.problems) or "失敗"


def probe_source(fund_id: str, fund_name: str, spec: dict,
                 src: dict) -> ProbeResult:
    """1つの source を試す。分解はしない。"""
    kind = str(src.get("kind") or "")
    priority = int(src.get("priority", 50))
    started = time.monotonic()
    items, error = (), None
    try:
        items = C._fetch_source(src, kind)
    except Exception as e:  # noqa: BLE001
        error = f"{type(e).__name__}: {e}"
    elapsed = int((time.monotonic() - started) * 1000)

    problems: list[str] = []
    ok = bool(items) and error is None
    if ok:
        vr = validate_constituents(
            items, spec.get("validation") or {},
            previous_tickers=C._previous_tickers(fund_id),
            min_constituents=spec.get("min_constituents"))
        # 銘柄入替による差分はヘルスチェックでは異常としない
        problems = [p for p in vr.problems if "入れ替わって" not in p]
        ok = not problems
    elif error is None:
        error = "0件（取得できないかパースできませんでした）"

    return ProbeResult(
        fund_id=fund_id, fund_name=fund_name, source_id=str(src.get("id")),
        kind=kind, priority=priority, ok=ok, count=len(items),
        elapsed_ms=elapsed, error=error, problems=problems,
        url=str(src.get("url") or src.get("path") or ""),
        policy=str(spec.get("coverage_policy") or "required"))


def probe_all(fund_map: dict, names: dict | None = None,
              include_excluded: bool = False) -> list[ProbeResult]:
    """全ファンドの全sourceを priority 順に試す。"""
    names = names or {}
    out: list[ProbeResult] = []
    for fund_id, spec in (fund_map.get("funds") or {}).items():
        spec = spec or {}
        if spec.get("reuse_from"):
            continue     # 流用なので実アクセスしない
        policy = str(spec.get("coverage_policy") or "required")
        if policy == POLICY_EXCLUDED and not include_excluded:
            continue
        fname = names.get(fund_id) or spec.get("name_hint") or fund_id
        for src in sorted(spec.get("sources") or [],
                          key=lambda s: int(s.get("priority", 50))):
            out.append(probe_source(fund_id, fname, spec, src))
    return out


# --------------------------------------------------------------------------
# レポート
# --------------------------------------------------------------------------

def to_markdown(results: list[ProbeResult], title: str,
                prev: dict | None = None,
                degraded_streaks: dict | None = None) -> str:
    ok_n = sum(1 for r in results if r.ok)
    L = [f"# {title}", "",
         f"実行: {datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M %Z')}",
         f"結果: **{ok_n}/{len(results)} source が成功**", ""]

    # priority 1 が落ちているファンド（＝要修正の予兆）
    first_fail = _first_priority_failures(results)
    if first_fail:
        L += ["## ⚠ priority 1 が失敗しているファンド", "",
              "下位のsourceで拾えていても、いずれ全滅するので直しておくもの。", ""]
        for r in first_fail:
            L.append(f"- **{r.fund_name}** … `{r.source_id}` (p{r.priority}): "
                     f"{r.detail}")
            streak = (degraded_streaks or {}).get(r.key)
            if streak and streak >= int(settings.get(
                    "source_health", "degraded_after_weeks", 2)):
                L.append(f"  - **要対応**: {streak}週連続で失敗しています")
        L.append("")

    L += ["## source 別の結果", "",
          "| ファンド | source | 優先 | 種別 | 結果 | 件数 | 前週差 | 応答 |",
          "|---|---|---:|---|---|---:|---:|---:|"]
    for r in results:
        diff = "—"
        if prev is not None:
            before = prev.get(r.key, {}).get("count")
            if before is not None and r.ok:
                d = r.count - int(before)
                diff = f"{d:+d}" if d else "0"
        L.append(f"| {r.fund_name} | `{r.source_id}` | {r.priority} | {r.kind} "
                 f"| {r.status} | {r.count if r.ok else '—'} | {diff} "
                 f"| {r.elapsed_ms}ms |")
    L.append("")

    failures = [r for r in results if not r.ok]
    if failures:
        L += ["## 失敗の詳細", ""]
        for r in failures:
            L.append(f"### {r.fund_name} / `{r.source_id}` (p{r.priority})")
            if r.url:
                L.append(f"- URL: `{r.url}`")
            if r.error:
                L.append(f"- エラー: {r.error}")
            for p in r.problems:
                L.append(f"- 検証NG: {p}")
            L.append("")

    L += ["## 判断のしかた", "",
          "- ある ファンドの source が **すべて NG** … そのファンドは分解できない。",
          "  `data/manual/` にCSVを置くか、`coverage_policy: excluded` にする。",
          "- priority 1 だけ NG … 動いてはいるが、URLの仕様変更が疑われる。",
          "  `data/fund_map.yml` の `url` / `columns` を直す。",
          "- 全部 OK … `data/fund_map.yml` の `verified: false` を true にしてよい。",
          ""]
    return "\n".join(L)


def _first_priority_failures(results: list[ProbeResult]) -> list[ProbeResult]:
    """各ファンドで最優先の source が失敗しているものを拾う。"""
    by_fund: dict[str, list[ProbeResult]] = {}
    for r in results:
        by_fund.setdefault(r.fund_id, []).append(r)
    out = []
    for rs in by_fund.values():
        first = min(rs, key=lambda r: r.priority)
        if not first.ok:
            out.append(first)
    return out


# --------------------------------------------------------------------------
# 週次履歴（priority 1 の連続失敗を数えるため）
# --------------------------------------------------------------------------

def history_path() -> Path:
    return settings.path_of("reports") / HISTORY_NAME


def load_history() -> dict:
    p = history_path()
    if not p.exists():
        return {"weeks": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"weeks": []}


def save_history(hist: dict, results: list[ProbeResult],
                 week: str, keep: int = 12) -> dict:
    entry = {"week": week, "date": date.today().isoformat(),
             "sources": {r.key: {"ok": r.ok, "count": r.count,
                                 "priority": r.priority,
                                 "elapsed_ms": r.elapsed_ms}
                         for r in results}}
    weeks = [w for w in hist.get("weeks", []) if w.get("week") != week]
    weeks.append(entry)
    weeks = weeks[-keep:]
    hist = {"weeks": weeks}
    p = history_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(hist, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    return hist


def previous_counts(hist: dict, current_week: str) -> dict:
    for w in reversed(hist.get("weeks", [])):
        if w.get("week") != current_week:
            return w.get("sources", {})
    return {}


def degraded_streaks(hist: dict) -> dict[str, int]:
    """priority 1 の source が「直近から何週連続で」失敗しているかを数える。

    最新の週から遡り、成功した週か記録の無い週に当たった時点で打ち切る。
    """
    weeks = hist.get("weeks", [])
    keys = {k for w in weeks
            for k, s in (w.get("sources") or {}).items()
            if int(s.get("priority", 50)) == 1}

    out: dict[str, int] = {}
    for key in keys:
        n = 0
        for w in reversed(weeks):
            s = (w.get("sources") or {}).get(key)
            if s is None or s.get("ok"):
                break
            n += 1
        if n:
            out[key] = n
    return out


def result_dicts(results: list[ProbeResult]) -> list[dict]:
    return [asdict(r) for r in results]
