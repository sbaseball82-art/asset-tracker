# アーキテクチャ

PhotoMind AI は **SwiftUI + MVVM + Repository パターン + Async/Await** で構築されています。
依存は一方向（UI → ViewModel → Repository/Service → Infra）で、各層は下位の**プロトコル/値型**にのみ依存します。

```
┌──────────────────────────────────────────────────────────────┐
│  View (SwiftUI)                                                │
│   LibraryView / SearchView / AlbumsView / CalendarScreen …     │
└───────────────┬──────────────────────────────────────────────┘
                │ @Observable ViewModel を保持
┌───────────────▼──────────────────────────────────────────────┐
│  ViewModel (@MainActor @Observable)                            │
│   LibraryViewModel / SearchViewModel / CleanupViewModel …      │
└───────────────┬──────────────────────────────────────────────┘
                │ Repository / Service を呼ぶ
┌───────────────▼──────────────────────────────────────────────┐
│  Repository            │  Service (actor / struct)            │
│   AssetRepository      │   AnalysisPipeline / SearchService   │
│   AlbumRepository      │   AlbumService / PhotoLibraryService │
│   SearchRepository     │   AIProvider(×4) / EmbeddingService  │
│   SettingsRepository   │   PrivacyGuard / BiometricAuth       │
└───────────────┬────────┴──────────────┬───────────────────────┘
                │                        │
┌───────────────▼──────────┐  ┌──────────▼───────────────────────┐
│  Infra: GRDB(SQLite)      │  │  Apple: PhotoKit / Vision /       │
│   AppDatabase / Records   │  │  NaturalLanguage / StoreKit /     │
│   VectorIndex(in-memory)  │  │  LocalAuthentication / ActivityKit│
└───────────────────────────┘  └───────────────────────────────────┘
```

## 依存性注入

`AppEnvironment`（コンポジションルート）が全サービスを一度だけ構築し、SwiftUI environment 経由で配布します。
ViewModel はコンストラクタでリポジトリ/サービスを受け取るため、テストではインメモリ DB や
スタブを差し込めます（`AppEnvironment.preview()` 参照）。

## 並行性（Swift 6 strict concurrency）

- 重い解析は `actor AnalysisPipeline` / `actor VectorIndex` にオフロード。
- UI 状態は `@MainActor @Observable`。
- ドメインモデル（`Asset` 等）は `Sendable` な値型で、アクター境界を安全に越えます。

## AI プロバイダー抽象化

`AIProvider` プロトコルに `classify / caption / embed / summarizeTrip` を定義。
`OpenAIProvider` / `GeminiProvider` / `ClaudeProvider` / `LocalAIProvider` が実装し、
`AIProviderFactory` が設定に応じて生成します。外部送信は必ず `PrivacyGuard` を通します。

## 検索パイプライン

1. `QueryParser` が日付/カテゴリ/場所/メディアの構造化フィルタと意味テキストに分解。
2. 構造化フィルタで候補集合を絞り込み（SQLite + FTS5）。
3. 意味テキストを埋め込み、`VectorIndex` で候補集合に限定した top-k コサイン検索。
4. FTS/OCR の完全一致でブースト → 最終ランキング。

詳細は [Database.md](Database.md) / [API.md](API.md) を参照。
