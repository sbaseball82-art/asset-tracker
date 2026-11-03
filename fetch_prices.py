# -*- coding: utf-8 -*-
"""
fetch_prices.py
===============
ETF・投資信託の価格/基準価額を取得し data.json に保存する。

取得元:
  ETF      : yfinance (Yahoo Finance US)
  USD/JPY  : yfinance (USDJPY=X)
  投資信託  : 投信総合検索ライブラリー 公式CSV (第一候補)
             → 失敗時 Yahoo!ファイナンスJP スクレイピング (フォールバック)

履歴(history)に毎日の総資産を蓄積し、前日比/先週比/先月比/年初来を計算する。
"""

import argparse
import copy
import math
import csv
import io
import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
import yfinance as yf

from config import ETF_HOLDINGS, FUND_HOLDINGS, load_stocks

OUTPUT_FILE = Path("data.json")
JST = timezone(timedelta(hours=9))

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")


# ─────────────────────────────────────────────────────
# 1. USD/JPY
# ─────────────────────────────────────────────────────
def valid_price(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and value > 0)


def quote_fx_dates_match(quote, fx):
    """円建て日次比較は株価と為替の両基準日が一致する場合だけ行う。"""
    return (not quote.get("stale") and not fx.get("stale")
            and not quote.get("corporate_action_review")
            and all(quote.get(key) and quote[key] == fx.get(key)
                    for key in ("curr_date", "prev_date")))


def split_events(frame):
    """取得窓内で提供元が報告した株式分割。数量は自動補正しない。"""
    if "Stock Splits" not in frame:
        return []
    return [{"date": str(index.date()), "ratio": float(ratio)}
            for index, ratio in frame["Stock Splits"].dropna().items()
            if valid_price(float(ratio)) and float(ratio) != 1]


def fetch_fx(existing=None):
    """確認済み価格だけを採用する。未確認の固定レートで補完しない。"""
    try:
        hist = yf.Ticker("USDJPY=X").history(period="5d", interval="1d", auto_adjust=False)
        series = hist["Close"].dropna().sort_index()
        rate, previous = float(series.iloc[-1]), float(series.iloc[-2])
        if not valid_price(rate) or not valid_price(previous):
            raise ValueError("invalid exchange rate")
        return {"rate": round(rate, 4), "prev_rate": round(previous, 4),
                "curr_date": str(series.index[-1].date()), "prev_date": str(series.index[-2].date()),
                "source": "Yahoo Finance USDJPY=X", "stale": False}
    except Exception:
        cached = (existing or {}).get("fx") or {}
        if valid_price(cached.get("rate")) and cached.get("curr_date") and cached.get("source"):
            return {**cached, "stale": True, "fetch_failed": True}
        raise RuntimeError("USD/JPY取得失敗。確認済み為替がないため更新を中止します") from None


def fetch_usdjpy(existing=None) -> float:
    """旧呼出元との互換用。新しい呼出元は日付も返す fetch_fx を使用。"""
    return fetch_fx(existing)["rate"]


