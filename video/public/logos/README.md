# ロゴ画像を置く場所

このリポジトリは各社のロゴ画像を同梱していない。ロゴは商標であり、
投稿物に載せる判断は人間がするため。

置かれていなければ、動画は社名の頭文字バッジ（spec の `monogram`）を
各社カラーで描く。権利面ではこちらのほうが安全。

## 置き方

データセットごとのフォルダに、ファイル名を企業IDに合わせて置き、
マニフェストを作り直す。

```
video/public/logos/memory10/samsung.svg
video/public/logos/memory10/micron.svg
video/public/logos/security8/paloalto.svg
video/public/logos/security8/crowdstrike.png
```

```bash
python scripts/build_logo_manifest.py
```

- 対応拡張子：`.svg` `.png` `.webp` `.jpg`
- 正方形に近い形で、余白の少ないものがきれいに収まる（40×40pxの枠に入る）
- 背景が白いカードの上に載るので、白抜きのロゴは避ける
- 一部の会社だけ置いてもよい。無い会社は頭文字バッジのままになる
- 企業IDは `data/specs/<slug>.yml` の `companies[].id`
