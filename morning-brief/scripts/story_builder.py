# -*- coding: utf-8 -*-
"""カード文面の合成：その日の実データ（レイヤ1・2）から記事を組み立てる。

方針（編集方針はコード末尾の LLM プロンプトにも明記）:
- 見出しは配信社の原文を使わず自作（20字以内）
- どのニュースにも当てはまる定型文で穴を埋めない。全ての文に
  「その日の数値」か「固有名詞」を含め、含められない文は書かない
- 数字は必ずレイヤ1（yfinance実測）・レイヤ2（一次情報）から取り、
  出典と取得日時を numbers メタデータに保持する（gate が検証する）
- 枠の文字数上限を超える場合は、描画時の自動改行に頼らず
  ここで（文節単位で）短縮する
"""
from __future__ import annotations
import datetime as dt
import os
import re
import unicodedata

# ティッカー → セクター（因果メカニズムの知識ベースのキー）
SECTOR = {
    "MU": "memory",
    "NVDA": "ai_semi", "AVGO": "ai_semi", "AMD": "ai_semi", "TSM": "ai_semi",
    "INTC": "ai_semi", "SMH": "ai_semi", "^SOX": "ai_semi",
    "MSFT": "megatech", "AAPL": "megatech", "GOOGL": "megatech",
    "AMZN": "megatech", "META": "megatech", "TSLA": "megatech",
    "^TNX": "rates", "JPY=X": "fx",
    "^GSPC": "index", "^IXIC": "index", "^DJI": "index",
    "VTI": "index", "QQQ": "index",
    "VYM": "dividend", "HDV": "dividend", "SCHD": "dividend",
    "XLE": "energy", "XLF": "financials", "XLU": "utilities",
}

THEME_BADGE = {
    "memory": "メモリ", "ai_semi": "半導体", "megatech": "ハイテク",
    "rates": "金利", "fx": "為替", "index": "指数", "dividend": "高配当",
    "energy": "エネルギー", "financials": "金融", "utilities": "公益",
}

# S&P500 / QQQ 構成比の近似（%。波及の定量表現に使う概算値）
SPX_WEIGHT = {"NVDA": 7.0, "MSFT": 6.5, "AAPL": 6.0, "GOOGL": 4.0, "AMZN": 3.8,
              "META": 2.6, "AVGO": 2.2, "TSLA": 1.6, "AMD": 0.6, "MU": 0.4,
              "INTC": 0.2}
QQQ_WEIGHT = {"NVDA": 9.0, "MSFT": 8.5, "AAPL": 8.0, "GOOGL": 5.5, "AMZN": 5.5,
              "META": 3.5, "AVGO": 4.5, "TSLA": 2.5, "AMD": 1.0, "MU": 0.6,
              "INTC": 0.3}



# ── 文字数ユーティリティ（全角=1 / 半角=0.5）────────────
def units(s: str) -> float:
    return sum(1.0 if unicodedata.east_asian_width(c) in "FWA" else 0.5 for c in s)


def fit_units(s: str, max_units: float) -> str:
    """上限超過時は文節（。、）単位で後ろから削って短縮する（改行に逃げない）。"""
    if units(s) <= max_units:
        return s
    parts = re.split(r"(?<=[。、])", s)
    while len(parts) > 1 and units("".join(parts)) > max_units:
        parts.pop()
    out = "".join(parts).rstrip("、")
    while units(out) > max_units and len(out) > 1:   # 最終手段の文字単位カット
        out = out[:-1]
    return out.rstrip("、")


def _move_word(pct: float) -> str:
    a = abs(pct)
    if a >= 8:
        return "急落" if pct < 0 else "急騰"
    if a >= 4:
        return "大幅安" if pct < 0 else "大幅高"
    if a >= 1.5:
        return "下落" if pct < 0 else "上昇"
    return "小幅安" if pct < 0 else "小幅高"


def _rel_move(market_metrics: dict, tk: str) -> float | None:
    m = market_metrics.get(tk)
    return m["ret1d_pct"] if m else None


