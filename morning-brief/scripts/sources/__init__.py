# -*- coding: utf-8 -*-
"""ニュース・データ取得の3レイヤ。

レイヤ1 market.py  : 市場の実際の動き（yfinance。最優先シグナル）
レイヤ2 primary.py : 一次情報（SEC EDGAR・FRED・米財務省・IR RSS・経済カレンダー）
レイヤ3 buzz.py    : 報道・話題性（Google News・Yahoo RSS・Finnhub・Reddit・HN）

原則: 画像に載せる数字は必ずレイヤ1・2から取る。レイヤ3は
「何が話題か」の検出と媒体一致数・SNS熱量のスコアリングにだけ使う。
各モジュールは単体実行できる（python -m sources.market 等）。
"""
