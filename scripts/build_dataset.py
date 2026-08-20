#!/usr/bin/env python3
"""CSVと為替表から、動画が読むJSONを作る。

    python scripts/build_dataset.py memory10
    python scripts/build_dataset.py security8 --dummy

- ローカル通貨（百万単位）→ 億ドルへ、その企業の会計期間に合うレートで換算する
- 営業利益率は営業利益/売上高から導出する（為替の影響を受けないようローカル通貨で計算）
- 埋まっていないセルは null のまま通す。推定・補完は一切しない
- 出典URLの無い数値は通さない（--dummy を除く）
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dataset_spec as ds  # noqa: E402

MILLIONS_PER_OKU_USD = 100.0  # 1億ドル = 100百万ドル


class BuildError(Exception):
    pass


def read_fx() -> dict[tuple[str, str, int], float]:
    rates: dict[tuple[str, str, int], float] = {}
    if not ds.FX_PATH.exists():
        return rates
    with ds.FX_PATH.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw = (row["rate_per_usd"] or "").strip()
            if raw:
                rates[(row["currency"], row["basis"], int(row["year"]))] = float(raw)
    return rates


def parse_value(raw: str) -> float | None:
    raw = (raw or "").strip().replace(",", "")
    return float(raw) if raw else None


def build(slug: str, dummy: bool) -> dict:
    spec = ds.load(slug)
    years: list[int] = spec["years"]
    companies: list[dict] = spec["companies"]
    metrics: list[dict] = spec["metrics"]
    fx = read_fx()

    if dummy:
        local = _dummy_local(companies, years)
        sources: dict = {}
        estimates: dict = {}
        for c in companies:  # ダミーは fx_rates.csv の空欄で止まらないようにする
            placeholder = {"KRW": 1200.0, "JPY": 130.0, "TWD": 30.0}.get(c["currency"], 1.0)
            for y in years:
                fx.setdefault((c["currency"], c["fx_basis"], y), placeholder)
    else:
        local, sources, estimates = _read_local(ds.DATA / f"{slug}.csv")

    points: list[dict] = []
    problems: list[str] = []

    for c in companies:
        cid, cur, basis = c["id"], c["currency"], c["fx_basis"]
        for y in years:
            rev = local.get((cid, "revenue", y))
            oi = local.get((cid, "operating_income", y))

            rate = 1.0 if cur == "USD" else fx.get((cur, basis, y))
            if rate is None and (rev is not None or oi is not None):
                problems.append(
                    f"{cur}/{basis}/{y} のレートが未記入のため {cid} を換算できない")

            def to_oku(v: float | None) -> float | None:
                return None if v is None or rate is None else round(v / rate / MILLIONS_PER_OKU_USD, 2)

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

    if problems:
        raise BuildError("\n".join(problems))

    filled = sum(1 for p in points if p["value"] is not None)
    return {
        "schema_version": 2,
        "slug": slug,
        "is_dummy": dummy,
        "year_mapping_rule": ds.YEAR_MAPPING_RULE,
        "years": years,
        "copy": spec["copy"],
        "companies": companies,
        "metrics": metrics,
        "fx_rates": [
            {"currency": cur, "basis": b, "year": y, "rate_per_usd": r}
            for (cur, b, y), r in sorted(fx.items())
        ],
        "coverage": {
            "total_cells": len(points),
            "filled_cells": filled,
            "filled_ratio": round(filled / len(points), 4) if points else 0.0,
        },
        "data": points,
    }


def _read_local(path: Path) -> tuple[dict, dict, dict]:
    if not path.exists():
        raise BuildError(f"{path} が無い。先に make_dataset_skeleton.py を実行すること")

    local: dict[tuple[str, str, int], float] = {}
    sources: dict[tuple[str, str, int], str] = {}
    estimates: dict[tuple[str, str, int], bool] = {}
    missing_source: list[str] = []

    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["derived"].upper() == "TRUE":
                continue
            value = parse_value(row["value_local"])
            if value is None:
                continue
            key = (row["company_id"], row["metric_id"], int(row["year"]))
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
    """動作確認専用の合成値。本番JSONには絶対に混ぜない。

    実データの形（後発企業は初期が欠損、赤字の年がある）だけ真似ておく。
    """
    rng = random.Random(20260820)
    local: dict[tuple[str, str, int], float] = {}
    for idx, c in enumerate(companies):
        base = 20_000 / (idx + 1) if c["currency"] == "USD" else 150_000
        start = idx % 3  # 何社かは途中から始まるようにする
        # 利益率は社ごとにばらつかせる。全社同じだと③のラベル配置の検証にならない
        ceiling = 0.10 + 0.05 * idx
        drag = 0.3 + 0.25 * ((idx * 7) % 5)
        for i, y in enumerate(years):
            if i < start:
                continue
            cycle = 1.0 + 0.35 * math.sin((i + rng.random()) * 0.8)
            rev = base * cycle * (1.0 + 0.18 * i)
            local[(c["id"], "revenue", y)] = round(rev, 1)
            margin = ceiling - drag / (i + 1)
            local[(c["id"], "operating_income", y)] = round(rev * margin, 1)
    return local


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", help=f"データセット（{', '.join(ds.available_slugs())}）")
    ap.add_argument("--dummy", action="store_true",
                    help="合成値で動作確認用のJSONを作る（本番ファイルは書き換えない）")
    args = ap.parse_args()

    try:
        dataset = build(args.slug, args.dummy)
    except (BuildError, ds.SpecError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1

    ds.VIDEO_DATA.mkdir(parents=True, exist_ok=True)
    name = f"{args.slug}.dummy.json" if args.dummy else f"{args.slug}.generated.json"
    (ds.VIDEO_DATA / name).write_text(
        json.dumps(dataset, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    cov = dataset["coverage"]
    print(f"wrote {ds.VIDEO_DATA / name}")
    print(f"  {cov['filled_cells']}/{cov['total_cells']} セル充填 "
          f"({cov['filled_ratio'] * 100:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
