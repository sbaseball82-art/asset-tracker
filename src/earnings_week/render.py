# -*- coding: utf-8 -*-
"""
render.py
=========
1180×1450 の決算カレンダー画像を Pillow で描く。

デザインは既存の ASSET LOG シリーズに合わせる（背景 #0B1220 / 金 #E0B45C）。
配色・級数・余白は config/theme.json に外出ししてあり、コードは触らない。

方針
----
* **詰め込まない。** 掲載は最大12社。行の高さは掲載社数から自動で決まり、
  少ない週は高さと余白を広げて埋める（引き伸ばして不格好にしない）。
* 描いた文字は1つずつ矩形を記録して qa.py に渡す。
  はみ出し・重なり・豆腐は画像を出す前に機械で落とす。
* **APIが返さなかった値は埋めない。** EPS予想が無ければ「—」と描く。

内部は 2倍で描いてから縮小している（角丸とロゴのジャギー対策）。
座標・級数は 1180×1450 のデザイン座標で書き、Canvas が倍率を吸収する。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw

from . import fonts, qa
from .qa import QAReport, TextBox

SUPERSAMPLE = 2

# レイアウトが破綻する前に許す最小値（theme.json の指定より下げる最後の手段）
_HARD_MIN_CARD_H = 50
_HARD_MIN_GAP = 6


# ---------------------------------------------------------------- データ


@dataclass
class Company:
    """画像に1行として載る1社分。すべて取得できた値だけを持つ。"""

    symbol: str
    date: str                       # ISO (YYYY-MM-DD)
    name: str = ""
    hour: str = ""                  # bmo / amc / dmh / ""
    eps_estimate: float | None = None
    revenue_estimate: float | None = None
    market_cap: float | None = None
    logo_path: str | None = None

    @property
    def day(self) -> date:
        return date.fromisoformat(self.date)


# ---------------------------------------------------------------- 表記


def fmt_eps(value: float | None) -> str:
    """EPS予想。取れていなければ「—」。**推測で埋めない。**"""
    if value is None:
        return "—"
    return f"{value:,.2f}"


def fmt_revenue(value: float | None) -> str:
    """売上予想（USD）を B / M に丸める。取れていなければ「—」。"""
    if value is None:
        return "—"
    v = float(value)
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1e12:
        return f"{sign}{v / 1e12:.2f}T"
    if v >= 1e9:
        return f"{sign}{v / 1e9:.1f}B"
    if v >= 1e6:
        return f"{sign}{v / 1e6:.0f}M"
    return f"{sign}{v:,.0f}"


def timing_label(hour: str | None, theme: dict) -> str:
    """bmo / amc / dmh を日本語に。未知の値は「時間未定」（勝手に決めない）。"""
    labels = theme["timing_labels"]
    return labels.get((hour or "").lower(), labels[""])


def timing_style(hour: str | None, theme: dict) -> dict:
    """バッジの見た目（solid=塗り / outline=枠線）。theme.json で差し替えられる。"""
    styles = theme["timing_styles"]
    return styles.get((hour or "").lower(), styles[""])


def fmt_day_heading(day: date, theme: dict) -> str:
    """「8/31 (月)」。"""
    return f"{day.month}/{day.day} ({theme['weekday_ja'][day.weekday()]})"


def fmt_range(start: date, end: date) -> str:
    """「2026/08/31 - 09/04」。年をまたぐときは両方に年を付ける。"""
    left = f"{start.year}/{start.month:02d}/{start.day:02d}"
    if start.year == end.year:
        right = f"{end.month:02d}/{end.day:02d}"
    else:
        right = f"{end.year}/{end.month:02d}/{end.day:02d}"
    return f"{left} - {right}"


def fmt_week_badge(start: date) -> str:
    """「2026 W36」。ISO週番号。"""
    iso = start.isocalendar()
    return f"{iso[0]} W{iso[1]:02d}"


def output_stem(start: date) -> str:
    """ファイル名は英数字のみ。"""
    return f"earnings_{start:%Y%m%d}"


def group_by_day(companies: list[Company]) -> list[tuple[date, list[Company]]]:
    """日付ごとにまとめる。日は昇順、同日内は時価総額の大きい順。"""
    buckets: dict[date, list[Company]] = {}
    for c in companies:
        buckets.setdefault(c.day, []).append(c)
    out = []
    for day in sorted(buckets):
        rows = sorted(buckets[day],
                      key=lambda c: (-(c.market_cap or 0.0), c.symbol))
        out.append((day, rows))
    return out


# ---------------------------------------------------------------- 配置計算


@dataclass
class LayoutPlan:
    card_h: float
    card_gap: float
    section_gap: float
    heading_gap: float
    heading_h: float
    top_offset: float
    ticker_size: int
    name_size: int
    timing_size: int
    estimate_size: int
    fits: bool = True


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def plan_layout(n_cards: int, n_days: int, avail_h: float,
                theme: dict) -> LayoutPlan:
    """掲載社数から行の高さと余白を決める（純粋関数）。

    多い週は余白を詰め、少ない週は高さと余白を広げて中央に置く。
    それでも入らないときは fits=False を返し、呼び出し側が掲載数を減らす。
    """
    s, lay = theme["sizes"], theme["layout"]
    heading_h = round(s["day_heading"] * 1.35)
    heading_gap = lay["day_heading_gap"]
    card_gap = lay["card_gap"]
    section_gap = lay["section_gap"]

    def total(card_h, card_gap, section_gap, heading_gap):
        return (n_days * (heading_h + heading_gap)
                + max(0, n_days - 1) * section_gap
                + max(0, n_cards - n_days) * card_gap
                + n_cards * card_h)

    fixed = total(0, card_gap, section_gap, heading_gap)
    card_h = _clamp((avail_h - fixed) / max(1, n_cards),
                    s["card_height_min"], s["card_height_max"])

    # ① 入らなければ余白を詰める
    if total(card_h, card_gap, section_gap, heading_gap) > avail_h:
        card_gap = _HARD_MIN_GAP
        section_gap = max(_HARD_MIN_GAP * 2, section_gap * 0.6)
        heading_gap = _HARD_MIN_GAP
    # ② それでも入らなければ行の高さを下げる
    if total(card_h, card_gap, section_gap, heading_gap) > avail_h:
        fixed = total(0, card_gap, section_gap, heading_gap)
        card_h = max(_HARD_MIN_CARD_H, (avail_h - fixed) / max(1, n_cards))

    fits = total(card_h, card_gap, section_gap, heading_gap) <= avail_h + 0.5

    # ③ 余ったぶんは余白へ回し、最後は上下中央に置く
    slack = avail_h - total(card_h, card_gap, section_gap, heading_gap)
    if slack > 0 and n_cards > 1:
        room = (lay["card_gap_max"] - card_gap) * max(0, n_cards - n_days)
        add = min(slack, room)
        if room > 0:
            card_gap += add / max(1, n_cards - n_days)
            slack -= add
    if slack > 0 and n_days > 1:
        room = (lay["section_gap_max"] - section_gap) * (n_days - 1)
        add = min(slack, room)
        if room > 0:
            section_gap += add / (n_days - 1)
            slack -= add
    top_offset = max(0.0, slack / 2)

    ticker = int(round(_clamp(card_h * s["ticker_ratio"],
                              s["ticker_min"], s["ticker_max"])))
    name = int(round(_clamp(card_h * s["name_ratio"],
                            s["name_min"], s["name_max"])))
    timing = int(round(_clamp(card_h * s["timing_ratio"],
                              s["timing_min"], s["timing_max"])))
    est = int(round(_clamp(card_h * s["estimate_ratio"],
                           s["estimate_min"], s["estimate_max"])))
    return LayoutPlan(card_h=card_h, card_gap=card_gap, section_gap=section_gap,
                      heading_gap=heading_gap, heading_h=heading_h,
                      top_offset=top_offset, ticker_size=ticker,
                      name_size=name, timing_size=timing, estimate_size=est,
                      fits=fits)


# ---------------------------------------------------------------- 描画基盤


def _hex(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def blend(fg: str, bg: str, alpha: float) -> tuple[int, int, int]:
    """半透明の代わりに、あらかじめ混ぜた色を作る（出力はRGB）。"""
    f, b = _hex(fg), _hex(bg)
    return tuple(round(f[i] * alpha + b[i] * (1 - alpha)) for i in range(3))  # type: ignore[return-value]


class Canvas:
    """デザイン座標で描き、描いた文字の矩形を記録するキャンバス。"""

    def __init__(self, width: int, height: int, bg: str,
                 scale: int = SUPERSAMPLE, font_family: str = "Noto Sans CJK JP",
                 font_index: int = 0, bg_bottom: str | None = None):
        self.w, self.h, self.scale = width, height, scale
        self.family, self.findex = font_family, font_index
        self.img = Image.new("RGB", (width * scale, height * scale), _hex(bg))
        if bg_bottom and bg_bottom != bg:
            self._paint_gradient(bg, bg_bottom)
        self.draw = ImageDraw.Draw(self.img)
        self.report = QAReport()

    def _paint_gradient(self, top: str, bottom: str) -> None:
        """上から下へごく淡く色を変える（参考デザインの下がわずかに明るい背景）。"""
        a, b = _hex(top), _hex(bottom)
        h = self.img.height
        column = Image.new("RGB", (1, h))
        px = column.load()
        for y in range(h):
            t = y / max(1, h - 1)
            px[0, y] = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))
        self.img.paste(column.resize((self.img.width, h)), (0, 0))

    # -- フォント --------------------------------------------------
    def font(self, size: int, bold: bool = False):
        return fonts.load(int(round(size * self.scale)), bold,
                          self.family, self.findex)

    def measure(self, text: str, size: int, bold: bool = False) -> float:
        return self.font(size, bold).getlength(text) / self.scale

    def ink(self, text: str, size: int, bold: bool = False) -> tuple[float, float, float, float]:
        """anchor="la" で描いたときに実際にインクが乗る範囲（デザイン座標）。

        CJKフォントの ascent+descent は 1.45em ほどあり、欧文のティッカーを
        並べるには過大。行の高さは実測のインクで決める。
        """
        bb = self.font(size, bold).getbbox(text, anchor="la")
        return tuple(v / self.scale for v in bb)  # type: ignore[return-value]

    def metrics(self, size: int, bold: bool = False) -> tuple[float, float]:
        ascent, descent = self.font(size, bold).getmetrics()
        return ascent / self.scale, descent / self.scale

    def fit(self, text: str, size: int, max_w: float, bold: bool = False) -> str:
        """max_w に収まるよう末尾を「…」で詰める（企業名にだけ使う）。"""
        if self.measure(text, size, bold) <= max_w:
            return text
        out = text
        while out and self.measure(out + "…", size, bold) > max_w:
            out = out[:-1]
        return (out + "…") if out else "…"

    # -- 図形 ------------------------------------------------------
    def _s(self, box):
        return [round(v * self.scale) for v in box]

    def rrect(self, box, radius: float, fill=None, outline=None, width: float = 1):
        self.draw.rounded_rectangle(
            self._s(box), radius=round(radius * self.scale),
            fill=fill, outline=outline, width=max(1, round(width * self.scale)))

    def line(self, box, fill, width: float = 1):
        self.draw.line(self._s(box), fill=fill,
                       width=max(1, round(width * self.scale)))

    def paste(self, image: Image.Image, xy, mask=None):
        self.img.paste(image, (round(xy[0] * self.scale), round(xy[1] * self.scale)),
                       mask)

    # -- 文字 ------------------------------------------------------
    def text(self, xy, text: str, size: int, fill, *, bold: bool = False,
             anchor: str = "la", clip=None, label: str = "",
             tracking: float = 0.0, collide: bool = True) -> TextBox:
        """文字を描いて矩形を記録する。描く前に必ず豆腐検査を通す。"""
        font = self.font(size, bold)
        qa.assert_glyphs(text, font, label)
        x, y = xy[0] * self.scale, xy[1] * self.scale

        if tracking:
            track = tracking * self.scale
            cursor = x
            boxes = []
            for ch in text:
                bb = self.draw.textbbox((cursor, y), ch, font=font, anchor=anchor)
                self.draw.text((cursor, y), ch, font=font, fill=fill, anchor=anchor)
                boxes.append(bb)
                cursor += font.getlength(ch) + track
            bbox = (min(b[0] for b in boxes), min(b[1] for b in boxes),
                    max(b[2] for b in boxes), max(b[3] for b in boxes))
        else:
            bbox = self.draw.textbbox((x, y), text, font=font, anchor=anchor)
            self.draw.text((x, y), text, font=font, fill=fill, anchor=anchor)

        rect = tuple(v / self.scale for v in bbox)
        box = TextBox(text=text, rect=rect,  # type: ignore[arg-type]
                      clip=tuple(clip) if clip else (0, 0, self.w, self.h),  # type: ignore[arg-type]
                      label=label, collide=collide)
        self.report.boxes.append(box)
        return box

    # -- 仕上げ ----------------------------------------------------
    def finish(self) -> Image.Image:
        if self.scale == 1:
            return self.img
        return self.img.resize((self.w, self.h), Image.LANCZOS)


# ---------------------------------------------------------------- ロゴ


def fallback_color(symbol: str, palette: list[str]) -> str:
    """ティッカーから決定的に色を選ぶ（毎回同じ色になる）。"""
    digest = hashlib.sha1(symbol.encode("utf-8")).hexdigest()
    return palette[int(digest, 16) % len(palette)]


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1),
                                           radius=radius, fill=255)
    return mask


def mean_luminance(image: Image.Image, alpha_floor: int = 32) -> float:
    """不透明な画素の平均的な明るさ（0〜255）。暗いロゴの判定に使う。"""
    rgba = image.convert("RGBA")
    total = count = 0.0
    for r, g, b, a in rgba.getdata():
        if a >= alpha_floor:
            total += 0.299 * r + 0.587 * g + 0.114 * b
            count += 1
    return total / count if count else 255.0


def _logo_tile(path: str, size: int, radius: int, theme: dict
               ) -> Image.Image | None:
    """カードに載せるロゴのタイル（RGBA）を作る。

    参考デザインに合わせ **白パッドは敷かない**。ただし黒一色の透過ロゴは
    暗い背景で消えてしまうため、不透明部の明るさが閾値を下回るときだけ
    白い角丸パッドを敷く（読めないロゴを出さないための保険）。
    読めない/壊れたファイルなら None を返し、呼び出し側が代替表示に落とす。
    """
    try:
        with Image.open(path) as src:
            logo = src.convert("RGBA")
    except Exception:  # noqa: BLE001 — 壊れたキャッシュで生成を止めない
        return None

    cfg = theme.get("logo", {})
    threshold = cfg.get("dark_luminance_threshold", 78)
    inset = cfg.get("inset_ratio", 0.94)

    if mean_luminance(logo) < threshold:
        # 暗いロゴ: 白い角丸パッドの上に置く
        tile = Image.new("RGBA", (size, size),
                         (*_hex(theme["colors"]["logo_pad"]), 255))
        fitted = logo.copy()
        fitted.thumbnail((round(size * 0.76), round(size * 0.76)), Image.LANCZOS)
        tile.alpha_composite(fitted, ((size - fitted.width) // 2,
                                      (size - fitted.height) // 2))
        tile.putalpha(_rounded_mask(size, radius))
        return tile

    # 明るい/色付きのロゴ: 背景を敷かずそのまま置く
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    fitted = logo.copy()
    fitted.thumbnail((round(size * inset), round(size * inset)), Image.LANCZOS)
    tile.alpha_composite(fitted, ((size - fitted.width) // 2,
                                  (size - fitted.height) // 2))
    return tile


# ---------------------------------------------------------------- 本体


@dataclass
class RenderResult:
    image: Image.Image
    report: QAReport
    logo_missing: list[str] = field(default_factory=list)


def render_week(companies: list[Company], week_start: date, week_end: date,
                theme: dict, others: int = 0, handle: str = "@84m5dm9xdm",
                stale_note: str = "", sample: bool = False) -> RenderResult:
    """1週間ぶんの決算カレンダー画像を描いて返す（保存は呼び出し側）。

    sample=True のときは「SAMPLE」表示を必ず入れる。ダミーの日付・数値で
    描いた画像が本物の決算日として読まれないようにするため。
    """
    cv_cfg, col, s, lay = (theme["canvas"], theme["colors"],
                           theme["sizes"], theme["layout"])
    W, H = cv_cfg["width"], cv_cfg["height"]
    mx = cv_cfg["margin_x"]
    cv = Canvas(W, H, col["bg"], font_family=theme["font"]["family"],
                font_index=theme["font"].get("index", 0),
                bg_bottom=col.get("bg_bottom"))
    right = W - mx
    rule = blend(col.get("rule", col["gold"]), col["bg"],
                 col.get("rule_alpha", 0.42))

    # ---- ヘッダー -------------------------------------------------
    top = cv_cfg["margin_top"]
    cv.text((mx, top), theme["text"]["brand"], s["brand"], col["gold"],
            bold=True, tracking=4, clip=(mx, top - 4, right, top + 60),
            label="brand")

    if sample:
        stext = theme["text"]["sample_badge"]
        sw = cv.measure(stext, s["badge_week"], bold=True)
        sa, sd = cv.metrics(s["badge_week"], bold=True)
        spill_h = round((sa + sd) + 16)
        spill = (mx + cv.measure(theme["text"]["brand"], s["brand"], True) + 4 * 13 + 26,
                 top - 2, 0, 0)
        spill = (spill[0], top - 2, spill[0] + sw + 34, top - 2 + spill_h)
        cv.rrect(spill, spill_h / 2, fill=blend(col["down"], col["bg"], 0.20),
                 outline=blend(col["down"], col["bg"], 0.65), width=1)
        cv.text(((spill[0] + spill[2]) / 2, (spill[1] + spill[3]) / 2), stext,
                s["badge_week"], col["down"], bold=True, anchor="mm",
                clip=(spill[0] + 4, spill[1], spill[2] - 4, spill[3]),
                label="sample_badge")

    badge_text = fmt_week_badge(week_start)
    bw = cv.measure(badge_text, s["badge_week"], bold=True)
    ba, bd = cv.metrics(s["badge_week"], bold=True)
    pill_h = round((ba + bd) + 16)
    pill = (right - bw - 36, top - 2, right, top - 2 + pill_h)
    cv.rrect(pill, pill_h / 2, fill=blend(col["gold"], col["bg"], 0.14),
             outline=blend(col["gold"], col["bg"], 0.45), width=1)
    cv.text(((pill[0] + pill[2]) / 2, (pill[1] + pill[3]) / 2), badge_text,
            s["badge_week"], col["gold"], bold=True, anchor="mm",
            clip=(pill[0] + 4, pill[1], pill[2] - 4, pill[3]), label="week_badge")

    ty = top + 50
    cv.text((mx, ty), theme["text"]["title"], s["title"], col["text"], bold=True,
            clip=(mx, ty - 4, right, ty + s["title"] * 1.5), label="title")

    ry = ty + round(s["title"] * 1.5) + 6
    cv.text((mx, ry), fmt_range(week_start, week_end), s["range"], col["dim"],
            clip=(mx, ry - 4, right - 260, ry + s["range"] * 1.6), label="range")
    cv.text((right, ry + 2), handle, s["handle"],
            col.get("handle", col["blue"]), anchor="ra",
            clip=(right - 260, ry - 4, right, ry + s["handle"] * 1.8),
            label="handle")

    div_y = ry + round(s["range"] * 1.6) + 18
    cv.line((mx, div_y, right, div_y), fill=rule, width=1)

    # ---- フッター（先に位置を決めて本文の高さを確定させる） -------
    foot_div = H - cv_cfg["margin_bottom"] - 52
    cv.line((mx, foot_div, right, foot_div), fill=rule, width=1)
    fy = foot_div + 16
    cv.text((mx, fy), theme["text"]["disclaimer"], s["footer"], col["dim"],
            clip=(mx, fy - 4, right - 190, fy + s["footer"] * 2), label="disclaimer")
    cv.text((right, fy - 4), theme["text"]["footer_brand"], s["footer_brand"],
            col["gold"], bold=True, anchor="ra",
            clip=(right - 190, fy - 8, right, fy + s["footer_brand"] * 1.6),
            label="footer_brand")

    body_bottom = foot_div - 22
    notes: list[str] = []
    if sample:
        notes.append(theme["text"]["sample_note"])
    if others > 0:
        notes.append(f"ほか{others}社（時価総額の大きい順に{lay['max_companies']}社を掲載）")
    if stale_note:
        notes.append(stale_note)
    if notes:
        note_text = "　".join(notes)
        ny = foot_div - 30
        cv.text((right, ny), note_text, s["note"], col["dim"], anchor="ra",
                clip=(mx, ny - 4, right, ny + s["note"] * 1.6), label="note")
        body_bottom = ny - 14

    # ---- 本文 -----------------------------------------------------
    body_top = div_y + 26
    days = group_by_day(companies)
    plan = plan_layout(len(companies), len(days), body_bottom - body_top, theme)

    y = body_top + plan.top_offset
    for di, (day, rows) in enumerate(days):
        if di:
            y += plan.section_gap
        head = fmt_day_heading(day, theme)
        cv.text((mx, y), head, s["day_heading"], col["gold"], bold=True,
                clip=(mx, y - 2, right, y + plan.heading_h + 2),
                label=f"day:{day}")
        hw = cv.measure(head, s["day_heading"], bold=True)
        rule_y = y + plan.heading_h * 0.55
        cv.line((mx + hw + 18, rule_y, right, rule_y), fill=rule, width=1)
        y += plan.heading_h + plan.heading_gap

        for ci, company in enumerate(rows):
            if ci:
                y += plan.card_gap
            _draw_card(cv, company, mx, y, right, y + plan.card_h, plan, theme)
            y += plan.card_h

    cv.report.companies = len(companies)
    missing = [c.symbol for c in companies if not c.logo_path]
    if not plan.fits:
        cv.report.notes.append("レイアウトが収まりきりませんでした")
    return RenderResult(image=cv.finish(), report=cv.report, logo_missing=missing)


def _draw_card(cv: Canvas, c: Company, x0: float, y0: float, x1: float, y1: float,
               plan: LayoutPlan, theme: dict) -> None:
    col, s, lay = theme["colors"], theme["sizes"], theme["layout"]
    h = y1 - y0
    cv.rrect((x0, y0, x1, y1), lay["card_radius"], fill=_hex(col["card"]),
             outline=_hex(col["line"]), width=1)

    # ロゴ（カードの上に直接。取れなければ配色ブロック＋ティッカー4文字）
    box = int(round(_clamp(h * lay["logo_box_ratio"], 38, 92)))
    lx, ly = x0 + lay["card_pad_x"], y0 + (h - box) / 2
    tile = _logo_tile(c.logo_path, box * cv.scale,
                      round(lay["logo_radius"] * cv.scale), theme) \
        if c.logo_path else None
    if tile is not None:
        cv.paste(tile.convert("RGB"), (lx, ly), tile.split()[-1])
    else:
        color = fallback_color(c.symbol, theme["fallback_palette"])
        cv.rrect((lx, ly, lx + box, ly + box), lay["logo_radius"], fill=_hex(color))
        short = c.symbol[:4]
        size = int(round(box * 0.46))
        while size > 8 and cv.measure(short, size, True) > box * 0.78:
            size -= 1
        cv.text((lx + box / 2, ly + box / 2), short, size, _hex(col["bg"]),
                bold=True, anchor="mm", clip=(lx, ly, lx + box, ly + box),
                label=f"logo_fallback:{c.symbol}", collide=False)

    # 右側（発表タイミングのバッジ / 予想値）
    tlabel = timing_label(c.hour, theme)
    tstyle = timing_style(c.hour, theme)
    tw = cv.measure(tlabel, plan.timing_size, bold=True)
    est = f"EPS予想 {fmt_eps(c.eps_estimate)}　売上予想 {fmt_revenue(c.revenue_estimate)}"
    ew = cv.measure(est, plan.estimate_size)
    right_w = max(tw + 30, ew)
    right_edge = x1 - lay["card_pad_x"]

    # 左側（ティッカー / 企業名）。行の高さは実測のインクで決めて上下中央に置く
    text_left = lx + box + lay["logo_gap"]
    text_right = right_edge - right_w - 30
    avail_w = text_right - text_left
    symbol = cv.fit(c.symbol, plan.ticker_size, avail_w, True)
    name = cv.fit(c.name or c.symbol, plan.name_size, avail_w)
    tb = cv.ink(symbol, plan.ticker_size, True)
    nb = cv.ink(name, plan.name_size)
    th, nh = tb[3] - tb[1], nb[3] - nb[1]
    gap = max(3.0, h * 0.055)
    block = th + gap + nh
    top = y0 + (h - block) / 2
    clip_l = (text_left - 1, y0 + 2, text_right, y1 - 2)

    cv.text((text_left, top - tb[1]), symbol, plan.ticker_size, col["text"],
            bold=True, clip=clip_l, label=f"ticker:{c.symbol}")
    cv.text((text_left, top + th + gap - nb[1]), name, plan.name_size, col["dim"],
            clip=clip_l, label=f"name:{c.symbol}")

    # バッジはティッカーの行、予想値は企業名の行に揃える
    badge_h = th * 1.35
    badge_cy = top + th / 2
    badge = (right_edge - tw - 30, badge_cy - badge_h / 2,
             right_edge, badge_cy + badge_h / 2)
    accent = tstyle["color"]
    if tstyle.get("mode") == "solid":
        fill, outline, tcolor = _hex(accent), None, tstyle.get("text", "#0B1220")
    else:
        fill = blend(accent, col["card"], 0.16)
        outline = blend(accent, col["card"], 0.55)
        tcolor = accent
    cv.rrect(badge, badge_h / 2, fill=fill, outline=outline, width=1)
    cv.text(((badge[0] + badge[2]) / 2, badge_cy), tlabel, plan.timing_size, tcolor,
            bold=True, anchor="mm",
            clip=(badge[0] + 2, y0 + 2, badge[2], y1 - 2),
            label=f"timing:{c.symbol}")
    cv.text((right_edge, top + th + gap + nh / 2), est, plan.estimate_size,
            col["dim"],
            anchor="rm", clip=(text_right, y0 + 2, right_edge, y1 - 2),
            label=f"est:{c.symbol}")


# ---------------------------------------------------------------- 保存


def save(image: Image.Image, out_dir: Path, stem: str, theme: dict) -> dict[str, Path]:
    """PNG と JPEG を書き出す。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / f"{stem}.png"
    jpg = out_dir / f"{stem}.jpg"
    rgb = image.convert("RGB")
    rgb.save(png, "PNG", optimize=True)
    rgb.save(jpg, "JPEG", quality=theme["qa"]["jpeg_quality"],
             progressive=False, optimize=True)
    return {"png": png, "jpg": jpg}
