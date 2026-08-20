#!/usr/bin/env python3
"""比較動画のデータセット定義を読む。

1つの動画＝1つの spec（data/specs/<slug>.yml）。
企業・指標・年・画面の文言・配色をここに集約し、
スクリプトとRemotion側はどちらも spec から組み立てる。
動画を増やすときは spec を足すだけにする。
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SPEC_DIR = DATA / "specs"
FX_PATH = DATA / "fx_rates.csv"
VIDEO_DATA = ROOT / "video" / "src" / "data"

REQUIRED_COMPANY_FIELDS = (
    "id", "name_ja", "name_en", "monogram", "color", "country",
    "currency", "fx_basis", "fiscal_year_end", "fiscal_year_end_month",
    "scope", "scope_note",
)

FX_BASIS_LABELS = {
    "calendar": "暦年平均",
    "fy_apr_mar": "年度平均(4月-3月)",
}


class SpecError(Exception):
    pass


def available_slugs() -> list[str]:
    return sorted(p.stem for p in SPEC_DIR.glob("*.yml"))


def load(slug: str) -> dict:
    path = SPEC_DIR / f"{slug}.yml"
    if not path.exists():
        raise SpecError(
            f"{path} が無い。使えるのは: {', '.join(available_slugs()) or '(なし)'}")

    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    _validate(spec, slug)
    return spec


def _validate(spec: dict, slug: str) -> None:
    problems: list[str] = []

    if spec.get("slug") != slug:
        problems.append(f"spec の slug が '{spec.get('slug')}' でファイル名 '{slug}' と違う")

    seen: set[str] = set()
    for c in spec.get("companies", []):
        missing = [f for f in REQUIRED_COMPANY_FIELDS if f not in c]
        if missing:
            problems.append(f"{c.get('id', '?')}: 項目が足りない {missing}")
        if c.get("id") in seen:
            problems.append(f"企業IDが重複している: {c['id']}")
        seen.add(c.get("id"))
        if c.get("fx_basis") not in FX_BASIS_LABELS:
            problems.append(
                f"{c.get('id')}: fx_basis は {list(FX_BASIS_LABELS)} のいずれか")

    colors = [c.get("color") for c in spec.get("companies", [])]
    if len(set(colors)) != len(colors):
        problems.append("系列色が重複している。線が見分けられなくなる")

    metric_ids = [m.get("id") for m in spec.get("metrics", [])]
    if "revenue" not in metric_ids or "operating_income" not in metric_ids:
        problems.append("metrics に revenue と operating_income が要る")

    if problems:
        raise SpecError("\n  ".join([f"{slug}.yml の内容が正しくない:"] + problems))


def fiscal_label(company: dict, year: int) -> str:
    """暦年 year に寄せた会計期間のラベル。

    決算月が6月以降のFYはその暦年へ、5月以前のFYは前暦年へ寄せる。
    """
    m = company["fiscal_year_end_month"]
    return f"{year}年{m}月期" if m >= 6 else f"{year + 1}年{m}月期"


YEAR_MAPPING_RULE = "決算月>=6月のFYはその暦年へ、決算月<6月のFYは前暦年へ寄せる"


def resolve_slug(argv: list[str]) -> str:
    """コマンドラインの第1引数からスラッグを取る。"""
    positional = [a for a in argv[1:] if not a.startswith("-")]
    if not positional:
        print(f"使い方: {Path(argv[0]).name} <slug>\n"
              f"  使えるスラッグ: {', '.join(available_slugs())}", file=sys.stderr)
        raise SystemExit(2)
    return positional[0]
