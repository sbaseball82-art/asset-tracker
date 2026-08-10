# -*- coding: utf-8 -*-
"""
constituents.py
===============
各ファンドの構成銘柄（ティッカーと構成比）を集める層。

多段フォールバック
------------------
``data/fund_map.yml`` の ``sources`` を priority の小さい順に試し、
最初に成功したものを採用する。どの source で取れたかは必ず記録し、
``data.json`` と ``notes.md`` の両方に残す。

各段で「成功」と認めるには次を満たす必要がある。
  - パースできて1件以上取れている
  - ``min_constituents`` 以上ある（10銘柄しか返らないVTIを掴まないため）
  - ``validation`` のルールを通る（FANG+ の等ウェイト検証など）

全滅したらキャッシュを使い ``stale: true`` と経過日数を記録する。
キャッシュも古すぎる／無い場合は、そのファンドを未分解にする。
**取れなかった値を推測で埋めることはしない。**

coverage_policy
---------------
``excluded`` のファンドは最初から取得を試みず、「対象外」として返す。
「取れなかった」ではなく「取らないと決めた」ものなので警告にも出さない。
"""

from __future__ import annotations

import csv
import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from src.common import settings
from src.common.util import REPO_ROOT, load_yaml, now_jst, retry
from src.lookthrough.compute import (
    POLICY_EXCLUDED, POLICY_REQUIRED, Constituent, FundConstituents,
    SourceAttempt,
)
from src.lookthrough.validation import validate_constituents

_UA = "Mozilla/5.0 (compatible; asset-tracker/1.0)"

# 現金・先物・未分類など、個別銘柄として扱わない行を落とすためのパターン
_NON_EQUITY = re.compile(
    r"^(CASH|USD|JPY|-|--|N/A|NA|XTSLA|MCASH|CASH_USD|BLK|FUTURE.*)$", re.I)


def fund_map_path() -> Path:
    return settings.path_of("fund_map")


def cache_dir() -> Path:
    return settings.path_of("cache")


def load_fund_map() -> dict:
    m = load_yaml(fund_map_path(), default=None)
    if not m or "funds" not in m:
        raise FileNotFoundError(f"ファンド定義がありません: {fund_map_path()}")
    return m


# --------------------------------------------------------------------------
# 収集
# --------------------------------------------------------------------------

def collect(fund_ids: list[str], offline: bool = False,
            fund_map: dict | None = None) -> dict[str, FundConstituents]:
    """指定ファンドの構成銘柄をまとめて取得する。

    Args:
        fund_ids: holdings.yml に載っている fund.id のリスト。
        offline: True なら取得を試みずキャッシュのみ使う。
    """
    fmap = fund_map or load_fund_map()
    specs = fmap.get("funds", {})
    out: dict[str, FundConstituents] = {}

    # reuse_from（QQQの結果をNASDAQ100投信で使い回す等）は後回しにする
    deferred: list[tuple[str, dict]] = []

    for fid in fund_ids:
        spec = specs.get(fid)
        if spec is None:
            out[fid] = FundConstituents(
                fund_id=fid, policy=POLICY_REQUIRED,
                error=f"{fund_map_path().name} に {fid} の取得元が未定義")
            continue
        if spec.get("reuse_from"):
            deferred.append((fid, spec))
            continue
        out[fid] = _collect_one(fid, spec, offline=offline)

    for fid, spec in deferred:
        out[fid] = _reuse(fid, spec, out)

    return out


def _reuse(fund_id: str, spec: dict, done: dict) -> FundConstituents:
    """他のファンドの取得結果を流用する（同じURLを二度叩かないため）。"""
    src_id = str(spec.get("reuse_from"))
    base = done.get(src_id)
    if base is None or not base.ok:
        return FundConstituents(
            fund_id=fund_id, policy=_policy(spec),
            proxy_of=spec.get("proxy_for"), proxy_reason=spec.get("proxy_reason"),
            error=f"流用元 {src_id} の構成銘柄が取得できていません")
    return FundConstituents(
        fund_id=fund_id, items=base.items, as_of=base.as_of,
        source=f"{base.source}（{src_id} の結果を流用）",
        source_id=base.source_id, proxy_of=spec.get("proxy_for"),
        proxy_reason=spec.get("proxy_reason"), stale=base.stale,
        age_days=base.age_days, policy=_policy(spec),
        attempts=base.attempts, change_note=base.change_note)


def _policy(spec: dict) -> str:
    return str(spec.get("coverage_policy") or POLICY_REQUIRED)


