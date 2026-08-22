# CLAUDE.md — このリポジトリの設計方針

Xアカウント「外資系営業マンの金融資産推移」の投稿素材を自動生成するリポジトリ。
**生成までを自動化し、投稿は必ず人間が確認してから手で行う。**

---

## 絶対に守ること

この5つは他のどんな都合よりも優先する。実装で迷ったらここに戻る。

### 1. データが取れない箇所を推測値で埋めない

取れなかった値は、0でも平均値でも「それらしい数字」でもなく、
**空欄＋「要手動確認」** として出力に残す。

- ファンドの構成銘柄が取れない → 按分せず `unresolved` に積む
- 構成比が100%に満たない（上位N銘柄しか無い） → 取れた分だけ按分し、
  残りは `uncovered_jpy` として別枠にする
- 取得に失敗したらキャッシュを使い、`stale: true` を立てて画像に明記する

投稿する数字は自分の資産の話なので、それらしく埋めた瞬間に価値が消える。
「分からない」と書ける仕組みのほうが、埋まっている数字より大事。

**カバレッジが足りないまま投稿文を作らない。**
`config.yml` の `coverage.halt_below`（既定90%）を下回ったら生成を中止する。
「カバレッジ72%のまま『上位10社で◯%』と書く」のが最も避けたい失敗。

### 1-2. 「取れなかった」と「取らないと決めた」を区別する

`data/fund_map.yml` の `coverage_policy` で3つに分ける。

| 値 | 意味 | 取れなかったとき |
|---|---|---|
| `required` | 必ず分解する | **生成を中止** |
| `best_effort` | 取れたら分解する | 続行。notes.md に記録 |
| `excluded` | 意図的に分解しない | 未カバー枠。**警告に出さない** |

`excluded` は「取りに行って失敗した」のではなく「取りに行かないと決めた」もの。
保有0.4%のファンドのために壊れやすいスクレイパーを持つほうが高くつく、
という判断を明示的に書き残すための区分。毎回警告に出すとノイズになるので、
画像には「分解対象外：◯◯（合計0.4%）」と小さく注記するだけにする。

### 2. 自動投稿しない

生成物（画像・本文）は必ず人間が読んでから投稿する。
X APIへの投稿処理をこのリポジトリに入れない。

### 3. 予測・断定をしない

一人称の推測形で書く。「〜だと思います」「〜に見えます」「〜のようです」。

禁止する表現は `src/lookthrough/compose.py` の `FORBIDDEN` に列挙してあり、
生成時に自動チェックされる。代表例：

> 必ず / 確実に / 間違いなく / 買い時 / 売り時 / おすすめ /
> 底打ち / 反発局面 / 〜するでしょう

事実の並置までは書いてよいが、「だから今後こうなる」に踏み込まない。

### 4. 免責文を必ず入れる

すべての投稿文の末尾に置く。

```
※記録・情報共有目的であり投資助言ではありません
```

加えて、数値には「公表ベースの概算」である旨を添える（`※公表データからの概算`）。
どちらも `validate_post()` でチェックしている。

### 5. 単位を混同しない

- **%** … 比率そのもの（実質保有比率、騰落率）
- **%pt** … 差分・寄与（指数寄与は必ず %pt）

### 6. 数字が入る経路は1本だけにする（Daily Growth）

投稿に出る数値は、**必ず**次の経路だけを通す。

```
data.json → facts.py（純粋関数） → builder → Val(raw, text) → {placeholder}
```

- テンプレ（YAML）に数値を直書きしない。書いても QA の照合で落ちる。
- 文章生成で金融数値を作らない。画像生成AIで数字を描かない。
- 事実が取れない話題は `builder: null` と `blocked_reason` を書いて宣言する。
  候補には出さず、`summary.md` に理由つきで残す（黙って消さない）。

### 7. 条件をゆるめたら必ず書き残す

ネタが尽きてローテーション条件をゆるめた、カバレッジが足りない、
データが古い——こうした「本来の条件を満たしていない状態」で生成したときは、
`summary.md` と `qa.json`（または `notes.md`）に必ず記録する。
**黙って本数を減らす／黙って同じ話題を出す／黙って条件を下げる、はしない。**

---

## 投稿文のトーン

