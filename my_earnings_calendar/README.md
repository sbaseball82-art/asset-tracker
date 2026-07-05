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

## 検証状況（2026-07-05 実施・Flutter 3.44.4 / Dart 3.12.2）

- `flutter analyze`：**error 0 / warning 0 / info 0**
- `flutter test`：**7テスト（unit 5 + widget 2）全パス**
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
