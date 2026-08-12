# -*- coding: utf-8 -*-
"""
投信の基準価額の取得元を1件ずつ叩いて、どこで失敗しているかを出す診断スクリプト。

`data.json` の source が `前日値(取得失敗)` や `Yahoo!(推定)` になった銘柄について、
「協会CSVが落ちているのか」「ISINが要るのか」「協会コード自体が違うのか」を切り分ける。

fetch_prices.py 本体と同じ関数を呼ぶので、ここで通れば本番でも通る。
ローカル環境は金融サイトへの接続が遮断されていることがあるため、
その場合は GitHub Actions の fund-source-check ワークフローから実行する。

    python3 scripts/diagnose_fund_source.py              # 全銘柄
    python3 scripts/diagnose_fund_source.py 89311265     # 銘柄を指定
"""

import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import FUND_HOLDINGS  # noqa: E402
from fetch_prices import (  # noqa: E402
    TOUSHIN_CSV,
    UA,
    fetch_fund_nav_toushin,
    fetch_fund_nav_yahoo,
)

# 協会CSVのレスポンスから ISIN らしき文字列を拾う(JP + 英数10桁)
ISIN_RE = re.compile(r"\bJP[0-9A-Z]{10}\b")


def probe(url: str, encoding: str = "shift_jis") -> tuple[int | None, int, str, str]:
    """URLを叩いて (ステータス, バイト数, 先頭の抜粋, 全文) を返す。"""
    try:
        res = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "ja"},
                           timeout=20)
    except Exception as e:  # noqa: BLE001
        return None, 0, f"{type(e).__name__}: {e}", ""
    full = res.content.decode(encoding, errors="replace")
    return res.status_code, len(res.content), full[:300].replace("\n", " ⏎ "), full


def find_isin(*bodies: str) -> list[str]:
    """レスポンス本文から ISIN らしき文字列(JP+英数10桁)を拾う。

    見つかっても『それがこのファンドのISINである』確証にはならないので、
    候補として出すだけにする。config.py へ書き込む前に必ず協会CSVで検証すること。
    """
    found: list[str] = []
    for body in bodies:
        for m in ISIN_RE.findall(body):
            if m not in found:
                found.append(m)
    return found


def verify_isin(code: str, isin: str) -> bool:
    """候補のISINで協会CSVが引けるかを実際に確かめる。"""
    return fetch_fund_nav_toushin(code, isin) is not None


def diagnose(code: str, name: str, isin: str | None) -> bool:
    print(f"\n{'=' * 70}\n{code}  {name}\n  config.py の ISIN: {isin or '(未設定)'}")

    # 1. 協会CSV: 協会コード単独
    url = f"{TOUSHIN_CSV}?associFundCd={code}"
    status, size, head, _ = probe(url)
    print(f"\n  [1] 協会CSV (協会コードのみ)  {url}")
    print(f"      status={status} size={size}")
    print(f"      body: {head[:200]}")

    # 2. 協会CSV: ISIN 併用(設定されていれば)
    if isin:
        url2 = f"{TOUSHIN_CSV}?isinCd={isin}&associFundCd={code}"
        status2, size2, head2, _ = probe(url2)
        print(f"\n  [2] 協会CSV (ISIN併用)  status={status2} size={size2}")
        print(f"      body: {head2[:200]}")
    else:
        print("\n  [2] 協会CSV (ISIN併用)  skip: ISIN未設定")

    # 3. Yahoo!ファイナンスJP
    yurl = f"https://finance.yahoo.co.jp/quote/{code}/history"
    status3, size3, _head3, ybody = probe(yurl, encoding="utf-8")
    print(f"\n  [3] Yahoo!JP  {yurl}")
    print(f"      status={status3} size={size3}")

    # 3b. ISIN未設定なら候補を探して、実際に協会CSVが引けるか検証する
    if not isin:
        _s, _z, _h, top = probe(f"https://finance.yahoo.co.jp/quote/{code}",
                                encoding="utf-8")
        candidates = find_isin(ybody, top)
        print(f"\n  [3b] ISIN候補(ページ本文から抽出): {candidates or 'なし'}")
        for cand in candidates:
            ok = verify_isin(code, cand)
            print(f"       {cand} で協会CSV: {'引ける ★これが正' if ok else '引けない'}")
            if ok:
                print(f"       => config.py の {code} に ISIN {cand} を設定すれば直る")
                break

    # 4. 本番と同じ関数で最終判定
    t = fetch_fund_nav_toushin(code, isin)
    y = fetch_fund_nav_yahoo(code)
    print(f"\n  [判定] 協会CSVパース: {'OK ' + str(len(t['navs'])) + '件' if t else 'NG'}"
          f" / Yahooパース: {'OK ' + str(len(y['navs'])) + '件' if y else 'NG'}")
    if t:
        print(f"         協会CSV 最新: {t['dates'][0]} = {t['navs'][0]:,.0f}円")
    if y:
        print(f"         Yahoo   最新: {y['dates'][0]} = {y['navs'][0]:,.0f}円")

    ok = bool(t)
    print(f"  => {'協会CSVで取得できる' if ok else '協会CSVで取得できない(要対応)'}")
    return ok


def main() -> int:
    codes = sys.argv[1:] or list(FUND_HOLDINGS)
    ng = []
    for code in codes:
        if code not in FUND_HOLDINGS:
            print(f"{code}: config.py に無い協会コード")
            ng.append(code)
            continue
        name, _units, isin = FUND_HOLDINGS[code]
        if not diagnose(code, name, isin):
            ng.append(code)

    print(f"\n{'=' * 70}")
    if ng:
        print(f"協会CSVで取得できない銘柄: {ng}")
        return 1
    print("全銘柄 協会CSVで取得できる")
    return 0


if __name__ == "__main__":
    sys.exit(main())
