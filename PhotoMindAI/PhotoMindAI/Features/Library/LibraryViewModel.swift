import Foundation
import SwiftUI

/// View model for the main photo grid. Loads assets from the repository, exposes the analysis
/// progress, and lets the user filter by category. MVVM: the view is dumb, this holds state.
@MainActor
@Observable
final class LibraryViewModel {
    private let assetRepository: AssetRepository
    private let pipeline: AnalysisPipeline
    let progress: AnalysisProgress

    var assets: [Asset] = []
    var selectedCategory: PhotoCategory?
    var isLoading = false
    var totalCount = 0

    init(assetRepository: AssetRepository, pipeline: AnalysisPipeline, progress: AnalysisProgress) {
        self.assetRepository = assetRepository
        self.pipeline = pipeline
        self.progress = progress
    }

    var filteredAssets: [Asset] {
        guard let category = selectedCategory else { return assets }
        // Category filtering is resolved against the DB in `load`; here we keep the cached list.
        return categoryFiltered ?? assets
    }
    private var categoryFiltered: [Asset]?

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            assets = try assetRepository.allAssets()
            totalCount = try assetRepository.totalCount()
        } catch {
            Log.ui.error("Library load failed: \(error.localizedDescription)")
        }
    }

    func select(category: PhotoCategory?) async {
        selectedCategory = category
        guard let category else { categoryFiltered = nil; return }
        if let ids = try? assetRepository.assetIDs(inCategory: category) {
            categoryFiltered = assets.filter { ids.contains($0.localIdentifier) }
        }
    }

    func refresh() async {
        await pipeline.syncAndAnalyze()
        await load()
    }
}
