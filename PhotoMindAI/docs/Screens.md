# 画面一覧

| # | 画面 | ファイル | 役割 |
|---|------|---------|------|
| 1 | ライブラリ | `Features/Library/LibraryView.swift` | 全写真グリッド、カテゴリ絞り込み、解析進捗ヘッダー |
| 2 | AI 検索 | `Features/Search/SearchView.swift` | 自然言語検索、サジェスト、残り検索回数ピル |
| 3 | アルバム | `Features/Albums/AlbumsView.swift` | 自動生成アルバム（旅行/仕事/家族/食事/ペット/レシート） |
| 4 | アルバム詳細 | `Features/Albums/AlbumDetailView.swift` | AI 要約、地図、メンバーグリッド |
| 5 | カレンダー | `Features/Calendar/CalendarScreen.swift` | 月別 / 旅行別 / イベント別タイムライン |
| 6 | 整理 | `Features/Cleanup/CleanupView.swift` | 重複/ピンボケ/スクショの削除候補 |
| 7 | 写真詳細 | `Features/AssetDetail/AssetDetailView.swift` | 大画像、AI キャプション、OCR、位置、メタデータ |
| 8 | 設定 | `Features/Settings/SettingsView.swift` | AI プロバイダー/キー、プライバシー、App ロック、課金 |
| 9 | ペイウォール | `Features/Paywall/PaywallView.swift` | Premium 訴求（StoreKit 2） |
| — | ロック画面 | `App/RootView.swift`（LockOverlay） | Face ID による App ロック |
| — | 送信確認 | `App/RootView.swift`（PrivacyConfirmationModifier） | AI 送信前の確認アラート |

## タブ構成（`RootView`）

`ライブラリ / 検索 / アルバム / カレンダー / 整理` の 5 タブ。
検索タブは iOS 18 の `Tab(role: .search)`。設定はライブラリ左上のギアから sheet 表示。

## ウィジェット / Live Activity

| 対象 | ファイル | 内容 |
|------|---------|------|
| ホーム画面ウィジェット | `PhotoMindWidget/MemoriesWidget.swift` | 「今日の思い出」+ ライブラリ統計（App Group 経由） |
| Live Activity / Dynamic Island | `PhotoMindWidget/AnalysisLiveActivity.swift` | 解析進捗をロック画面/ダイナミックアイランドに表示 |

## デザイン

- iOS 26 の Liquid Glass に合わせた `GlassCard`（iOS 18 では `.ultraThinMaterial` にフォールバック）。
- Dark Mode 完全対応（AccentColor は light/dark 両対応の colorset）。
- SF Symbols + `symbolEffect(.pulse)` などのシステムアニメーション。
