import Foundation
import SwiftUI

/// View model for the cleanup screen: computes duplicate/blur/screenshot suggestions and
/// performs user-confirmed deletions through PhotoKit.
@MainActor
@Observable
final class CleanupViewModel {
    private let assetRepository: AssetRepository
    private let photos: PhotoLibraryService
    private let detector = DuplicateDetector()

    var suggestions: DuplicateDetector.CleanupSuggestions?
    var isLoading = false
    var selectedForDeletion: Set<String> = []
    var deleteError: String?

    init(assetRepository: AssetRepository, photos: PhotoLibraryService) {
        self.assetRepository = assetRepository
        self.photos = photos
    }

    var reclaimable: Int { suggestions?.totalReclaimable ?? 0 }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        let assets = (try? assetRepository.allAssets()) ?? []
        suggestions = detector.suggestions(for: assets)
        // Pre-select the recommended discards.
        var preselect: Set<String> = []
        suggestions?.duplicateGroups.forEach { group in
            preselect.formUnion(group.discard.map(\.localIdentifier))
        }
        selectedForDeletion = preselect
    }

    func toggle(_ id: String) {
        if selectedForDeletion.contains(id) { selectedForDeletion.remove(id) }
        else { selectedForDeletion.insert(id) }
    }

    func deleteSelected() async {
        guard !selectedForDeletion.isEmpty else { return }
        do {
            try await photos.delete(localIdentifiers: Array(selectedForDeletion))
            selectedForDeletion.removeAll()
            await load()
        } catch {
            deleteError = error.localizedDescription
        }
    }
}
