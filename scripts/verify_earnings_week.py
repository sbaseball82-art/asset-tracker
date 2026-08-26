# -*- coding: utf-8 -*-
"""本番投入前の総点検（Finnhub に実アクセスせずに行う）。

    python scripts/verify_earnings_week.py


Finnhub の公開仕様どおりの応答を作り、本番のコード経路をそのまま通す。
異常系（429リトライ / 403 / 空応答 / profile欠損 / ロゴ404 / 13社以上）も含める。
"""
import io, json, sys, tempfile, types, datetime as dt
from pathlib import Path
from PIL import Image, ImageDraw
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.earnings_week import fetch_earnings as fe, fetch_profile as fp, main as m, render, qa

SCRATCH = Path(tempfile.mkdtemp(prefix="earnings_week_verify_"))
ROOT = Path(__file__).resolve().parents[1]
THEME = json.load(open(ROOT / "config" / "theme.json"))
WATCH = json.load(open(ROOT / "config" / "watchlist.json"))["tickers"]
ok = lambda t: print(f"  ✓ {t}")

def png(color, bg=None):
    im = Image.new("RGBA",(240,240), bg or (0,0,0,0))
    ImageDraw.Draw(im).ellipse((30,30,210,210), fill=color)
    b=io.BytesIO(); im.save(b,"PNG"); return b.getvalue()

class Res:
    def __init__(self, payload=None, content=b"", code=200, headers=None):
        self.status_code=code; self._p=payload; self.content=content; self.headers=headers or {}
    def json(self):
        if self._p is None: raise ValueError("no json")
        return self._p

def install(get):
    fe.requests = types.SimpleNamespace(get=get, RequestException=requests.RequestException)
    fp.requests = types.SimpleNamespace(get=get, RequestException=requests.RequestException)
fe.MIN_INTERVAL_SEC = 0
fe.RETRY_WAITS = (0, 0, 0, 0)

# Finnhub の実際の応答形（docs の例に合わせる）
def calendar_payload(rows):
    return {"earningsCalendar": [
        {"date": r[0], "epsActual": None, "epsEstimate": r[2], "hour": r[1],
         "quarter": 3, "revenueActual": None, "revenueEstimate": r[3],
         "symbol": r[4], "year": 2026} for r in rows]}

print("\n[1] 正常系: 週20社 → watchlist絞り込み → 時価総額順 → 上位12社")
rows = [(f"2026-08-{24+i%5}", ["bmo","amc","dmh","",None][i%5],
         None if i%6==0 else round(0.5+i*0.37,2),
         None if i%8==0 else (i+1)*4.4e9, s) for i,s in enumerate(WATCH[:20])]
rows.append(("2026-08-26","amc",1.0,1e9,"ZZZZNOTINLIST"))
CACHE = SCRATCH/"cache_v"; m.CACHE_DIR = CACHE
calls = {"cal":0,"prof":0,"logo":0}
def get1(url, params=None, timeout=None, headers=None):
    if "calendar/earnings" in url:
        calls["cal"]+=1; return Res(calendar_payload(rows))
    if "profile2" in url:
        calls["prof"]+=1; s=params["symbol"]
        if s == WATCH[3]: return Res({})                       # profile が空
        return Res({"country":"US","currency":"USD","name":f"{s} Corporation",
                    "marketCapitalization": 3_400_000 - WATCH.index(s)*40_000,
                    "logo": "" if WATCH.index(s)%5==0 else f"https://static.finnhub.io/logo/{s}.png",
                    "ticker": s, "weburl":"https://example.com"})
    calls["logo"]+=1
    s = url.rsplit("/",1)[-1].split(".")[0]
    if s in (WATCH[1], WATCH[7]): return Res(code=404)          # ロゴ404
    return Res(content=png((10,10,12,255)) if WATCH.index(s)%3==0 else png((240,120,50,255)))
install(get1)
comps, others, missing = m.collect_live(dt.date(2026,8,24), THEME, offline=False, token="k")
assert len(comps)==12 and others==8, (len(comps), others)
assert all(c.symbol!="ZZZZNOTINLIST" for c in comps)
caps=[c.market_cap or 0 for c in comps]; assert caps==sorted(caps, reverse=True)
ok(f"掲載12社 / ほか{others}社 / 時価総額降順 / watchlist外を除外 / ロゴ失敗{len(missing)}社")
res = render.render_week(comps, dt.date(2026,8,24), dt.date(2026,8,28), THEME, others=others)
qa.verify(res.image, res.report, (1180,1450)); render.save(res.image, SCRATCH, "verify_full", THEME)
ok("画像生成 + 品質検査（豆腐/はみ出し/重なり）通過")
empty_name = [c for c in comps if c.symbol==WATCH[3]]
if empty_name: assert empty_name[0].name=="" ; ok("profile が空でも企業名を捏造せず空のまま")

