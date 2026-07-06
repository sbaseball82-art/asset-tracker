import Foundation
import SwiftUI

/// Composition root / dependency container. Constructs every service once and hands typed
/// dependencies to the feature view models. Injected into the SwiftUI environment so views
/// build their view models from it. Keeping wiring here (not in views) is what makes the
/// MVVM + Repository layering testable — view models receive protocols/values, not singletons.
@MainActor
@Observable
final class AppEnvironment {
    // Infrastructure
    let database: AppDatabase
    let keychain: KeychainStore
    let photos: PhotoLibraryService
    let vectorIndex: VectorIndex

    // Repositories
    let assetRepository: AssetRepository
    let albumRepository: AlbumRepository
    let searchRepository: SearchRepository
    let settings: SettingsRepository

    // AI
    let providerFactory: AIProviderFactory

    // Cross-cutting observable state
    let privacy: PrivacyGuard
    let biometrics: BiometricAuth
    let entitlements: EntitlementStore
    let usageMeter: UsageMeter
    let store: StoreService
    let analysisProgress: AnalysisProgress
    let liveActivity: LiveActivityController

    // Long-running services
    let analysisPipeline: AnalysisPipeline
    let albumService: AlbumService

    init(database: AppDatabase) {
        self.database = database
        let keychain = KeychainStore()
        self.keychain = keychain
        self.photos = PhotoLibraryService()
        self.vectorIndex = VectorIndex()

        self.assetRepository = AssetRepository(db: database)
        self.albumRepository = AlbumRepository(db: database)
        self.searchRepository = SearchRepository(db: database)
        self.settings = SettingsRepository(keychain: keychain)

        self.providerFactory = AIProviderFactory(keychain: keychain)

        self.privacy = PrivacyGuard()
        self.biometrics = BiometricAuth()
        let entitlements = EntitlementStore()
        self.entitlements = entitlements
        self.usageMeter = UsageMeter(db: database, entitlements: entitlements)
        self.store = StoreService(entitlements: entitlements)
        self.analysisProgress = AnalysisProgress()
        let liveActivity = LiveActivityController()
        self.liveActivity = liveActivity

        self.analysisPipeline = AnalysisPipeline(
            photos: photos, repository: assetRepository, vectorIndex: vectorIndex,
            providerFactory: providerFactory, settings: settings,
            privacy: privacy, progress: analysisProgress, liveActivity: liveActivity)

        self.albumService = AlbumService(
            assetRepository: assetRepository, albumRepository: albumRepository,
            providerFactory: providerFactory, settings: settings, privacy: privacy)
    }

    /// Convenience factory for the search stack used by `SearchViewModel`.
    func makeSearchService() -> SearchService {
        SearchService(repository: assetRepository, searchRepository: searchRepository,
                      vectorIndex: vectorIndex, providerFactory: providerFactory,
                      settings: settings, usage: usageMeter)
    }

    /// Called once on first appear: request Photos access, kick off sync/analysis, load IAP.
    func bootstrap() async {
        let status = await photos.requestAuthorization()
        Log.photos.info("Photos authorization: \(String(describing: status))")
        await store.loadProducts()
        usageMeter.refresh()
        if settings.backgroundAnalysisEnabled {
            await analysisPipeline.syncAndAnalyze()
        }
    }

    /// Live preview / test environment backed by an in-memory database.
    @MainActor
    static func preview() -> AppEnvironment {
        // swiftlint:disable:next force_try
        AppEnvironment(database: try! AppDatabase.makeInMemory())
    }
}