def _collect_one(fund_id: str, spec: dict, offline: bool) -> FundConstituents:
    policy = _policy(spec)
    proxy_of = spec.get("proxy_for")
    proxy_reason = spec.get("proxy_reason")

    # --- 意図的に分解しないファンド（取得を試みない） ---
    if policy == POLICY_EXCLUDED:
        return FundConstituents(
            fund_id=fund_id, policy=POLICY_EXCLUDED,
            proxy_of=proxy_of, proxy_reason=proxy_reason,
            excluded_reason=_clean(spec.get("excluded_reason")),
            error="分解対象外（excluded）")

    rules = spec.get("validation") or {}
    min_n = spec.get("min_constituents")
    prev = _previous_tickers(fund_id)

    attempts: list[SourceAttempt] = []
    sources = sorted(spec.get("sources") or [],
                     key=lambda s: int(s.get("priority", 50)))

    for src in sources:
        kind = str(src.get("kind") or "")
        # オフライン指定ではネットワークを使う source を飛ばす
        if offline and kind in ("json", "csv"):
            continue

        started = time.monotonic()
        try:
            items = _fetch_source(src, kind)
            err = None
        except Exception as e:  # noqa: BLE001
            items, err = (), f"{type(e).__name__}: {e}"
        elapsed = int((time.monotonic() - started) * 1000)

        if not items:
            attempts.append(SourceAttempt(
                id=str(src.get("id")), kind=kind,
                priority=int(src.get("priority", 50)), ok=False,
                elapsed_ms=elapsed, error=err or "取得できませんでした"))
            continue

        vr = validate_constituents(items, rules, previous_tickers=prev,
                                   min_constituents=min_n)
        if not vr.ok:
            attempts.append(SourceAttempt(
                id=str(src.get("id")), kind=kind,
                priority=int(src.get("priority", 50)), ok=False,
                count=len(items), elapsed_ms=elapsed,
                problems=tuple(vr.problems)))
            print(f"[warn] {fund_id}/{src.get('id')} は検証に通らず不採用: "
                  f"{'; '.join(vr.problems)}")
            continue

        attempts.append(SourceAttempt(
            id=str(src.get("id")), kind=kind,
            priority=int(src.get("priority", 50)), ok=True,
            count=len(items), elapsed_ms=elapsed))

        # 四半期リバランス等での入替は正常。中止せず記録して通知する。
        change_note = None
        if vr.changed:
            change_note = f"銘柄入替を検出（{vr.diff_text()}）"
            print(f"[info] {fund_id}: {change_note}")

        fc = FundConstituents(
            fund_id=fund_id, items=items,
            as_of=_as_of_for(src, kind),
            source=f"{src.get('id')}:{src.get('url') or src.get('path') or kind}",
            source_id=str(src.get("id")),
            proxy_of=proxy_of, proxy_reason=proxy_reason,
            age_days=0, policy=policy,
            verify_required=bool(src.get("verify_required")),
            attempts=tuple(attempts), change_note=change_note)
        _save_cache(fc)
        return fc

    # --- 全滅 → キャッシュにフォールバック ---
    cached, age, why = _load_cache(fund_id)
    if cached is not None:
        return FundConstituents(
            fund_id=fund_id, items=cached["items"], as_of=cached.get("as_of"),
            source=(cached.get("source") or "") + f"（キャッシュ {age}日前）",
            source_id=cached.get("source_id"), proxy_of=proxy_of,
            proxy_reason=proxy_reason, stale=True, age_days=age,
            policy=policy, attempts=tuple(attempts))

    return FundConstituents(
        fund_id=fund_id, proxy_of=proxy_of, proxy_reason=proxy_reason,
        policy=policy, attempts=tuple(attempts),
        error=(why or ("すべてのsourceが失敗し、キャッシュもありません")))


def _clean(text) -> str | None:
    if not text:
        return None
    return " ".join(str(text).split())


def _as_of_for(src: dict, kind: str) -> str:
    if kind == "local_csv":
        p = REPO_ROOT / str(src.get("path"))
        if p.exists():
            return datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d")
    if kind == "equal_weight" and src.get("members_as_of"):
        return str(src["members_as_of"])
    return now_jst().strftime("%Y-%m-%d")


def _previous_tickers(fund_id: str) -> list[str] | None:
    """前回採用した銘柄（入替判定に使う）。キャッシュが無ければ None。"""
    cached, _, _ = _load_cache(fund_id, ignore_age=True)
    if not cached:
        return None
    return [c.ticker for c in cached["items"]]


