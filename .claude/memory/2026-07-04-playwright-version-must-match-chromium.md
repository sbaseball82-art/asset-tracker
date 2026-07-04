Claude Codeリモート環境で「Please run playwright install」が出たら、playwright installは実行禁止→プリインストール済みブラウザのリビジョンに合うplaywrightバージョンをpipで入れ直す。

## 状況

`python3 make_slide.py` 実行時に以下が出て失敗:

```
║ Looks like Playwright was just installed or updated.       ║
║ Please run the following command to download new browsers: ║
║     playwright install                                     ║
```

原因: pipが入れた playwright（例: 1.61.0 → chromium-1228 を要求）と、
環境にプリインストールされたブラウザ（/opt/pw-browsers/ に chromium-1194）の
リビジョン不一致。

## 誤った対処（やりがちなこと）

- 表示どおり `playwright install` を実行する（この環境では禁止。
  PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 が設定されており、環境の方針に反する）
- make_slide.py に executablePath を追加する（動作コードの改変。禁止）

## 正しい対処

1. プリインストールのリビジョンを確認: `ls /opt/pw-browsers/` → 例: chromium-1194
2. そのリビジョンに対応する playwright バージョンを入れる:

```bash
pip install playwright==1.56.0   # chromium-1194 に対応（2026-07-04時点で確認済み）
```

対応確認方法（バージョンを変えて試すとき）:

```bash
python3 -c "
import json, pathlib, playwright
p = pathlib.Path(playwright.__file__).parent / 'driver' / 'package' / 'browsers.json'
print([b['revision'] for b in json.loads(p.read_text())['browsers'] if b['name']=='chromium'][0])"
```

これが /opt/pw-browsers/ のリビジョン番号と一致すればよい。
requirements.txt は `playwright>=1.44.0` なので 1.56.0 でも満たす（編集不要）。

## 出典

2026-07-04 のClaude Codeセッション。playwright 1.61→1.56 に差し替えて
make_slide.py / make_allocation_slide.py の成功を確認。