- 煽らない。数字を大きく見せる語（爆益・暴落・ヤバい）を使わない
- 個別銘柄を推奨しない
- メモリ・DRAM に触れるときは必ず「**シクリカル**」を添える
  （`CYCLICAL_TRIGGERS` に該当したら自動で補われ、無ければ検査で落ちる）
- **1行目と2行目だけで意味が通ること**。Xのプレビューで切られる前提
- **画像が無くてもテキスト単体で成立すること**（画像なし投稿のほうが伸びた実績がある）
- ハッシュタグは末尾のみ、2〜3個
- 着地は「分散しているつもりが、実は◯◯」のように、
  守りの構造が崩れている／効いている点に置く

文字数は**全角換算**（全角=1 / 半角=0.5 / URL=11.5）。
`src/common/textcheck.py` の `zenkaku_len()` を使う。

---

## ディレクトリ

```
config.yml              運用設定（アカウント・闾値・通知・パス）★ここが唯一の設定
config.py               銘柄マスタ（名前・ISIN）。X_ACCOUNT は config.yml を読む
holdings.json           保有数量（買い増したらここだけ編集）
data.json               毎朝の価格取得結果と履歴

data/
  holdings.yml          総資産とファンド別評価額（data.json から生成）
  fund_map.yml          ファンド → 構成銘柄の取得元（多段）。代用と方針の宣言もここ
  cache/constituents/   構成銘柄のキャッシュ（取得失敗時に stale として使う）
  manual/               取得元が無いファンドのCSVを手で置く場所
  history/              月次スナップショット（前月比の算出に使う）
  lookthrough.json      機能②が読むルックスルー結果

data/
  daily_growth_topics.yml    ← 機能③：ネタプール（文言と重みだけ。数値は書かない）
  daily_growth_designs.yml   画像デザインのプール（10種）
  daily_growth_history.jsonl 生成履歴（重複防止の判定に使う。1行1投稿）

src/
  common/               textcheck / render / fontcheck / util / notify / postlog / settings
  daily_growth/         ← 機能③：毎朝の投稿候補5本
    facts.py            data.json から事実だけを取り出す（純粋関数のみ）
    topics.py           ネタプールと builder（数値は必ず Val で作る）
    compose.py          投稿文の組み立てと検査（純粋関数のみ）
    score.py            スコアと選抜、ローテーションのゆるめ方（純粋関数のみ）
    history.py          daily_growth_history.jsonl と重複判定
    render.py           画像（theme × layout）
    qa.py               生成物の自動QA
    generate.py         入出力とオーケストレーション
  lookthrough/          ← 機能①：保有を個別銘柄まで分解する
    compute.py          按分計算（純粋関数のみ）
    validation.py       構成銘柄の検証（純粋関数のみ）
    constituents.py     多段フォールバック取得とキャッシュ
    health.py           source の生存確認
  earnings/  evergreen/  report/

scripts/
  verify_live.py        全sourceに実アクセスして確認（本番投入前に1回）
  source_health.py      週1のヘルスチェック（予兆検知）

output/lookthrough/YYYY-MM/   画像・投稿文・data.json・notes.md
reports/                      source_health_YYYY-WW.md / live_verification.md
logs/posts.csv                生成物の記録（views等は週1で手入力）
```

---

## 機能①：ルックスルー分解

保有ファンドを「中身の個別銘柄」まで分解し、実質的にどの企業を何円分
持っているかを出す。**このアカウントの一番の差別化点。**

```bash
python -m src.lookthrough.generate            # 通常（公開データを取得）
python -m src.lookthrough.generate --offline  # キャッシュのみ
python -m src.lookthrough.generate --sample   # サンプルで動作確認
python -m src.lookthrough.generate --dry-run  # 取得状況とカバレッジだけ見る

python scripts/verify_live.py                 # 全sourceに実アクセスして確認
python scripts/source_health.py               # 週次ヘルスチェック
```

計算の中心は `src/lookthrough/compute.py`。
**このモジュールは純粋関数だけにする**（I/O・ネットワークを入れない）。
投稿に出す数字そのものなので、手計算で検算できるテストで固める。

```
実質保有額 = Σ（ファンド評価額 × ファンド内での構成比）
```

一番大事なのは「**経由の内訳**」（`Position.via`）。
同じ銘柄を高配当ETFとグロース系の両方から持っている状態を金額で見せる。

