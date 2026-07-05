# Claude Code 作業指示（My Earnings Calendar）

このリポジトリは仕様書v1.0のFlutter実装。静的検証済みだが、**コンパイル・実機検証はこの先で行う**。以下を順に実行し、すべて緑になるまで修正すること。

## セットアップと検証手順（この順で）
1. `flutter create . --org jp.assetlog --project-name my_earnings_calendar --platforms ios,android`
   - 既存の lib/ test/ pubspec.yaml README.md は上書きされない（test/widget_test.dart は正しい版を同梱済み）
2. `flutter pub get`
3. `flutter analyze` → **warning 0 / error 0 になるまで修正**
   - 既知の可能性: `withOpacity` / `Switch.activeColor` の deprecation info（Flutter 3.27+）。出た場合は `withValues(alpha:)` / `activeThumbColor` に置換してよい
4. `flutter test` → 7テスト（unit 5 + widget 2）全パス
5. `flutter run` で起動確認：
   - ホーム: TOP5カード・今日のイベント・週切替チップ・AI Weekly Summary が表示される
   - イベントタップ → ボトムシートに Impact Score / 保有ETF内訳 / 見るポイント
   - ETFタブ: トグルOFFでホームのScoreが変わる（VTIをOFF→MSFT決算の%が減る）
   - 通知タブ: 3つのトグルが動く
   - ライト/ダーク: 端末設定に追従
6. スクロール・シート開閉にジャンクがないこと（Impellerデフォルトで可）

## 受け入れ基準
- [ ] analyze クリーン / test 全パス / iOSシミュレータ+Androidエミュレータで起動
- [ ] 60fps相当でスクロール（DevTools Performanceで確認）
- [ ] クラッシュなしで全タブ・全イベント詳細を巡回できる

## 次フェーズ（この順で拡張。UI/ロジックは変更不要）
1. `ApiMarketDataRepository` 実装（`lib/data/repository.dart` の抽象に準拠）→ `repositoryProvider` で差替
2. Firebase（`flutterfire configure`）→ Auth(Apple/Google) → FCM
3. Cloud Functions + OpenAI（AI要約 / Impact分析の置換）
4. WidgetKit / ActivityKit / App Intents（ウィジェット・Live Activity・Siri）
