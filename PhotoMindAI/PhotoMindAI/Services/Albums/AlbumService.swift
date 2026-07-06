import Foundation

/// Regenerates smart albums from the current analyzed library and (optionally) enriches each
/// trip album with an AI summary via the active provider. Runs off the main actor.
actor AlbumService {
    private let assetRepository: AssetRepository
    private let albumRepository: AlbumRepository
    private let providerFactory: AIProviderFactory
    private let settings: SettingsRepository
    private let privacy: PrivacyGuard
    private let builder = AlbumBuilder()

    init(assetRepository: AssetRepository,
         albumRepository: AlbumRepository,
         providerFactory: AIProviderFactory,
         settings: SettingsRepository,
         privacy: PrivacyGuard) {
        self.assetRepository = assetRepository
        self.albumRepository = albumRepository
        self.providerFactory = providerFactory
        self.settings = settings
        self.privacy = privacy
    }

    func regenerate() async {
        guard let assets = try? assetRepository.allAssets() else { return }

        // Build a category lookup once.
        var lookup: [String: [PhotoCategory]] = [:]
        for asset in assets {
            guard let id = asset.id else { continue }
            let tags = (try? assetRepository.categories(forAssetID: id)) ?? []
            lookup[asset.localIdentifier] = tags.map(\.category)
        }

        let generated = builder.build(from: assets, categoryLookup: lookup)
        let payload = generated.map { (album: $0.album, memberIdentifiers: $0.memberIdentifiers) }
        try? albumRepository.replaceAll(payload)

        await summarizeTrips(generated, categoryLookup: lookup, assets: assets)
    }

    /// Generate the "京都旅行 2025年4月 写真128枚 …" summaries. Uses the local provider by
    /// default (deterministic, offline); a remote provider is used only when configured and
    /// permitted by PrivacyGuard (text-only, no images leave the device here).
    private func summarizeTrips(_ generated: [AlbumBuilder.GeneratedAlbum],
                                categoryLookup: [String: [PhotoCategory]],
                                assets: [Asset]) async {
        let assetsByID = Dictionary(uniqueKeysWithValues: assets.map { ($0.localIdentifier, $0) })
        let allAlbums = (try? albumRepository.allAlbums()) ?? []

        for gen in generated where gen.album.kind == .trip {
            let members = gen.memberIdentifiers.compactMap { assetsByID[$0] }
            let counts = builder.categoryCounts(members, categoryLookup: categoryLookup)
            let captions = members.compactMap(\.captionSummary).prefix(5)
            let context = TripSummaryContext(
                title: gen.album.title,
                startDate: gen.album.startDate,
                endDate: gen.album.endDate,
                placeName: gen.album.subtitle,
                totalCount: gen.album.assetCount,
                categoryCounts: counts,
                sampleCaptions: Array(captions)
            )

            let kind = await MainActor.run { settings.provider }
            var provider: any AIProvider = LocalAIProvider()
            if kind.requiresAPIKey, providerFactory.isConfigured(kind) {
                let remote = providerFactory.make(kind)
                if await privacy.authorizeUpload(provider: remote) { provider = remote }
            }
            guard let summary = try? await provider.summarizeTrip(context) else { continue }

            // Match this generated album back to its stored row to persist the summary.
            if let stored = allAlbums.first(where: {
                $0.title == gen.album.title && $0.startDate == gen.album.startDate
            }), let id = stored.id {
                try? albumRepository.updateSummary(albumID: id, summary: summary)
            }
        }
    }
}
