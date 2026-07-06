import Foundation

/// Anthropic Claude implementation. Vision + text via the Messages API. Claude does not
/// expose a text-embedding endpoint, so embeddings fall back to the on-device `NLEmbedding`
/// (documented behavior — surfaced in Settings). Classification/captioning/summaries use
/// the multimodal Messages API.
struct ClaudeProvider: AIProvider {
    let id: AIProviderKind = .claude
    let displayName = "Claude"
    let isLocal = false

    private let http = AIHTTPClient()
    private let keychain: KeychainStore
    private let model = "claude-sonnet-5"

    init(keychain: KeychainStore) { self.keychain = keychain }

    private func headers() throws -> [String: String] {
        guard let k = keychain.apiKey(for: .claude), !k.isEmpty else {
            throw AIError.missingAPIKey(.claude)
        }
        return [
            "x-api-key": k,
            "anthropic-version": "2023-06-01",
        ]
    }

    func classify(imageJPEG: Data) async throws -> [CategoryTag] {
        let text = try await message(prompt: AIPrompts.classify, imageJPEG: imageJPEG)
        return CategoryJSONParser.parse(text)
    }

    func caption(imageJPEG: Data) async throws -> String {
        try await message(prompt: AIPrompts.caption, imageJPEG: imageJPEG)
    }

    func summarizeTrip(_ context: TripSummaryContext) async throws -> String {
        try await message(prompt: AIPrompts.tripSummary(context), imageJPEG: nil)
    }

    /// Claude has no embeddings endpoint; use the on-device model so search still works.
    func embed(text: String) async throws -> AssetEmbedding {
        try EmbeddingService.localEmbed(text: text, assetLocalIdentifier: "")
    }

    private func message(prompt: String, imageJPEG: Data?) async throws -> String {
        let url = URL(string: "https://api.anthropic.com/v1/messages")!
        var content: [[String: Any]] = [["type": "text", "text": prompt]]
        if let jpeg = imageJPEG {
            content.insert([
                "type": "image",
                "source": [
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": jpeg.base64EncodedString(),
                ],
            ], at: 0)
        }
        let body: [String: Any] = [
            "model": model,
            "max_tokens": 300,
            "messages": [["role": "user", "content": content]],
        ]
        let data = try await http.postJSON(url, headers: try headers(), body: body)
        guard
            let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let blocks = obj["content"] as? [[String: Any]],
            let text = blocks.first(where: { ($0["type"] as? String) == "text" })?["text"] as? String
        else { throw AIError.decoding("claude messages response") }
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
