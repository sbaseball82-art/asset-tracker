# Morning Brief — 世界のマーケットニュース 毎朝5枚 自動生成

国内・海外メディアのRSSを横断して「今いちばん話題の株式・マーケットニュース」を推定し、
**毎朝5枚のニュースカード画像（チャート付き・ASSET LOGデザイン）＋対応する投稿文**を
GitHub Actionsで自動生成します。**Xへの投稿は手動**（画像と文面をコピーして投稿）。

## 毎朝できるもの（output/latest/）
| ファイル | 内容 |
|---|---|
| 1_news.png〜5_news.png | 話題ニュースTOP5のカード（1ニュース=1枚・まとめカード無し） |
| posts.md | 画像1〜5に対応する投稿文（コピペ用） |

各カードの構成: 見出し → **関連マーケットチャート（直近6ヶ月・終値）** →
**統計タイル3枚（関連銘柄・S&P500・ドル円の前日比）** → ❶何が起きた → ❷どう見るか
→ 自分のスタンス。海外メディア発は英語見出しを自動翻訳し「海外発」バッジ付き。
チャートは見出しのトピックで自動選択（メモリ→MU、半導体→SOX指数、日経→N225、
為替→ドル円、金利→米10年債、AI/ハイテク→ナスダック 等。既定はS&P500）。

### 文字切れ・はみ出しの二重防止（構造的対策）
1. `fit_text()`: 全角/半角の実効ピクセル幅で折り返し、行数超過時は**文の区切りまで**
   戻して省略する。文の途中でぶつ切りのまま終わることはない。
2. `validate_card()`: 描画後に全テキストのピクセル範囲を実測し、キャンバス・パネルを
   超えていればフォントを段階縮小して自動再描画（保存前検査）。

## しくみ
1. 平日・土日問わず毎朝6:30 JSTを目標にActionsが起動（Claudeの定時トリガーが6:20 JSTにworkflow_dispatchで確実に起動。GitHub cron 21:30 UTCはバックアップ）
2. `scripts/fetch_news.py` が国内RSS（Yahoo!・NHK・Google News日本語）＋海外RSS（Google News英語・CNBC）を取得し、英語見出しは自動翻訳
3. 「複数媒体が同時に報じている度合い×新しさ×相場ホットワード」で話題度をスコア化し、海外・国内をミックスしてTOP5を選定
4. `scripts/market_charts.py` が関連指数・銘柄の6ヶ月データを取得（yfinance）、`generate_images.py` が5枚を描画、`generate_posts.py` が投稿文を生成
5. `output/日付/` と `output/latest/` に保存してcommit（Artifactでも取得可）
6. **フィード全滅時**は「投資の原則」カード、**マーケットデータ全滅時**は話題度バーへ自動フォールバックし、必ず5枚出る

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