def _pct(w: float | None) -> str:
    """指数構成比の表示（1%未満は小数1桁で「約0%」を避ける）。"""
    if w is None:
        return "1%未満"
    return f"{w:.1f}%" if w < 2 else f"{w:.0f}%"


# ── 因果メカニズム知識ベース（セクター×方向。数値は呼び出し側が埋める）──
def _why(sector: str, down: bool, p: dict) -> str:
    if sector == "memory":
        if down:
            return (f"DRAM・HBMは需給で単価が決まるシクリカル。供給増や在庫調整の観測は"
                    f"将来の採算悪化予想として業績より先に株価へ織り込まれるため、"
                    f"出来高{p['vr']:.1f}倍を伴う下げになりやすい。")
        return (f"HBMはAIサーバー投資に直結し、供給不足の観測は単価上昇→採算改善の予想として"
                f"先回りで買われるため、出来高{p['vr']:.1f}倍の上げにつながる。")
    if sector == "ai_semi":
        core = (f"AI半導体はデータセンター投資の期待でPERが拡張してきたため、"
                f"投資計画の増減観測に株価が最も敏感に反応する。")
        return core + (f"当日z={p['z']:+.1f}は期待の修正が入ったことを示す。")
    if sector == "rates":
        return (f"長期金利は将来の割引率そのもので、金利が動くと高PER株の理論価値が逆方向に動くため、"
                f"z={p['z']:+.1f}の金利変動は株式全体の再評価につながる。")
    if sector == "fx":
        return (f"ドル円は日米金利差で動き、円建ての米国資産評価額に直結するため、"
                f"z={p['z']:+.1f}の変動は国内投資家の円換算リターンを直接動かす。")
    if sector == "megatech":
        return (f"時価総額上位は指数連動資金の売買が集中するため、個社材料でも"
                f"出来高{p['vr']:.1f}倍規模の需給が指数全体の方向を左右する。")
    if sector == "dividend":
        return (f"高配当株は金利との利回り比較で買われるため、金利水準の変化が"
                f"z={p['z']:+.1f}の資金移動として現れる。")
    if sector == "energy":
        return (f"エネルギー株は原油価格に業績が連動するため、需給観測の変化が"
                f"z={p['z']:+.1f}のセクター変動として現れる。")
    if sector == "financials":
        return (f"銀行は長短金利差が利ざやを決めるため、金利見通しの変化が"
                f"z={p['z']:+.1f}の株価変動につながる。")
    if sector == "utilities":
        return (f"公益はデータセンター電力需要と金利の両方に感応するため、"
                f"どちらかの見通し変化がz={p['z']:+.1f}の変動として出る。")
    # index
    return (f"指数z={p['z']:+.1f}の変動は個別材料でなく、金利・業績見通しなど"
            f"市場全体の前提が動いたことを意味するため、幅広い銘柄に同時に効く。")


def _counter(sector: str, down: bool) -> str:
    if sector == "memory":
        return ("メーカー各社の長期契約価格が維持され、26年の供給増がAI需要に吸収されれば"
                + ("、値崩れ前提のこの下げは巻き戻る。" if down else "、上昇は定着する。"))
    if sector == "ai_semi":
        return ("大手クラウド4社の設備投資計画が次回決算で維持されれば"
                + ("、減速前提のこの下げは行き過ぎになる。" if down else "、この見立ては保たれる。逆に下方修正なら崩れる。"))
    if sector == "rates":
        return "次回CPI・雇用統計が予想を外れFRBの路線が変われば、この金利前提は崩れる。"
    if sector == "fx":
        return "日銀の追加利上げ観測や介入で金利差シナリオが変われば、この方向は反転する。"
    if sector == "megatech":
        return "次回決算のガイダンスが市場予想を上回れば（下回れば）、この見立ては反転する。"
    if sector == "dividend":
        return "FRBが利下げに転じ金利が低下すれば、利回り比較の資金は逆流する。"
    if sector == "energy":
        return "OPECの供給方針や在庫統計が逆方向に出れば、原油前提ごと崩れる。"
    if sector == "financials":
        return "イールドカーブが平坦化し利ざや見通しが崩れれば、この方向は反転する。"
    if sector == "utilities":
        return "電力需要見通しの下方修正か金利急騰で、この見立ては崩れる。"
    return "翌営業日に出来高を伴う反対方向の動きが出れば、前提の変化は否定される。"


