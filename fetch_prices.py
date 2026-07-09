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

import csv
import io
import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
import yfinance as yf

from config import ETF_HOLDINGS, FUND_HOLDINGS

OUTPUT_FILE = Path("data.json")
JST = timezone(timedelta(hours=9))

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")


# ─────────────────────────────────────────────────────
# 1. USD/JPY
# ─────────────────────────────────────────────────────
def fetch_usdjpy() -> float:
    try:
        hist = yf.Ticker("USDJPY=X").history(period="5d", interval="1d")
        rate = float(hist["Close"].dropna().iloc[-1])
        print(f"[USD/JPY] {rate:.2f} 円")
        return round(rate, 2)
    except Exception as e:
        print(f"[USD/JPY] 取得失敗: {e} → 150.00 を使用")
        return 150.00


# ─────────────────────────────────────────────────────
# 2. ETF (yfinance)
# ─────────────────────────────────────────────────────
def fetch_etf_prices(usdjpy: float) -> dict:
    results = {}
    symbols = list(ETF_HOLDINGS.keys())
    print(f"\n[ETF] 取得開始: {', '.join(symbols)}")

    try:
        data = yf.download(
            tickers=symbols, period="5d", interval="1d",
            progress=False, auto_adjust=True, group_by="ticker",
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
            if len(series) < 2:
                print(f"  ⚠️  {symbol}: データ不足")
                continue

            prev_usd = round(float(series.iloc[-2]), 4)
            curr_usd = round(float(series.iloc[-1]), 4)
            change_pct = round((curr_usd - prev_usd) / prev_usd * 100, 2)

            results[symbol] = {
                "name": display_name, "type": "ETF", "shares": shares,
                "prev_price": prev_usd, "curr_price": curr_usd,
                "change_pct": change_pct,
                "prev_jpy": round(prev_usd * shares * usdjpy),
                "curr_jpy": round(curr_usd * shares * usdjpy),
                "usdjpy": usdjpy,
            }
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
    """
    if not isin:
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
    フォールバック: Yahoo!ファイナンスJP の時系列ページから直近2件を推定取得。
    協会CSVが使えない(ISIN未設定など)場合のみ使用。
    """
    url = f"https://finance.yahoo.co.jp/quote/{assoc_code}/history"
    try:
        res = requests.get(
            url, headers={"User-Agent": UA, "Accept-Language": "ja"},
            timeout=20,
        )
        text = res.text
        # 基準価額らしき4-6桁の数値(カンマ区切り含む)を抽出
        nums = []
        for mt in re.finditer(r"(\d{1,3}(?:,\d{3})+|\d{4,6})", text):
            v = int(mt.group(1).replace(",", ""))
            if 1000 <= v <= 999999:
                nums.append(float(v))
        if len(nums) >= 2:
            return {"dates": ["推定", "推定"], "navs": [nums[0], nums[1]],
                    "estimated": True}
    except Exception:
        pass
    return None


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
    return cands[-1] if cands else (history[0] if history else None)

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

    def find(days_ago=None, ymd=None):
        if ymd is None:
            target = (d - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        else:
            target = ymd
        rec = nearest_on_or_before(history, target)
        return rec

    def contrib_after(base_date: str) -> int:
        # 基準日(排他) < 記録日 <= 当日 の純拠出を合計(当日分を含む)。
        # cash_flow_jpy を持たない旧レコードは 0 とみなす。
        return int(sum(h.get("cash_flow_jpy", 0) or 0
                       for h in history if h["date"] > base_date))

    # 前日比は history の最後から2番目(=前回記録)を使う
    prev_rec = history[-2] if len(history) >= 2 else None
    week_rec = find(days_ago=7)
    month_rec = find(days_ago=30)
    ytd_rec = find(ymd=f"{d.year}-01-01")

    for key, rec in (("day", prev_rec), ("week", week_rec),
                     ("month", month_rec), ("ytd", ytd_rec)):
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
                "cash_flow_jpy": contrib,        # 参考: 期間中の純拠出額
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


def main():
    now = datetime.now(JST)
    today = now.strftime("%Y-%m-%d")
    print(f"\n{'='*55}\n  資産価格取得  {now:%Y-%m-%d %H:%M:%S} JST\n{'='*55}")

    existing = {}
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            existing = json.load(f)

    usdjpy = fetch_usdjpy()
    etf = fetch_etf_prices(usdjpy)
    fund = fetch_fund_prices()

    prev_total, curr_total = calc_total(etf, fund)
    if curr_total == 0:
        print("\n❌ 取得できた資産がありません。終了します。")
        return

    # 当日の純拠出(買い増し-売却)を算出。前回 data.json の保有数量と当日数量の差 ×
    # 当日価格。相場変動と資金の出し入れを分離し、期間比較を市場変動ベースにするため。
    cash_flow_jpy = compute_cash_flow(existing, etf, fund, usdjpy)
    # 同日に複数回実行された場合(1日に複数回 買い増しを反映する等)、既存の当日拠出に
    # 上乗せして累計にする。existing は前回runの出力なので、同日なら compute_cash_flow は
    # 前回run以降の増分のみを返す。既存の当日拠出を足さないと過去分が失われ比較が狂う。
    if existing.get("date") == today:
        for h in existing.get("history", []):
            if h.get("date") == today:
                cash_flow_jpy += int(h.get("cash_flow_jpy", 0) or 0)
                break
    if cash_flow_jpy:
        print(f"\n[拠出] 当日の純拠出(買い増し-売却): ¥{cash_flow_jpy:,}")

    # 履歴更新(同日上書き, 昇順, 直近400日保持)
    history = [h for h in existing.get("history", []) if h.get("date") != today]
    history.append({"date": today, "total_jpy": curr_total,
                    "usdjpy": usdjpy, "cash_flow_jpy": cash_flow_jpy})
    history = sorted(history, key=lambda x: x["date"])[-400:]

    comparisons = build_comparisons(history, curr_total, now)

    # 前日比(history不足時はprice差分でフォールバック)
    day_change_jpy = curr_total - prev_total
    day_change_pct = pct(curr_total, prev_total) or 0.0

    print(f"\n{'─'*40}")
    print(f"  総資産(当日): ¥{curr_total:,}")
    for label, key in (("前日比", "day"), ("先週比", "week"),
                       ("先月比", "month"), ("年初来", "ytd")):
        c = comparisons.get(key)
        if c and c["change_pct"] is not None:
            print(f"  {label}: {c['change_pct']:+.2f}% "
                  f"({'+' if c['change_jpy']>=0 else ''}¥{c['change_jpy']:,})")
        else:
            print(f"  {label}: データ蓄積中")
    print(f"{'─'*40}")

    output = {
        "updated_at": now.isoformat(),
        "date": today,
        "usdjpy": usdjpy,
        "total_jpy": curr_total,
        "day_change_jpy": day_change_jpy,
        "day_change_pct": day_change_pct,
        "comparisons": comparisons,
        "etf": etf,
        "fund": fund,
        "history": history,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n💾 {OUTPUT_FILE} を保存しました（履歴 {len(history)} 日分）")


if __name__ == "__main__":
    main()
