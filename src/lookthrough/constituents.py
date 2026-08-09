# -*- coding: utf-8 -*-
"""
constituents.py
===============
各ファンドの構成銘柄（ティッカーと構成比）を集める層。

方針
----
1. まず運用会社の公開データを取りに行く（リトライ3回＋指数バックオフ）。
2. 失敗したら ``data/cache/constituents/<fund_id>.json`` の前回分を使い、
   ``stale: true`` を立てる。
3. キャッシュも無ければ **推測で埋めずに** error を持たせて返す。
   呼び出し側（compute.look_through）が「未分解＝要手動確認」として扱う。

取得元の宣言はコードではなく ``data/fund_map.yml`` に置く。
公開CSVの列名変更などはYAMLの修正だけで追随できるようにするため。
"""

from __future__ import annotations

import csv
import io
import json
import re
import urllib.request
from pathlib import Path

from src.common.util import REPO_ROOT, load_yaml, now_jst, retry
from src.lookthrough.compute import Constituent, FundConstituents

FUND_MAP_PATH = REPO_ROOT / "data" / "fund_map.yml"
CACHE_DIR = REPO_ROOT / "data" / "cache" / "constituents"
MANUAL_DIR = REPO_ROOT / "data" / "manual"

_UA = "Mozilla/5.0 (compatible; asset-tracker/1.0)"
_TIMEOUT = 60

# 現金・先物・未分類など、個別銘柄として扱わない行を落とすためのパターン
_NON_EQUITY = re.compile(
    r"^(CASH|USD|JPY|-|--|N/A|NA|XTSLA|MCASH|CASH_USD|BLK|FUTURE.*)$", re.I)


def load_fund_map() -> dict:
    m = load_yaml(FUND_MAP_PATH, default=None)
    if not m or "funds" not in m:
        raise FileNotFoundError(f"ファンド定義がありません: {FUND_MAP_PATH}")
    return m


def collect(fund_ids: list[str], offline: bool = False,
            fund_map: dict | None = None) -> dict[str, FundConstituents]:
    """指定ファンドの構成銘柄をまとめて取得する。

    Args:
        fund_ids: holdings.yml に載っている fund.id のリスト。
        offline: True なら取得を試みずキャッシュのみ使う（stale扱い）。
    """
    fmap = fund_map or load_fund_map()
    specs = fmap.get("funds", {})
    out: dict[str, FundConstituents] = {}
    for fid in fund_ids:
        spec = specs.get(fid)
        if spec is None:
            out[fid] = FundConstituents(
                fund_id=fid,
                error=f"data/fund_map.yml に {fid} の取得元が未定義",
            )
            continue
        out[fid] = _collect_one(fid, spec, offline=offline)
    return out


