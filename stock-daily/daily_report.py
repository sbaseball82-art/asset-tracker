# -*- coding: utf-8 -*-
"""
毎日の株式マーケット情報を1枚の画像 + X投稿用テキストに自動生成するスクリプト。
GitHub Actions で毎朝実行される想定。

出力:
  output/latest.png            … 最新の画像(常に上書き)
  output/report_YYYY-MM-DD.png … 日付付きアーカイブ
  output/post_text.txt         … X投稿用コメント

環境変数:
  MOCK=1  … ネットワークを使わずサンプルデータで画像生成(動作確認用)
"""

import os
import sys
import time
import traceback
from datetime import datetime, date, timedelta, timezone

JST = timezone(timedelta(hours=9))
TODAY = datetime.now(JST).date()
MOCK = os.environ.get("MOCK") == "1"

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUT_DIR, exist_ok=True)

# ----------------------------------------------------------------------------
# 1. 設定: 監視対象
# ----------------------------------------------------------------------------
INDICES = [
    ("日経平均", "^N225"),
    ("TOPIX(1306)", "1306.T"),
    ("NYダウ", "^DJI"),
    ("S&P500", "^GSPC"),
    ("NASDAQ", "^IXIC"),
    ("ドル円", "JPY=X"),
    ("FANG+指数", "^NYFANG"),
    ("半導体ETF(SMH)", "SMH"),
    ("DRAM関連(4社平均)", "DRAM_AVG"),
]

# 主役銘柄の分類用(ハッシュタグ自動判定)
FANG_TICKERS = {"META", "AAPL", "AMZN", "NFLX", "NVDA", "GOOGL", "MSFT",
                "AVGO", "TSLA", "CRWD", "NOW", "SNOW"}
DRAM_TICKERS = {"MU", "WDC", "SNDK", "285A.T"}

JP_UNIVERSE = {
    "7203.T": "トヨタ", "6758.T": "ソニーG", "8306.T": "三菱UFJ", "6861.T": "キーエンス",
    "9983.T": "ファーストリテ", "8035.T": "東エレク", "6098.T": "リクルート", "9432.T": "NTT",
    "4063.T": "信越化学", "8058.T": "三菱商事", "9984.T": "SBG", "6501.T": "日立",
    "7974.T": "任天堂", "4568.T": "第一三共", "6902.T": "デンソー", "8766.T": "東京海上",
    "9433.T": "KDDI", "4519.T": "中外製薬", "6367.T": "ダイキン", "6954.T": "ファナック",
    "7741.T": "HOYA", "6273.T": "SMC", "8031.T": "三井物産", "8316.T": "三井住友FG",
    "6981.T": "村田製作所", "2914.T": "JT", "6503.T": "三菱電機", "7267.T": "ホンダ",
    "6702.T": "富士通", "4661.T": "OLC", "8001.T": "伊藤忠", "8411.T": "みずほFG",
    "6146.T": "ディスコ", "6857.T": "アドテスト", "7011.T": "三菱重工", "9101.T": "日本郵船",
    "5401.T": "日本製鉄", "4502.T": "武田薬品", "8801.T": "三井不動産", "9020.T": "JR東日本",
    "285A.T": "キオクシアHD",
}

US_UNIVERSE = {
    "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA", "GOOGL": "Alphabet",
    "AMZN": "Amazon", "META": "Meta", "TSLA": "Tesla", "AVGO": "Broadcom",
    "BRK-B": "Berkshire", "JPM": "JPMorgan", "LLY": "Eli Lilly", "V": "Visa",
    "UNH": "UnitedHealth", "XOM": "Exxon", "MA": "Mastercard", "COST": "Costco",
    "HD": "Home Depot", "PG": "P&G", "NFLX": "Netflix", "JNJ": "J&J",
    "AMD": "AMD", "CRM": "Salesforce", "ORCL": "Oracle", "KO": "Coca-Cola",
    "ADBE": "Adobe", "QCOM": "Qualcomm", "INTC": "Intel", "DIS": "Disney",
    "PLTR": "Palantir", "UBER": "Uber", "MU": "Micron", "BA": "Boeing",
    "CAT": "Caterpillar", "GS": "Goldman", "PFE": "Pfizer", "WMT": "Walmart",
    "TSM": "TSMC", "ARM": "Arm", "SMCI": "SuperMicro", "COIN": "Coinbase",
    "WDC": "WesternDigital", "SNDK": "SanDisk",
}

