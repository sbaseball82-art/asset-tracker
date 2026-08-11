# data/manual/

構成銘柄の公開データを自動取得できないファンドは、ここにCSVを置くと
ルックスルー分解の対象になります。**置かなければ「要手動確認」として
未分解のまま出力されます**（取れない値を推測では埋めません）。

---

## いま置く必要があるファイル（2026-08-10 時点）

実アクセス検証（`reports/live_verification.md`）の結果、
次の3本は自動取得できていません。**この3本で保有の約20%を占めるため、
CSVを置くまでカバレッジが90%に届かず、生成は中止されます。**

| ファイル | 対象 | 保有比率 | 自動取得できない理由 |
|---|---|---:|---|
| `QQQ.csv` | QQQ ナスダック100ETF（＋NASDAQ100投信2本の代用元） | 約6.2% | Invesco のURLがCSVでなくHTMLを返す |
| `SCHD.csv` | SBI S 米国高配当(年4回) の代用 | 約7.5% | Schwab のURLが存在しない |
| `HDV.csv` | HDV 米国高配当ETF | 約6.8% | iShares のURLがCSVでなくHTMLを返す |

自動取得できているもの（CSV不要）:
VTI / VYM / SBI・V・S&P500（Vanguard API）、iFreeNEXT FANG+（等ウェイトの宣言）

### 入手先

各運用会社の商品ページから「Holdings（保有銘柄）」のCSVをダウンロードします。

- **QQQ** … Invesco の QQQ 商品ページ → Holdings → Download
- **SCHD** … Schwab Asset Management の SCHD 商品ページ → Holdings
- **HDV** … iShares の HDV 商品ページ → Holdings → Detailed Holdings and Analytics

落としたCSVをそのまま `data/manual/` に置き、
列名が下の例と違う場合は `data/fund_map.yml` の該当 source の
`columns:` を実際の列名に合わせてください（コード変更は不要です）。

### 正しいURLが分かったら

自動取得に戻せます。`data/fund_map.yml` の該当 source の `url` を差し替え、
`scripts/verify_live.py`（または Actions の verify-live）で確認してください。
通ったら `verified: true` にします。手動CSVは priority 99 のまま
残しておけば、自動取得が壊れたときの受け皿になります。

---

## ファイル名

`data/fund_map.yml` の `path:` に書いた名前と合わせてください。

| ファイル | 対象 |
|---|---|
| `VTI.csv` / `VYM.csv` / `VOO.csv` | 自動取得の予備 |
| `QQQ.csv` | QQQ（NASDAQ100投信2本もこれを流用） |
| `SCHD.csv` | SBI S 米国高配当(年4回) の代用 |
| `HDV.csv` | HDV 米国高配当ETF |
| `FANGPLUS.csv` | iFreeNEXT FANG+ の代用（10銘柄・等ウェイト） |
| `innovation_ai.csv` | イノベーションAI（既定では分解対象外） |
| `DRAM.csv` | DRAM メモリ半導体ETF（既定では分解対象外） |

## 形式

ヘッダ行に `ticker` / `weight` / `name`（任意）を含むCSV。
先頭に説明行が入っていても、ヘッダ行から読み始めます。

```csv
ticker,weight,name
ABBV,4.30,AbbVie
HD,4.20,Home Depot
CVX,4.10,Chevron
```

- `weight` は構成比(%)。`4.30` でも `4.30%` でも読めます
- 合計が100%に満たなくても構いません。足りない分は按分せず
  「未カバー」として別枠で扱われます（notes.md に出ます）
- 合計が100%を明らかに超えるとデータ異常として生成が止まります
- 現金行（`CASH` / `USD` / `-` など）は自動で除かれます

運用会社のCSVをそのまま置きたい場合は、列名を `data/fund_map.yml` の
`columns:` に書けばそのまま読めます。

## 更新の目安

構成比は月次で変わります。**週次実行（毎週日曜 21:00 JST）の前**に
置き換えておくと、その週のルックスルーに反映されます。

置いたCSVのファイル更新日時が「構成比基準日」として画像に出ます。
35日を超えると画像の基準日が金色で強調され、91日を超えると
取得失敗と同じ扱いになってカバレッジから外れます。
