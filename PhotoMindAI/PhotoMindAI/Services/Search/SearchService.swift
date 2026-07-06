import Foundation

/// Executes natural-language search:
///
///   1. `QueryParser` extracts date/category/place/media filters + semantic text.
///   2. Structured filters narrow a candidate set (over the SQLite metadata + FTS).
///   3. The semantic text is embedded and matched against the warm `VectorIndex`, restricted
///      to the candidate set, producing a cosine-ranked top-k.
///   4. Results are blended: an exact FTS/OCR hit boosts the score for precision on things
///      like "領収書 2025" while embeddings handle fuzzy concepts like "夜景".
///
/// Enforces the freemium search quota via `UsageMeter` before running.
struct SearchService: Sendable {
    let repository: AssetRepository
    let searchRepository: SearchRepository
    let vectorIndex: VectorIndex
    let providerFactory: AIProviderFactory
    let settings: SettingsRepository
    let usage: UsageMeter

    enum SearchError: LocalizedError {
        case quotaExceeded(limit: Int)
        var errorDescription: String? {
            switch self {
            case .quotaExceeded(let limit):
                return "今月の無料検索（\(limit)回）を使い切りました。Premium で検索無制限に。"
            }
        }
    }

    @MainActor
    func canSearch() -> Bool { usage.canSearch() }

    func search(_ rawQuery: String, limit: Int = 60) async throws -> [SearchResult] {
        // Quota gate (Premium users are unmetered — handled inside UsageMeter).
        let allowed = await MainActor.run { usage.consumeSearchIfAllowed() }
        guard allowed else { throw SearchError.quotaExceeded(limit: await MainActor.run { usage.freeMonthlyLimit }) }

        let providerKind = await MainActor.run { settings.provider }
        let parser = QueryParser()
        let query = parser.parse(rawQuery)

        // 2. Candidate set from structured filters (nil == "no restriction").
        let candidates = try candidateIdentifiers(for: query)

        // 3. Semantic ranking.
        var semanticHits: [(id: String, score: Float)] = []
        if !query.semanticText.isEmpty {
            let provider = providerFactory.make(providerKind)
            let embedder = EmbeddingService(provider: provider)
            let queryEmbedding = try await embedder.embed(text: query.semanticText, assetLocalIdentifier: "")
            semanticHits = await vectorIndex.topK(queryEmbedding.vector, k: limit, candidates: candidates)
        } else if let candidates {
            // Pure filter search (e.g. "先月の動画") — return by recency.
            semanticHits = candidates.map { (id: $0, score: 0) }
        }

        // 4. Blend with keyword/OCR hits and hydrate into results.
        let ftsHits = try searchRepository.keywordMatches(query.semanticText, limit: limit)
        return try assemble(semanticHits: semanticHits, ftsHits: ftsHits, query: query, limit: limit)
    }

    /// Compute the candidate identifier set from date/category/place/media filters.
    /// Returns nil when there are no structured filters (search whole library).
    private func candidateIdentifiers(for query: SearchQuery) throws -> Set<String>? {
        var sets: [Set<String>] = []

        if !query.categories.isEmpty {
            var union: Set<String> = []
            for category in query.categories {
                union.formUnion(try repository.assetIDs(inCategory: category))
            }
            sets.append(union)
        }
        if let range = query.dateRange {
            sets.append(try searchRepository.identifiers(in: range))
        }
        if let place = query.placeKeyword {
            sets.append(try searchRepository.identifiers(placeContains: place))
        }
        if let media = query.mediaType {
            sets.append(try searchRepository.identifiers(mediaType: media))
        }

        guard !sets.isEmpty else { return nil }
        return sets.dropFirst().reduce(sets[0]) { $0.intersection($1) }
    }

    private func assemble(semanticHits: [(id: String, score: Float)],
                          ftsHits: [String: String],
                          query: SearchQuery,
                          limit: Int) throws -> [SearchResult] {
        var scores: [String: Float] = [:]
        for hit in semanticHits { scores[hit.id] = hit.score }
        // Keyword/OCR exact matches get a strong additive boost.
        for id in ftsHits.keys { scores[id, default: 0] += 0.5 }

        let ranked = scores.sorted { $0.value > $1.value }.prefix(limit)
        var results: [SearchResult] = []
        for (id, score) in ranked {
            guard let asset = try repository.asset(localIdentifier: id) else { continue }
            results.append(SearchResult(asset: asset, score: score, matchedText: ftsHits[id]))
        }
        return results
    }
}
