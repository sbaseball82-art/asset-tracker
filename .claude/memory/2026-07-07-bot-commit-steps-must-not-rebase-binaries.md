ワークフローがmainへ生成物(画像)をコミットする工程で `git pull --rebase` を使うと、バイナリ衝突で復旧不能に失敗する→「fetch + checkout -B origin/main + 生成物を重ねて commit + pushリトライ」方式にする。

## 状況

daily-stock-report の「生成物をリポジトリにコミット」工程が失敗:

```
CONFLICT (content): Merge conflict in stock-daily/output/latest.png
error: could not apply 237deaf... daily report 2026-07-07
```

原因の組み合わせ:
1. Actionsの**Re-runは失敗当時の古いコミットをcheckoutする**（最新mainではない）
2. その間にmainには別の daily report コミットが積まれていた
3. `git pull --rebase` は**バイナリ(PNG)をマージできない**ため、同じファイルを触る
   コミットと衝突すると必ず失敗する。リトライしても同じ衝突で失敗し続ける

このリポジトリはボット(fetch / daily-report / morning-brief)が毎日mainへpushするため、
この衝突は構造的に再発する。

## 誤った対処（やりがちなこと）

- 失敗したrunを何度もRe-runする（古いSHAのままなので毎回同じ衝突で失敗）
- リトライ回数を増やす（rebase衝突はリトライでは解決しない。push拒否とrebase衝突は別物）
- `--force` でpushする（他ワークフローのコミットを消し飛ばす。禁止）

## 正しい対処

コミット工程を「rebase/merge を使わない」形にする（2026-07-07 に daily_report.yml へ適用済み）:

```bash
cp -r <出力dir> "$RUNNER_TEMP/output-new"     # 生成物を退避
for i in 1 2 3 4 5; do
  git fetch origin main
  git reset --hard && git clean -fd <出力dir>
  git checkout -B main origin/main            # 常に最新mainの上で作業（古いSHA問題も解消）
  cp -r "$RUNNER_TEMP/output-new/." <出力dir>/ # 生成物を重ねる（上書きのみ）
  git add -A <出力dir> && git diff --cached --quiet && exit 0
  git commit -m "..." && git push origin main && exit 0
  sleep 5                                     # push拒否＝割り込みされた時だけリトライ
done; exit 1
```

**同じ潜在バグが morning-brief.yml にも残っている**（naiveな `git pull --rebase; git push`）。
fetch.yml はリトライ付きだが、Re-run時のバイナリ衝突には同様に弱い。
症状が出たらこのパターンを適用する。

## 出典

2026-07-07 のセッション。run 28793324922 / 28736308619 の失敗ログで確認。
ローカルのgitレース再現ハーネスで4シナリオ（本番失敗の再現・変更なし・push拒否リトライ・
30日保持削除）の成功を検証済み。
