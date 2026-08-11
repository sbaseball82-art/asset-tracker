# source 実アクセス検証

実行: 2026-08-11 02:42 UTC
結果: **4/17 source が成功**

## ⚠ priority 1 が失敗しているファンド

下位のsourceで拾えていても、いずれ全滅するので直しておくもの。

- **HDV 米国高配当ETF** … `ishares_csv` (p1): ValueError: ヘッダ行（Ticker / Weight (%)）が見つかりません
- **QQQ ナスダック100ETF** … `invesco_csv` (p1): ValueError: ヘッダ行（Holding Ticker / Weight）が見つかりません
- **SBI S 米国高配当(年4回)** … `schwab_csv` (p1): 0件（取得できないかパースできませんでした）
- **iFreeNEXT FANG+** … `ice_index_page` (p1): 0件（取得できないかパースできませんでした）

## source 別の結果

| ファンド | source | 優先 | 種別 | 結果 | 件数 | 前週差 | 応答 |
|---|---|---:|---|---|---:|---:|---:|
| VTI 全米株式ETF | `vanguard_api` | 1 | json | OK | 499 | — | 1313ms |
| VTI 全米株式ETF | `manual` | 99 | local_csv | NG | — | — | 0ms |
| VYM 米国高配当ETF | `vanguard_api` | 1 | json | OK | 499 | — | 1179ms |
| VYM 米国高配当ETF | `manual` | 99 | local_csv | NG | — | — | 0ms |
| HDV 米国高配当ETF | `ishares_csv` | 1 | csv | NG | — | — | 731ms |
| HDV 米国高配当ETF | `manual` | 99 | local_csv | NG | — | — | 0ms |
| QQQ ナスダック100ETF | `invesco_csv` | 1 | csv | NG | — | — | 1027ms |
| QQQ ナスダック100ETF | `manual` | 99 | local_csv | NG | — | — | 0ms |
| SBI・V・S&P500 | `vanguard_api_voo` | 1 | json | OK | 498 | — | 1192ms |
| SBI・V・S&P500 | `manual` | 99 | local_csv | NG | — | — | 0ms |
| SBI S 米国高配当(年4回) | `schwab_csv` | 1 | csv | NG | — | — | 10785ms |
| SBI S 米国高配当(年4回) | `schwab_fund_page` | 2 | csv | NG | — | — | 10529ms |
| SBI S 米国高配当(年4回) | `manual` | 99 | local_csv | NG | — | — | 0ms |
| iFreeNEXT FANG+ | `ice_index_page` | 1 | json | NG | — | — | 9685ms |
| iFreeNEXT FANG+ | `fngs_etn` | 2 | csv | NG | — | — | 11717ms |
| iFreeNEXT FANG+ | `manual` | 3 | local_csv | NG | — | — | 0ms |
| iFreeNEXT FANG+ | `declared_equal_weight` | 90 | equal_weight | OK | 10 | — | 0ms |

## 失敗の詳細

### VTI 全米株式ETF / `manual` (p99)
- URL: `data/manual/VTI.csv`
- エラー: 0件（取得できないかパースできませんでした）

### VYM 米国高配当ETF / `manual` (p99)
- URL: `data/manual/VYM.csv`
- エラー: 0件（取得できないかパースできませんでした）

### HDV 米国高配当ETF / `ishares_csv` (p1)
- URL: `https://www.ishares.com/us/products/239563/ishares-core-high-dividend-etf/1467271812596.ajax?fileType=csv&fileName=HDV_holdings&dataType=fund`
- エラー: ValueError: ヘッダ行（Ticker / Weight (%)）が見つかりません

### HDV 米国高配当ETF / `manual` (p99)
- URL: `data/manual/HDV.csv`
- エラー: 0件（取得できないかパースできませんでした）

### QQQ ナスダック100ETF / `invesco_csv` (p1)
- URL: `https://www.invesco.com/us/financial-products/etfs/holdings/main/holdings/0?audienceType=Investor&action=download&ticker=QQQ`
- エラー: ValueError: ヘッダ行（Holding Ticker / Weight）が見つかりません

### QQQ ナスダック100ETF / `manual` (p99)
- URL: `data/manual/QQQ.csv`
- エラー: 0件（取得できないかパースできませんでした）

### SBI・V・S&P500 / `manual` (p99)
- URL: `data/manual/VOO.csv`
- エラー: 0件（取得できないかパースできませんでした）

### SBI S 米国高配当(年4回) / `schwab_csv` (p1)
- URL: `https://www.schwabassetmanagement.com/data/SCHD_holdings.csv`
- エラー: 0件（取得できないかパースできませんでした）

### SBI S 米国高配当(年4回) / `schwab_fund_page` (p2)
- URL: `https://www.schwabassetmanagement.com/sites/g/files/eyrktu361/files/SCHD_Holdings.csv`
- エラー: 0件（取得できないかパースできませんでした）

### SBI S 米国高配当(年4回) / `manual` (p99)
- URL: `data/manual/SCHD.csv`
- エラー: 0件（取得できないかパースできませんでした）

### iFreeNEXT FANG+ / `ice_index_page` (p1)
- URL: `https://www.ice.com/api/productguide/info/nyse-fang-plus/constituents`
- エラー: 0件（取得できないかパースできませんでした）

### iFreeNEXT FANG+ / `fngs_etn` (p2)
- URL: `https://www.microsectors.com/api/holdings/FNGS.csv`
- エラー: 0件（取得できないかパースできませんでした）

### iFreeNEXT FANG+ / `manual` (p3)
- URL: `data/manual/FANGPLUS.csv`
- エラー: 0件（取得できないかパースできませんでした）

## 判断のしかた

- ある ファンドの source が **すべて NG** … そのファンドは分解できない。
  `data/manual/` にCSVを置くか、`coverage_policy: excluded` にする。
- priority 1 だけ NG … 動いてはいるが、URLの仕様変更が疑われる。
  `data/fund_map.yml` の `url` / `columns` を直す。
- 全部 OK … `data/fund_map.yml` の `verified: false` を true にしてよい。
