保有変更・スライド修正はフィーチャーブランチで検証して終わりにせず、**その日のうちにmainへマージ**しないと翌朝のスライドに一切反映されない（スケジュール実行はmainのみ）。

## 状況

2026-07-09〜10に holdings.json の買い増し反映・新銘柄追加（DRAM/イノベーションAI/SBI NASDAQ100）・
スライド修正を `claude/...` ブランチで実施し、workflow_dispatch（ブランチ指定）で
生成まで検証して「完了」と報告した。しかし翌朝 7/11 の定期実行が生成したスライドは
**旧保有のまま**（QQQ 15株・新銘柄なし）で、オーナーから「含まれていない。毎回ミスが多すぎる」
と指摘された。

原因: GitHub Actions の `schedule` トリガーは**デフォルトブランチ(main)の workflow と
ファイルだけ**を使う。ブランチ上でいくら検証・生成しても、mainにマージされるまで
毎朝の成果物には反映されない。

## 誤った対処（やりがちなこと）

- ブランチ上の workflow_dispatch 実行で生成物を確認して「反映済み」と報告して終える
  （翌朝の定期実行はmainなので反映されない）
- 「PRをマージしてください」とオーナーに依頼して完了扱いにする
  （マージされたか翌朝まで誰も確認せず、翌朝壊れた成果物が出る）

## 正しい対処

保有・設定・スライド生成コードを変更したタスクは、以下まで含めて完了条件とする:

1. 変更をブランチで検証（workflow_dispatch）
2. **mainへマージ**（PRマージまで確認する。マージ競合は生成物=ours、他workflowの出力=theirs）
3. マージ後に main で `fetch.yml` を workflow_dispatch 実行し、
   `git show origin/main:data.json` で全銘柄・数量が正しいことを確認
4. main の slide/*.png を開いて目視確認

「mainのholdings.json / config.py が最新か」を疑うこと:
```bash
git fetch origin main && git show origin/main:holdings.json
```

## 出典

2026-07-11 のセッション。7/11朝の定期実行（main, 旧保有）と PR #10（未マージだった）で確認。
