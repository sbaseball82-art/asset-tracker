#!/usr/bin/env python3
"""video/public/logos/ に置かれたロゴ画像を見つけて、動画が読む一覧を作る。

各社の実ロゴは商標であり、配布物に含める判断は人間がすること。
このリポジトリはロゴ画像を同梱しない。置かれていればそれを使い、
無ければ社名の頭文字バッジ（monogram）で描く。

ファイル名は企業ID（data/memory10.json の companies[].id）に合わせる:
    video/public/logos/micron.svg
    video/public/logos/kioxia.png
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGO_DIR = ROOT / "video" / "public" / "logos"
OUT = ROOT / "video" / "src" / "data" / "logos.generated.json"

EXTENSIONS = (".svg", ".png", ".webp", ".jpg", ".jpeg")


def main() -> int:
    companies = json.loads((ROOT / "data" / "memory10.json").read_text(encoding="utf-8"))
    known = {c["id"] for c in companies["companies"]}

    found: dict[str, str] = {}
    unknown: list[str] = []
    if LOGO_DIR.exists():
        for path in sorted(LOGO_DIR.iterdir()):
            if path.suffix.lower() not in EXTENSIONS:
                continue
            if path.stem in known:
                found[path.stem] = f"logos/{path.name}"
            else:
                unknown.append(path.name)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(found, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"wrote {OUT}")
    if found:
        for cid, rel in found.items():
            print(f"  {cid}: {rel}")
    else:
        print("  ロゴ画像なし。全社を頭文字バッジで描く")
    for name in unknown:
        print(f"  警告: {name} は企業IDと一致しないので使われない")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
