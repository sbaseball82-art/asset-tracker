# memory10 — 世界メモリ大手8社の業績推移動画

縦型 1080×1920 / 60fps / 音声なしの mp4 を Remotion で書き出す。

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
python scripts/build_memory10_dataset.py

# 2. 使う文字だけのフォントを同梱し、グリフ欠けが無いか確かめる
python scripts/subset_fonts.py
python scripts/check_video_glyphs.py

# 3. 書き出し
cd video
npm run typecheck
npm test
npm run render          # → out/memory10.mp4
```

確認：

```bash
npx remotion ffprobe ../out/memory10.mp4
```

## コンポジション

| id | 中身 |
|---|---|
| `Memory10` | 本番。`src/data/memory10.generated.json` を読む |
| `Memory10Dummy` | 動作確認用。`src/data/memory10.dummy.json` を読む |

ダミーの数字が本番の書き出しに混ざらないよう、読むファイルごと分けてある。
`Memory10` が `dummyDataset` を読むようにはしないこと。
ダミーの生成は `python scripts/build_memory10_dataset.py --dummy`。

## 数値を直したいとき

**`data/memory10.csv` だけを編集する。** 手順1から流し直せば動画に反映される。

| 直したいもの | 直すファイル |
|---|---|
| 各社の売上高・営業利益 | `data/memory10.csv` の `value_local` と `source_url` |
| 為替レート | `data/fx_rates.csv` の `rate_per_usd` |
| 社名・色・決算期・注記 | `data/memory10.json`（`scripts/make_memory10_skeleton.py` が生成） |
| 尺・1期あたりの秒数 | `video/src/timing.ts` |
| 配色・テーマ | `video/src/theme.ts` |
| 文言（ヘッダー・注記・締め） | `video/src/components/` 各ファイル |

`value_local` は**ローカル通貨の百万単位**で入れる（百万KRW / 百万JPY / 百万TWD / 百万USD）。
営業利益率は入力しない。`営業利益 ÷ 売上高` で導出する。

文言を足したら `scripts/subset_fonts.py` を必ず再実行すること
（同梱フォントは使う文字だけに絞ってあるため、足した文字は入っていない）。

## 設計上の決め事

- **欠損は0で描かない。** 線を途切れさせ、先端ラベルはフェードアウトさせる
- **推測で埋めない。** 出典URLの無い数値はデータ生成の時点で弾く
- 先端ラベルは縦方向に押し出して重なりを解く。押し出したぶんはリード線で点と結ぶ。
  カードの上下の並び順は必ず値の順と一致する（`src/layout/collision.ts`）
- フォントはシステム任せにせず同梱する。グリフが1文字でも欠けたら
  `scripts/check_video_glyphs.py` が失敗する
- 上下200pxはSNSのUIに隠れる想定で、重要な情報を置かない
