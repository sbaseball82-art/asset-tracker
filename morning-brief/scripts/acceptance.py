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

    # 6: meta.json に slot / template_id / topic_tag / score が記録されている
    metas = {}
    for day in DAYS_RICH:
        p = os.path.join(ROOT, "out", f"{day}_meta.json")
        if not os.path.exists(p):
            failures.append(f"{day}: meta.json が無い")
            continue
        meta = json.load(open(p, encoding="utf-8"))
        metas[day] = meta
        for m in meta:
            for k in ("slot", "template_id", "topic_tag", "score"):
                if k not in m:
                    failures.append(f"{day} meta: キー {k} が無い")

    # 7: 同じ日に同じテンプレートを繰り返さない ＆ 日をまたいで組み合わせが変わる
    combos = {}
    for day, meta in metas.items():
        tpls = [m["template_id"] for m in meta]
        if len(tpls) != len(set(tpls)):
            failures.append(f"{day}: 同日で同じテンプレートを重複使用 {tpls}")
        combos[day] = tuple(tpls)
    if len(combos) >= 2 and len(set(combos.values())) < 2:
        failures.append(f"日をまたいでテンプレ構成が同一: {combos}")

    # 8: ダミー実績で学習の選択が実績上位に偏る（ε=0の活用側で検証）
    import datetime as _dt
    sys.path.insert(0, HERE)
    import learner
    dummy = ([{"date": "2026-07-15", "slot": 1, "template_id": "T3",
               "topic_tag": "semiconductor", "views": 900.0}] * 6
             + [{"date": "2026-07-15", "slot": 2, "template_id": t,
                 "topic_tag": "macro", "views": 100.0}
                for t in ("T1", "T2", "T4", "T5", "T6") for _ in range(6)])
    cfg_exploit = {"learning": {"epsilon": 0.0, "epsilon_bootstrap": 0.0,
                                "min_samples_template": 5, "min_samples_tag": 5},
                   "scoring": {"learn_bonus_cap": 0.2}}
    pick = learner.choose_template("semiconductor", 1, _dt.date(2026, 7, 22),
                                   dummy, [], set(), cfg_exploit)
    if pick != "T3":
        failures.append(f"学習バイアス検証NG: 実績最上位T3でなく{pick}が選ばれた")
    bonus = learner.topic_bonuses(dummy, cfg_exploit)
    if bonus.get("semiconductor", 0) <= 0:
        failures.append(f"話題タグ学習ボーナスが付かない: {bonus}")

    # 9: 週次レポートがダミー実績から生成できる
    import report as _report
    tmp_report = os.path.join(ROOT, "out", "_test_weekly_report.md")
    import csv as _csv
    tmp_csv = os.path.join(ROOT, "data", "_test_feedback.csv")
    with open(tmp_csv, "w", encoding="utf-8", newline="") as f:
        wr = _csv.DictWriter(f, fieldnames=learner.FIELDNAMES)
        wr.writeheader()
        for i, r in enumerate(dummy):
            wr.writerow({**{k: "" for k in learner.FIELDNAMES}, **r,
                         "views": int(r["views"]), "slot": i % 2 + 1,
                         "date": "2026-07-20", "likes": 0})
    orig = learner.FEEDBACK_CSV
    try:
        learner.FEEDBACK_CSV = tmp_csv
        _report.load_feedback = lambda until, window_days=6: learner.load_feedback(
            until, window_days, path=tmp_csv)
        if not _report.generate(_dt.date(2026, 7, 26), tmp_report):
            failures.append("週次レポートが生成されない")
    finally:
        learner.FEEDBACK_CSV = orig
        for p in (tmp_csv, tmp_report):
            if os.path.exists(p):
                os.remove(p)

    if failures:
        print("NG:")
        for f in failures:
            print(" -", f)
        return 1
    print("受け入れ基準: すべて合格")
    print(f" - 3日再生成で定型文0件 / 採用カードは全て出典つき数値3+ / "
          f"{DAY_THIN} は画像0枚で正常終了 / はみ出し0件")
    print(" - meta.json記録あり / 同日テンプレ重複なし / 日をまたいで構成が変化")
    print(" - ダミー実績で選択が実績上位(T3)に偏る / タグ学習ボーナス付与 / 週次レポート生成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
