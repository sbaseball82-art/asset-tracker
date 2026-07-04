# 作業後セルフチェックリスト

各工程の作業を終えたら、該当セクションのチェックを**上から順に全部**実行する。
1つでもFAILなら、コミット・報告の前に「よくある失敗」欄で原因を切り分けること。
「たぶん大丈夫」で飛ばさない。チェックはすべて機械的に判定できるように書いてある。

---

## 工程A: 価格取得（fetch_prices.py の後）

以下をそのまま実行する。全行 `PASS` になること。

```bash
python3 - <<'EOF'
import json, datetime
d = json.load(open("data.json"))
today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y-%m-%d")

def check(label, ok, detail=""):
    print(f'{"PASS" if ok else "FAIL"}: {label} {detail}')

check("date が今日", d["date"] == today, f'(date={d["date"]}, today={today})')
check("ETFが4銘柄", len(d["etf"]) == 4, f'(actual={list(d["etf"])})')
check("投信が4銘柄", len(d["fund"]) == 4, f'(actual={list(d["fund"])})')
check("USD/JPYがフォールバック値でない", d["usdjpy"] != 150.0, f'(usdjpy={d["usdjpy"]})')
check("全投信が協会CSV", all(v["source"] == "協会CSV" for v in d["fund"].values()),
      str({k: v["source"] for k, v in d["fund"].items()}))
h = d["history"]
if len(h) >= 2:
    pct = (h[-1]["total_jpy"] - h[-2]["total_jpy"]) / h[-2]["total_jpy"] * 100
    check("前回比が±10%以内", abs(pct) <= 10, f'({pct:+.2f}%)')
EOF
```

| FAILした項目 | よくある原因 | 対処 |
|---|---|---|
| date が今日でない | fetch_prices.py が失敗して古いdata.jsonのまま | 実行ログ末尾を確認。「取得できた資産がありません」なら未書込みで安全。再実行 |
| 銘柄数が足りない | 一部銘柄の取得失敗（レート制限・一時障害） | **このままコミット禁止**。数分待って再実行。同日再実行は自動で上書きされる |
| usdjpy=150.0 | 為替取得失敗のフォールバック固定値 | **このままコミット禁止**。円換算が全部ズレている。再実行 |
| source が Yahoo!(推定) | 協会CSV失敗 or config.py のISIN未設定/誤り | 一時障害なら再実行。恒常的なら ISIN を確認（add-instrument スキル参照） |
| ±10%超 | 一部銘柄欠落の偽急落 or 本物の暴落 | 各銘柄の change_pct で説明できるか確認。説明できなければ repair-data-history スキル |
| そもそも全部 ProxyError/403 | 実行環境が金融サイトをブロック（コードのバグではない） | `.claude/memory/2026-07-04-sandbox-proxy-blocks-finance-sites.md` を読む |

## 工程B: イベント取得（fetch_events.py の後）

```bash
python3 - <<'EOF'
import json
d = json.load(open("events.json"))
evs = d["events"]
def check(label, ok, detail=""):
    print(f'{"PASS" if ok else "FAIL"}: {label} {detail}')
check("3件ある", len(evs) == 3)
check("取得失敗プレースホルダなし", not any("取得失敗" in e["title"] for e in evs))
check("空見出し(—)なし", not any(e["title"] == "—" for e in evs))
check("title 20字以内", all(len(e["title"]) <= 20 for e in evs),
      str([len(e["title"]) for e in evs]))
check("dir が有効値", all(e["dir"] in ("up", "down", "flat") for e in evs))
EOF
```

追加チェック（機械化しにくいが重要）: **前日と同一の見出し3件になっていないか**

```bash
git show HEAD~1:events.json 2>/dev/null | python3 -c "import json,sys; print([e['title'] for e in json.load(sys.stdin)['events']])"
python3 -c "import json; print([e['title'] for e in json.load(open('events.json'))['events']])"
```

2つの出力が完全一致していたら要注意（本当に同じニュースが続いた可能性もあるが、
取得ロジックの空振りで前日と同じ見出しを拾っている可能性もある）。2日以上続いたら
オーナーに報告する。

