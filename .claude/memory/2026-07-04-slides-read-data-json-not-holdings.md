holdings.json を更新してもスライドは即座に変わらない→スライドは data.json を読むため、反映は次回の fetch_prices.py 実行（=翌朝のActions）後。

## 状況

holdings.json で SBI S 米国高配当の口数を 1,955,365 → 1,969,774 に更新した直後に
make_slide.py でスライドを再生成したところ、画像には旧口数 1,955,365 が表示された。

## 誤った対処（やりがちなこと）

- 「更新が反映されていない、編集に失敗した」と誤診して holdings.json を再編集する
- make_slide.py が holdings.json を読むように改造する（動作コードの改変。禁止）

## 正しい対処

データの流れを理解する:

```
holdings.json（保有数量）→ fetch_prices.py が読む → data.json に書く → make_slide.py が読む
```

- holdings.json の編集は、次回 fetch_prices.py が走ったとき（=翌朝のActions）に初めて
  data.json へ反映される
- 買い増し反映の確認は「翌朝のスライドの口数・金額」で行うのが正
- 即時確認したい場合のみ fetch_prices.py を手動実行する（ネット接続可能な環境が必要）

## 出典

2026-07-04 のClaude Codeセッション。買い増し反映（commit 5b3b921）後の
スライド再生成で旧口数が表示されることを実機確認。