NEWS_FEEDS = [
    ("NHK経済", "https://www3.nhk.or.jp/rss/news/cat5.xml", 3),
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html", 2),
    ("Yahoo Finance", "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC&region=US&lang=en-US", 2),
]

# 2026年 主要イベント(公式発表ベース)。日付は「結果発表日」。
EVENTS_2026 = [
    ("2026-01-23", "日銀会合 結果発表(展望レポート)"),
    ("2026-01-28", "FOMC 結果発表"),
    ("2026-03-13", "メジャーSQ(日本)"),
    ("2026-03-18", "FOMC 結果発表(ドットチャート)"),
    ("2026-03-19", "日銀会合 結果発表"),
    ("2026-04-28", "日銀会合 結果発表(展望レポート)"),
    ("2026-04-29", "FOMC 結果発表"),
    ("2026-06-12", "メジャーSQ(日本)"),
    ("2026-06-16", "日銀会合 結果発表"),
    ("2026-06-17", "FOMC 結果発表(ドットチャート)"),
    ("2026-07-29", "FOMC 結果発表"),
    ("2026-07-31", "日銀会合 結果発表(展望レポート)"),
    ("2026-09-11", "メジャーSQ(日本)"),
    ("2026-09-16", "FOMC 結果発表(ドットチャート)"),
    ("2026-09-18", "日銀会合 結果発表"),
    ("2026-10-28", "FOMC 結果発表"),
    ("2026-10-30", "日銀会合 結果発表(展望レポート)"),
    ("2026-12-09", "FOMC 結果発表(ドットチャート)"),
    ("2026-12-11", "メジャーSQ(日本)"),
    ("2026-12-18", "日銀会合 結果発表"),
]


def first_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    return d + timedelta(days=(4 - d.weekday()) % 7)


def upcoming_events(n: int = 5):
    events = [(datetime.strptime(d, "%Y-%m-%d").date(), name) for d, name in EVENTS_2026]
    for m in range(1, 13):
        events.append((first_friday(2026, m), "米雇用統計(予定)"))
    events = sorted(e for e in events if e[0] >= TODAY)
    return events[:n]


# ----------------------------------------------------------------------------
# 2. データ取得(リトライ付き)
# ----------------------------------------------------------------------------
def retry(func, tries=3, wait=10, label=""):
    for i in range(tries):
        try:
            return func()
        except Exception as e:
            print(f"[warn] {label} 失敗 ({i+1}/{tries}): {e}")
            if i < tries - 1:
                time.sleep(wait)
    return None


def fetch_changes(tickers):
    """{ticker: (close, pct_change)} を返す"""
    import yfinance as yf
    df = yf.download(tickers=list(tickers), period="7d", interval="1d",
                     group_by="ticker", auto_adjust=False, progress=False, threads=True)
    out = {}
    for t in tickers:
        try:
            closes = (df[t]["Close"] if len(tickers) > 1 else df["Close"]).dropna()
            if len(closes) >= 2:
                last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
                out[t] = (last, (last / prev - 1) * 100)
        except Exception:
            pass
    return out


