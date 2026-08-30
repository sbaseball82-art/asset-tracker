# source ヘルスチェック 2026-35

実行: 2026-08-30 16:23 UTC
結果: **1/18 source が成功**

## ⚠ priority 1 が失敗しているファンド

下位のsourceで拾えていても、いずれ全滅するので直しておくもの。

- **VTI 全米株式ETF** … `vanguard_api` (p1): JSONDecodeError: Expecting value: line 1 column 1 (char 0)
  - **要対応**: 3週連続で失敗しています
- **VYM 米国高配当ETF** … `vanguard_api` (p1): JSONDecodeError: Expecting value: line 1 column 1 (char 0)
- **HDV 米国高配当ETF** … `ishares_csv` (p1): ValueError: ヘッダ行（Ticker / Weight (%)）が見つかりません
  - **要対応**: 3週連続で失敗しています
- **QQQ ナスダック100ETF** … `invesco_csv` (p1): ValueError: ヘッダ行（Holding Ticker / Weight）が見つかりません
  - **要対応**: 3週連続で失敗しています
- **SBI・V・S&P500** … `vanguard_api_voo` (p1): JSONDecodeError: Expecting value: line 1 column 1 (char 0)
- **SBI S 米国高配当(年4回)** … `schwab_csv` (p1): 0件（取得できないかパースできませんでした）
  - **要対応**: 3週連続で失敗しています
- **iFreeNEXT FANG+** … `ice_index_page` (p1): 0件（取得できないかパースできませんでした）
  - **要対応**: 3週連続で失敗しています

## source 別の結果

| ファンド | source | 優先 | 種別 | 結果 | 件数 | 前週差 | 応答 |
|---|---|---:|---|---|---:|---:|---:|
| VTI 全米株式ETF | `vanguard_api` | 1 | json | NG | — | — | 418ms |
| VTI 全米株式ETF | `vanguard_api_alt` | 2 | json | NG | — | — | 253ms |
| VTI 全米株式ETF | `manual` | 99 | local_csv | NG | — | — | 0ms |
| VYM 米国高配当ETF | `vanguard_api` | 1 | json | NG | — | — | 334ms |
| VYM 米国高配当ETF | `manual` | 99 | local_csv | NG | — | — | 0ms |
| HDV 米国高配当ETF | `ishares_csv` | 1 | csv | NG | — | — | 555ms |
| HDV 米国高配当ETF | `manual` | 99 | local_csv | NG | — | — | 0ms |
| QQQ ナスダック100ETF | `invesco_csv` | 1 | csv | NG | — | — | 274ms |
| QQQ ナスダック100ETF | `manual` | 99 | local_csv | NG | — | — | 0ms |
| SBI・V・S&P500 | `vanguard_api_voo` | 1 | json | NG | — | — | 686ms |
| SBI・V・S&P500 | `manual` | 99 | local_csv | NG | — | — | 0ms |
| SBI S 米国高配当(年4回) | `schwab_csv` | 1 | csv | NG | — | — | 10678ms |
| SBI S 米国高配当(年4回) | `schwab_fund_page` | 2 | csv | NG | — | — | 10725ms |
| SBI S 米国高配当(年4回) | `manual` | 99 | local_csv | NG | — | — | 0ms |
| iFreeNEXT FANG+ | `ice_index_page` | 1 | json | NG | — | — | 9375ms |
| iFreeNEXT FANG+ | `fngs_etn` | 2 | csv | NG | — | — | 11464ms |
| iFreeNEXT FANG+ | `manual` | 3 | local_csv | NG | — | — | 0ms |
| iFreeNEXT FANG+ | `declared_equal_weight` | 90 | equal_weight | OK | 10 | 0 | 0ms |

## 失敗の詳細

### VTI 全米株式ETF / `vanguard_api` (p1)
- URL: `https://investor.vanguard.com/investment-products/etfs/profile/api/VTI/portfolio-holding/stock`
- エラー: JSONDecodeError: Expecting value: line 1 column 1 (char 0)

### VTI 全米株式ETF / `vanguard_api_alt` (p2)
- URL: `https://investor.vanguard.com/investment-products/etfs/profile/api/VTI/portfolio-holding/bond`
- エラー: JSONDecodeError: Expecting value: line 1 column 1 (char 0)

### VTI 全米株式ETF / `manual` (p99)
- URL: `data/manual/VTI.csv`
- エラー: 0件（取得できないかパースできませんでした）

### VYM 米国高配当ETF / `vanguard_api` (p1)
- URL: `https://investor.vanguard.com/investment-products/etfs/profile/api/VYM/portfolio-holding/stock`
- エラー: JSONDecodeError: Expecting value: line 1 column 1 (char 0)

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

### SBI・V・S&P500 / `vanguard_api_voo` (p1)
- URL: `https://investor.vanguard.com/investment-products/etfs/profile/api/VOO/portfolio-holding/stock`
- エラー: JSONDecodeError: Expecting value: line 1 column 1 (char 0)

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
