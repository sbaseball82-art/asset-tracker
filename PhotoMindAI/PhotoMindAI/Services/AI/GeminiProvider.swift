import Foundation

/// Google Gemini implementation. Vision + text via `gemini-1.5-flash:generateContent`;
/// embeddings via `text-embedding-004` (768-d).
struct GeminiProvider: AIProvider {
    let id: AIProviderKind = .gemini
    let displayName = "Google Gemini"
    let isLocal = false

    private let http = AIHTTPClient()
    private let keychain: KeychainStore
    private let genModel = "gemini-1.5-flash"
    private let embeddingModel = "text-embedding-004"

    init(keychain: KeychainStore) { self.keychain = keychain }

    private func key() throws -> String {
        guard let k = keychain.apiKey(for: .gemini), !k.isEmpty else {
            throw AIError.missingAPIKey(.gemini)
        }
        return k
    }

    func classify(imageJPEG: Data) async throws -> [CategoryTag] {
        let text = try await generate(prompt: AIPrompts.classify, imageJPEG: imageJPEG)
        return CategoryJSONParser.parse(text)
    }

    func caption(imageJPEG: Data) async throws -> String {
        try await generate(prompt: AIPrompts.caption, imageJPEG: imageJPEG)
    }

    func summarizeTrip(_ context: TripSummaryContext) async throws -> String {
        try await generate(prompt: AIPrompts.tripSummary(context), imageJPEG: nil)
    }

    func embed(text: String) async throws -> AssetEmbedding {
        let k = try key()
        let url = URL(string:
            "https://generativelanguage.googleapis.com/v1beta/models/\(embeddingModel):embedContent?key=\(k)")!
        let body: [String: Any] = [
            "model": "models/\(embeddingModel)",
            "content": ["parts": [["text": text]]],
        ]
        let data = try await http.postJSON(url, headers: [:], body: body)
        guard
            let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let embedding = obj["embedding"] as? [String: Any],
            let values = embedding["values"] as? [Double]
        else { throw AIError.decoding("gemini embed response") }
        return AssetEmbedding(assetLocalIdentifier: "", model: embeddingModel,
                              vector: values.map(Float.init))
    }

    private func generate(prompt: String, imageJPEG: Data?) async throws -> String {
        let k = try key()
        let url = URL(string:
            "https://generativelanguage.googleapis.com/v1beta/models/\(genModel):generateContent?key=\(k)")!
        var parts: [[String: Any]] = [["text": prompt]]
        if let jpeg = imageJPEG {
            parts.append(["inline_data": ["mime_type": "image/jpeg",
                                          "data": jpeg.base64EncodedString()]])
        }
        let body: [String: Any] = [
            "contents": [["parts": parts]],
            "generationConfig": ["temperature": 0.2, "maxOutputTokens": 300],
        ]
        let data = try await http.postJSON(url, headers: [:], body: body)
        guard
            let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let candidates = obj["candidates"] as? [[String: Any]],
            let content = candidates.first?["content"] as? [String: Any],
            let resultParts = content["parts"] as? [[String: Any]],
            let text = resultParts.first?["text"] as? String
        else { throw AIError.decoding("gemini generate response") }
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
