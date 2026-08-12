# -*- coding: utf-8 -*-
"""
data.json の各銘柄がどの取得元から来たかを一覧し、劣化していれば警告を出す。

`前日値(取得失敗)` や `Yahoo!(推定)` に落ちても、これまでは data.json の
奥にある source 文字列に残るだけで、誰も見ないまま何日も経ってしまった。
GitHub Actions の警告アノテーションとして出しておけば実行ページで目に入る。

パイプラインを止めたくないので、劣化していても exit 0 にする。
1銘柄の取得失敗でスライド生成ごと落とすのはやり過ぎで、
値そのものは前日値で埋まっており総資産の桁が壊れるわけではないため。
止めるべき異常(口数のズレなど)は tests/test_holdings_sync.py が落とす。
"""

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "data.json"

# これ以外の source は「劣化」とみなす
HEALTHY_FUND_SOURCE = "協会CSV"


def warn(msg: str) -> None:
    """GitHub Actions の警告アノテーション(ローカルでは普通の行)。"""
    print(f"::warning::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"警告: {msg}")


def main() -> int:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    degraded = []

    print(f"基準日: {data['date']}  USD/JPY: {data['usdjpy']}")
    print("\n投資信託")
    newest = max((v.get("curr_date") or "") for v in data["fund"].values())
    for code, v in data["fund"].items():
        mark = "  " if v["source"] == HEALTHY_FUND_SOURCE else "!!"
        print(f" {mark} {v['name']:<24} {v['source']:<16} 基準日 {v.get('curr_date', '?')}")
        if v["source"] != HEALTHY_FUND_SOURCE:
            degraded.append((code, v))
        elif v.get("curr_date") and v["curr_date"] < newest:
            degraded.append((code, v))

    print("\nETF")
    for sym, v in data["etf"].items():
        stale = v.get("stale")
        print(f" {'!!' if stale else '  '} {v['name']:<24} {'前日値(取得失敗)' if stale else 'Yahoo Finance'}")
        if stale:
            degraded.append((sym, v))

    for key, v in degraded:
        share = v["curr_jpy"] / data["total_jpy"] * 100
        warn(
            f"{key} ({v['name']}) の価格が正規の取得元から取れていません: "
            f"source={v.get('source', '前日値(取得失敗)')} "
            f"基準日={v.get('curr_date', '?')} 全体の{share:.1f}%。"
            " 続くようなら scripts/diagnose_fund_source.py で切り分けること"
        )

    print(f"\n劣化: {len(degraded)}件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