# --------------------------------------------------------------------------
# source の種類ごとの取得
# --------------------------------------------------------------------------

def _fetch_source(src: dict, kind: str) -> tuple[Constituent, ...]:
    if kind == "equal_weight":
        members = src.get("members") or []
        if not members:
            return ()
        w = 100.0 / len(members)
        return tuple(Constituent(ticker=t, weight_pct=w) for t in members)

    if kind == "local_csv":
        path = REPO_ROOT / str(src.get("path") or "")
        if not path.exists():
            return ()
        return _parse_csv(path.read_text(encoding="utf-8-sig"),
                          src.get("columns") or _DEFAULT_COLUMNS,
                          skip_until_header=True)

    url = src.get("url")
    if not url:
        return ()
    raw = _http_get(url)
    if raw is None:
        return ()

    if kind == "json":
        return _parse_json(raw.decode("utf-8", "replace"))
    if kind == "csv":
        return _parse_csv(raw.decode("utf-8-sig", "replace"),
                          src.get("columns") or {},
                          skip_until_header=bool(src.get("skip_until_header")))
    return ()


def _http_get(url: str) -> bytes | None:
    timeout = int(settings.get("source_health", "timeout_sec", 60))

    def _get():
        req = urllib.request.Request(url, headers={
            "User-Agent": _UA,
            "Accept": "application/json,text/csv,*/*",
        })
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.read()

    return retry(_get, tries=3, wait=3.0, backoff=2.0, label=f"取得({url[:60]})")


_DEFAULT_COLUMNS = {"ticker": "ticker", "weight": "weight",
                    "name": "name", "sector": "sector"}


# --------------------------------------------------------------------------
# パーサ
# --------------------------------------------------------------------------

_TICKER_KEYS = ("ticker", "symbol", "holdingticker", "tickersymbol")
_WEIGHT_KEYS = ("percentweight", "weight", "percentoffund", "marketvaluepercent",
                "pctweight", "weighting")
_NAME_KEYS = ("longname", "name", "securityname", "shortname", "holdingname")
_SECTOR_KEYS = ("sector", "gicssector", "sectorname")


def _parse_json(text: str) -> tuple[Constituent, ...]:
    """JSONから構成銘柄を抜く。

    レスポンス構造が変わりやすいため階層を決め打ちせず、
    「ティッカーらしいキー」と「構成比らしいキー」を両方持つ dict を探す。
    """
    data = json.loads(text)
    rows: list[Constituent] = []

    def walk(node):
        if isinstance(node, dict):
            lower = {str(k).lower().replace("_", ""): v for k, v in node.items()}
            tk = _first(lower, _TICKER_KEYS)
            wt = _num(_first(lower, _WEIGHT_KEYS))
            if tk and wt is not None:
                c = _make(tk, wt, _first(lower, _NAME_KEYS),
                          _first(lower, _SECTOR_KEYS))
                if c:
                    rows.append(c)
                return
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return _finalize(rows)


def _parse_csv(text: str, columns: dict,
               skip_until_header: bool = False) -> tuple[Constituent, ...]:
    """公開CSVから構成銘柄を抜く。

    iShares / Invesco のCSVは前置きの説明行が入るため、
    ``skip_until_header`` でティッカー列を含むヘッダ行まで読み飛ばす。
    """
    t_col = columns.get("ticker") or "ticker"
    w_col = columns.get("weight") or "weight"
    n_col = columns.get("name")
    s_col = columns.get("sector")

    lines = text.splitlines()
    start = 0
    if skip_until_header:
        for i, line in enumerate(lines):
            cells = [c.strip() for c in next(csv.reader([line]), [])]
            if t_col in cells and w_col in cells:
                start = i
                break
        else:
            raise ValueError(f"ヘッダ行（{t_col} / {w_col}）が見つかりません")

    reader = csv.DictReader(lines[start:])
    rows: list[Constituent] = []
    for r in reader:
        clean = {(k.strip() if k else ""): v for k, v in r.items()}
        c = _make(clean.get(t_col), clean.get(w_col),
                  clean.get(n_col) if n_col else None,
                  clean.get(s_col) if s_col else None)
        if c:
            rows.append(c)
    return _finalize(rows)


def _make(ticker, weight, name=None, sector=None) -> Constituent | None:
    tk = str(ticker or "").strip()
    if not tk or _NON_EQUITY.match(tk):
        return None
    w = _num(weight)
    if w is None or w <= 0:
        return None
    name = str(name).strip() if name else None
    sector = str(sector).strip() if sector else None
    return Constituent(ticker=tk, weight_pct=w, name=name or None,
                       sector=sector or None)


