# -*- coding: utf-8 -*-
"""
verify_live.py
==============
data/fund_map.yml に書いた全 source に**実アクセス**して、
どれが生きているかを確かめる。本番投入前に1回流すためのもの。

    python scripts/verify_live.py
    python scripts/verify_live.py --fund VTI        # 1本だけ試す
    python scripts/verify_live.py --include-excluded

出力: reports/live_verification.md

構成銘柄の分解も投稿文の生成もしない。取得・パース・検証だけを行う。
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common import settings                       # noqa: E402
from src.lookthrough import health                    # noqa: E402
from src.lookthrough.constituents import (            # noqa: E402
    load_fund_map, load_holdings,
)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="全sourceに実アクセスして確認する")
    ap.add_argument("--fund", default=None, help="このファンドIDだけ試す")
    ap.add_argument("--include-excluded", action="store_true",
                    help="coverage_policy: excluded のファンドも試す")
    args = ap.parse_args(argv)

    fmap = load_fund_map()
    try:
        funds, _, _ = load_holdings()
        names = {f.id: f.name for f in funds}
    except FileNotFoundError:
        names = {}

    if args.fund:
        spec = (fmap.get("funds") or {}).get(args.fund)
        if not spec:
            print(f"[error] {args.fund} は fund_map.yml にありません")
            return 1
        fmap = {"funds": {args.fund: spec}}

    print("各sourceに実アクセスします（1本ずつ、リトライ3回）…\n")
    results = health.probe_all(fmap, names=names,
                               include_excluded=args.include_excluded)

    for r in results:
        mark = "✅" if r.ok else "❌"
        print(f"{mark} {r.fund_name} / {r.source_id} (p{r.priority}) "
              f"… {r.detail} [{r.elapsed_ms}ms]")

    body = health.to_markdown(results, "source 実アクセス検証")
    path = settings.path_of("reports") / "live_verification.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")

    ok_n = sum(1 for r in results if r.ok)
    print(f"\n結果: {ok_n}/{len(results)} 成功")
    print(f"レポート: {path}")

    # ファンド単位で「全滅」しているものがあれば、そこが実運用の穴になる
    dead = _dead_funds(results)
    if dead:
        print("\n⚠ すべてのsourceが失敗したファンド:")
        for fid, name in dead:
            print(f"  - {name}（{fid}）")
        print("  → data/manual/ にCSVを置くか、"
              "coverage_policy を excluded にしてください。")
        return 2
    return 0


def _dead_funds(results) -> list[tuple[str, str]]:
    by_fund: dict[str, list] = {}
    for r in results:
        by_fund.setdefault(r.fund_id, []).append(r)
    return [(fid, rs[0].fund_name) for fid, rs in by_fund.items()
            if not any(r.ok for r in rs)]


if __name__ == "__main__":
    sys.exit(main())
