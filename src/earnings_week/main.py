# -*- coding: utf-8 -*-
"""
main.py
=======
週次・米国決算カレンダー画像のエントリポイント。

    python -m src.earnings_week.main                      # 翌週ぶんを生成
    python -m src.earnings_week.main --week-start 2026-08-31
    python -m src.earnings_week.main --sample             # ダミーデータでレイアウト確認
    python -m src.earnings_week.main --offline            # プロフィール/ロゴはキャッシュのみ

出すもの
--------
* ``output/earnings_week/earnings_YYYYMMDD.png`` と ``.jpg``
* ``qa/earnings_YYYYMMDD_thumb.png``（幅400px。目視確認用）

**成果物は画像だけ。** 投稿文はこのリポジトリでは作らない。

終了コード
----------
* 0 … 生成できた
* 2 … DATA WAIT（その週に対象が無い。**ダミーで作らない**）
* 1 … 異常（APIキー無し・取得失敗・品質検査に落ちた等）

``--sample`` は tests/fixtures/earnings_week_sample.json だけを読み、
``output/earnings_week/sample/`` にしか書かない。本番の出力・キャッシュには触れない。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.earnings_week import qa, render          # noqa: E402
from src.earnings_week.render import Company      # noqa: E402

THEME_PATH = REPO_ROOT / "config" / "theme.json"
WATCHLIST_PATH = REPO_ROOT / "config" / "watchlist.json"
SAMPLE_PATH = REPO_ROOT / "tests" / "fixtures" / "earnings_week_sample.json"
CACHE_DIR = REPO_ROOT / "cache"
OUT_DIR = REPO_ROOT / "output" / "earnings_week"
QA_DIR = REPO_ROOT / "qa"

EXIT_OK, EXIT_ERROR, EXIT_DATA_WAIT = 0, 1, 2


class DataWait(RuntimeError):
    """その週に載せる会社が無い。画像は作らない（ダミーで埋めない）。"""


# ---------------------------------------------------------------- 入出力


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_watchlist(path: Path = WATCHLIST_PATH) -> list[str]:
    """config/watchlist.json（{"tickers": [...]} でも [...] でも読める）。"""
    data = load_json(path)
    tickers = data.get("tickers", data) if isinstance(data, dict) else data
    if not isinstance(tickers, list) or not tickers:
        raise RuntimeError(f"watchlist が空です: {path}")
    return [str(t).strip().upper() for t in tickers if str(t).strip()]


def step_summary(lines: list[str]) -> None:
    """GitHub Actions のサマリーに書く（ローカルでは何もしない）。"""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------- 収集


def collect_live(week_start: date, theme: dict, offline: bool,
                 token: str | None = None) -> tuple[list[Company], int, list[str]]:
    """本番データを集めて (掲載する会社, ほか何社, ロゴ失敗) を返す。"""
    from src.earnings_week import fetch_earnings as fe
    from src.earnings_week import fetch_profile as fp

    start, end = fe.week_bounds(week_start)
    key = fe.api_key(token)
    watchlist = load_watchlist()

    raw = fe.fetch_calendar(start, end, key)
    matched = fe.dedupe(fe.filter_watchlist(raw, watchlist))
    print(f"[count] 取得社数={len(raw)} / watchlist該当数={len(matched)} "
          f"/ watchlist登録={len(watchlist)}")

    if not raw:
        raise DataWait(f"Finnhub が {start}〜{end} の決算を1件も返しませんでした")
    if not matched:
        raise DataWait(
            f"{start}〜{end} に watchlist の銘柄の決算がありません"
            f"（APIは{len(raw)}件返しています）")

    enriched, missing_logo = fp.enrich(matched, key, CACHE_DIR, offline=offline)
    ranked = fp.sort_by_market_cap(enriched)
    limit = theme["layout"]["max_companies"]
    listed, others = ranked[:limit], max(0, len(ranked) - limit)

    companies = [Company(symbol=e["symbol"], name=e.get("name") or "",
                         date=e["date"], hour=e.get("hour") or "",
                         eps_estimate=e.get("eps_estimate"),
                         revenue_estimate=e.get("revenue_estimate"),
                         market_cap=e.get("market_cap"),
                         logo_path=e.get("logo_path"))
                 for e in listed]
    shown = {c.symbol for c in companies}
    return companies, others, [s for s in missing_logo if s in shown]


def collect_sample(theme: dict) -> tuple[list[Company], date, int]:
    """レイアウト確認用のダミーデータ。本番の取得元には一切触れない。"""
    data = load_json(SAMPLE_PATH)
    limit = theme["layout"]["max_companies"]
    rows = data["companies"]
    companies = [Company(symbol=c["symbol"], name=c.get("name", ""),
                         date=c["date"], hour=c.get("hour") or "",
                         eps_estimate=c.get("epsEstimate"),
                         revenue_estimate=c.get("revenueEstimate"),
                         market_cap=c.get("marketCapitalization"))
                 for c in rows[:limit]]
    return companies, date.fromisoformat(data["week_start"]), max(0, len(rows) - limit)


# ---------------------------------------------------------------- 本体


def run(args: argparse.Namespace) -> int:
    theme = load_json(args.theme)
    handle = str(theme.get("handle") or "@84m5dm9xdm")

    if args.sample:
        companies, week_start, others = collect_sample(theme)
        out_dir = Path(args.out_dir) / "sample"
        qa_dir = Path(args.qa_dir) / "sample"
        missing_logo: list[str] = [c.symbol for c in companies]
    else:
        week_start = (date.fromisoformat(args.week_start) if args.week_start
                      else None)
        if week_start is None:
            from src.earnings_week.fetch_earnings import next_week_start
            week_start = next_week_start(date.today())
        companies, others, missing_logo = collect_live(
            week_start, theme, offline=args.offline)
        out_dir, qa_dir = Path(args.out_dir), Path(args.qa_dir)

    from src.earnings_week.fetch_earnings import week_bounds
    start, end = week_bounds(week_start)

    result = render.render_week(companies, start, end, theme, others=others,
                                handle=handle, sample=args.sample)
    qa.verify(result.image, result.report,
              (theme["canvas"]["width"], theme["canvas"]["height"]))

    stem = render.output_stem(start)
    paths = render.save(result.image, out_dir, stem, theme)
    thumb = qa.write_thumbnail(result.image, qa_dir / f"{stem}_thumb.png",
                               theme["qa"]["thumbnail_width"])

    print(f"[count] 掲載数={len(companies)} / ほか={others}社 "
          f"/ ロゴ取得失敗={len(missing_logo)}"
          f"{'（' + ', '.join(missing_logo) + '）' if missing_logo else ''}")
    print(f"[out] {paths['png']}")
    print(f"[out] {paths['jpg']}")
    print(f"[out] {thumb}")

    step_summary([
        f"## ✅ 決算カレンダー画像を生成しました（{start} 〜 {end}）",
        "",
        "| 項目 | 値 |",
        "|---|---|",
        f"| 掲載社数 | {len(companies)} |",
        f"| 掲載しなかった社数 | {others} |",
        f"| ロゴ取得失敗 | {len(missing_logo)}"
        f"{'（' + ', '.join(missing_logo) + '）' if missing_logo else ''} |",
        f"| 出力 | `{paths['png'].name}` / `{paths['jpg'].name}` |",
        "",
        "サムネイル（幅400px）は artifact の `qa/` に入っています。",
    ])
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="その週に決算を発表する米国企業の一覧画像を作る（画像のみ）")
    ap.add_argument("--week-start", help="対象週の任意の日 YYYY-MM-DD（既定: 翌週）")
    ap.add_argument("--sample", action="store_true",
                    help="ダミーデータでレイアウトだけ確認する（APIを叩かない）")
    ap.add_argument("--offline", action="store_true",
                    help="企業プロフィール・ロゴはキャッシュのみ使う")
    ap.add_argument("--theme", type=Path, default=THEME_PATH)
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--qa-dir", default=str(QA_DIR))
    args = ap.parse_args(argv)

    try:
        return run(args)
    except DataWait as exc:
        print(f"[DATA WAIT] {exc}")
        step_summary([
            "## ⏸ DATA WAIT（画像は作っていません）",
            "",
            f"> {exc}",
            "",
            "対象が無い週にダミーの数字で画像を作ることはしません。",
            "watchlist（`config/watchlist.json`）の見直しか、"
            "`week_start` を指定した手動実行で再確認してください。",
        ])
        return EXIT_DATA_WAIT
    except qa.QAError as exc:
        print(f"[QA NG] {exc}")
        step_summary(["## ❌ 画像の品質検査に落ちました", "", "```", str(exc), "```"])
        return EXIT_ERROR
    except Exception as exc:  # noqa: BLE001 — 理由を必ずサマリーに残す
        print(f"[ERROR] {type(exc).__name__}: {exc}")
        step_summary([f"## ❌ 生成に失敗しました（{type(exc).__name__}）", "",
                      "```", str(exc), "```"])
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
