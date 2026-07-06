import Foundation

/// The provider-agnostic surface the rest of the app talks to. OpenAI, Gemini, Claude and
/// the on-device engine all conform to this, so the AI backend is a runtime switch
/// (Settings → AI Provider) with no call-site changes.
///
/// Privacy contract: every method here may transmit data off-device. Callers MUST route
/// through `PrivacyGuard` first, which enforces "local-first" and the pre-send confirmation
/// gate. Providers themselves never read the Photos library directly — they receive already
/// down-scaled JPEG data or plain text.
protocol AIProvider: Sendable {
    var id: AIProviderKind { get }
    var displayName: String { get }
    /// True when this provider runs entirely on-device (no confirmation needed).
    var isLocal: Bool { get }

    /// Classify a down-scaled image into the PhotoMind taxonomy.
    func classify(imageJPEG: Data) async throws -> [CategoryTag]

    /// Produce a one-line caption used for the semantic embedding and album summaries.
    func caption(imageJPEG: Data) async throws -> String

    /// Embed a piece of text (a query, or an asset's caption+OCR) into a vector.
    func embed(text: String) async throws -> AssetEmbedding

    /// Summarize a trip/album from structured stats + sample captions.
    func summarizeTrip(_ context: TripSummaryContext) async throws -> String
}

enum AIProviderKind: String, Codable, CaseIterable, Sendable, Identifiable {
    case local
    case openAI
    case gemini
    case claude

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .local:  return "オンデバイス (プライバシー優先)"
        case .openAI: return "OpenAI GPT"
        case .gemini: return "Google Gemini"
        case .claude: return "Claude"
        }
    }

    var requiresAPIKey: Bool { self != .local }
}

/// Structured context handed to `summarizeTrip`. Keeping it a value type means we can unit
/// test summary prompts without any network.
struct TripSummaryContext: Sendable {
    let title: String
    let startDate: Date?
    let endDate: Date?
    let placeName: String?
    let totalCount: Int
    let categoryCounts: [PhotoCategory: Int]
    let sampleCaptions: [String]
}

enum AIError: LocalizedError {
    case missingAPIKey(AIProviderKind)
    case http(status: Int, body: String)
    case decoding(String)
    case cancelledByPrivacyGuard
    case unsupported

    var errorDescription: String? {
        switch self {
        case .missingAPIKey(let k): return "\(k.displayName) の API キーが設定されていません。"
        case .http(let s, _):       return "AI サーバーエラー (HTTP \(s))"
        case .decoding(let m):      return "AI 応答の解析に失敗しました: \(m)"
        case .cancelledByPrivacyGuard: return "プライバシー設定により送信がキャンセルされました。"
        case .unsupported:          return "この操作はこのプロバイダーでは対応していません。"
        }
    }
}
