# -*- coding: utf-8 -*-
"""生成ゲート：条件が揃った記事だけ画像化する（揃わなければスキップ）。

1記事につき、以下がすべて揃った場合のみ通過:
- 固有名詞（企業名・指数名）が1つ以上
- 検証済みの数値（出典・取得日時つき）が3つ以上
- 因果メカニズム（AだからB）が1文で書けている
- 「この見立てが外れる条件」が1つ書けている

check() は未充足項目のリストを返す（空リスト＝通過）。
未充足の内訳は logs/YYYY-MM-DD.json に記録される。
"""
from __future__ import annotations
import re

# 固有名詞として認める語（企業名・指数名。story_builder が使う表示名と揃える）
PROPER_NOUNS = (
    "エヌビディア", "マイクロソフト", "アップル", "アルファベット", "アマゾン",
    "メタ", "テスラ", "ブロードコム", "マイクロン", "インテル", "TSMC", "AMD",
    "SKハイニックス", "サムスン", "キオクシア",
    "S&P500", "ナスダック", "NYダウ", "SOX指数", "米10年金利", "ドル円",
    "VTI", "QQQ", "VYM", "HDV", "SCHD", "SMH", "XLE", "XLF", "XLU",
    "FRB", "FOMC", "日銀", "米財務省", "SEC",
)

# 因果マーカー：「AだからB」が1文で書けているかの判定に使う
_CAUSAL = ("ため", "ので", "ことで", "を受け", "につながる", "が効く", "に波及")


def _all_text(story: dict) -> str:
    return " ".join([story.get("headline", ""), story.get("conclusion", ""),
                     story.get("fact", ""), story.get("why", ""),
                     story.get("sowhat", ""), story.get("counter", "")])


def check(story: dict, cfg: dict) -> list[str]:
    """未充足項目のリストを返す。空なら生成してよい。"""
    unmet: list[str] = []
    g = cfg["gate"]

    nouns = [n for n in PROPER_NOUNS if n in _all_text(story)]
    if len(nouns) < g["min_proper_nouns"]:
        unmet.append(f"固有名詞が{g['min_proper_nouns']}件未満")

    nums = [n for n in story.get("numbers", [])
            if n.get("value") not in (None, "", "未検証")
            and n.get("source") and n.get("asof")]
    if len(nums) < g["min_numbers"]:
        unmet.append(f"検証済み数値が{len(nums)}件（{g['min_numbers']}件必要）")

    why = story.get("why", "")
    if not (why and any(m in why for m in _CAUSAL) and re.search(r"[0-9０-９]", why + story.get("fact", ""))):
        unmet.append("因果メカニズム（AだからB）が1文で書けていない")

    if not story.get("counter", "").strip():
        unmet.append("「見立てが外れる条件」が書けていない")

    return unmet
