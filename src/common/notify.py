# -*- coding: utf-8 -*-
"""
notify.py
=========
生成完了通知（Slack Webhook）。SLACK_WEBHOOK_URL 未設定なら標準出力のみ。
T-60分通知は遅延が致命的なため、失敗時はリトライ3回＋失敗を明示する。
"""

import json
import os
import time
import urllib.request


def notify(message: str, critical: bool = False) -> bool:
    """通知を送る。成功で True。失敗時は3回リトライし、最後に失敗通知を出す。"""
    print(f"[notify] {message}")
    url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not url:
        return True  # Webhook未設定はローカル運用とみなし正常

    payload = json.dumps({"text": message}).encode("utf-8")
    for i in range(3):
        try:
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as res:
                if 200 <= res.status < 300:
                    return True
        except Exception as e:  # noqa: BLE001
            print(f"[warn] Slack通知失敗 ({i + 1}/3): {e}")
            time.sleep(2 * (i + 1))

    # GitHub Actions のログで目立たせる（criticalはT-60分など時刻厳守の通知）
    level = "error" if critical else "warning"
    print(f"::{level}::Slack通知に3回失敗しました: {message}")
    return False
