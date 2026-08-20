# 業績比較アニメーション動画

縦型 1080×1920 / 60fps / 音声なしの mp4 を Remotion で書き出す。
**1つの動画＝1つのデータセット**で、定義は `data/specs/<slug>.yml` に集約してある。

| slug | 内容 | Composition |
|---|---|---|
| `memory10` | 世界メモリ大手8社 | `Memory10` / `Memory10Dummy` |
| `security8` | 世界サイバーセキュリティ大手8社 | `Security8` / `Security8Dummy` |

## 前提

```bash
cd video && npm install
```

Remotion は旧ヘッドレスモードを使うため **chrome-headless-shell** が要る。
環境ごとにパスが違うので環境変数で渡す。

```bash
export REMOTION_BROWSER_EXECUTABLE=/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell
```

## 手順

```bash
# 1. CSVからデータJSONを作る（出典URLの無い数値は通らない）
python scripts/build_dataset.py security8

# 2. ロゴ画像を置いていれば一覧に反映する（置いていなければ頭文字バッジ）
python scripts/build_logo_manifest.py

# 3. 使う文字だけのフォントを同梱し、グリフ欠けが無いか確かめる
python scripts/subset_fonts.py
python scripts/check_video_glyphs.py

# 4. 書き出し
cd video
npm run typecheck
npm test
npm run render:security8      # → out/security8.mp4
npm run render:memory10       # → out/memory10.mp4
```

確認：

```bash
npx remotion ffprobe ../out/security8.mp4
```

## 動画を1本増やすとき

1. `data/specs/<slug>.yml` を書く（企業・指標・年・文言・配色）
2. `python scripts/make_dataset_skeleton.py <slug>` で収集用CSVを作る
3. CSVを埋める
4. `video/src/data/dataset.ts` の `DATASETS` / `DUMMY_DATASETS` と
   `src/Root.tsx` の `COMPOSITION_IDS` に1行ずつ足す
5. `package.json` に `render:<slug>` を足す

Remotion側のコンポーネントは spec 駆動なので、**画面の作りには触らなくてよい**。

## 数値を直したいとき

**`data/<slug>.csv` だけを編集する。** 手順1から流し直せば動画に反映される。

| 直したいもの | 直すファイル |
|---|---|
| 各社の売上高・営業利益 | `data/<slug>.csv` の `value_local` と `source_url` |
| 為替レート | `data/fx_rates.csv` の `rate_per_usd`（通貨×基準×年で1行） |
| 社名・色・決算期・頭文字・注記・画面の文言 | `data/specs/<slug>.yml` → `make_dataset_skeleton.py` |
| 尺・1期あたりの秒数 | `video/src/timing.ts` |
| 指標ごとのテーマ色 | `video/src/theme.ts` |
| 動きの粘り（年ごとの止まり具合） | `video/src/layout/geometry.ts` の `CRUISE` |
| 各社ロゴ | `video/public/logos/<slug>/<企業ID>.svg` を置いて手順2 |

`value_local` は**ローカル通貨の百万単位**で入れる（百万USD / 百万JPY / 百万KRW / 百万TWD）。
営業利益率は入力しない。`営業利益 ÷ 売上高` で導出する。

文言や社名を足したら `scripts/subset_fonts.py` を必ず再実行すること
（同梱フォントは使う文字だけに絞ってあるため、足した文字は入っていない）。

## 設計上の決め事

- **欠損は0で描かない。** 線を途切れさせ、先端ラベルはフェードアウトさせる
- **推測で埋めない。** 出典URLの無い数値はデータ生成の時点で弾く
- 先端ラベルは縦方向に押し出して重なりを解く。押し出したぶんはリード線で点と結ぶ。
  カードの上下の並び順は必ず値の順と一致する（`src/layout/collision.ts`）
- フォントはシステム任せにせず同梱する。グリフが1文字でも欠けたら
  `scripts/check_video_glyphs.py` が失敗する
- 上下200pxはSNSのUIに隠れる想定で、重要な情報を置かない
- **年ごとに止めない。** 1期ぶんを両端の速度を指定したエルミート補間でつなぎ、
  中間の期は巡航速度で通過する（`CRUISE`）。最初と最後だけ静止から入って静止で終わる。
  速度が年の境目で途切れないことはテストで固定してある
- **線は単調3次補間**（Fritsch–Carlson）。データ点の外側に膨らまないので、
  「年と年のあいだに実際より高い値があったように見える」ことがない。
  開示値そのものは中抜きの点で必ず示す
- 縦軸のレンジは直近0.6秒ぶんを重み付き平均してならす。
  目盛りが1本増える瞬間に軸が跳ねないようにするため。
  平均で現在値がはみ出さないよう、最後に必ず収まるところまで広げ直す
- **本番とダミーは Composition ごと分ける。** ダミーの数字が本番の書き出しに
  混ざらないようにするためなので、本番側が `DUMMY_DATASETS` を読むようにはしない

## ロゴについて

このリポジトリは各社のロゴ画像を同梱していない。ロゴは商標であり、
投稿物に載せる判断は人間がすべきものなので、既定では社名の頭文字バッジを描く。
実ロゴを使いたい場合は `video/public/logos/` の README を参照。
