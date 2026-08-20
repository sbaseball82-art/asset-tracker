#!/usr/bin/env python3
"""video/public/logos/<slug>/ に置かれたロゴ画像を見つけて、動画が読む一覧を作る。

各社の実ロゴは商標であり、配布物に含める判断は人間がすること。
このリポジトリはロゴ画像を同梱しない。置かれていればそれを使い、
無ければ社名の頭文字バッジ（monogram）で描く。

ファイル名は企業ID（spec の companies[].id）に合わせる:
    video/public/logos/memory10/micron.svg
    video/public/logos/security8/crowdstrike.png
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dataset_spec as ds  # noqa: E402

LOGO_ROOT = ds.ROOT / "video" / "public" / "logos"
OUT = ds.VIDEO_DATA / "logos.generated.json"
EXTENSIONS = (".svg", ".png", ".webp", ".jpg", ".jpeg")


def main() -> int:
    manifest: dict[str, dict[str, str]] = {}
    warnings: list[str] = []

    for slug in ds.available_slugs():
        spec = ds.load(slug)
        known = {c["id"] for c in spec["companies"]}
        found: dict[str, str] = {}

        folder = LOGO_ROOT / slug
        if folder.exists():
            for path in sorted(folder.iterdir()):
                if path.suffix.lower() not in EXTENSIONS:
                    continue
                if path.stem in known:
                    found[path.stem] = f"logos/{slug}/{path.name}"
                else:
                    warnings.append(f"{slug}/{path.name} は企業IDと一致しないので使われない")

        manifest[slug] = found
        label = ", ".join(found) if found else "なし（全社を頭文字バッジで描く）"
        print(f"{slug}: {label}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    for w in warnings:
        print(f"  警告: {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
