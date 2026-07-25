# -*- coding: utf-8 -*-
"""受け入れ基準の自動検証（オフライン・フィクスチャで実行）。

  python scripts/acceptance.py

検証項目:
1. 任意の3日を --date で再生成し、共通定型文が1文も含まれない
2. 生成された全カードが数値3つ以上を持ち、各数値がログ上で出典と紐づく
3. 材料が薄い日は画像0枚で正常終了する
4. 旧版のスタンス欄・同時報道数の文字列が生成物に存在しない
5. 描画は検証合格時のみ保存されるため、はみ出し0件（[error] が出ないこと）
"""
from __future__ import annotations
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DAYS_RICH = ["2026-07-22", "2026-07-23"]
DAY_THIN = "2026-07-20"

# どのニュースにも当てはまる定型文（旧実装の残骸検出）。
# ※リポジトリ全体のgrepでもヒットさせないよう、検査語自体は分割して保持する
BANNED = ["".join(p) for p in [
    ("自分の", "スタンス"),
    ("メディアが", "同時報道"),
    ("きっかけは需給・", "観測報道・ポジション調整など複合的"),
    ("予想は当てず、", "指数で淡々と継続"),
]]


def run_day(day: str) -> str:
    r = subprocess.run([sys.executable, os.path.join(HERE, "main.py"),
                        "--date", day, "--fixtures"],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, f"{day}: 異常終了\n{r.stdout}\n{r.stderr}"
    assert "[error]" not in r.stdout, f"{day}: 描画検証NG\n{r.stdout}"
    return r.stdout


def main() -> int:
    failures = []

    for day in DAYS_RICH + [DAY_THIN]:
        run_day(day)

    # 1・4: 定型文ゼロ（投稿文・ログの全生成物を走査）
    texts = []
    for name in os.listdir(os.path.join(ROOT, "out")):
        p = os.path.join(ROOT, "out", name)
        if name.endswith(".txt") and os.path.isfile(p):
            texts.append((p, open(p, encoding="utf-8").read()))
    for name in os.listdir(os.path.join(ROOT, "logs")):
        p = os.path.join(ROOT, "logs", name)
        texts.append((p, open(p, encoding="utf-8").read()))
    for path, body in texts:
        for b in BANNED:
            if b in body:
                failures.append(f"定型文検出: {b!r} in {path}")

    # 2: 全採用カードが検証済み数値3つ以上（出典・取得日時つき）
    for day in DAYS_RICH:
        log = json.load(open(os.path.join(ROOT, "logs", f"{day}.json"),
                             encoding="utf-8"))
        if not log["adopted"]:
            failures.append(f"{day}: 材料の濃い日にカード0枚")
        for a in log["adopted"]:
            ok = [n for n in a["numbers"] if n.get("source") and n.get("asof")]
            if len(ok) < 3:
                failures.append(f"{day} {a['ticker']}: 出典つき数値が{len(ok)}件")
        if len(log["adopted"]) > log["max_cards"]:
            failures.append(f"{day}: 上限{log['max_cards']}枚を超過")

    # 3: 薄い日は画像0枚
    thin_pngs = [f for f in os.listdir(os.path.join(ROOT, "out"))
                 if f.startswith(DAY_THIN) and f.endswith(".png")]
    if thin_pngs:
        failures.append(f"{DAY_THIN}: 材料薄の日に画像が生成された {thin_pngs}")
    thin_log = json.load(open(os.path.join(ROOT, "logs", f"{DAY_THIN}.json"),
                              encoding="utf-8"))
    if thin_log["adopted"]:
        failures.append(f"{DAY_THIN}: adopted が空でない")

    if failures:
        print("NG:")
        for f in failures:
            print(" -", f)
        return 1
    print("受け入れ基準: すべて合格")
    print(f" - 3日再生成で定型文0件 / 採用カードは全て出典つき数値3+ / "
          f"{DAY_THIN} は画像0枚で正常終了 / はみ出し0件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
