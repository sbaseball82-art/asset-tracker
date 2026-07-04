stock-daily をローカル検証すると PIL の「OSError: cannot open resource」でフォント読込に失敗する→本番(Actions)はNoto CJKをaptで入れる。ローカルはIPAフォントへのシンボリックリンクで代替。

## 状況

`MOCK=1 python3 stock-daily/daily_report.py` をClaude Codeリモート環境で実行したところ:

```
OSError: cannot open resource
```

daily_report.py は `/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc` を
ハードコードで参照するが、このコンテナに Noto CJK はなく IPAゴシックのみ
（`fc-list | grep -i gothic` で確認できる）。

本番の GitHub Actions では workflow が `apt-get install fonts-noto-cjk` を実行するので
この問題は起きない。**ローカル検証限定の環境差分**。

## 誤った対処（やりがちなこと）

- daily_report.py の FONT_PATH を書き換える（本番はNotoで動いている。コード改変で本番を壊す）
- 「壊れている」と報告して検証を放棄する

## 正しい対処

ローカル検証時のみ、期待されるパスに手持ちフォントをリンクする:

```bash
mkdir -p /usr/share/fonts/opentype/noto
ln -sf /usr/share/fonts/opentype/ipafont-gothic/ipag.ttf /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc
ln -sf /usr/share/fonts/opentype/ipafont-gothic/ipag.ttf /usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc
```

その後 `MOCK=1 python3 stock-daily/daily_report.py` が成功する
（ネット不要。output/latest.png と post_text.txt が生成される）。
見た目のフォントは本番と異なるが、レイアウト検証には十分。

## 出典

2026-07-04 のClaude Codeセッション。stock-daily 導入時のMOCK検証で確認。
