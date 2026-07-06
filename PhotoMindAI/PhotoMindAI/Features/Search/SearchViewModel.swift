import Foundation
import SwiftUI

/// View model for natural-language search. Debounces input, runs `SearchService`, surfaces
/// quota errors (routing to the paywall), and keeps recent/suggested queries.
@MainActor
@Observable
final class SearchViewModel {
    private let searchService: SearchService
    let usageMeter: UsageMeter
    private let debouncer = Debouncer(delay: .milliseconds(350))

    var queryText = ""
    var results: [SearchResult] = []
    var isSearching = false
    var errorMessage: String?
    var showPaywall = false

    let suggestions = ["去年 大阪 ラーメン", "白い犬", "子供の運動会", "富士山", "結婚式",
                       "京都 夜景", "寿司", "先月の動画", "クリスマス", "レシート 2025"]

    init(searchService: SearchService, usageMeter: UsageMeter) {
        self.searchService = searchService
        self.usageMeter = usageMeter
    }

    func onQueryChange() {
        let text = queryText
        Task {
            await debouncer.call { [weak self] in
                await self?.run(text)
            }
        }
    }

    func submit() { Task { await run(queryText) } }

    func run(_ text: String) async {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { results = []; return }
        isSearching = true
        errorMessage = nil
        defer { isSearching = false }
        do {
            results = try await searchService.search(trimmed)
        } catch let error as SearchService.SearchError {
            errorMessage = error.errorDescription
            showPaywall = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func useSuggestion(_ text: String) {
        queryText = text
        submit()
    }
}
