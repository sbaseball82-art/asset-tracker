# My Earnings Calendar（マイ決算カレンダー）

あなたの保有ETFに連動し、「自分の資産に影響するイベント」だけをImpact Score付きで表示する決算カレンダー。仕様書 v1.0 準拠のFlutter実装（iOS / Android共通）。

## いますぐ動かす（APIキー不要）

```bash
cd my_earnings_calendar
flutter pub get
flutter run          # 接続中のシミュレータ/実機で起動
flutter test         # ImpactEngineのユニットテスト + widgetテスト
```

iOS / Android / Web のプラットフォーム雛形（`ios/` `android/` `web/`）は生成済みです。Webで試す場合は `flutter run -d chrome`。

初回は `MockMarketDataRepository`（2026年7月のサンプルデータ）で全画面が動きます。Firebase・OpenAI・決算APIのキーは不要です。

## 新機能（2026-07-06 追加）

| 機能 | 実装 |
|---|---|
| 保有数の編集（ETF株数・投信口数を鉛筆アイコンから変更→配分%とImpact Score即時再計算） | `lib/ui/etf_screen.dart` 編集ダイアログ + `holdingsProvider` |
| GitHub自動同期（リポジトリ直下 `holdings.json` を起動時＆ボタンで取得・自動反映。オフライン時は同梱コピーへフォールバック） | `lib/data/holdings_sync.dart` + `syncProvider` |
| 保有ETF・投信の個別株式割合（帯グラフ＋「あなたの投資額」換算） | `lib/ui/etf_screen.dart` EtfDetailScreen |
| ニュース→どのETF/投信に効くか可視化（ファンド別影響度%・バー表示。イベントカードにも上位3ファンドをチップ表示） | `EventImpact.byFund` + `lib/ui/common.dart` / `home_screen.dart` |
| 評価額ベースのポートフォリオ（保有数×単価から配分%を自動計算・合計評価額表示） | `Portfolio.build`（`lib/state/providers.dart`） |

投信協会コード対応（holdings.jsonの "fund" キー）：29313233=iFreeNEXT FANG+ / 89311199=SBI・V・S&P500 / 04311181=ニッセイNASDAQ100 / 8931224C=SBI・S・米国高配当

## 実装済み（仕様書との対応）

| 仕様書 | 実装 |
|---|---|
| §7 ホーム（TOP5 / 今日 / 今週 / 保有ETF / AI Weekly Summary） | `lib/ui/home_screen.dart` |
| §8 ETF画面（一覧→構成銘柄・保有比率・前月比較） | `lib/ui/etf_screen.dart` |
| §9 イベント詳細（Score / 保有ETFへの影響 / 理由 / 見るポイント） | `lib/ui/common.dart` EventDetailSheet |
| §10 通知設定UI | `lib/main.dart` NotifScreen |
| §14 ライト/ダーク自動切替・Glass UI | `buildTheme` + `GlassCard` |
| §17 Impact Score 0–100・★1–5 | `lib/state/providers.dart` ImpactEngine（ルールベース初期版） |
| §18 Impact Timeline 色分け（赤/黄/青） | `timelineColor`（イベントカード左のドット） |
| §22 Unit Test | `test/impact_engine_test.dart`（5ケース） |
| §25 クリーンアーキテクチャ / Riverpod / Repository | `domain / data / state / ui` 分離 |

## 外部サービス接続（TODO・差し替えポイント）

すべて `MarketDataRepository`（`lib/data/repository.dart`）の実装差し替えで対応します。UI・ロジックは変更不要です。

- **ETF Holdings API / 決算API / 経済指標**：`MarketDataRepository` を実装した `ApiMarketDataRepository` を作成し、`repositoryProvider`（`lib/state/providers.dart`）で差し替え
- **Firebase Auth（Apple/Google Sign In）・Firestore**：`flutterfire configure` 実行後、`main()` で初期化
- **FCM / APNs 通知（§10）**：`notifSettingsProvider` の値をトークン登録に接続
- **OpenAI（AI要約・Impact分析 §11/§17）**：Cloud Functions 経由で `aiWeeklySummary` と `ImpactEngine` を置換
- **ウィジェット（§12）/ Live Activity（§13）/ Siriショートカット**：iOSネイティブ拡張（WidgetKit / ActivityKit / App Intents）が必要。Xcodeでターゲット追加後に実装

## 検証状況（2026-07-06 実施・Flutter 3.44.4 / Dart 3.12.2）

- `flutter analyze`：**error 0 / warning 0 / info 0**
- `flutter test`：**17テスト（unit 12 + widget 5）全パス**
- 新機能もChromium実機操作で検証済み：
  - 起動時にGitHubの holdings.json から自動同期（「GitHubと同期済み」表示・合計評価額 ¥32,487,011）
  - 保有数編集：VTI 195株→390株で配分28.8%→44.7%・合計評価額が即時再計算、「初期値に戻す」で復元
  - 「GitHub同期」ボタンで再同期・オフライン時は同梱値フォールバック（widgetテストで検証）
  - イベント詳細に「どのETF・投信に効く？（影響度）」：JPM決算→VYM 3.4% / SBI・S 3.0% / SBI・V 1.5% / VTI 1.3%（バー＋資産全体への寄与%）
  - イベントカードに影響ファンドのチップ表示（例：NFLX決算→FNG 10.0% / QQQ 2.0% / NDX 2.0%）
  - ETF詳細に構成の帯グラフ＋銘柄ごと「あなたの投資額」換算（VTI→NVDA 約¥561,600 等）
  - ダークモード表示OK・コンソールエラー0
- `flutter build web --release` + Chromium 実機操作で全フローを検証済み：
  - ホーム（TOP5 / 今日 / 週切替チップ / 保有ETFピル / AI Weekly Summary）表示
  - イベント詳細ボトムシート（Impact Score・保有ETF内訳・見るポイント）の開閉・シート内スクロール
  - ETFトグルOFF→ホームのScore/直接反応%が再計算される（VTI OFFでMSFT決算 65→50・3.8%→1.9%）
  - ETF詳細（構成銘柄・前月比較）への遷移と戻る
  - 通知の3トグルON/OFF双方向
  - ライト/ダークテーマ両対応（`prefers-color-scheme` 追従）
  - コンソールエラー・クラッシュなし

### 検証中に修正した点

- `CupertinoPageTransitionsBuilder` が Flutter 3.44 で cupertino ライブラリへ移動 → import 追加（`lib/main.dart`）
- `withOpacity` → `withValues(alpha:)`、`Switch.activeColor` → `activeThumbColor` に置換（deprecation解消）
- 週切替の `ChoiceChip` がWebでラベル幅を誤計測し「今週/来週」等が見切れる → 自前のピル型ボタンに置き換え（`lib/ui/home_screen.dart`）

iOS/Androidシミュレータはこの環境に無いため未実施です。`ios/` `android/` の雛形は生成済みなので、お手元で `flutter run` すればそのまま起動します。