def fetch_etf_prices(usdjpy: float, prev_usdjpy=None, fx=None) -> dict:
    results = {}
    prev_usdjpy = prev_usdjpy if valid_price(prev_usdjpy) else usdjpy
    symbols = list(ETF_HOLDINGS.keys())
    print(f"\n[ETF] 取得開始: {', '.join(symbols)}")

    try:
        data = yf.download(
            tickers=symbols, period="5d", interval="1d",
            progress=False, auto_adjust=False, group_by="ticker", actions=True,
        )
    except Exception as e:
        print(f"  ❌ yfinance エラー: {e}")
        return results

    for symbol, (display_name, shares) in ETF_HOLDINGS.items():
        try:
            if len(symbols) == 1:
                series = data["Close"].dropna()
            else:
                series = data[symbol]["Close"].dropna()
            events = split_events(data if len(symbols) == 1 else data[symbol])
            if len(series) < 2:
                print(f"  ⚠️  {symbol}: データ不足")
                continue

            prev_usd = round(float(series.iloc[-2]), 4)
            curr_usd = round(float(series.iloc[-1]), 4)
            if not valid_price(curr_usd) or not valid_price(prev_usd):
                continue
            change_pct = round((curr_usd - prev_usd) / prev_usd * 100, 2)

            results[symbol] = {
                "name": display_name, "type": "ETF", "shares": shares,
                "prev_price": prev_usd, "curr_price": curr_usd,
                "change_pct": change_pct,
                "prev_jpy": round(prev_usd * shares * prev_usdjpy),
                "curr_jpy": round(curr_usd * shares * usdjpy),
                "usdjpy": usdjpy, "source": "Yahoo Finance close",
                "curr_date": str(series.index[-1].date()),
                "prev_date": str(series.index[-2].date()), "stale": False,
                "corporate_action_review": bool(events), "split_events": events,
            }
            row = results[symbol]
            matched = quote_fx_dates_match(row, fx or {})
            row["change_jpy"] = row["curr_jpy"] - row["prev_jpy"] if matched else None
            row["jpy_change_note"] = "基準日一致" if matched else "株価・為替の基準日不一致、旧価格または分割要確認"
            if events:
                row["change_pct"] = None
            print(f"  ✅ {symbol}: ${prev_usd} → ${curr_usd} "
                  f"({change_pct:+.2f}%) ≈ ¥{results[symbol]['curr_jpy']:,}")
        except Exception as e:
            print(f"  ❌ {symbol}: {e}")
    return results


# ─────────────────────────────────────────────────────
# 3a. 投資信託: 投信協会 公式CSV
# ─────────────────────────────────────────────────────
TOUSHIN_CSV = "https://toushin-lib.fwg.ne.jp/FdsWeb/FDST030000/csv-file-download"

def fetch_fund_nav_toushin(assoc_code: str, isin: str) -> dict | None:
    """
    投信協会の公式CSVから時系列の基準価額を取得。
    CSV列(ヘッダ): 年月日,基準価額(円),純資産総額(百万円),...
    返却: {dates:[...], navs:[...]} 新しい順

    **このCSVはISIN必須**。associFundCd だけを渡すと HTTP 200 のまま
    `{"statusCode":null}` の19バイトが返るだけで、CSVにはならない
    (2026-08-12 に全6銘柄で実測。ISINを持つ銘柄でも同じ)。
    そのため ISIN が無ければ叩かずに None を返し、呼び出し側の
    Yahoo! フォールバックに回す。

    ISINが無い銘柄は事実上このフォールバック一本になり、一時障害がそのまま
    その日の欠落になる。config.py には必ずISINを入れること
    (候補の検証は scripts/diagnose_fund_source.py --isin)。
    """
    if not isin:
        print(f"  ❌ {assoc_code} [協会CSV]: ISIN未設定のため取得不可"
              f"(協会CSVはISIN必須)")
        return None
    url = f"{TOUSHIN_CSV}?isinCd={isin}&associFundCd={assoc_code}"
    try:
        res = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        res.raise_for_status()
        # 協会CSVはShift-JIS
        text = res.content.decode("shift_jis", errors="replace")
    except Exception as e:
        print(f"  ❌ {assoc_code} [協会CSV]: {e}")
        return None

    reader = csv.reader(io.StringIO(text))
    dates, navs = [], []
    for row in reader:
        if len(row) < 2:
            continue
        # 1列目が日付(YYYY/MM/DD or YYYY年MM月DD日)の行のみ
        date_raw = row[0].strip()
        m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", date_raw)
        if not m:
            continue
        try:
            nav = float(row[1].replace(",", "").strip())
        except ValueError:
            continue
        ymd = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        dates.append(ymd)
        navs.append(nav)

    if len(navs) < 2:
        return None

    # 新しい順にソート
    pairs = sorted(zip(dates, navs), key=lambda x: x[0], reverse=True)
    dates_s = [p[0] for p in pairs]
    navs_s = [p[1] for p in pairs]
    return {"dates": dates_s, "navs": navs_s}