def _collect_one(fund_id: str, spec: dict, offline: bool) -> FundConstituents:
    source = spec.get("source")
    proxy_of = spec.get("proxy_of")
    proxy_reason = spec.get("proxy_reason")
    verify_required = bool(spec.get("verify_required"))

    # --- 等ウェイト（指数の公表メソドロジーに基づく宣言的な定義） ---
    if source == "equal_weight":
        members = spec.get("members") or []
        if not members:
            return FundConstituents(
                fund_id=fund_id, proxy_of=proxy_of, proxy_reason=proxy_reason,
                error="equal_weight だが members が空")
        w = 100.0 / len(members)
        items = tuple(Constituent(ticker=t, weight_pct=w) for t in members)
        return FundConstituents(
            fund_id=fund_id, items=items,
            as_of=str(spec.get("members_as_of") or ""),
            source=f"equal_weight({len(members)}銘柄)",
            proxy_of=proxy_of, proxy_reason=proxy_reason,
            verify_required=True if verify_required else False,
        )

    # --- 手動配置CSV（取得元が無いものの逃げ道） ---
    if source == "manual_csv":
        path = MANUAL_DIR / str(spec.get("file") or f"{fund_id}.csv")
        if not path.exists():
            return FundConstituents(
                fund_id=fund_id, proxy_of=proxy_of, proxy_reason=proxy_reason,
                error=f"手動CSV未配置（{path.relative_to(REPO_ROOT)}）")
        try:
            items = _parse_csv(path.read_text(encoding="utf-8-sig"),
                               spec.get("columns") or _DEFAULT_MANUAL_COLUMNS,
                               skip_until_header=True)
        except Exception as e:  # noqa: BLE001
            return FundConstituents(
                fund_id=fund_id, proxy_of=proxy_of, proxy_reason=proxy_reason,
                error=f"手動CSVの解析に失敗: {e}")
        if not items:
            return FundConstituents(
                fund_id=fund_id, proxy_of=proxy_of, proxy_reason=proxy_reason,
                error=f"手動CSVに有効な行がない（{path.name}）")
        return FundConstituents(
            fund_id=fund_id, items=items, as_of=_file_date(path),
            source=f"manual_csv:{path.name}", proxy_of=proxy_of,
            proxy_reason=proxy_reason, verify_required=verify_required)

    if source is None:
        return FundConstituents(
            fund_id=fund_id, proxy_of=proxy_of, proxy_reason=proxy_reason,
            error="取得元が未設定（source: null）")

    # --- ネットワーク取得（vanguard / csv） ---
    items: tuple[Constituent, ...] = ()
    if not offline:
        items = _fetch(fund_id, spec, source)

    if items:
        fc = FundConstituents(
            fund_id=fund_id, items=items,
            as_of=now_jst().strftime("%Y-%m-%d"),
            source=f"{source}:{spec.get('url', '')}",
            proxy_of=proxy_of, proxy_reason=proxy_reason,
            verify_required=verify_required)
        _save_cache(fc)
        return fc

    # --- 取得失敗 → 前回キャッシュを stale として使う ---
    cached = _load_cache(fund_id)
    if cached is not None:
        return FundConstituents(
            fund_id=fund_id, items=cached["items"], as_of=cached.get("as_of"),
            source=(cached.get("source") or "") + "（前回キャッシュ）",
            proxy_of=proxy_of, proxy_reason=proxy_reason,
            stale=True, verify_required=verify_required)

    return FundConstituents(
        fund_id=fund_id, proxy_of=proxy_of, proxy_reason=proxy_reason,
        error=("構成銘柄の取得に失敗し、キャッシュもありません"
               if not offline else
               "オフライン指定だがキャッシュがありません"))


_DEFAULT_MANUAL_COLUMNS = {"ticker": "ticker", "weight": "weight",
                           "name": "name", "sector": "sector"}


def _fetch(fund_id: str, spec: dict, source: str) -> tuple[Constituent, ...]:
    """公開データを取得して構成銘柄に変換する。失敗時は空タプル。"""
    url = spec.get("url")
    if not url:
        return ()

    def _get():
        req = urllib.request.Request(url, headers={
            "User-Agent": _UA,
            "Accept": "application/json,text/csv,*/*",
        })
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as res:
            return res.read()

    raw = retry(_get, tries=3, wait=3.0, backoff=2.0,
                label=f"構成銘柄取得({fund_id})")
    if raw is None:
        return ()

    try:
        if source == "vanguard":
            return _parse_vanguard_json(raw.decode("utf-8", "replace"))
        if source == "csv":
            return _parse_csv(raw.decode("utf-8-sig", "replace"),
                              spec.get("columns") or {},
                              skip_until_header=bool(spec.get("skip_until_header")))
    except Exception as e:  # noqa: BLE001
        print(f"[warn] {fund_id} の解析に失敗（推測では埋めません）: {e}")
    return ()


# --------------------------------------------------------------------------
# パーサ
# --------------------------------------------------------------------------

