import Foundation

/// A parsed natural-language query. `QueryParser` extracts structured filters (dates,
/// places, categories) from the raw string; whatever is left over becomes the semantic
/// text that gets embedded and matched against asset vectors.
struct SearchQuery: Hashable, Sendable {
    let raw: String
    var semanticText: String
    var categories: Set<PhotoCategory>
    var dateRange: DateInterval?
    var placeKeyword: String?
    var mediaType: Asset.MediaType?

    var isEmpty: Bool {
        semanticText.trimmingCharacters(in: .whitespaces).isEmpty
            && categories.isEmpty
            && dateRange == nil
            && placeKeyword == nil
            && mediaType == nil
    }
}

/// A single ranked search result.
struct SearchResult: Identifiable, Hashable, Sendable {
    var id: String { asset.localIdentifier }
    let asset: Asset
    let score: Float          // combined semantic + filter score, higher is better
    let matchedText: String?  // OCR/caption snippet that matched, for highlighting
}