# ─────────────────────────────────────────────────────
# 3b. 投資信託: Yahoo!ファイナンスJP フォールバック
# ─────────────────────────────────────────────────────
def fetch_fund_nav_yahoo(assoc_code: str) -> dict | None:
    """
    フォールバック: Yahoo!ファイナンスJP の時系列ページから基準価額を推定取得。
    協会CSVが使えない(ISIN未設定など)場合のみ使用。

    時系列テーブルは「日付 → 基準価額 → 純資産総額(百万円)」の順で並ぶため、
    ページ全体から数値を無差別に拾うと純資産総額(桁が大きい)を基準価額と誤認する。
    そこで『日付の直後に来る最初の数値』だけを基準価額として拾い、基準価額として
    妥当な範囲(500〜200,000円/万口)に収まるものだけ採用する。

    協会CSVが使えない銘柄はこのフォールバックしか取得手段が無いため、
    一時的な5xxで1日分を落とさないよう数回リトライする。ステータスを見ずに
    本文をパースするとエラーページを基準価額として読みかけるので、
    2xx以外は本文を捨てる。
    """
    url = f"https://finance.yahoo.co.jp/quote/{assoc_code}/history"
    text = None
    for attempt in range(3):
        if attempt:
            time.sleep(2 ** attempt)   # 2秒 → 4秒
        try:
            res = requests.get(
                url, headers={"User-Agent": UA, "Accept-Language": "ja"},
                timeout=20,
            )
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  {assoc_code} [Yahoo! {attempt + 1}回目]: {type(e).__name__}")
            continue
        if res.status_code == 200:
            text = res.text
            break
        print(f"  ⚠️  {assoc_code} [Yahoo! {attempt + 1}回目]: HTTP {res.status_code}")
    if text is None:
        return None

    # 日付(YYYY/M/D or YYYY年M月D日)ごとに、その直後の最初の数値を基準価額とみなす
    pairs = []
    for m in re.finditer(r"(\d{4})[/年](\d{1,2})[/月](\d{1,2})日?", text):
        tail = text[m.end():m.end() + 400]
        nm = re.search(r"(\d{1,3}(?:,\d{3})+|\d{3,6})(?:\.\d+)?", tail)
        if not nm:
            continue
        v = float(nm.group(1).replace(",", ""))
        if not (500 <= v <= 200000):   # 純資産総額など桁違いの値を除外
            continue
        ymd = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        pairs.append((ymd, v))

    if len(pairs) < 2:
        return None
    # 日付が新しい順に整列(同日重複は先勝ち)
    seen, uniq = set(), []
    for ymd, v in sorted(pairs, key=lambda x: x[0], reverse=True):
        if ymd in seen:
            continue
        seen.add(ymd)
        uniq.append((ymd, v))
    if len(uniq) < 2:
        return None
    return {"dates": [p[0] for p in uniq[:120]],
            "navs": [p[1] for p in uniq[:120]], "estimated": True}


def fetch_fund_prices() -> dict:
    results = {}
    print(f"\n[投資信託] 取得開始")

    for assoc_code, (display_name, units, isin) in FUND_HOLDINGS.items():
        time.sleep(1.0)

        data = fetch_fund_nav_toushin(assoc_code, isin)
        source = "協会CSV"
        if data is None:
            print(f"  ⚠️  {assoc_code}: 協会CSV不可 → Yahoo!フォールバック")
            data = fetch_fund_nav_yahoo(assoc_code)
            source = "Yahoo!(推定)"

        if data is None or len(data["navs"]) < 2:
            print(f"  ❌ {assoc_code} ({display_name}): 取得失敗")
            continue

        navs = data["navs"]
        curr, prev = navs[0], navs[1]
        if not valid_price(curr) or not valid_price(prev):
            continue

        # Yahoo!推定は HTML から粗く数値を拾うため、純資産総額などを誤取得して
        # 基準価額として異常な値になることがある(総資産・履歴を汚染する)。
        # 基準価額として不自然な水準・前日比±20%超は不採用にする(堅牢化)。
        if data.get("estimated"):
            ok = (all(500 <= n <= 200000 for n in (curr, prev))
                  and prev and abs(curr - prev) / prev <= 0.20)
            if not ok:
                print(f"  ❌ {assoc_code} ({display_name}): Yahoo!推定値が異常 "
                      f"(curr={curr:g}, prev={prev:g}) → 不採用(ISIN設定を推奨)")
                continue

        change_pct = round((curr - prev) / prev * 100, 2) if prev else None
        curr_jpy = round(units * curr / 10000) if units else 0
        prev_jpy = round(units * prev / 10000) if (units and prev) else 0

        results[assoc_code] = {
            "name": display_name, "type": "投資信託",
            "fund_code": assoc_code, "units": units,
            "prev_nav": prev, "curr_nav": curr, "change_pct": change_pct,
            "prev_jpy": prev_jpy, "curr_jpy": curr_jpy, "source": source,
            "curr_date": data["dates"][0],
            # 履歴系列(円/万口換算)も保持: 先週比/先月比/年初来用
            "nav_series": [{"date": d, "jpy": round(units * n / 10000)}
                           for d, n in zip(data["dates"], navs)][:120],
        }
        pct = f"{change_pct:+.2f}%" if change_pct is not None else "不明"
        print(f"  ✅ {display_name}: {prev:,.0f}円 → {curr:,.0f}円 "
              f"({pct}) ≈ ¥{curr_jpy:,} [{source}]")
    return results