def get_market_data():
    if MOCK:
        idx = {"^N225": (41250.55, 1.24), "1306.T": (2985.0, 0.98), "^DJI": (44320.1, -0.35),
               "^GSPC": (6120.44, 0.42), "^IXIC": (20110.8, 0.88), "JPY=X": (152.34, -0.21),
               "^NYFANG": (13850.2, 1.55), "SMH": (275.4, 2.10),
               "DRAM_AVG": (float("nan"), -3.42)}
        jp = {t: (3000.0, v) for t, v in zip(list(JP_UNIVERSE), [5.8, 4.9, 4.1, 3.6, 3.2, 1.0, -2.0, 0.5, 0.2, 2.8])}
        us = {t: (300.0, v) for t, v in zip(list(US_UNIVERSE), [7.2, 6.1, 5.5, 4.0, 3.8, -1.2, 2.2, 0.9, -0.3, 3.1])}
        return idx, jp, us

    real = [t for _, t in INDICES if t != "DRAM_AVG"] + ["FNGS"]
    idx = retry(lambda: fetch_changes(real), label="指数") or {}
    jp = retry(lambda: fetch_changes(list(JP_UNIVERSE)), label="日本株") or {}
    us = retry(lambda: fetch_changes(list(US_UNIVERSE)), label="米国株") or {}

    # FANG+指数が取れない日はFNGS(FANG+連動ETN)で代替
    if "^NYFANG" not in idx and "FNGS" in idx:
        idx["^NYFANG"] = idx["FNGS"]

    # DRAM関連平均: MU/SanDisk/WesternDigital/キオクシアの前日比の単純平均
    pool = {**jp, **us}
    dram = [pool[t][1] for t in DRAM_TICKERS if t in pool]
    if dram:
        idx["DRAM_AVG"] = (float("nan"), sum(dram) / len(dram))
    return idx, jp, us


def get_news():
    if MOCK:
        return ["【日本】日経平均、半導体株主導で3日続伸 4万1000円台回復",
                "【日本】政府、成長戦略に半導体支援を明記へ",
                "【米国】FRB高官、年内の利下げに慎重姿勢を示す",
                "【米国】NVIDIA決算、市場予想を上回る売上高見通し",
                "【米国】原油価格が反落、中東情勢の緊張緩和で"]
    import feedparser
    items = []
    for label, url, limit in NEWS_FEEDS:
        def _fetch(u=url, lim=limit, lb=label):
            feed = feedparser.parse(u)
            tag = "日本" if lb == "NHK経済" else "米国"
            return [f"【{tag}】{e.title.strip()}" for e in feed.entries[:lim] if getattr(e, "title", "")]
        got = retry(_fetch, tries=2, wait=5, label=f"ニュース({label})")
        if got:
            items.extend(got)
    return items[:5]


def top5(changes: dict, names: dict):
    ranked = sorted(changes.items(), key=lambda kv: kv[1][1], reverse=True)[:5]
    return [(names.get(t, t), pct, t) for t, (_, pct) in ranked]


# ----------------------------------------------------------------------------
# 3. 画像生成
# ----------------------------------------------------------------------------
BG = (13, 20, 33)
PANEL = (22, 32, 50)
ACCENT = (255, 200, 60)
WHITE = (238, 242, 248)
GRAY = (150, 160, 175)
UP = (255, 82, 82)      # 日本式: 上昇=赤
DOWN = (77, 166, 255)   # 下落=青
LINE = (45, 58, 80)

FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"


