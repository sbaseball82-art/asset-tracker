import Foundation

/// OpenAI implementation. Vision via chat completions with an image_url data URI; embeddings
/// via `text-embedding-3-small` (1536-d). API key is read from Keychain at call time and is
/// never persisted anywhere else.
struct OpenAIProvider: AIProvider {
    let id: AIProviderKind = .openAI
    let displayName = "OpenAI GPT"
    let isLocal = false

    private let http = AIHTTPClient()
    private let keychain: KeychainStore
    private let visionModel = "gpt-4o-mini"
    private let embeddingModel = "text-embedding-3-small"

    init(keychain: KeychainStore) { self.keychain = keychain }

    private func key() throws -> String {
        guard let k = keychain.apiKey(for: .openAI), !k.isEmpty else {
            throw AIError.missingAPIKey(.openAI)
        }
        return k
    }

    private var authHeaders: [String: String] {
        get throws { ["Authorization": "Bearer \(try key())"] }
    }

    func classify(imageJPEG: Data) async throws -> [CategoryTag] {
        let text = try await chatWithImage(imageJPEG, prompt: AIPrompts.classify)
        return CategoryJSONParser.parse(text)
    }

    func caption(imageJPEG: Data) async throws -> String {
        try await chatWithImage(imageJPEG, prompt: AIPrompts.caption)
    }

    func embed(text: String) async throws -> AssetEmbedding {
        let url = URL(string: "https://api.openai.com/v1/embeddings")!
        let body: [String: Any] = ["model": embeddingModel, "input": text]
        let data = try await http.postJSON(url, headers: try authHeaders, body: body)
        guard
            let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let arr = obj["data"] as? [[String: Any]],
            let first = arr.first,
            let vec = first["embedding"] as? [Double]
        else { throw AIError.decoding("embeddings response") }
        return AssetEmbedding(assetLocalIdentifier: "", model: embeddingModel,
                              vector: vec.map(Float.init))
    }

    func summarizeTrip(_ context: TripSummaryContext) async throws -> String {
        try await chatText(AIPrompts.tripSummary(context))
    }

    // MARK: - Chat helpers

    private func chatWithImage(_ jpeg: Data, prompt: String) async throws -> String {
        let dataURI = "data:image/jpeg;base64,\(jpeg.base64EncodedString())"
        let messages: [[String: Any]] = [[
            "role": "user",
            "content": [
                ["type": "text", "text": prompt],
                ["type": "image_url", "image_url": ["url": dataURI, "detail": "low"]],
            ],
        ]]
        return try await chat(messages)
    }

    private func chatText(_ prompt: String) async throws -> String {
        try await chat([["role": "user", "content": prompt]])
    }

    private func chat(_ messages: [[String: Any]]) async throws -> String {
        let url = URL(string: "https://api.openai.com/v1/chat/completions")!
        let body: [String: Any] = [
            "model": visionModel,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 300,
        ]
        let data = try await http.postJSON(url, headers: try authHeaders, body: body)
        guard
            let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let choices = obj["choices"] as? [[String: Any]],
            let message = choices.first?["message"] as? [String: Any],
            let content = message["content"] as? String
        else { throw AIError.decoding("chat response") }
        return content.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
