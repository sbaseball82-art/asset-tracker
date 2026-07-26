# -*- coding: utf-8 -*-
"""取得共通部品：リトライ＋指数バックオフ、User-Agent、失敗の局所化。

どの取得元が失敗しても例外は外に漏らさず None を返し、
その取得元だけ落として全体は続行する。
"""
from __future__ import annotations
import time

import requests

# SEC EDGAR・Reddit は UA 必須。連絡先入りのUAを名乗る（EDGARの推奨形式）
USER_AGENT = "asset-log-morning-brief/2.0 (contact: github.com/sbaseball82-art/asset-tracker)"

RETRIES = 3
BACKOFF = 2.0  # 2s, 4s, 8s


def get(url: str, *, params: dict | None = None, timeout: int = 20,
        headers: dict | None = None, as_json: bool = False):
    """GET with retry/backoff. 失敗したら None（呼び出し元は欠損として扱う）。"""
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    for attempt in range(RETRIES):
        try:
            r = requests.get(url, params=params, timeout=timeout, headers=hdrs)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.RequestException(f"HTTP {r.status_code}")
            r.raise_for_status()
            return r.json() if as_json else r.text
        except Exception as e:
            if attempt == RETRIES - 1:
                print(f"[warn] 取得失敗（この取得元だけ落として続行）: {url.split('?')[0]} : {e}")
                return None
            time.sleep(BACKOFF * (2 ** attempt))
    return None
