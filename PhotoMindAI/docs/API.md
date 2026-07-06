# API 設計（AI プロバイダー）

すべての AI 呼び出しは `AIProvider` プロトコル（`Services/AI/AIProvider.swift`）を経由します。
プロバイダーは実行時に切替可能で、呼び出し側は具体実装に依存しません。

```swift
protocol AIProvider: Sendable {
    var id: AIProviderKind { get }
    var isLocal: Bool { get }
    func classify(imageJPEG: Data) async throws -> [CategoryTag]
    func caption(imageJPEG: Data) async throws -> String
    func embed(text: String) async throws -> AssetEmbedding
    func summarizeTrip(_ context: TripSummaryContext) async throws -> String
}
```

## 送信データの最小化

外部送信されるのは **512px に縮小・再エンコードした JPEG のみ**（`ImageDownscaler` / `PrivacyGuard.downscaledJPEG`）。
オリジナル画像・EXIF は端末から出ません。送信は毎回 `PrivacyGuard.authorizeUpload` を通過します。

## 各プロバイダーのエンドポイント

| 機能 | OpenAI | Gemini | Claude | Local |
|------|--------|--------|--------|-------|
| 画像分類 | `chat/completions` (gpt-4o-mini, image_url) | `gemini-1.5-flash:generateContent` (inline_data) | `messages` (image block) | `VNClassifyImageRequest` |
| キャプション | 同上 | 同上 | 同上 | Vision + OCR 合成 |
| 埋め込み | `embeddings` (text-embedding-3-small, 1536d) | `text-embedding-004:embedContent` (768d) | ⚠ なし → ローカル `NLEmbedding` | `NLEmbedding`(sentence/word) |
| 旅行要約 | chat (text) | generate (text) | messages (text) | 決定的テンプレート |
| OCR | すべて端末側 `VNRecognizeTextRequest`（ja-JP / en-US）で実施。外部送信なし。 |

> **埋め込みの一貫性**: クエリと写真の埋め込みは必ず同一モデルで生成する必要があります。
> 実行時に設定中プロバイダーを 1 つに固定し、各ベクトルに `model` を記録します。
> Claude は埋め込み API を持たないため、Claude 選択時は分類/キャプションのみ Claude、
> 埋め込みはローカル `NLEmbedding` を使用します（設定画面に明記）。

## 認証・キー管理

- API キーは **Keychain**（`kSecAttrAccessibleWhenUnlockedThisDeviceOnly`, iCloud 同期なし）に保存。
  リポジトリ・ログ・コミットには一切残りません（`KeychainStore`）。
- `URLSession` は `ephemeral` 構成（AI 通信をディスクキャッシュしない）。

## 共通プロンプト

分類は全プロバイダーに同一の指示（`AIPrompts.classify`）を送り、
`{"category": …, "confidence": …}` の JSON 配列で返させ、`CategoryJSONParser` が
`PhotoCategory` にマッピング（マークダウン fence や余計な散文にも耐性）。

## エラーハンドリング

`AIError`（`missingAPIKey / http / decoding / cancelledByPrivacyGuard / unsupported`）で
ローカライズ済みメッセージを提供。リモート失敗時は自動でローカルにフォールバックし、
オフラインでも分類・検索が継続します。

## レート/コスト対策

- 画像は low-detail 512px、`max_tokens` は 300 に制限。
- 分類は端末側で先に実施し、リモートは**精度向上の追加パス**（任意・許可時のみ）。
- 検索埋め込みはクエリ 1 回のみ課金（写真側の埋め込みは解析時に一度だけ生成）。
