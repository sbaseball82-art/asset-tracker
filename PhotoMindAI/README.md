# PhotoMind AI

> 写真アプリではなく、**AI が思い出を管理するアプリ**。
> 写真を自動分類し、「去年 大阪で食べた ラーメン」「白い犬」「子供の運動会」のように
> **自然言語で検索**できます。

iOS 18+ / SwiftUI / Swift 6。オンデバイス AI 優先・プライバシーファースト設計。

---

## ✨ 主な機能

| 機能 | 内容 | 実装 |
|------|------|------|
| 📥 ライブラリ同期 | 写真・動画・Live Photo・HEIC・RAW を Apple Photos から取得 | `PhotoLibraryService` |
| 🧠 AI 画像解析 | 人物/料理/建物/風景/犬/猫/花/レシート/QR/書類/旅行/飲み物/服/車/スポーツ を自動分類 | `LocalAIProvider` + Vision、リモート AI 併用可 |
| 🔤 OCR | 画像内文字（レシート/名刺/書類/ホワイトボード）を日英認識 | `OCRService`（Vision） |
| 🔎 AI 検索 | 自然言語 → 日付/場所/カテゴリ抽出 + 埋め込みベクトル検索 | `QueryParser` + `SearchService` + `VectorIndex` |
| 🗂 自動アルバム | 旅行/仕事/家族/食事/ペット/レシートを自動生成 | `AlbumBuilder` / `AlbumService` |
| 📝 AI 要約 | 「京都旅行 2025年4月 写真128枚 食事12件 寺5件」 | `AIProvider.summarizeTrip` |
| 🧹 重複・整理 | 類似画像/ピンボケ/スクショの削除候補 | `ImageQualityAnalyzer` + `DuplicateDetector` |
| 📅 カレンダー | 月別 / 旅行別 / イベント別タイムライン | `CalendarScreen` |
| 🔐 セキュリティ | Face ID ロック、送信前確認、ローカル解析優先、写真は外部保存しない | `BiometricAuth` / `PrivacyGuard` |
| 🧩 ウィジェット | ホーム画面「思い出」+ Live Activity / Dynamic Island（解析進捗） | `PhotoMindWidget` |
| 💳 収益化 | 無料（月100検索）/ Premium（検索無制限・AI要約・Cloud同期・広告なし） | `StoreService` / `UsageMeter` |

## 🤖 切替可能な AI

OpenAI GPT / Google Gemini / Claude / **オンデバイス** を設定から切替。
画像解析・埋め込み・OCR・要約をカバー。外部送信は縮小 JPEG のみ・送信前確認あり。
→ [docs/API.md](docs/API.md)

## 🏗 技術スタック

SwiftUI · MVVM · Repository パターン · Async/Await · Swift 6 strict concurrency ·
GRDB(SQLite) + FTS5 · Vision · NaturalLanguage · PhotoKit · StoreKit 2 ·
WidgetKit · ActivityKit · LocalAuthentication · Swift Testing · GitHub Actions。

## 📁 フォルダ構成

```
PhotoMindAI/
├── project.yml                 # XcodeGen プロジェクト定義
├── PhotoMindAI/                # アプリターゲット
│   ├── App/                    # エントリ・DIコンテナ・RootView
│   ├── Core/
│   │   ├── Models/             # Asset / Category / Album / Embedding / SearchQuery
│   │   ├── Database/           # AppDatabase(GRDB) / Records / VectorIndex
│   │   └── Utils/              # Logger / Debouncer / ImageDownscaler
│   ├── Services/
│   │   ├── Photos/             # PhotoKit 同期・取得
│   │   ├── Analysis/           # 分類/OCR/品質/重複/解析パイプライン/Live Activity
│   │   ├── AI/                 # AIProvider ×4 / Factory / EmbeddingService
│   │   ├── Search/             # QueryParser / SearchService
│   │   ├── Albums/             # AlbumBuilder / AlbumService
│   │   ├── Security/           # Keychain / BiometricAuth / PrivacyGuard
│   │   └── Subscription/       # StoreKit / UsageMeter
│   ├── Repositories/           # Asset / Album / Search / Settings
│   ├── Features/               # 画面ごとの View + ViewModel（MVVM）
│   └── Resources/              # Info.plist / entitlements / Assets.xcassets
├── PhotoMindWidget/            # ウィジェット + Live Activity 拡張
├── Shared/                     # アプリ↔拡張 共有（ActivityAttributes）
├── Tests/PhotoMindAITests/     # Swift Testing ユニットテスト
└── docs/                       # Architecture / Screens / Database / API / Release
```

## 🚀 クイックスタート

```bash
brew install xcodegen
cd PhotoMindAI
xcodegen generate
open PhotoMindAI.xcodeproj      # Xcode で Run（iPhone シミュレータ）
```

外部 AI を使う場合はアプリ内 **設定 → AI プロバイダー** で API キーを入力（Keychain 保存）。
未入力でもオンデバイス AI で全機能が動作します。

## ✅ テスト

```bash
xcodebuild test -project PhotoMindAI.xcodeproj -scheme PhotoMindAI \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=latest'
```

純粋ロジック（ベクトル演算・クエリ解析・重複検出・アルバム生成・課金メーター・
永続化ラウンドトリップ）を Swift Testing で網羅（`Tests/`）。

## 🔒 プライバシー方針

- 写真ピクセルは**端末内のみ**。外部 AI へは縮小 JPEG のみ、送信前に確認。
- API キーは Keychain（iCloud 非同期）。AI 通信は ephemeral セッション。
- 「送信しない（ローカルのみ）」を選べば一切外部送信なし。
- App ロック（Face ID / Touch ID）対応。

## 📚 ドキュメント

- [アーキテクチャ](docs/Architecture.md)
- [画面一覧](docs/Screens.md)
- [DB 設計](docs/Database.md)
- [API 設計](docs/API.md)
- [リリース手順](docs/Release.md)

## ⚠️ 補足

`.xcodeproj` は `project.yml` から生成する方針のためコミットしていません（差分レビュー性のため）。
本番アイコン・スクリーンショット・サブスク Product 登録は [docs/Release.md](docs/Release.md) を参照。