# ── 本体 ────────────────────────────────────────────────
def build_story(cand: dict, market_metrics: dict, primary: dict,
                cfg: dict, asof: dt.date) -> dict:
    """候補1件からカード素材一式（gate 検証対象）を組み立てる。"""
    lim = cfg["limits"]
    tk, name, sector = cand["ticker"], cand["name"], SECTOR.get(cand["ticker"], "index")
    m = cand["metrics"]
    ret, z, vr = m["ret1d_pct"], m["zscore"], m["vol_ratio"] or 0.0
    down = ret < 0
    mw = _move_word(ret)
    asof_s = m["asof"]
    p = {"z": z, "vr": vr}

    # 検証済み数値（出典・取得日時つき）。数字カードとゲート検証の両方に使う
    if tk == "^TNX":   # 金利は%変化でなくbpで示す
        bp = (m["last"] - m["prev"]) * 100
        main_num = {"label": f"{name} 日次", "value": f"{bp:+.0f}bp",
                    "sub": f"{m['last']:.2f}% / z={z:+.1f}σ",
                    "source": "yfinance終値", "asof": asof_s}
        event_label = f"{bp:+.0f}bp"
    else:
        main_num = {"label": f"{name} 日次", "value": f"{ret:+.1f}%",
                    "sub": f"z={z:+.1f}σ", "source": "yfinance終値", "asof": asof_s}
        event_label = f"{ret:+.1f}%"
    numbers = [
        main_num,
        {"label": "6ヶ月騰落", "value": f"{m['ret6m_pct']:+.1f}%",
         "sub": name, "source": "yfinance終値", "asof": asof_s},
    ]
    if vr:
        numbers.insert(1, {"label": "出来高 20日比", "value": f"{vr:.1f}倍",
                           "sub": "当日/平均", "source": "yfinance出来高", "asof": asof_s})
    # 波及の定量化に使う関連指標（本人が指数のときは構成銘柄側でなく別指数）
    rel_ticks = [t for t in ("^GSPC", "^SOX", "^TNX", "JPY=X") if t != tk]
    rel_facts = []
    for rt in rel_ticks:
        rv = _rel_move(market_metrics, rt)
        if rv is None:
            continue
        rname = {"^GSPC": "S&P500", "^SOX": "SOX指数", "^TNX": "米10年金利",
                 "JPY=X": "ドル円"}[rt]
        rel_facts.append((rname, rv))
        if len(numbers) < 5:
            numbers.append({"label": f"{rname} 日次", "value": f"{rv:+.1f}%",
                            "sub": "同日", "source": "yfinance終値", "asof": asof_s})
    # レイヤ2：財務省イールドカーブ（取れた日は数字カード候補に加える）
    ty = primary.get("treasury")
    if ty and "y10" in ty:
        numbers.append({"label": "米10年利回り", "value": f"{ty['y10']:.2f}%",
                        "sub": ty["date"], "source": ty["source"], "asof": ty["date"]})

    if tk == "^TNX":
        mw = "急伸" if (ret >= 0 and abs(z) >= 2) else ("急低下" if abs(z) >= 2 else mw)
        headline = fit_units(f"{name}{mw} {event_label}", lim["headline"])
    else:
        headline = fit_units(f"{name}{mw} {ret:+.0f}%", lim["headline"])

    if abs(z) >= 2.5 and vr >= 2:
        concl = f"出来高{vr:.1f}倍の{mw}は一時要因でなくシナリオ修正の動き"
    elif abs(z) >= 2.5:
        concl = f"z={z:+.1f}σは通常の値動きの外。前提が変わった可能性"
    else:
        concl = f"{name}のz={z:+.1f}σは{THEME_BADGE[sector]}見通しの修正を示唆"
    conclusion = fit_units(concl, lim["conclusion"])

    if tk == "^TNX":
        fact_s = f"{name}は{event_label}の{m['last']:.2f}%（60日分布でz={z:+.1f}σ）。"
    else:
        fact_s = f"{name}は{ret:+.1f}%（60日分布でz={z:+.1f}σ）。"
    if vr:
        fact_s += f"出来高は20日平均の{vr:.1f}倍。"
    if rel_facts:
        fact_s += "、".join(f"{n}{v:+.1f}%" for n, v in rel_facts[:2]) + "。"
    fact = fit_units(fact_s, lim["fact_line"] * lim["fact_lines"] - 1)

    why = fit_units(_why(sector, down, p), lim["why_line"] * lim["why_lines"] - 1)

    w_spx, w_qqq = SPX_WEIGHT.get(tk), QQQ_WEIGHT.get(tk)
    if w_spx:
        contrib = w_spx / 100 * ret
        so = (f"{name}はS&P500の約{_pct(w_spx)}を占め、本日の指数寄与は約{contrib:+.2f}%pt。"
              f"QQQでは約{_pct(w_qqq)}でVTI・S&P500連動の投信にも同比率で効く。")
    elif tk in ("^GSPC", "^IXIC", "^DJI", "VTI", "QQQ"):
        so = (f"{name}{ret:+.1f}%はVTI・S&P500連動の投信にほぼ同率で反映される。"
              + (f"SOX指数は同日{dict(rel_facts).get('SOX指数', 0):+.1f}%で、"
                 f"ハイテク比率の高いQQQほど振れが大きい。" if rel_facts else ""))
    elif tk == "^TNX" or sector == "rates":
        so = (f"金利{event_label}の変化は高PER株比率の高いQQQに逆方向に効きやすく、"
              f"S&P500(構成の約3割がハイテク)にも同方向の圧力になる。")
    elif sector == "fx":
        so = (f"ドル円{ret:+.1f}%は米国株投信の円建て評価額に同率で直結する。"
              f"S&P500が同日{dict(rel_facts).get('S&P500', 0):+.1f}%なら円建てでは合算になる。")
    elif sector == "ai_semi":
        so = (f"半導体はS&P500の約1割・QQQの約2割を占め、{name}{ret:+.1f}%は"
              f"指数へ約{0.10 * ret:+.1f}%pt・約{0.20 * ret:+.1f}%ptの寄与。"
              f"VTI・S&P500連動の投信にも同経路で効く。")
    else:
        so = (f"{name}を含むセクターに{ret:+.1f}%が直接反映され、"
              f"S&P500全体への影響は構成比に応じて限定的（1%未満）にとどまる。")
    sowhat = fit_units(so, lim["sowhat_line"] * lim["sowhat_lines"] - 1)

    counter = fit_units(_counter(sector, down), lim["counter_line"] * lim["counter_lines"] - 1)

    # 投稿文（画像見出しと重複しない・一人称推測形・リスク併記・出典末尾）
    outlets = []
    for h in cand.get("headlines", []):
        o = h.get("outlet")
        if o and o not in outlets:
            outlets.append(o)
    cyc = "シクリカルな値動きなので、" if sector in ("memory", "ai_semi") else ""
    post1 = fit_units(
        f"{name}が{event_label}、出来高は平常時の{vr:.1f}倍。" if vr else
        f"{name}が{event_label}（z={z:+.1f}σ）。", 60)
    post1 += fit_units(f"単日の需給でなく{THEME_BADGE[sector]}シナリオの見直しが入ったと見ている。", 76)
    risk = f"{cyc}逆方向に振れる可能性も同じだけある前提で、指数の積立は淡々と継続。"
    src_line = "出典: " + "・".join(outlets[:2]) if outlets else "出典: yfinance(終値実測)"
    url = next((h.get("url") for h in cand.get("headlines", []) if h.get("url")), "")
    if url:
        src_line += f" {url}"
    post = fit_units(post1, cfg["limits"]["post"]) + "\n" + risk + "\n" + src_line

    story = {
        "ticker": tk, "name": name, "sector": sector,
        "theme": THEME_BADGE[sector],
        "headline": headline, "conclusion": conclusion,
        "fact": fact, "why": why, "sowhat": sowhat, "counter": counter,
        "numbers": numbers, "post": post,
        "event_date": asof_s, "event_pct": ret, "event_label": event_label,
        "score": cand.get("score"), "score_parts": cand.get("score_parts"),
        "n_media": cand.get("n_media"), "sns_heat": cand.get("sns_heat"),
    }
    return maybe_llm_polish(story, cfg)