def _finalize(rows: list[Constituent]) -> tuple[Constituent, ...]:
    """同一ティッカーの重複行をまとめ、構成比の降順に並べる。"""
    merged: dict[str, Constituent] = {}
    for c in rows:
        key = c.ticker.upper()
        prev = merged.get(key)
        if prev is None:
            merged[key] = c
        else:
            merged[key] = Constituent(
                ticker=prev.ticker,
                weight_pct=prev.weight_pct + c.weight_pct,
                name=prev.name or c.name,
                sector=prev.sector or c.sector)
    return tuple(sorted(merged.values(), key=lambda c: -c.weight_pct))


def _first(lower: dict, keys):
    for k in keys:
        if k in lower and lower[k] not in (None, ""):
            return lower[k]
    return None


def _num(v):
    """'6.21%' や '1,234' を float にする。数値でなければ None（推測しない）。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("%", "").replace(",", "")
    if not s or s in ("-", "--", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# キャッシュ（経過日数で扱いを変える）
# --------------------------------------------------------------------------

def _cache_path(fund_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(fund_id))
    return cache_dir() / f"{safe}.json"


def _save_cache(fc: FundConstituents) -> None:
    path = _cache_path(fc.fund_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fund_id": fc.fund_id,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of": fc.as_of,
        "source": fc.source,
        "source_id": fc.source_id,
        "proxy_of": fc.proxy_of,
        "count": len(fc.items),
        "coverage_pct": round(fc.coverage_pct, 4),
        "items": [{"ticker": c.ticker, "weight_pct": c.weight_pct,
                   "name": c.name, "sector": c.sector} for c in fc.items],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                    encoding="utf-8")


def cache_age_days(fetched_at: str | None) -> int | None:
    if not fetched_at:
        return None
    try:
        dt = datetime.fromisoformat(str(fetched_at))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - dt).days)


def _load_cache(fund_id: str, ignore_age: bool = False
                ) -> tuple[dict | None, int | None, str | None]:
    """キャッシュを読む。

    Returns:
        (中身, 経過日数, 使えない理由)。古すぎる場合は中身を None にして
        理由を返す（取得失敗と同じ扱いにするため）。
    """
    path = _cache_path(fund_id)
    if not path.exists():
        return None, None, None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"[warn] キャッシュ読込失敗 {path.name}: {e}")
        return None, None, f"キャッシュが壊れています（{e}）"

    items = tuple(
        Constituent(ticker=i["ticker"], weight_pct=float(i["weight_pct"]),
                    name=i.get("name"), sector=i.get("sector"))
        for i in raw.get("items", []) if i.get("ticker"))
    if not items:
        return None, None, "キャッシュが空です"

    age = cache_age_days(raw.get("fetched_at"))
    if not ignore_age and age is not None:
        _, warn_days = settings.freshness_days()
        if age > warn_days:
            return (None, age,
                    f"キャッシュが{age}日前で古すぎます"
                    f"（{warn_days}日超は取得失敗と同じ扱い）")

    return ({"items": items, "as_of": raw.get("as_of"),
             "source": raw.get("source"),
             "source_id": raw.get("source_id")}, age, None)


def freshness_label(age_days: int | None) -> str:
    """経過日数の区分名（notes.md と画像の表記に使う）。"""
    if age_days is None:
        return "不明"
    ok_days, warn_days = settings.freshness_days()
    if age_days <= ok_days:
        return "正常"
    if age_days <= warn_days:
        return "警告"
    return "期限切れ"


# --------------------------------------------------------------------------

def load_holdings() -> tuple[list, float, str]:
    """data/holdings.yml を読み、(Fundリスト, 総資産, 基準日) を返す。"""
    from src.lookthrough.compute import Fund

    path = settings.path_of("holdings")
    h = load_yaml(path, default=None)
    if not h:
        raise FileNotFoundError(
            f"{path} がありません。先に scripts/sync_holdings_yml.py を実行してください")
    funds = [Fund(id=str(f["id"]), name=f["name"], kind=f.get("kind", ""),
                  value_jpy=float(f["value_jpy"]))
             for f in h.get("funds", []) if f.get("value_jpy")]
    total = float(h.get("total_jpy") or sum(f.value_jpy for f in funds))
    return funds, total, str(h.get("generated_at", ""))
