import Foundation
import NaturalLanguage

/// Produces text embeddings. Delegates to the active `AIProvider` for remote models, but
/// always has a local fallback via Apple's `NLEmbedding` so search works offline and for
/// providers (Claude) that lack an embeddings endpoint.
///
/// Query and asset embeddings MUST come from the same model to be comparable — the caller
/// (SearchService / AnalysisPipeline) pins one model per run and records it on each vector.
struct EmbeddingService: Sendable {
    let provider: any AIProvider

    func embed(text: String, assetLocalIdentifier: String) async throws -> AssetEmbedding {
        let base: AssetEmbedding
        do {
            base = try await provider.embed(text: text)
        } catch {
            Log.ai.error("Remote embed failed, using local fallback: \(error.localizedDescription)")
            base = try Self.localEmbed(text: text, assetLocalIdentifier: assetLocalIdentifier)
        }
        return AssetEmbedding(assetLocalIdentifier: assetLocalIdentifier,
                              model: base.model, vector: base.vector)
    }

    /// On-device sentence embedding. Tries Japanese then English `NLEmbedding`; both yield
    /// fixed-dimension vectors we average across tokens. Deterministic and offline.
    static func localEmbed(text: String, assetLocalIdentifier: String) throws -> AssetEmbedding {
        let cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let ja = NLEmbedding.sentenceEmbedding(for: .japanese)
        let en = NLEmbedding.sentenceEmbedding(for: .english)

        if let vec = ja?.vector(for: cleaned) ?? en?.vector(for: cleaned) {
            return AssetEmbedding(assetLocalIdentifier: assetLocalIdentifier,
                                  model: "NLEmbedding.sentence", vector: vec.map(Float.init))
        }
        // Fallback: average per-word vectors (handles short fragments the sentence model rejects).
        let wordEmbedding = NLEmbedding.wordEmbedding(for: .japanese)
            ?? NLEmbedding.wordEmbedding(for: .english)
        guard let we = wordEmbedding else {
            throw AIError.decoding("NLEmbedding unavailable on this device")
        }
        let tokens = cleaned.split(whereSeparator: { $0.isWhitespace || $0.isPunctuation })
        var accum = [Double](repeating: 0, count: we.dimension)
        var n = 0
        for token in tokens {
            if let v = we.vector(for: String(token).lowercased()) {
                for i in 0..<accum.count { accum[i] += v[i] }
                n += 1
            }
        }
        if n > 0 { for i in 0..<accum.count { accum[i] /= Double(n) } }
        return AssetEmbedding(assetLocalIdentifier: assetLocalIdentifier,
                              model: "NLEmbedding.word", vector: accum.map(Float.init))
    }
}