_TICKER_KEYS = ("ticker", "symbol", "holdingticker", "tickersymbol")
_WEIGHT_KEYS = ("percentweight", "weight", "percentoffund", "marketvaluepercent",
                "pctweight", "weighting")
_NAME_KEYS = ("longname", "name", "securityname", "shortname", "holdingname")
_SECTOR_KEYS = ("sector", "gicssector", "sectorname")


def _parse_vanguard_json(text: str) -> tuple[Constituent, ...]:
    """Vanguard APIのJSONから構成銘柄を抜く。

    レスポンス構造が変わりやすいため、階層を決め打ちせず
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
                c = _make_constituent(tk, wt, _first(lower, _NAME_KEYS),
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
    t_col = columns.get("ticker") or "Ticker"
    w_col = columns.get("weight") or "Weight"
    n_col = columns.get("name")
    s_col = columns.get("sector")

    lines = text.splitlines()
    start = 0
    if skip_until_header:
        for i, line in enumerate(lines):
            cells = next(csv.reader([line]), [])
            norm = [c.strip() for c in cells]
            if t_col in norm and any(w_col == c for c in norm):
                start = i
                break
        else:
            raise ValueError(f"ヘッダ行（{t_col} / {w_col}）が見つかりません")

    reader = csv.DictReader(lines[start:])
    rows: list[Constituent] = []
    for r in reader:
        clean = {(k.strip() if k else ""): v for k, v in r.items()}
        c = _make_constituent(clean.get(t_col), clean.get(w_col),
                              clean.get(n_col) if n_col else None,
                              clean.get(s_col) if s_col else None)
        if c:
            rows.append(c)
    return _finalize(rows)


def _make_constituent(ticker, weight, name=None, sector=None) -> Constituent | None:
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
# キャッシュ
# --------------------------------------------------------------------------

def _cache_path(fund_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(fund_id))
    return CACHE_DIR / f"{safe}.json"


def _save_cache(fc: FundConstituents) -> None:
    path = _cache_path(fc.fund_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fund_id": fc.fund_id,
        "fetched_at": now_jst().strftime("%Y-%m-%d %H:%M JST"),
        "as_of": fc.as_of,
        "source": fc.source,
        "proxy_of": fc.proxy_of,
        "count": len(fc.items),
        "coverage_pct": round(fc.coverage_pct, 4),
        "items": [{"ticker": c.ticker, "weight_pct": c.weight_pct,
                   "name": c.name, "sector": c.sector} for c in fc.items],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                    encoding="utf-8")


def _load_cache(fund_id: str) -> dict | None:
    path = _cache_path(fund_id)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"[warn] キャッシュ読込失敗 {path.name}: {e}")
        return None
    items = tuple(
        Constituent(ticker=i["ticker"], weight_pct=float(i["weight_pct"]),
                    name=i.get("name"), sector=i.get("sector"))
        for i in raw.get("items", []) if i.get("ticker"))
    if not items:
        return None
    return {"items": items, "as_of": raw.get("as_of"),
            "source": raw.get("source")}


def _file_date(path: Path) -> str:
    from datetime import datetime
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")


def load_holdings() -> tuple[list, float, str]:
    """data/holdings.yml を読み、(Fundリスト, 総資産, 基準日) を返す。"""
    from src.lookthrough.compute import Fund

    path = REPO_ROOT / "data" / "holdings.yml"
    h = load_yaml(path, default=None)
    if not h:
        raise FileNotFoundError(
            f"{path} がありません。先に scripts/sync_holdings_yml.py を実行してください")
    funds = [Fund(id=str(f["id"]), name=f["name"], kind=f.get("kind", ""),
                  value_jpy=float(f["value_jpy"]))
             for f in h.get("funds", []) if f.get("value_jpy")]
    total = float(h.get("total_jpy") or sum(f.value_jpy for f in funds))
    return funds, total, str(h.get("generated_at", ""))
