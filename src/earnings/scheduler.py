# -*- coding: utf-8 -*-
"""
scheduler.py（機能B: 毎時実行の判定役）
=======================================
GitHub Actions から毎時呼ばれ、決算カレンダーを見て
「いま生成すべきタイミング」だけを実行する。

  pre     … 発表90分前〜発表時刻の間（毎時cronでもT-60分相当を拾える）
  post    … 発表後〜6時間の間（まだ生成していなければ）
  morning … 翌朝 7:00-10:00 JST（cron遅延も許容）に、
            直近30時間以内に発表があった銘柄について生成

生成済みかどうかは output/earnings/*/{phase}.txt の有無で判定する
（再実行しても二重生成しない）。
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.common.util import JST, REPO_ROOT, load_yaml, now_jst
from src.earnings.generate import generate

PRE_WINDOW_MIN = 90        # 発表90分前から
POST_WINDOW_HOURS = 6      # 発表後6時間まで
MORNING_HOURS = (7, 10)    # 7:00-10:59 JST
MORNING_LOOKBACK_H = 30


def _parse_jst(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=JST)


def _done(date_str: str, ticker: str, phase: str) -> bool:
    return (REPO_ROOT / "output" / "earnings"
            / f"{date_str}_{ticker}" / f"{phase}.txt").exists()


def due_phases(event: dict, now: datetime) -> list[str]:
    """このイベントについて、いま生成すべきphaseのリストを返す。"""
    announce = _parse_jst(str(event["announce_jst"]))
    date_str = str(event["date"])
    ticker = event["ticker"]
    phases = []

    if (announce - timedelta(minutes=PRE_WINDOW_MIN) <= now < announce
            and not _done(date_str, ticker, "pre")):
        phases.append("pre")

    if (announce <= now <= announce + timedelta(hours=POST_WINDOW_HOURS)
            and not _done(date_str, ticker, "post")):
        phases.append("post")

    if (MORNING_HOURS[0] <= now.hour <= MORNING_HOURS[1]
            and timedelta(0) <= now - announce <= timedelta(hours=MORNING_LOOKBACK_H)
            and not _done(date_str, ticker, "morning")):
        phases.append("morning")

    return phases


def main(argv=None) -> int:
    now = now_jst()
    if argv and "--at" in argv:  # テスト用: 時刻を固定
        now = _parse_jst(argv[argv.index("--at") + 1])

    cal = load_yaml(REPO_ROOT / "data" / "earnings_calendar.yml",
                    default={"events": []})
    generated = 0
    for ev in cal.get("events", []):
        for phase in due_phases(ev, now):
            print(f"[run] {ev['ticker']} {ev['date']} {phase}")
            try:
                generate(ev["ticker"], str(ev["date"]), phase)
                generated += 1
            except SystemExit as e:
                print(f"[warn] スキップ: {e}")
            except Exception as e:  # noqa: BLE001
                print(f"::warning::{ev['ticker']} {phase} 生成失敗: {e}")
    print(f"[done] {generated}件生成（{now.strftime('%Y-%m-%d %H:%M JST')}）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
