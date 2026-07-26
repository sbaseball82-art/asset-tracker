# -*- coding: utf-8 -*-
"""
sync_holdings_yml.py
====================
data.json（毎朝の価格取得結果）から data/holdings.yml（保有と比率）を再生成する。
機能A/Bの生成スクリプトはこのYAMLを読む。

使い方: python scripts/log_metrics.py と同様にリポジトリルートで
  python scripts/sync_holdings_yml.py
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common.util import save_yaml  # noqa: E402

JST = timezone(timedelta(hours=9))


def main():
    data_path = ROOT / "data.json"
    if not data_path.exists():
        print("[error] data.json がありません")
        sys.exit(1)
    data = json.loads(data_path.read_text(encoding="utf-8"))
    total = data.get("total_jpy") or 0
    if total <= 0:
        print("[error] total_jpy が不正です")
        sys.exit(1)

    funds = []
    for section, id_key in (("etf", "symbol"), ("fund", "code")):
        for key, v in (data.get(section) or {}).items():
            jpy = v.get("curr_jpy") or 0
            funds.append({
                "id": key,
                "name": v.get("name", key),
                "kind": section,
                "value_jpy": int(round(jpy)),
                "share_pct": round(jpy / total * 100, 2),
            })
    funds.sort(key=lambda x: -x["value_jpy"])

    out = {
        "generated_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"),
        "source": "data.json（毎朝の自動取得結果）",
        "total_jpy": int(total),
        "usdjpy": data.get("usdjpy"),
        "funds": funds,
    }
    save_yaml(ROOT / "data" / "holdings.yml", out)
    print(f"[ok] data/holdings.yml を更新（{len(funds)}銘柄 / 総額 ¥{int(total):,}）")


if __name__ == "__main__":
    main()