def shorten(story: dict, level: int, cfg: dict) -> dict:
    """描画検証NG時の生成側短縮（levelが上がるほど強く縮める）。"""
    lim = cfg["limits"]
    k = 1.0 - 0.12 * level
    for key, budget in (("fact", lim["fact_line"] * lim["fact_lines"]),
                        ("why", lim["why_line"] * lim["why_lines"]),
                        ("sowhat", lim["sowhat_line"] * lim["sowhat_lines"]),
                        ("counter", lim["counter_line"] * lim["counter_lines"]),
                        ("conclusion", lim["conclusion"]),
                        ("headline", lim["headline"])):
        story[key] = fit_units(story[key], budget * k)
    return story


# ── 任意：Claude で文面を磨く（数値は変更禁止・失敗時は原文のまま）────
_EDITORIAL_POLICY = """あなたは投資情報カードの編集者。以下を厳守:
- 煽らない・断定しない。予測は「〜とみられる」等の推測形
- 個別銘柄・ETFを「買い」と推奨しない
- リスク・下落の可能性を必ず併記。メモリ/DRAM関連は「シクリカル」と明記
- 政治的な是非論に踏み込まない（事実と市場影響のみ）
- 会員限定記事の本文を引用しない
- 文中の数値・固有名詞は一切変更・追加しない（裏取りできない数字は書かない）
- 抽象論やどのニュースにも当てはまる文章を書かない"""


