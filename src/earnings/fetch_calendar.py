# -*- coding: utf-8 -*-
"""
fetch_calendar.py
=================
watchlist銘柄の決算日程を Finnhub（無料枠）から取得して
data/earnings_calendar.yml に追記する。

- FINNHUB_API_KEY が無ければ何もしない（YAMLの手動管理で運用継続）
- 既存エントリ（date+ticker が同じ）は上書きしない
  （announce_jst を人間が調整している可能性があるため）
- 発表時刻: Finnhub の hour（bmo=寄り前/amc=引け後）から日本時間を概算。
  不明なら announce_jst を「要手動入力」にせず、引け後(翌朝05:05 JST)を
  既定にし note に「時刻は概算」と明記する。
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.common.util import REPO_ROOT, load_yaml, save_yaml
from src.earnings.data_sources import _finnhub_get

CAL_PATH = REPO_ROOT / "data" / "earnings_calendar.yml"


def _announce_jst(d: str, hour: str | None) -> str:
    """米国発表日と時間帯から日本時間の概算を作る（夏時間ベース）。"""
    day = date.fromisoformat(d)
    if hour == "bmo":  # 寄り前 ≒ 現地朝7時 ≒ 同日20:00 JST
        return f"{day} 20:00"
    # amc/不明 → 引け後 ≒ 現地16:05 ≒ 翌朝05:05 JST
    return f"{day + timedelta(days=1)} 05:05"


def main() -> int:
    wl = load_yaml(REPO_ROOT / "data" / "watchlist.yml", default={})
    tickers = list((wl.get("tickers") or {}).keys())
    frm = date.today().isoformat()
    to = (date.today() + timedelta(days=45)).isoformat()

    data = _finnhub_get("calendar/earnings", {"from": frm, "to": to})
    if data is None:
        print("[skip] FINNHUB_API_KEY 未設定 or 取得失敗。カレンダーは手動管理のまま")
        return 0

    cal = load_yaml(CAL_PATH, default={"events": []})
    existing = {(str(e["date"]), e["ticker"]) for e in cal.get("events", [])}
    added = 0
    for row in data.get("earningsCalendar", []):
        sym, d = row.get("symbol"), row.get("date")
        if sym not in tickers or not d or (d, sym) in existing:
            continue
        cal["events"].append({
            "date": d, "ticker": sym, "type": "earnings",
            "announce_jst": _announce_jst(d, row.get("hour")),
            "session": "寄り前" if row.get("hour") == "bmo" else "引け後",
            "note": "Finnhub自動追記・時刻は概算",
        })
        added += 1
    if added:
        cal["events"].sort(key=lambda e: str(e["date"]))
        save_yaml(CAL_PATH, cal)
    print(f"[done] {added}件追記")
    return 0


if __name__ == "__main__":
    sys.exit(main())
