# 週次・米国決算カレンダー画像

その週に決算を発表する注目の米国企業を一覧にした画像を、毎週自動で作る。
**成果物は画像（PNG / JPEG）だけ。投稿文はこのツールでは作らない。**
したがって投稿文を書くのに要る数字（EPS予想・売上予想・発表タイミング）は
すべて画像の中に入れてある。

| | |
|---|---|
| サイズ | 1180 × 1450（既存の ASSET LOG シリーズと共通） |
| 出力 | `output/earnings_week/earnings_YYYYMMDD.png` / `.jpg` |
| 目視確認用 | `qa/earnings_YYYYMMDD_thumb.png`（幅400px） |
| データ | [Finnhub](https://finnhub.io/) Earnings Calendar + `stock/profile2` |
| 実行 | 日曜 22:00 JST に GitHub Actions が翌週ぶんを生成 |

やらないこと：投稿文の生成 / X への投稿 / 株価予測・投資判断・推奨コメント。

---

## 1. Finnhub APIキーの取得と登録

1. <https://finnhub.io/register> で登録する（無料枠でよい）
2. ダッシュボードの **API Key** をコピーする
3. GitHub のリポジトリで
   **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `FINNHUB_API_KEY`
   - Secret: コピーしたキー

**キーをコードやYAMLに直書きしない。** 読み込みは環境変数だけ。

無料枠は **60 リクエスト/分**。呼び出し間隔を1.1秒空け、429/5xx は
2→4→8→16秒のバックオフで4回まで再試行する。企業プロフィールとロゴは
30日キャッシュするので、2回目以降のリクエストはほとんど発生しない。

## 2. ローカルでの実行

```bash
pip install -r requirements-earnings-week.txt
sudo apt-get install -y fonts-noto-cjk        # 日本語フォント（必須）

export FINNHUB_API_KEY=xxxxxxxx

# レイアウトだけ確認する（APIを叩かない。ダミーデータ）
python -m src.earnings_week.main --sample

# 翌週ぶんを生成
python -m src.earnings_week.main

# 週を指定して作り直す（過去週・未来週）
python -m src.earnings_week.main --week-start 2026-08-31

# 企業プロフィール・ロゴはキャッシュのみ使う（カレンダーは取得する）
python -m src.earnings_week.main --offline
```

`--sample` は `tests/fixtures/earnings_week_sample.json` だけを読み、
`output/earnings_week/sample/` と `qa/sample/` にしか書かない。
**サンプルの数字が本番の出力に混ざることはない。**

終了コード：`0` 生成できた / `2` DATA WAIT（対象0社） / `1` 異常。

## 3. watchlist の編集

APIは週に数百社を返すので `config/watchlist.json` で絞り込む。
ここに載っているティッカーだけが候補になり、**時価総額の大きい順**に
上位12社を画像に載せる（13社目以降はフッターに「ほか◯社」と出る）。

```jsonc
{
  "tickers": ["AAPL", "MSFT", "NVDA", ...]   // 米国上場のティッカー
}
```

- 載せたい会社が出てこない → `tickers` に足す
- ADR は Finnhub の表記に合わせる（例：台湾積体電路は `TSM`）
- ドット付きティッカー（`BRK.B` など）は Finnhub 側の表記ゆれがあるため、
  入れる場合は `--week-start` を指定した手動実行で拾えるか確かめる

見た目（配色・級数・余白・最大掲載社数）は `config/theme.json`。
どちらもコードを触らずに編集できる。

## 4. 画像に載る内容

```
EARNINGS WEEK                                    [2026 W36]
今週の米国決算
2026/08/31 - 09/04                              @84m5dm9xdm
────────────────────────────────────────────────────────
8/31 (月) ───────────────────────────────────────────────
 [logo] AAPL                                        引け後
        Apple Inc.              EPS予想 2.41  売上予想 98.5B
 ...
────────────────────────────────────────────────────────
※データ：Finnhub。予想値は市場コンセンサス。投資助言ではありません   ASSET LOG
```

- 発表タイミング：`bmo` → 寄付前 / `amc` → 引け後 / `dmh` → 場中 /
  不明 → **時間未定**（引け後と決めつけない）
- ロゴが取れない会社は、ティッカー4文字を配色ブロックに載せて代替する
  （青 `#6BA8F5` / 青緑 `#7FD4C1` / 金 `#E0B45C` からティッカーのハッシュで決定）
- 掲載社数によって行の高さと余白は自動で変わる。12社の週は詰まり、
  数社の週は行を広げて余白で調整する

### 数字の扱い（最重要）

**APIが返さなかった値は推測・補完しない。**
EPS予想が `null` の行は `EPS予想 —` と描く。0 で埋めたり、前週の値を
流用したり、他社の平均を入れたりはしない。画像に写っている数字だけを
投稿文に使えばよい、という状態を保つための約束。

対象が0社の週は **画像を作らずに DATA WAIT で終わる**。
ダミーデータで1枚でっち上げるほうが、出さないことよりずっと悪い。

## 5. 生成後の自動チェック

`src/earnings_week/qa.py` が全部を検査し、1つでも落ちたら異常終了する。

| 検査 | やり方 |
|---|---|
| 豆腐（□ / U+FFFD / 未定義グリフ） | 描画**前**に1文字ずつ `getmask` で .notdef と照合 |
| はみ出し | 描いた文字の実測 bbox がカード内に収まっているか |
| 重なり | 文字の矩形どうしの交差判定 |
| 画像サイズ | 1180 × 1450 であること |
| 掲載社数 | 1社以上あること |
| サムネイル | 幅400pxを `qa/` に出力（Xで潰れないかを人間が見る） |

## 6. よくある失敗と対処

| 症状 | 原因 | 対処 |
|---|---|---|
| `日本語を描けるフォントが見つかりません` | Noto CJK 未インストール | `sudo apt-get install -y fonts-noto-cjk && fc-cache -f`。Actions では `Install Noto CJK fonts` ステップが入れる |
| `豆腐（グリフ欠落）: ...` | フォントに無い文字を使った | その文字を使わないか、フォントを替える。**画像は出さない**（□の混じった画像を出すより止めるほうがよい） |
| `環境変数 FINNHUB_API_KEY が設定されていません` | Secret 未登録 / ローカルで未export | 上の「1.」を参照 |
| `レート制限（HTTP 429）` が続く | 無料枠 60 req/min 超過 | 自動で待って再試行する。それでも駄目なら時間を空けて再実行。`cache/` を消さないこと（消すと全社ぶん取り直しになる） |
| `Finnhub に拒否されました（HTTP 401/403）` | キーが無効、または無料枠外 | キーを再発行して Secret を更新する |
| `DATA WAIT` | その週に watchlist 該当の決算が無い | 正常な結果。決算シーズンの谷間や祝日週に起きる。載せたい会社があるなら watchlist に足して再実行 |
| `画像の品質検査に失敗しました: はみ出し...` | 文言や級数を変えて枠に収まらなくなった | `config/theme.json` の級数・`max_companies` を調整する |
| 画像が更新されない | Actions が DATA WAIT で終わっている | 実行サマリーに理由が出ている。`workflow_dispatch` で `week_start` を指定して再実行 |

## 7. ファイル

```
config/watchlist.json          監視ティッカー（編集する）
config/theme.json              配色・級数・余白（編集する）
src/earnings_week/
  main.py                      エントリポイント
  fetch_earnings.py            Finnhub 決算カレンダー（リトライ・レート制限）
  fetch_profile.py             企業名・時価総額・ロゴ（30日キャッシュ）
  render.py                    Pillow 描画
  qa.py                        品質チェック
  fonts.py                     フォント探索（パスをハードコードしない）
cache/logos/                   ロゴのキャッシュ（.gitignore）
output/earnings_week/          生成物（PNG / JPEG）
qa/                            幅400px サムネイル
tests/test_earnings_week.py    テスト
.github/workflows/weekly-earnings.yml
```
