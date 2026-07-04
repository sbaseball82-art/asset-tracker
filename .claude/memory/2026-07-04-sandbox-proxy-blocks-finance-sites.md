Claude Codeリモート環境では金融サイトが403でブロックされる→コードのバグではないので修理せず、価格取得はGitHub Actionsに任せる。

## 状況

Claude Codeのリモートコンテナで `python3 fetch_prices.py` を実行したところ、
全銘柄が以下のエラーで失敗した:

```
curl: (56) CONNECT tunnel failed, response 403
ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden'))
```

対象: query1.finance.yahoo.com、toushin-lib.fwg.ne.jp、feeds.marketwatch.com、www.cnbc.com など
金融・ニュース系の外部サイト全部。

## 誤った対処（やりがちなこと）

- 「コードが壊れている」と判断してリトライ処理やUA偽装を追加する（本番Actionsでは毎朝動いている）
- プロキシ設定を外す・TLS検証を無効にする（環境の規約違反）
- 一部銘柄だけ成功した不完全な data.json をコミットする

## 正しい対処

1. これは実行環境のネットワークポリシーによるブロック。コードは触らない
2. 価格取得が必要なら GitHub Actions の workflow_dispatch で本番環境に実行させる
   （Actionsタブ → daily-asset-slide → Run workflow）
3. この環境でできる検証はスライド生成（make_slide.py、ローカル完結）と、
   stock-daily の `MOCK=1 python3 stock-daily/daily_report.py`（ネット不要のモック実行）

## 出典

2026-07-04 のClaude Codeセッション（引き継ぎマニュアル作成時の実機検証）。
fetch_prices.py / fetch_events.py の両方で再現確認済み。