def make_image(idx, jp5, us5, news, events, path):
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1080, 1700
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    def font(size, bold=False):
        p = FONT_BOLD if (bold and os.path.exists(FONT_BOLD)) else FONT_PATH
        return ImageFont.truetype(p, size)

    def text(x, y, s, size, color=WHITE, bold=False, anchor="la"):
        d.text((x, y), s, font=font(size, bold), fill=color, anchor=anchor)

    def clip(s, size, maxw, bold=False):
        f = font(size, bold)
        while d.textlength(s, font=f) > maxw and len(s) > 1:
            s = s[:-1]
        return s

    def section(y, title):
        d.rectangle([40, y, 48, y + 34], fill=ACCENT)
        text(64, y - 2, title, 30, ACCENT, bold=True)
        return y + 52

    # --- ヘッダー ---
    d.rectangle([0, 0, W, 130], fill=(9, 14, 24))
    d.rectangle([0, 128, W, 132], fill=ACCENT)
    wd = "月火水木金土日"[TODAY.weekday()]
    text(40, 26, "今日の株式マーケット情報", 42, WHITE, bold=True)
    text(W - 40, 38, f"{TODAY.strftime('%Y/%m/%d')}({wd})", 32, ACCENT, bold=True, anchor="ra")

    y = 160
    # --- 主要指数 ---
    y = section(y, "主要指数・為替(前日比)")
    tile_w, tile_h, gap = 320, 118, 20
    for i, (name, tk) in enumerate(INDICES):
        col, row = i % 3, i // 3
        x0, y0 = 40 + col * (tile_w + gap), y + row * (tile_h + gap)
        d.rounded_rectangle([x0, y0, x0 + tile_w, y0 + tile_h], 12, fill=PANEL)
        text(x0 + 18, y0 + 12, clip(name, 24, tile_w - 36), 24, GRAY)
        if tk in idx:
            price, pct = idx[tk]
            c = UP if pct >= 0 else DOWN
            if tk == "DRAM_AVG":
                ps, psz = "MU/キオクシア等", 24
            else:
                ps, psz = (f"{price:,.2f}" if price < 1000 else f"{price:,.1f}"), 32
            text(x0 + 18, y0 + 46 + (32 - psz) // 2, ps, psz, WHITE, bold=True)
            text(x0 + tile_w - 16, y0 + 52, f"{pct:+.2f}%", 27, c, bold=True, anchor="ra")
        else:
            text(x0 + 18, y0 + 50, "取得失敗", 26, GRAY)
    rows = (len(INDICES) + 2) // 3
    y += rows * (tile_h + gap) + 20

    # --- 値上がり率TOP5 ---
    y = section(y, "値上がり率TOP5(主力株)")
    col_w = 490
    for ci, (label, data) in enumerate([("日本株", jp5), ("米国株", us5)]):
        x0 = 40 + ci * (col_w + 20)
        d.rounded_rectangle([x0, y, x0 + col_w, y + 300], 12, fill=PANEL)
        text(x0 + 20, y + 12, label, 26, ACCENT, bold=True)
        if not data:
            text(x0 + 20, y + 60, "取得失敗", 24, GRAY)
        for ri, (name, pct, _) in enumerate(data):
            yy = y + 58 + ri * 47
            text(x0 + 20, yy, f"{ri+1}", 24, GRAY, bold=True)
            text(x0 + 58, yy, clip(name, 25, 290), 25, WHITE)
            text(x0 + col_w - 20, yy, f"{pct:+.2f}%", 25, UP if pct >= 0 else DOWN, bold=True, anchor="ra")
        if ri := len(data):
            d.line([x0 + 20, y + 50, x0 + col_w - 20, y + 50], fill=LINE, width=2)
    y += 340

    # --- ニュース ---
    y = section(y, "注目ニュース")
    d.rounded_rectangle([40, y, W - 40, y + 210], 12, fill=PANEL)
    if not news:
        text(64, y + 20, "取得失敗", 24, GRAY)
    for i, h in enumerate(news[:5]):
        text(64, y + 14 + i * 39, "・" + clip(h, 24, W - 150), 24, WHITE)
    y += 250

    # --- イベント ---
    y = section(y, "今後の注目イベント")
    d.rounded_rectangle([40, y, W - 40, y + 178], 12, fill=PANEL)
    for i, (ed, name) in enumerate(events[:4]):
        yy = y + 14 + i * 41
        days = (ed - TODAY).days
        text(64, yy, ed.strftime("%m/%d"), 24, ACCENT, bold=True)
        text(160, yy, clip(name, 24, 680), 24, WHITE)
        text(W - 64, yy, "本日!" if days == 0 else f"あと{days}日", 24, GRAY, anchor="ra")

    # --- フッター ---
    d.line([40, H - 66, W - 40, H - 66], fill=LINE, width=2)
    text(40, H - 52, "※投資判断はご自身の責任で。データ: Yahoo Finance 等 / 前営業日終値ベース", 20, GRAY)
    text(W - 40, H - 52, "毎朝自動更新", 20, ACCENT, anchor="ra")

    img.save(path)
    print(f"[ok] 画像を保存: {path}")


# ----------------------------------------------------------------------------
# 4. X投稿用テキスト
# ----------------------------------------------------------------------------
def make_post_text(idx, jp5, us5, events, path):
    """ASSET LOG運用方針: 煽らない・一人称・「指数を淡々と」に着地。
    タグ含め100文字以内。#FANG/#DRAMは主役が該当銘柄の日のみ付与。"""
    wd = "月火水木金土日"[TODAY.weekday()]
    date_s = f"{TODAY.month}/{TODAY.day}({wd})"
    n225, spx = idx.get("^N225"), idx.get("^GSPC")

    # その日の主役(日米の値上がり1位のうち大きい方)
    tops = [t for t in (jp5[0] if jp5 else None, us5[0] if us5 else None) if t]
    star = max(tops, key=lambda x: x[1]) if tops else None

    head = f"【{date_s}】"
    if n225:
        head += f"日経{n225[0]:,.0f}({n225[1]:+.1f}%)"
    if spx:
        head += f" S&P500 {spx[0]:,.0f}({spx[1]:+.1f}%)"

    hook = f"。主役は{star[0]}{star[1]:+.1f}%" if star and star[1] > 0 else ""
    down = (spx and spx[1] < 0) or (not spx and n225 and n225[1] < 0)
    stance = "。下げる日も私は指数を淡々と積立" if down else "。それでも私は指数を淡々と積立"

    # 主役がFANG+/DRAM関連のときだけ該当タグを付ける
    extra = []
    if star:
        if star[2] in DRAM_TICKERS:
            extra.append("#DRAM")
        if star[2] in FANG_TICKERS:
            extra.append("#FANG")
    tags_full = "\n" + " ".join(extra + ["#米国株", "#インデックス投資"])
    tags_min = "\n" + " ".join(extra + ["#米国株"])
    candidates = [
        head + hook + stance + tags_full,
        head + hook + stance + tags_min,
        head + hook + "。私は指数を淡々と" + tags_min,
        head + stance + tags_min,
        head + tags_min,
    ]
    text = next((c for c in candidates if len(c) <= 100), None)
    if text is None:  # 万一の保険: タグを残して本文を切り詰め
        body_max = 100 - len(tags_min)
        text = (head + stance)[:body_max] + tags_min
    text = text.replace("】。", "】")  # 指数欠損時の体裁調整
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"[ok] 投稿テキストを保存: {path} ({len(text)}文字)")


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------
def main():
    print(f"=== {TODAY} レポート生成開始 (MOCK={MOCK}) ===")
    idx, jp, us = get_market_data()
    jp5, us5 = top5(jp, JP_UNIVERSE), top5(us, US_UNIVERSE)
    news = get_news()
    events = upcoming_events()

    img_path = os.path.join(OUT_DIR, "latest.png")
    make_image(idx, jp5, us5, news, events, img_path)
    import shutil
    shutil.copy(img_path, os.path.join(OUT_DIR, f"report_{TODAY.isoformat()}.png"))
    make_post_text(idx, jp5, us5, events, os.path.join(OUT_DIR, "post_text.txt"))

    # 30日より古いアーカイブ画像を削除(リポジトリ肥大化防止)
    limit = TODAY - timedelta(days=30)
    for fn in os.listdir(OUT_DIR):
        if fn.startswith("report_") and fn.endswith(".png"):
            try:
                if datetime.strptime(fn[7:17], "%Y-%m-%d").date() < limit:
                    os.remove(os.path.join(OUT_DIR, fn))
                    print(f"[ok] 旧ファイル削除: {fn}")
            except ValueError:
                pass

    ok = bool(idx) + bool(jp5) + bool(us5) + bool(news)
    print(f"=== 完了: 4セクション中{ok}件のデータ取得に成功 ===")
    if ok == 0:
        sys.exit(1)  # 全滅時のみ失敗扱い(Actionsのリトライ対象)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
