#!/usr/bin/env python3
"""memory10 データセットの骨格を生成する。

値は一切埋めない。全セルを status="unfilled" で出力し、
出典URLと参照箇所が確認できたセルだけを後から埋める運用にする。
（CLAUDE.md「データが取れない箇所を推測値で埋めない」に従う）
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

YEARS = list(range(2016, 2026))

# fiscal_year_end_month で暦年への寄せ方が決まる。
# 規則: 決算月 >= 6 → その暦年 / 決算月 < 6 → 前暦年
COMPANIES = [
    {
        "id": "samsung", "monogram": "S", "name_ja": "サムスン電子", "name_en": "Samsung Electronics",
        "country": "韓国", "currency": "KRW", "fiscal_year_end": "12月",
        "fiscal_year_end_month": 12,
        "scope": "DS部門（半導体：メモリ＋ファウンドリ＋System LSI）",
        "scope_note": "メモリ単独の営業利益は非開示のため、3指標すべてDS部門ベース。売上高は実態よりファウンドリ/LSI分だけ大きく出る。",
    },
    {
        "id": "skhynix", "monogram": "SK", "name_ja": "SKハイニックス", "name_en": "SK hynix",
        "country": "韓国", "currency": "KRW", "fiscal_year_end": "12月",
        "fiscal_year_end_month": 12,
        "scope": "連結（メモリ専業。2021年末以降Solidigmを含む）",
        "scope_note": "Intel NANDメモリ事業(Solidigm)の第1段階クロージングは2021年12月。2022年以降は連結に含まれる。",
    },
    {
        "id": "micron", "monogram": "MU", "name_ja": "マイクロン", "name_en": "Micron Technology",
        "country": "米国", "currency": "USD", "fiscal_year_end": "8月/9月",
        "fiscal_year_end_month": 8,
        "scope": "連結（メモリ専業）",
        "scope_note": "会計年度は8月末〜9月初に終了。FY2016は2016年9月1日終了。",
    },
    {
        "id": "kioxia", "monogram": "KX", "name_ja": "キオクシア", "name_en": "Kioxia",
        "country": "日本", "currency": "JPY", "fiscal_year_end": "3月",
        "fiscal_year_end_month": 3,
        "scope": "連結（NANDフラッシュ専業）",
        "scope_note": "2017年4月に東芝メモリとして分社、2018年6月に東芝から独立。2016〜2017年度は法人として存在せず、遡及開示も無い。",
    },
    {
        "id": "sandisk", "monogram": "SD", "name_ja": "サンディスク", "name_en": "SanDisk",
        "country": "米国", "currency": "USD", "fiscal_year_end": "6月/7月",
        "fiscal_year_end_month": 6,
        "scope": "2016〜2024年度=Western Digitalのフラッシュ事業、2025年度=SanDisk単体",
        "scope_note": "WDは営業利益をセグメント別に開示していない（FY2023までは単一報告セグメント、FY2024以降もセグメント開示は売上高と売上総利益まで）。営業利益はSanDisk単体開示のある年度のみ。",
    },
    {
        "id": "nanya", "monogram": "NT", "name_ja": "南亞科技", "name_en": "Nanya Technology",
        "country": "台湾", "currency": "TWD", "fiscal_year_end": "12月",
        "fiscal_year_end_month": 12,
        "scope": "連結（DRAM専業）", "scope_note": "",
    },
    {
        "id": "winbond", "monogram": "WB", "name_ja": "華邦電子", "name_en": "Winbond Electronics",
        "country": "台湾", "currency": "TWD", "fiscal_year_end": "12月",
        "fiscal_year_end_month": 12,
        "scope": "連結（特殊DRAM/NORフラッシュ。ファウンドリ事業を含む）",
        "scope_note": "メモリ以外の受託生産を含む全社連結。メモリ単独のセグメント開示は無い。",
    },
    {
        "id": "macronix", "monogram": "MX", "name_ja": "旺宏電子", "name_en": "Macronix International",
        "country": "台湾", "currency": "TWD", "fiscal_year_end": "12月",
        "fiscal_year_end_month": 12,
        "scope": "連結（NORフラッシュ/ROM中心）", "scope_note": "",
    },
]

METRICS = [
    {"id": "revenue", "label_ja": "売上高", "unit_ja": "億ドル", "theme": "navy", "derived": False},
    {"id": "operating_income", "label_ja": "営業利益", "unit_ja": "億ドル", "theme": "green", "derived": False},
    {"id": "operating_margin", "label_ja": "営業利益率", "unit_ja": "%", "theme": "rust", "derived": True,
     "formula": "operating_income / revenue * 100"},
]


def fiscal_label(company, year):
    """暦年 year に寄せた会計期間のラベルを返す。"""
    m = company["fiscal_year_end_month"]
    if m >= 6:
        return f"{year}年{m}月期"
    return f"{year + 1}年{m}月期"


def already_filled() -> bool:
    """CSVに1つでも数値が入っていれば True。"""
    path = DATA / "memory10.csv"
    if not path.exists():
        return False
    with path.open(encoding="utf-8") as f:
        return any((row.get("value_local") or "").strip() for row in csv.DictReader(f))


def main():
    if already_filled() and "--force" not in sys.argv:
        print("data/memory10.csv にすでに数値が入っている。"
              "作り直すと消えるので中止した（本当にやるなら --force）", file=sys.stderr)
        return 1

    DATA.mkdir(exist_ok=True)

    rows = []
    for c in COMPANIES:
        for m in METRICS:
            for y in YEARS:
                rows.append({
                    "company_id": c["id"],
                    "company_ja": c["name_ja"],
                    "metric_id": m["id"],
                    "year": y,
                    "fiscal_period": fiscal_label(c, y),
                    "value_local": "",
                    "currency": "" if m["derived"] else c["currency"],
                    "value_usd_oku": "",
                    "is_estimate": "",
                    "derived": "TRUE" if m["derived"] else "FALSE",
                    "status": "derived" if m["derived"] else "unfilled",
                    "source_url": "",
                    "source_note": "",
                })

    csv_path = DATA / "memory10.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    fx_path = DATA / "fx_rates.csv"
    with fx_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["currency", "year", "basis", "rate_per_usd", "source_url", "source_note"])
        for cur, basis in (("KRW", "暦年平均"), ("JPY", "年度平均(4月-3月)"),
                           ("TWD", "暦年平均"), ("USD", "換算不要")):
            for y in YEARS:
                w.writerow([cur, y, basis, "" if cur != "USD" else "1", "", ""])

    meta = {
        "schema_version": 1,
        "generated_by": "scripts/make_memory10_skeleton.py",
        "year_mapping_rule": "決算月>=6月のFYはその暦年へ、決算月<6月のFYは前暦年へ寄せる",
        "years": YEARS,
        "companies": COMPANIES,
        "metrics": METRICS,
        "data": [],
    }
    (DATA / "memory10.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {csv_path} ({len(rows)} rows)")
    print(f"wrote {fx_path}")
    print(f"wrote {DATA / 'memory10.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