必ず成り立つ恒等式（`_reconcile` が検算し、1%超ずれたら止まる）：

```
Σ実質保有額 + uncovered_jpy + unresolved合計 = 総資産
```

### 取得は多段フォールバック

`data/fund_map.yml` の `sources` を priority の小さい順に試し、
最初に成功したものを採用する。**どの source で取れたかは必ず記録する**
（`data.json` の `sources` と `notes.md` の取得状況表）。

各段で「成功」と認めるには次を全部満たす必要がある。

1. パースできて1件以上ある
2. `min_constituents` 以上ある … 「10銘柄しか返らないVTI」を掴まないため
3. `validation` のルールを通る … FANG+ の等ウェイト検証など

全滅したらキャッシュを使い `stale: true` と経過日数を記録する。

新しい取得元を足すときは **YAMLだけ**を編集する。パーサは
`kind: json / csv / local_csv / equal_weight` の4つで足りるようにしてあり、
列名は `columns:` で指定する。コードを触るのは新しい `kind` が要るときだけ。

### データの鮮度

| 経過 | 扱い |
|---|---|
| 0〜35日 | 正常（ETFの構成比は月次更新のため） |
| 36〜90日 | 警告。画像の基準日を金色で強調 |
| 91日〜 | **取得失敗と同じ扱い**。カバレッジから除外する |

画像には常に「構成比基準日」を出す。

### 代用（proxy）の扱い

投信は構成銘柄を公表しないため、連動対象ETFの構成で代用する
（SBI・V・S&P500 → VOO、SBI S 米国高配当 → SCHD、NASDAQ100投信 → QQQ）。

代用は `data/fund_map.yml` に `proxy_for` として**宣言的に**書く。
コードに埋め込まない。代用したことは `data.json` と `notes.md` の両方に必ず残る。

同じデータを使う複数の投信は `reuse_from: QQQ` と書けば、
同じURLを何度も叩かずに結果を使い回す。

### FANG+ の検証（例外的に厳しくしている理由）

NYSE FANG+ は10銘柄の等ウェイト指数なので、取得結果が正しいかを
機械的に確かめられる。`validation` に3つ書いてある。

- `exact_count: 10` … ちょうど10銘柄
- `weight_range: [8.0, 12.0]` … 概ね等ウェイト
- `max_member_diff: 2` … 前回から2銘柄以内の入替

**入替 1〜2銘柄は正常**（四半期リバランス）。中止せず「入替を検出」として
notes.md に残し、通知を出す。3銘柄以上入れ替わっていたら取得ミスを疑って
そのsourceを不採用にし、次のpriorityへ進む。

### サンプル実行の隔離

`--sample` は `tests/fixtures/constituents_sample.yml` を読む。
本番の実行がこのファイルを読むことはない。サンプル実行は
`output/lookthrough/sample/` にだけ書き、`data/lookthrough.json` も
`data/history/` も更新しない。**サンプルの数字が本番に混ざらないようにする。**

---

## 画像（ASSET LOG デザイン）

1180×1450 / 背景 `#0B1220`。HTML を Chromium でスクリーンショットして作る。

| 用途 | 色 |
|---|---|
| 背景 | `#0B1220` |
| 表カード | `#111A2E` |
| サマリーカード | `#16203A` |
| 罫線 | `#1E2A42` |
| 本文グレー | `#8B96AB` |
| アクセント青 | `#4A9EFF` |
| 金（ブランド・重複マーカー） | `#E0B45C` |
| プラス | `#6EE7A8` / マイナス | `#F08A8A` |

日本語は Noto Sans JP（無ければ Noto Sans CJK JP）。
GitHub Actions では `fonts-noto-cjk` をワークフロー内で入れる。

### 生成後の自動チェック

- **豆腐（□）**: `src/common/fontcheck.py` がフォントに全文字のグリフが
  あるか調べる。1文字でも欠けたら生成を失敗させる（`--allow-tofu` で回避可）。
  `fc-match` は日本語の無いフォントを黙って返すため、返り値を検証してから使う。
- **はみ出し**: `render_png(report=...)` が中身の高さを測る。
  行数や文言が増えてキャンバスからはみ出したら警告する。

---

## テスト

