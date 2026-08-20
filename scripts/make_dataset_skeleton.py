#!/usr/bin/env python3
"""spec から、値が空のデータ収集用ファイル一式を作る。

    python scripts/make_dataset_skeleton.py memory10
    python scripts/make_dataset_skeleton.py security8

作るもの:
    data/<slug>.csv       long形式の本体（company × metric × year）。値は空
    data/<slug>.json      企業・指標のメタデータ（Remotion側も読む）
    data/fx_rates.csv     期中平均レート（全データセット共通。既存の値は消さない）

値は一切埋めない。出典を確認できたセルだけを後から手で入れる。
（CLAUDE.md「データが取れない箇所を推測値で埋めない」に従う）
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dataset_spec as ds  # noqa: E402

FX_FIELDS = ["currency", "basis", "basis_label", "year", "rate_per_usd",
             "source_url", "source_note"]


def already_filled(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open(encoding="utf-8") as f:
        return any((row.get("value_local") or "").strip() for row in csv.DictReader(f))


def write_rows_csv(spec: dict, path: Path) -> int:
    rows = []
    for c in spec["companies"]:
        for m in spec["metrics"]:
            for y in spec["years"]:
                rows.append({
                    "company_id": c["id"],
                    "company_ja": c["name_ja"],
                    "metric_id": m["id"],
                    "year": y,
                    "fiscal_period": ds.fiscal_label(c, y),
                    "value_local": "",
                    "currency": "" if m["derived"] else c["currency"],
                    "value_usd_oku": "",
                    "is_estimate": "",
                    "derived": "TRUE" if m["derived"] else "FALSE",
                    "status": "derived" if m["derived"] else "unfilled",
                    "source_url": "",
                    "source_note": "",
                })
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def merge_fx(spec: dict) -> int:
    """このデータセットに要るレート行を、既存の表を壊さずに足す。"""
    existing: dict[tuple[str, str, int], dict] = {}
    if ds.FX_PATH.exists():
        with ds.FX_PATH.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                existing[(row["currency"], row["basis"], int(row["year"]))] = row

    needed = {(c["currency"], c["fx_basis"]) for c in spec["companies"]}
    added = 0
    for currency, basis in sorted(needed):
        for year in spec["years"]:
            key = (currency, basis, year)
            if key in existing:
                continue
            existing[key] = {
                "currency": currency,
                "basis": basis,
                "basis_label": "換算不要" if currency == "USD" else ds.FX_BASIS_LABELS[basis],
                "year": year,
                "rate_per_usd": "1" if currency == "USD" else "",
                "source_url": "",
                "source_note": "",
            }
            added += 1

    with ds.FX_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FX_FIELDS)
        w.writeheader()
        for key in sorted(existing):
            row = existing[key]
            w.writerow({k: row.get(k, "") for k in FX_FIELDS})
    return added


def main() -> int:
    slug = ds.resolve_slug(sys.argv)
    try:
        spec = ds.load(slug)
    except ds.SpecError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1

    csv_path = ds.DATA / f"{slug}.csv"
    if already_filled(csv_path) and "--force" not in sys.argv:
        print(f"{csv_path} にすでに数値が入っている。"
              "作り直すと消えるので中止した（本当にやるなら --force）", file=sys.stderr)
        return 1

    ds.DATA.mkdir(exist_ok=True)
    count = write_rows_csv(spec, csv_path)
    added = merge_fx(spec)

    meta = {
        "schema_version": 2,
        "slug": slug,
        "generated_by": "scripts/make_dataset_skeleton.py",
        "year_mapping_rule": ds.YEAR_MAPPING_RULE,
        "years": spec["years"],
        "copy": spec["copy"],
        "companies": spec["companies"],
        "metrics": spec["metrics"],
    }
    (ds.DATA / f"{slug}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {csv_path} ({count} rows)")
    print(f"wrote {ds.DATA / f'{slug}.json'}")
    print(f"wrote {ds.FX_PATH} ({added} 行を追加)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