| FAILした項目 | よくある原因 | 対処 |
|---|---|---|
| プレースホルダ/— あり | RSS取得失敗（ネットブロック or 配信元障害） | このままだと**失敗文言がスライド画像に載る**。write-event-commentary スキルで手書きするか、オーナーに確認 |
| title 20字超 | AI生成 or 手書きが長すぎ | スライドで見切れる。events_manual.json で書き直す |
| 前日と同一見出し | 偶然の一致 or 取得ロジックの空振り | 1日なら記録のみ。連日続くならオーナーに報告 |

## 工程C: スライド生成（make_slide.py / make_allocation_slide.py の後）

```bash
python3 - <<'EOF'
import json, os, time
def check(label, ok, detail=""):
    print(f'{"PASS" if ok else "FAIL"}: {label} {detail}')
for f in ("slide/slide.png", "slide/allocation.png"):
    check(f"{f} が存在", os.path.exists(f))
    if os.path.exists(f):
        check(f"{f} が今回生成(10分以内)", time.time() - os.path.getmtime(f) < 600)
        check(f"{f} サイズ>100KB", os.path.getsize(f) > 100_000,
              f'({os.path.getsize(f):,} bytes)')
d = json.load(open("data.json"))
check("スライドの元データ日付", True, f'→ 画像には {d["date"]} のデータが載っているはず')
EOF
```

さらに **slide/slide.png を画像として開いて目視**で確認（機械チェック不可の3点）:

- [ ] 日付が意図した日になっている
- [ ] イベント欄に「見出し取得失敗」「—」が載っていない
- [ ] 文字化け（□豆腐）がない ← 化けていたら日本語フォント未導入の環境

**注意**: スライドは `data.json` と `events.json` **だけ**を読む。
`holdings.json` を今日編集しても、fetch_prices.py を再実行するまで画像の口数・金額は変わらない
（買い増し反映の確認は翌朝のスライドで行うのが正）。

## 工程D: コミット・プッシュの前

- [ ] `git status` を見て、**意図したファイルだけ**がステージされている
      （日次生成物は6ファイル限定: data.json / events.json / slide/*.png / slide/*.html）
- [ ] `git diff --staged` の内容を実際に読んだ（特に data.json は history の増分1日だけか）
- [ ] プッシュ先ブランチを確認した:
      - 日次生成物・events_manual.json → main（翌朝運用に直結。JST 6:30 が締切）
      - コード・スキル・設定の変更 → 作業ブランチ + PR（mainに直接プッシュしない）
- [ ] main への force-push は**いかなる場合も禁止**

## 工程E: stock-daily（日米市場レポート）を触った後

stock-daily は独立した第2システム（毎日 JST 7:30、`.github/workflows/daily_report.yml`）。
コード・設定を変更したら、ネット不要のモック実行で必ず検証する:

```bash
MOCK=1 python3 stock-daily/daily_report.py
```

- [ ] 最後に「=== 完了: 4セクション中4件のデータ取得に成功 ===」が出る
- [ ] `stock-daily/output/latest.png` が生成され、画像として開いて文字化けがない
- [ ] `stock-daily/output/post_text.txt` が140字以内（X投稿用）

| 症状 | 原因 | 対処 |
|---|---|---|
| `OSError: cannot open resource` | ローカルにNoto CJKフォントがない（本番はaptで導入済み） | `.claude/memory/2026-07-04-pil-font-path-differs-from-actions.md` |
| `ModuleNotFoundError` | 依存未導入 | `pip install -r stock-daily/requirements.txt`（feedparserのビルド失敗時は pillow 等を個別に入れる） |

## 番外: お金と本番に関わる操作（事故多発地帯）

| 操作 | ルール |
|---|---|
| `EVENT_MODE = "auto"` への変更 | **禁止**（Anthropic API課金が毎朝発生）。オーナーの明示指示があるときのみ |
| ANTHROPIC_API_KEY の設定・使用 | 同上。ローカル検証で auto モードを試すのも課金されるので不可 |
| data.json / holdings.json の削除 | **禁止**。data.json の history は再取得不能（repair-data-history スキル参照） |
| slide/*.png の削除 | 再生成可能なので低リスク（消しても次回実行で復活） |
| X への投稿 | このシステムの範囲外（オーナーが手動で行う）。自動投稿を実装しない |
