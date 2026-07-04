# Morning Brief — 株式投資ネタ 毎朝5枚 自動生成

複数メディアのRSSを横断して「今いちばん話題の株式・マーケットニュース」を推定し、
**毎朝5枚のカード画像（深掘り解説型・ASSET LOGデザイン）＋対応する投稿文**を
GitHub Actionsで自動生成します。**Xへの投稿は手動**（画像と文面をコピーして投稿）。

## 毎朝できるもの（output/latest/）
| ファイル | 内容 |
|---|---|
| 1_news.png〜4_news.png | 話題ニュースTOP4の深掘り解説カード（1ニュース=1枚） |
| 5_summary.png | 今朝の話題まとめ |
| posts.md | 画像1〜5に対応する投稿文（コピペ用） |

各ニュースカードは「見出し → ❶何が起きた（数字を抽出） → ❷背景 → ❸市場への影響
→ ❹リスク・注意 → 用語メモ → 自分のスタンス」の7要素で深掘り解説します。
解説はトピック知識ベース（scripts/explainer.py）から見出しに応じて自動生成されます。

## しくみ
1. 平日・土日問わず毎朝5:45 JSTにActionsが起動（cronはUTC指定）
2. `scripts/fetch_news.py` が複数RSS（Yahoo!ニュース・NHK・Google Newsクエリ等）を取得
3. 「複数媒体が同時に報じている度合い×新しさ×相場ホットワード」で話題度をスコア化
4. `scripts/explainer.py` が見出しから解説を組み立て、`generate_images.py` が5枚を描画、`generate_posts.py` が投稿文を生成
5. `output/日付/` と `output/latest/` に保存してcommit（Artifactでも取得可）
6. **全フィード取得失敗時**（休場・障害等）は「投資の原則」深掘りカードへ自動フォールバックし、必ず5枚出る

## 導入手順（asset-tracker リポジトリ内で運用）
本ツールは `asset-tracker` リポジトリの `morning-brief/` サブディレクトリとして動作します。
ワークフローはリポジトリルートの `.github/workflows/morning-brief.yml` にあります。

1. Settings → Actions → General → Workflow permissions が **Read and write** であることを確認
2. Actionsタブ → morning-brief → **Run workflow** で手動テスト
3. 毎朝 `morning-brief/output/latest/` の5枚と `posts.md` を見て投稿（スマホのGitHubアプリでOK）

## ローカルテスト
```bash
cd morning-brief
pip install -r requirements.txt
python scripts/main.py --local fixtures/feed1.xml fixtures/feed2.xml fixtures/feed3.xml
# → output/latest/ に5枚＋posts.md
python scripts/main.py --local fixtures/nonexistent.xml   # フォールバック動作の確認
```

## 任意：投稿文をAIで自然化
リポジトリの Secrets に `ANTHROPIC_API_KEY` を設定すると、テンプレート文を
Claude APIが自然な文面に整えます（**未設定でもテンプレート文で必ず動きます**。
API利用は有料なので任意）。

## 正直な注意点（重要）
- **「最も閲覧数の多いニュース」を直接返す無料APIは存在しません。** 本ツールは
  「複数媒体の同時報道×新しさ×ホットワード」による**話題度の推定**です。
- RSSの仕様変更・停止はありえます。フィードは `fetch_news.py` の `FEEDS` で差し替え可能。
  一部が死んでも生きているフィードだけで動き、全滅時は原則カードに切り替わります。
- 見出しは各媒体の著作物のため、画像・投稿文では**短い要約表示**に留めています。
  投稿時はご自身でも内容の正確さをご確認ください（数値は報道ベースの概算）。
- X APIでの自動投稿は仕様・料金が変わりやすいため本ツールには含めていません
  （画像＋文面の生成まで。投稿はワンタップの手動運用）。
- ブランド方針（煽らない・断定しない・リスク併記・指数で継続に着地）を
  テンプレートと画像レイアウトに組み込み済みです。

## カスタマイズ
- 色・レイアウト：`scripts/generate_images.py` 冒頭のパレット
- スタンス文・原則ネタ：`generate_images.py` の `STANCES` / `EVERGREEN`
- ニュース解説の中身：`explainer.py` の `TOPICS`（トピック知識ベース。自由に追記可）
- 投稿文の口調：`generate_posts.py` の `OPENERS` / `CLOSERS`
- ニュース源：`fetch_news.py` の `FEEDS`
- 保存日数：`main.py` の `KEEP_DAYS`（既定14日）