```bash
python -m pytest tests/ -q
```

計算ロジック（ルックスルー・寄与率・スコア）は**必ず検算テストを書く**。
手で答えを出せる小さな例を用意して、それと一致させる。

「推測で埋めない」も仕様なのでテストする。
構成データが無いファンドが `unresolved` に落ちること、
構成比が100%未満なら残りが按分されないこと、を確認している。

---

## 機能③：Daily Growth System（毎朝の投稿候補5本）

毎朝 `data.json` を読んで、**その日のデータでしか書けない話題**を選び、
投稿候補を5本つくる。生成のみ。投稿ボタンは人間が押す。

```bash
python -m src.daily_growth.generate            # 通常
python -m src.daily_growth.generate --dry-run  # 履歴・ログを書かない
python -m src.daily_growth.generate --sample   # 隔離ディレクトリにだけ書く
python -m src.daily_growth.generate --no-render
```

出力は `output/daily-growth/YYYY-MM-DD/`（`post_1..5.png` / `post_1..5.txt` /
`summary.md` / `qa.json`）。GitHub Actions は **毎朝 08:00 JST 前後**
（`.github/workflows/daily_growth.yml`）。

### 守ること（機能③固有）

- **1投稿1画像**。5投稿を1枚にまとめない。
- 画像に通し番号（`01` / `1/5` / `①`）を入れない。
- 全角換算165字以内（`zenkaku_len()` を使う）。1〜2行目だけで意味が通ること。
- 末尾は資産投稿なら `※記録・情報共有目的であり投資助言ではありません`、
  報道ベースなら `※報道ベースの概算。投資助言ではありません`。
- メモリ・DRAM に触れたら「シクリカル」。禁止語は `compose.FORBIDDEN`
  （lookthrough と共通のものに煽り表現を足したもの）。
- `compute.py` と同じく、`facts.py` / `compose.py` / `score.py` に
  I/O・ネットワークを入れない。

### 毎日同じにならないための規則（既定値は config.yml）

| 規則 | 既定 |
|---|---|
| 同一 `topic_id` の再利用 | 14日禁止 |
| 同一・類似 `hook` | 30日回避 |
| 同一 `design_id` | 3日連続まで |
| 前日の5本と似た候補 | 除外 |
| 同じ日の同じデザイン／同じ計算 | 禁止 |

違反は**減点ではなく除外**。ネタが尽きたときのゆるめ方はあらかじめ決めてあり
（`score.relaxation_ladder`）、**ゆるめた事実を必ず記録する**。

### QA を通らなかったものは投稿素材ではない

`qa.json` の `ok` が `false` の日は、生成物をコミットしないし投稿もしない。
「作れたけれど出さない」を選べることが、この機能の価値。

---

## 「完全自動」の範囲

自動化するのは **データ取得から投稿文・画像の生成まで**。
投稿ボタンを押すのは人間。ここは動かさない。

| 自動 | 手動 |
|---|---|
| 構成銘柄の取得（多段フォールバック） | 生成物の目視確認 |
| 分解・集計・前月比 | X への投稿 |
| 画像・投稿文の生成と検査 | `data/manual/` のCSV更新（必要時） |
| 毎朝の投稿候補5本の生成とQA | 5本のうちどれを出すかの判断 |
| source のヘルスチェック（週1） | 壊れた source のURL修正 |
| 中止・劣化の通知 | `excluded` にするかの判断 |
| — | `logs/posts.csv` の実績入力（週1） |

---

## やらないこと

- X への自動投稿（`tests/test_settings.py` が投稿系コードの不在を検査している）
- 取得できなかった数値の穴埋め（推定・補完・前月値の流用）
- カバレッジ不足のまま投稿文を作ること
- 投資判断・推奨の文言を出力に含めること
- `compute.py` / `validation.py` / `daily_growth/facts.py` / `daily_growth/compose.py`
  / `daily_growth/score.py` にネットワークやファイル読み書きを入れること
- 投稿テンプレ（YAML）に金融数値を直書きすること
- 画像生成AIに数字を描かせること
- 5投稿を1枚の画像にまとめること／画像に通し番号を入れること
- 保有比率の小さいファンドのために壊れやすいスクレイパーを書くこと
  （`excluded` にして、必要なら手動CSVで足す）