print("\n[2] キャッシュ: 2回目はプロフィール/ロゴを取り直さない")
before = dict(calls)
comps2,_,_ = m.collect_live(dt.date(2026,8,24), THEME, offline=False, token="k")
assert calls["prof"]==before["prof"], calls               # プロフィールは30日キャッシュ
retried = calls["logo"] - before["logo"]
assert retried == len(missing) - 3, (retried, missing)    # 404の2件だけ再試行
ok(f"プロフィールは再取得なし / 成功したロゴも再取得なし / 失敗した{retried}件だけ再試行")

print("\n[3] 429 → リトライして成功")
state={"n":0}
def get429(url, params=None, timeout=None, headers=None):
    if "calendar/earnings" in url:
        state["n"]+=1
        if state["n"] < 3: return Res(code=429, headers={"Retry-After":"0"})
        return Res(calendar_payload(rows[:3]))
    return get1(url, params, timeout, headers)
install(get429)
got = fe.fetch_calendar(dt.date(2026,8,24), dt.date(2026,8,28), "k")
assert len(got)==3 and state["n"]==3
ok(f"429を2回受けても3回目で取得成功（{len(got)}件）")

print("\n[4] 403（キー無効/枠外）→ 明確なエラーで停止")
install(lambda *a, **k: Res(code=403))
try:
    fe.fetch_calendar(dt.date(2026,8,24), dt.date(2026,8,28), "k"); raise AssertionError("停止しない")
except fe.FinnhubError as e:
    assert "FINNHUB_API_KEY" in str(e); ok(f"FinnhubError: {str(e)[:44]}…")

print("\n[5] 空応答 → DATA WAIT（ダミーで作らない）")
install(lambda url, **k: Res({"earningsCalendar": []}))
try:
    m.collect_live(dt.date(2026,8,24), THEME, offline=False, token="k"); raise AssertionError("止まらない")
except m.DataWait as e: ok(f"DataWait: {str(e)[:44]}…")

print("\n[6] 期間外・壊れた行を落とす")
install(lambda url, **k: Res({"earningsCalendar":[
    {"symbol":"AAPL","date":"2026-08-26","hour":"amc","epsEstimate":2.4,"revenueEstimate":1e11},
    {"symbol":"MSFT","date":"2026-09-30","hour":"bmo","epsEstimate":3.6,"revenueEstimate":1e11},
    {"symbol":"MSFT","date":"2026-08-29","hour":"bmo","epsEstimate":3.6,"revenueEstimate":1e11},
    {"symbol":"","date":"2026-08-26"}, {"symbol":"XYZ","date":"bad-date"},
    {"symbol":"GOOGL","date":"2026-08-26","hour":"amc","epsEstimate":"n/a","revenueEstimate":None}]}))
got = fe.fetch_calendar(dt.date(2026,8,24), dt.date(2026,8,28), "k")
assert [g["symbol"] for g in got]==["AAPL","GOOGL"], got
assert got[1]["eps_estimate"] is None
ok("期間外/空シンボル/不正日付を除外、数値でないEPSは None（0で埋めない）")

print("\n[7] ファイル名・出力形式")
paths = render.save(res.image, SCRATCH/"outcheck", render.output_stem(dt.date(2026,8,24)), THEME)
assert paths["png"].name=="earnings_20260824.png" and paths["png"].stem.isascii()
with Image.open(paths["jpg"]) as im:
    assert im.size==(1180,1450) and im.mode=="RGB" and not im.info.get("progressive")
with Image.open(paths["png"]) as im: assert im.size==(1180,1450)
ok("PNG/JPEG 1180×1450 RGB / progressive無効 / 英数字ファイル名")

print("\n[8] ワークフローのシェル判定（DATA WAIT=2 は緑、異常=1 は赤）")
import subprocess
for code, expect in ((0,0),(2,0),(1,1)):
    r = subprocess.run(["bash","-c",
        f'set +e; (exit {code}); CODE=$?; if [ "$CODE" = "2" ]; then exit 0; fi; exit $CODE'])
    assert r.returncode==expect, (code, r.returncode)
ok("終了コードの扱いがワークフローの意図どおり")
print("\n=== すべて通過 ===")
