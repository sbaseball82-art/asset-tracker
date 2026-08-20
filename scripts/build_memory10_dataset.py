#!/usr/bin/env python3
"""data/memory10.csv と data/fx_rates.csv から動画が読むJSONを作る。

- ローカル通貨（百万単位）→ 億ドルへ、当該年度の期中平均レートで換算する
- 営業利益率は営業利益/売上高から導出する（為替の影響を受けないようローカル通貨で計算）
- 埋まっていないセルは null のまま通す。推定・補完は一切しない
- 出典URLの無い数値は通さない（--dummy を除く）

使い方:
    python scripts/build_memory10_dataset.py            # 本番
    python scripts/build_memory10_dataset.py --dummy    # 動作確認用のダミー値
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT_DIR = ROOT / "video" / "src" / "data"

MILLIONS_PER_OKU_USD = 100.0  # 1億ドル = 100百万ドル


class BuildError(Exception):
    pass


def read_meta() -> dict:
    return json.loads((DATA / "memory10.json").read_text(encoding="utf-8"))


def read_fx() -> dict[tuple[str, int], float]:
    rates: dict[tuple[str, int], float] = {}
    with (DATA / "fx_rates.csv").open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw = (row["rate_per_usd"] or "").strip()
            if not raw:
                continue
            rates[(row["currency"], int(row["year"]))] = float(raw)
    return rates


def read_rows() -> list[dict]:
    with (DATA / "memory10.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_value(raw: str) -> float | None:
    raw = (raw or "").strip().replace(",", "")
    if raw == "":
        return None
    return float(raw)


def build(dummy: bool) -> dict:
    meta = read_meta()
    years: list[int] = meta["years"]
    companies: list[dict] = meta["companies"]
    metrics: list[dict] = meta["metrics"]
    fx = read_fx()

    if dummy:
        local = _dummy_local(companies, years)
        sources = {}
        estimates = {}
        # ダミー実行は fx_rates.csv に依存させない（本番の空欄で止まらないように）
        for cur, r in (("KRW", 1200.0), ("JPY", 130.0), ("TWD", 30.0)):
            for y in years:
                fx.setdefault((cur, y), r)
    else:
        local, sources, estimates = _read_local(read_rows(), fx)

    points: list[dict] = []
    problems: list[str] = []

    for c in companies:
        cid = c["id"]
        cur = c["currency"]
        for y in years:
            rev = local.get((cid, "revenue", y))
            oi = local.get((cid, "operating_income", y))

            rate = 1.0 if cur == "USD" else fx.get((cur, y))
            if rate is None and (rev is not None or oi is not None):
                problems.append(f"{cur} {y} の期中平均レートが未記入のため {cid} を換算できない")
                rate = None

            def to_oku(v: float | None) -> float | None:
                if v is None or rate is None:
                    return None
                return round(v / rate / MILLIONS_PER_OKU_USD, 2)

            margin = None
            if rev is not None and oi is not None and rev != 0:
                margin = round(oi / rev * 100.0, 2)

            for metric_id, value, value_local in (
                ("revenue", to_oku(rev), rev),
                ("operating_income", to_oku(oi), oi),
                ("operating_margin", margin, None),
            ):
                points.append({
                    "company_id": cid,
                    "metric_id": metric_id,
                    "year": y,
                    "value": value,
                    "value_local": value_local,
                    "currency": None if metric_id == "operating_margin" else cur,
                    "fx_rate": None if metric_id == "operating_margin" else rate,
                    "is_estimate": bool(estimates.get((cid, metric_id, y), False)),
                    "source": sources.get((cid, metric_id, y)),
                })

    filled = sum(1 for p in points if p["value"] is not None)
    dataset = {
        "schema_version": 1,
        "is_dummy": dummy,
        "year_mapping_rule": meta["year_mapping_rule"],
        "years": years,
        "companies": companies,
        "metrics": metrics,
        "fx_rates": [
            {"currency": cur, "year": y, "rate_per_usd": r}
            for (cur, y), r in sorted(fx.items())
        ],
        "coverage": {
            "total_cells": len(points),
            "filled_cells": filled,
            "filled_ratio": round(filled / len(points), 4) if points else 0.0,
        },
        "data": points,
    }

    if problems:
        raise BuildError("\n".join(problems))
    return dataset


def _read_local(rows, fx) -> tuple[dict, dict, dict]:
    local: dict[tuple[str, str, int], float] = {}
    sources: dict[tuple[str, str, int], str] = {}
    estimates: dict[tuple[str, str, int], bool] = {}
    missing_source: list[str] = []

    for row in rows:
        if row["derived"].upper() == "TRUE":
            continue
        key = (row["company_id"], row["metric_id"], int(row["year"]))
        value = parse_value(row["value_local"])
        if value is None:
            continue
        url = (row["source_url"] or "").strip()
        if not url:
            missing_source.append(f"{key[0]} / {key[1]} / {key[2]}")
            continue
        local[key] = value
        sources[key] = url
        estimates[key] = (row["is_estimate"] or "").strip().upper() in ("TRUE", "1", "YES")

    if missing_source:
        raise BuildError(
            "出典URLの無い数値がある。埋めるか消すこと:\n  " + "\n  ".join(missing_source))
    return local, sources, estimates


def _dummy_local(companies, years) -> dict:
    """動作確認専用の合成値。本番JSONには絶対に混ぜない。"""
    rng = random.Random(20260820)
    scale = {  # 百万ローカル通貨のオーダーだけ合わせる
        "samsung": 90_000_000, "skhynix": 30_000_000, "micron": 20_000,
        "kioxia": 1_200_000, "sandisk": 15_000, "nanya": 60_000,
        "winbond": 70_000, "macronix": 40_000,
    }
    holes = {("kioxia", 2016), ("kioxia", 2017)}
    local: dict[tuple[str, str, int], float] = {}
    for c in companies:
        cid = c["id"]
        base = scale[cid]
        for i, y in enumerate(years):
            if (cid, y) in holes:
                continue
            cycle = 1.0 + 0.55 * math.sin((i + rng.random()) * 0.9)
            trend = 1.0 + 0.09 * i
            rev = base * cycle * trend
            local[(cid, "revenue", y)] = round(rev, 1)
            if cid == "sandisk" and y <= 2022:
                continue  # WDはフラッシュ事業の営業利益を開示していない
            local[(cid, "operating_income", y)] = round(rev * (cycle - 0.75) * 0.6, 1)
    return local


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dummy", action="store_true",
                    help="合成値で動作確認用のJSONを作る（本番ファイルは書き換えない）")
    args = ap.parse_args()

    try:
        dataset = build(args.dummy)
    except BuildError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    name = "memory10.dummy.json" if args.dummy else "memory10.generated.json"
    (OUT_DIR / name).write_text(
        json.dumps(dataset, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    cov = dataset["coverage"]
    print(f"wrote {OUT_DIR / name}")
    print(f"  {cov['filled_cells']}/{cov['total_cells']} セル充填 "
          f"({cov['filled_ratio'] * 100:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