def maybe_llm_polish(story: dict, cfg: dict) -> dict:
    """ANTHROPIC_API_KEY があれば why/sowhat の文章を自然化する（任意）。"""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return story
    try:
        import json as _json
        import requests
        lim = cfg["limits"]
        req = {
            "model": "claude-sonnet-4-6", "max_tokens": 700,
            "system": _EDITORIAL_POLICY,
            "messages": [{"role": "user", "content":
                "次のJSONの why / sowhat / counter を、意味と数値を変えずに"
                f"自然で具体的な日本語へ整えて同じキーのJSONだけを返せ。"
                f"文字数上限: why={lim['why_line']*lim['why_lines']-1}字, "
                f"sowhat={lim['sowhat_line']*lim['sowhat_lines']-1}字, "
                f"counter={lim['counter_line']*lim['counter_lines']-1}字。\n"
                + _json.dumps({k: story[k] for k in ("why", "sowhat", "counter")},
                              ensure_ascii=False)}],
        }
        r = requests.post("https://api.anthropic.com/v1/messages",
                          headers={"x-api-key": key,
                                   "anthropic-version": "2023-06-01",
                                   "content-type": "application/json"},
                          json=req, timeout=45)
        r.raise_for_status()
        txt = "".join(b.get("text", "") for b in r.json().get("content", [])
                      if b.get("type") == "text")
        mjs = re.search(r"\{.*\}", txt, re.S)
        upd = _json.loads(mjs.group(0)) if mjs else {}
        # 数値が1つでも消えていたら採用しない（裏取り済み数字の保全）
        for k in ("why", "sowhat", "counter"):
            new = upd.get(k, "")
            olds = set(re.findall(r"[+-]?\d+(?:\.\d+)?", story[k]))
            if new and olds <= set(re.findall(r"[+-]?\d+(?:\.\d+)?", new)):
                lim_map = {"why": ("why_line", "why_lines"),
                           "sowhat": ("sowhat_line", "sowhat_lines"),
                           "counter": ("counter_line", "counter_lines")}
                ln, ns = lim_map[k]
                story[k] = fit_units(new, cfg["limits"][ln] * cfg["limits"][ns] - 1)
    except Exception as e:
        print(f"[warn] LLM整文はスキップ（テンプレでなくデータ由来の原文で続行）: {e}")
    return story