# ─────────────────────────────────────────────────────
# 4. 期間比較(前日/先週/先月/年初来)
# ─────────────────────────────────────────────────────
def nearest_on_or_before(history: list, target: str):
    """history(date昇順)からtarget日付以前で最も近いレコードを返す。"""
    cands = [h for h in history if h["date"] <= target]
    return cands[-1] if cands else None

def pct(curr, base):
    if not base:
        return None
    return round((curr - base) / base * 100, 2)

def build_comparisons(history: list, curr_total: int, today: datetime) -> dict:
    """history(date昇順,各{date,total_jpy,cash_flow_jpy})から各種比較を作る。

    買い増し・売却(=拠出/引き出し)の影響を除いた『市場変動ベース』の騰落を返す。
    各期間の生の総資産差から、基準日より後に発生した純拠出(cash_flow_jpy)の累計を
    差し引くことで、資金の出し入れではなく相場でどれだけ動いたかを表す。
    """
    comp = {}
    d = today.date()

    def find(days_ago=None, ymd=None, max_lag=4):
        if ymd is None:
            target = (d - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        else:
            target = ymd
        rec = nearest_on_or_before(history, target)
        if rec and (datetime.fromisoformat(target).date()
                    - datetime.fromisoformat(rec["date"]).date()).days > max_lag:
            return None
        return rec

    def contrib_after(base_date: str) -> int:
        # 基準日(排他) < 記録日 <= 当日 の純拠出を合計(当日分を含む)。
        # cash_flow_jpy を持たない旧レコードは 0 とみなす。
        return int(sum(h.get("cash_flow_jpy", 0) or 0
                       for h in history if h["date"] > base_date))

    # 前日比は history の最後から2番目(=前回記録)を使う
    prev_rec = history[-2] if len(history) >= 2 else None
    if prev_rec and prev_rec["date"] != (d - timedelta(days=1)).isoformat():
        prev_rec = None
    week_rec = find(days_ago=7)
    month_rec = find(days_ago=30)
    ytd_rec = find(ymd=f"{d.year - 1}-12-31", max_lag=7)

    for key, rec in (("day", prev_rec), ("week", week_rec),
                     ("month", month_rec), ("ytd", ytd_rec)):
        if rec and any(h.get("stale") or h.get("complete") is False
                       for h in history if rec["date"] <= h["date"] <= d.isoformat()):
            rec = None
        if rec:
            base = rec["total_jpy"]
            gross = curr_total - base            # 総資産の増減(拠出込み)
            contrib = contrib_after(rec["date"])  # 期間中の純拠出(買い増し-売却)
            market = gross - contrib             # 相場による変動(拠出を除外)
            comp[key] = {
                "base_date": rec["date"], "base_jpy": base,
                "change_jpy": market,
                "change_pct": (round(market / base * 100, 2) if base else None),
                "gross_change_jpy": gross,       # 参考: 拠出込みの総資産増減
                "cash_flow_jpy": contrib,
                "method": "quantity_change_at_current_price_estimate",
                "note": "数量差を当日価格で評価した概算。実際の入出金・配当・税手数料は未反映"
            }
        else:
            comp[key] = None
    return comp


# ─────────────────────────────────────────────────────
# 5. 集計 & 保存
# ─────────────────────────────────────────────────────
def calc_total(etf, fund):
    prev = sum(v["prev_jpy"] for v in etf.values()) + \
           sum(v["prev_jpy"] for v in fund.values())
    curr = sum(v["curr_jpy"] for v in etf.values()) + \
           sum(v["curr_jpy"] for v in fund.values())
    return int(prev), int(curr)


def compute_cash_flow(existing: dict, etf: dict, fund: dict, usdjpy: float) -> int:
    """当日の純拠出額(円)を算出する。

    前回 data.json(existing)の保有数量と当日の数量の差 × 当日価格の合計。
    買い増し=正、売却=負。新規銘柄は前回数量0として全量が拠出扱いになる。
    前回データが無い(初回)場合や数量に変化がなければ 0。
    FXや価格改定の影響を含まないよう、価格ではなく『数量の差』だけを見る。
    """
    if not existing:
        return 0
    prev_etf = existing.get("etf") or {}
    prev_fund = existing.get("fund") or {}
    flow = 0.0

    def etf_unit_jpy(v):   # 1株あたり当日円価
        if v.get("shares"):
            return v["curr_jpy"] / v["shares"]
        return (v.get("curr_price") or 0) * usdjpy

    def fund_unit_jpy(v):  # 1口あたり当日円価
        if v.get("units"):
            return v["curr_jpy"] / v["units"]
        return (v.get("curr_nav") or 0) / 10000

    for sym, v in etf.items():
        d_sh = (v.get("shares") or 0) - (prev_etf.get(sym, {}).get("shares") or 0)
        if d_sh:
            flow += d_sh * etf_unit_jpy(v)
    for code, v in fund.items():
        d_u = (v.get("units") or 0) - (prev_fund.get(code, {}).get("units") or 0)
        if d_u:
            flow += d_u * fund_unit_jpy(v)
    return int(round(flow))


def carry_forward_missing(existing: dict, etf: dict, fund: dict, usdjpy: float):
    """取得失敗した保有を前回 data.json の値で補完する(堅牢化)。

    ある銘柄の価格取得に失敗すると、その銘柄が総資産から丸ごと抜け、履歴に
    『見かけ上の急落』として残り、以後の先週比/先月比/年初来まで狂わせてしまう。
    これを防ぐため、前回値がある銘柄は最終価格を据え置き(当日変化は不明=0%扱い)、
    現在の数量・為替で円換算し直して総資産に含める。
    一度も取得できていない新規銘柄は補完材料が無いため対象外(欠落のまま)。
    """
    prev_etf = existing.get("etf") or {}
    prev_fund = existing.get("fund") or {}

    for sym, (name, shares) in ETF_HOLDINGS.items():
        if sym in etf or sym not in prev_etf:
            continue
        price = prev_etf[sym].get("curr_price")
        if not valid_price(price):
            continue
        jpy = round(price * shares * usdjpy)
        etf[sym] = {
            "name": name, "type": "ETF", "shares": shares,
            "prev_price": price, "curr_price": price, "change_pct": None,
            "prev_jpy": jpy, "curr_jpy": jpy, "usdjpy": usdjpy, "stale": True,
            "curr_date": prev_etf[sym].get("curr_date"), "prev_date": None,
            "source": "確認済み保存価格(取得失敗)", "fetch_failed": True,
            "change_jpy": None, "jpy_change_note": "価格取得失敗",
            "corporate_action_review": prev_etf[sym].get("corporate_action_review", False),
            "split_events": prev_etf[sym].get("split_events", []),
        }
        print(f"  ⚠️  {sym}: 取得失敗 → 前日値で補完 (¥{jpy:,})")

    for code, (name, units, isin) in FUND_HOLDINGS.items():
        if code in fund or code not in prev_fund:
            continue
        nav = prev_fund[code].get("curr_nav")
        if not valid_price(nav):
            continue
        jpy = round(units * nav / 10000)
        fund[code] = {
            "name": name, "type": "投資信託", "fund_code": code, "units": units,
            "prev_nav": nav, "curr_nav": nav, "change_pct": None,
            "prev_jpy": jpy, "curr_jpy": jpy, "source": "前日値(取得失敗)",
            "curr_date": prev_fund[code].get("curr_date", ""), "stale": True,
            "nav_series": prev_fund[code].get("nav_series", []),
        }
        print(f"  ⚠️  {code} ({name}): 取得失敗 → 前日値で補完 (¥{jpy:,})")

    return etf, fund


def main():
    now = datetime.now(JST)
    today = now.strftime("%Y-%m-%d")
    existing = json.loads(OUTPUT_FILE.read_text(encoding="utf-8")) if OUTPUT_FILE.exists() else {}
    fx = fetch_fx(existing)
    usdjpy = fx["rate"]
    etf = fetch_etf_prices(usdjpy, fx.get("prev_rate"), fx)
    fund = fetch_fund_prices()
    etf, fund = carry_forward_missing(existing, etf, fund, usdjpy)
    missing = (set(ETF_HOLDINGS) - set(etf)) | (set(FUND_HOLDINGS) - set(fund))
    if missing:
        raise RuntimeError("価格未取得の銘柄があります。部分合計を総資産として保存しません")
    warnings = mark_freshness(etf, fund, fx, now)
    for warning in warnings:
        print("::warning::" + warning)
    prev_total, curr_total = calc_total(etf, fund)
    if curr_total == 0:
        raise RuntimeError("資産評価額が0のため更新を中止します")
    cash_flow_jpy = compute_cash_flow(existing, etf, fund, usdjpy)
    if existing.get("date") == today:
        for row in existing.get("history", []):
            if row.get("date") == today:
                cash_flow_jpy += int(row.get("cash_flow_jpy", 0) or 0)
                break
    history = [row for row in existing.get("history", []) if row.get("date") != today]
    history.append({"date": today, "total_jpy": curr_total, "usdjpy": usdjpy,
                    "cash_flow_jpy": cash_flow_jpy, "complete": True, "stale": bool(warnings)})
    history = sorted(history, key=lambda row: row["date"])[-400:]
    comparisons = build_comparisons(history, curr_total, now)
    day = comparisons.get("day") or {}
    output = {"updated_at": now.isoformat(), "date": today, "usdjpy": usdjpy, "fx": fx,
              "complete": True, "status": "degraded" if warnings else "ok", "warnings": warnings,
              "total_jpy": curr_total, "day_change_jpy": day.get("change_jpy"),
              "day_change_pct": day.get("change_pct"), "comparisons": comparisons,
              "etf": etf, "fund": fund, "history": history}
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(f"{OUTPUT_FILE} を保存しました（履歴 {len(history)} 日分）")



def mark_freshness(etf, fund, fx, now):
    """休日を含む4暦日を超える価格、または基準日不明を明示する。"""
    warnings = []
    for symbol, row in list(etf.items()) + list(fund.items()) + [("USD/JPY", fx)]:
        try:
            quote_date = datetime.fromisoformat(row["curr_date"]).date()
            age = (now.date() - quote_date).days
            outdated = age > 4 or age < 0
        except (KeyError, TypeError, ValueError):
            outdated = True
        if outdated:
            row["stale"] = True
        if row.get("stale"):
            warnings.append(f"{symbol}: 取得失敗・価格が古い・基準日不明のいずれか。価格基準日を確認してください")
        if row.get("corporate_action_review"):
            warnings.append(f"{symbol}: 株式分割を検出。保有数量・取得単価・入出金の要確認（自動補正なし）")
    return warnings


def stock_valuation(meta, quote, fx):
    """個別株の計算。取得時為替未設定なら円建て取得損益を推測しない。"""
    shares = meta.get("shares")
    price = quote.get("curr_price")
    missing = shares is None or not valid_price(price) or not valid_price(fx.get("rate"))
    row = {**meta, **quote, "type": "個別株", "shares": shares,
           "missing": missing, "curr_jpy": None, "prev_jpy": None,
           "usdjpy": fx.get("rate"), "unrealized_gain_usd": None,
           "unrealized_jpy": None, "unrealized_pct": None,
           "cost_basis_status": "未設定"}
    if missing:
        return row
    row["curr_jpy"] = round(price * shares * fx["rate"])
    matched = quote_fx_dates_match(quote, fx)
    row["jpy_change_note"] = "基準日一致" if matched else "株価・為替の基準日不一致、旧価格または分割要確認"
    if valid_price(quote.get("prev_price")) and valid_price(fx.get("prev_rate")) and matched:
        row["prev_jpy"] = round(quote["prev_price"] * shares * fx["prev_rate"])
        row["change_jpy"] = row["curr_jpy"] - row["prev_jpy"]
    else:
        row["change_jpy"] = None
    if quote.get("corporate_action_review"):
        row["change_pct"] = None
    cost = meta.get("purchase_price_usd")
    if valid_price(cost):
        row["unrealized_gain_usd"] = round((price - cost) * shares, 2)
        row["unrealized_pct"] = round((price - cost) / cost * 100, 2)
        row["cost_basis_status"] = "USD建て・税手数料除外"
        purchase_fx = meta.get("purchase_usdjpy")
        if valid_price(purchase_fx):
            row["unrealized_jpy"] = row["curr_jpy"] - round(cost * shares * purchase_fx)
            row["cost_basis_status"] = "取得時為替設定済・税手数料除外"
    return row


def fetch_stock_prices(stocks, fx, previous=None):
    results = {}
    previous = previous or {}
    for symbol, meta in stocks.items():
        quote = {"curr_price": None, "prev_price": None, "change_pct": None,
                 "curr_date": None, "prev_date": None, "stale": False,
                 "source": "Yahoo Finance close"}
        if meta.get("shares") is not None:
            try:
                hist = yf.Ticker(symbol).history(period="5d", interval="1d", auto_adjust=False, actions=True)
                series = hist["Close"].dropna().sort_index()
                price, prev = float(series.iloc[-1]), float(series.iloc[-2])
                if not valid_price(price) or not valid_price(prev):
                    raise ValueError("invalid stock price")
                quote.update(curr_price=price, prev_price=prev,
                             curr_date=str(series.index[-1].date()), prev_date=str(series.index[-2].date()),
                             change_pct=round((price - prev) / prev * 100, 2))
                events = split_events(hist)
                quote.update(corporate_action_review=bool(events), split_events=events)
            except Exception:
                cached = previous.get(symbol, {})
                if valid_price(cached.get("curr_price")) and cached.get("curr_date"):
                    quote.update(curr_price=cached["curr_price"], curr_date=cached["curr_date"],
                                 source="確認済み保存価格(取得失敗)",
                                 corporate_action_review=cached.get("corporate_action_review", False),
                                 split_events=cached.get("split_events", []))
                quote.update(stale=True, fetch_failed=True)
        results[symbol] = stock_valuation(meta, quote, fx)
    return results


def portfolio_snapshot(public, previous, stocks, now):
    """既存11銘柄と個別株を統合する。統合前の履歴は接続しない。"""
    etf, fund = copy.deepcopy(public.get("etf", {})), copy.deepcopy(public.get("fund", {}))
    fx = copy.deepcopy(public.get("fx") or {
        "rate": None, "prev_rate": None, "curr_date": None, "prev_date": None,
        "source": "旧データ・価格基準日不明", "stale": True})
    warnings = mark_freshness(etf, fund, fx, now)
    warnings += mark_freshness(stocks, {}, fx, now)
    if public.get("date") != now.strftime("%Y-%m-%d"):
        warnings.append("ETF・投資信託の取得結果が本日更新されていません")
    rows = list(etf.values()) + list(fund.values()) + list(stocks.values())
    complete = (bool(stocks) and valid_price(fx.get("rate"))
                and set(etf) == set(ETF_HOLDINGS) and set(fund) == set(FUND_HOLDINGS)
                and all(not row.get("missing") and isinstance(row.get("curr_jpy"), (int, float))
                        and math.isfinite(row["curr_jpy"]) and row["curr_jpy"] >= 0 for row in rows))
    known = sum(row["curr_jpy"] for row in rows if isinstance(row.get("curr_jpy"), (int, float))
                and math.isfinite(row["curr_jpy"]) and row["curr_jpy"] >= 0)
    total = known if complete else None
    quantities_match = (all(row.get("shares") == ETF_HOLDINGS[symbol][1]
                            for symbol, row in etf.items() if symbol in ETF_HOLDINGS)
                        and all(row.get("units") == FUND_HOLDINGS[symbol][1]
                                for symbol, row in fund.items() if symbol in FUND_HOLDINGS))
    if not quantities_match:
        complete = False
        total = None
        warnings.append("ETF・投資信託の数量が設定と異なります。先に通常の価格更新を実行してください")
    if not complete:
        warnings.append("保有数量または価格が未取得のため総資産・運用変動は未確定です")
    history = copy.deepcopy(previous.get("history", []))
    date = now.strftime("%Y-%m-%d")
    if complete:
        flow = compute_cash_flow(previous, etf, fund, fx["rate"])
        if previous:
            for symbol, row in stocks.items():
                old_shares = previous.get("stocks", {}).get(symbol, {}).get("shares") or 0
                flow += round((row["shares"] - old_shares) * row["curr_price"] * fx["rate"])
        if previous.get("date") == date:
            flow += sum(row.get("cash_flow_jpy", 0) for row in history if row["date"] == date)
        history = [row for row in history if row["date"] != date]
        history.append({"date": date, "total_jpy": total, "usdjpy": fx["rate"],
                        "cash_flow_jpy": flow, "complete": True, "stale": bool(warnings),
                        "cash_flow_method": "quantity_change_at_current_price_estimate"})
        history = sorted(history, key=lambda row: row["date"])[-400:]
    comparisons = build_comparisons(history, total, now) if complete else dict.fromkeys(("day", "week", "month", "ytd"))
    day = comparisons.get("day") or {}
    for row in rows:
        row["weight_pct"] = round(row["curr_jpy"] / total * 100, 2) if total and row.get("curr_jpy") is not None else None
    return {"updated_at": now.isoformat(), "date": date,
            "price_data_updated_at": public.get("updated_at"), "usdjpy": fx.get("rate"), "fx": fx,
            "total_jpy": total, "known_total_jpy": known, "complete": complete,
            "status": "incomplete" if not complete else "degraded" if warnings else "ok",
            "warnings": list(dict.fromkeys(warnings)),
            "day_change_jpy": day.get("change_jpy"), "day_change_pct": day.get("change_pct"),
            "comparisons": comparisons, "etf": etf, "fund": fund, "stocks": stocks,
            "history": history, "legacy_history": public.get("history", []),
            "history_note": "統合資産の履歴は初回取得から。旧11銘柄の履歴はlegacy_historyに保存し接続しません",
            "performance_note": "数量差を当日価格で評価した概算拠出を除外。配当・税金・手数料・実取引価格は未反映",
            "corporate_action_note": "株式分割・併合等の数量と取得単価は自動補正しません。取得窓外または提供元未報告の企業行動は未検知のため、証券口座の保有数量と照合してください"}


def portfolio_main():
    public = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    destination = Path("portfolio.json")
    cache_path = Path("portfolio_last_complete.json")
    previous = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    fx = public.get("fx") or {"rate": None, "prev_rate": None, "curr_date": None, "stale": True}
    stocks = fetch_stock_prices(load_stocks(), fx, previous.get("stocks"))
    output = portfolio_snapshot(public, previous, stocks, datetime.now(JST))
    from src.portfolio_analysis import analyze
    output["analysis"] = analyze(output)
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    if output["complete"]:
        cache_path.write_text(destination.read_text(encoding="utf-8"), encoding="utf-8")
    print("統合ダッシュボードデータを更新しました。状態: " + output["status"])
    if output["status"] == "degraded":
        print("::warning::価格の取得失敗・古い価格があります。ダッシュボードの価格基準日を確認してください")
    return 0 if output["complete"] else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="既存11銘柄または個別株を含む統合資産を更新")
    parser.add_argument("--portfolio", action="store_true", help="既存data.jsonと個別株設定からportfolio.jsonを生成")
    args = parser.parse_args()
    if args.portfolio:
        raise SystemExit(portfolio_main())
    main()
