import Foundation

/// Orchestrates the on-device (+ optional remote) analysis of pending assets:
///
///   fetch image → local classify + OCR + quality/hash → (optional) remote caption/classify
///   → embed caption+OCR → persist (categories + embedding) → update warm VectorIndex.
///
/// Runs in bounded batches so a 100k-photo first import stays responsive and can be paused /
/// resumed. Everything heavy happens off the main actor; only progress updates hop to main.
actor AnalysisPipeline {
    private let photos: PhotoLibraryService
    private let repository: AssetRepository
    private let vectorIndex: VectorIndex
    private let providerFactory: AIProviderFactory
    private let settings: SettingsRepository
    private let privacy: PrivacyGuard
    private let progress: AnalysisProgress
    private let liveActivity: LiveActivityController

    private let localProvider = LocalAIProvider()
    private let ocr = OCRService()
    private let quality = ImageQualityAnalyzer()

    private var runningTask: Task<Void, Never>?

    init(photos: PhotoLibraryService,
         repository: AssetRepository,
         vectorIndex: VectorIndex,
         providerFactory: AIProviderFactory,
         settings: SettingsRepository,
         privacy: PrivacyGuard,
         progress: AnalysisProgress,
         liveActivity: LiveActivityController) {
        self.photos = photos
        self.repository = repository
        self.vectorIndex = vectorIndex
        self.providerFactory = providerFactory
        self.settings = settings
        self.privacy = privacy
        self.progress = progress
        self.liveActivity = liveActivity
    }

    /// Discover new assets from Photos and start analyzing anything pending.
    func syncAndAnalyze(batchSize: Int = 50) {
        guard runningTask == nil else { return }
        runningTask = Task { [weak self] in
            await self?.runLoop(batchSize: batchSize)
            await self?.clearTask()
        }
    }

    func pause() {
        runningTask?.cancel()
        runningTask = nil
    }

    private func clearTask() { runningTask = nil }

    private func runLoop(batchSize: Int) async {
        // 1. Mirror the library and prune deletions.
        let discovered = await photos.fetchAllAssets()
        try? repository.syncDiscovered(discovered)
        let live = Set(discovered.map(\.localIdentifier))
        if let pruned = try? repository.pruneMissing(keeping: live) {
            for id in pruned { await vectorIndex.remove(id) }
        }

        // 2. Warm the vector index from whatever is already embedded.
        if let embeddings = try? repository.allEmbeddings() {
            await vectorIndex.replaceAll(embeddings)
        }

        // 3. Drain the pending queue in batches.
        let pendingTotal = (try? repository.pendingCount()) ?? 0
        await progress.begin(total: pendingTotal)
        await liveActivity.start(total: pendingTotal)
        defer {
            Task { @MainActor in progress.finish() }
            Task { await liveActivity.end() }
        }

        while !Task.isCancelled {
            let batch = (try? repository.pendingAssets(limit: batchSize)) ?? []
            if batch.isEmpty { break }
            for asset in batch {
                if Task.isCancelled { return }
                await analyze(asset)
                let stage = asset.mediaType == .video ? "動画を解析中" : "写真を解析中"
                await progress.advance(stage: stage)
                // Throttle Live Activity updates to every 5 items to respect the system budget.
                let processed = await progress.processed
                if processed % 5 == 0 {
                    await liveActivity.update(processed: processed, total: pendingTotal, stage: stage)
                }
            }
        }
    }

    /// Analyze a single asset end-to-end and persist the result.
    private func analyze(_ asset: Asset) async {
        guard let data = await photos.imageData(for: asset.localIdentifier) else {
            await markFailed(asset); return
        }

        var updated = asset

        // Local, always-on signals.
        let metrics = quality.analyze(imageJPEG: data)
        updated.perceptualHash = metrics.perceptualHash
        updated.qualityScore = metrics.qualityScore

        let ocrResult = (try? await ocr.recognize(imageJPEG: data)) ?? .init(lines: [], averageConfidence: 0)
        updated.ocrText = ocrResult.isEmpty ? nil : ocrResult.joinedText

        var categories = (try? await localProvider.classify(imageJPEG: data)) ?? []
        var caption = (try? await localProvider.caption(imageJPEG: data)) ?? ""

        // Optional richer remote pass, gated by PrivacyGuard.
        let providerKind = await settings.provider
        if providerKind.requiresAPIKey, providerFactory.isConfigured(providerKind) {
            let provider = providerFactory.make(providerKind)
            let allowed = await privacy.authorizeUpload(provider: provider)
            if allowed, let jpeg = PrivacyGuard.downscaledJPEG(from: data) {
                if let remoteTags = try? await provider.classify(imageJPEG: jpeg), !remoteTags.isEmpty {
                    categories = mergeCategories(local: categories, remote: remoteTags)
                }
                if let remoteCaption = try? await provider.caption(imageJPEG: jpeg), !remoteCaption.isEmpty {
                    caption = remoteCaption
                }
            }
        }
        updated.captionSummary = caption.isEmpty ? nil : caption

        // Embed the searchable text (caption + OCR) with the configured provider (or local).
        let embeddingProvider = providerFactory.make(providerKind)
        let embeddingService = EmbeddingService(provider: embeddingProvider)
        let searchText = [caption, updated.ocrText ?? ""].filter { !$0.isEmpty }.joined(separator: " ")
        var embedding: AssetEmbedding?
        if !searchText.isEmpty {
            embedding = try? await embeddingService.embed(text: searchText,
                                                          assetLocalIdentifier: asset.localIdentifier)
        }

        updated.analysisState = embedding != nil ? .embedded : .classified

        try? repository.saveAnalysis(updated, categories: categories, embedding: embedding)
        if let embedding { await vectorIndex.upsert(embedding) }
    }

    private func markFailed(_ asset: Asset) async {
        var failed = asset
        failed.analysisState = .failed
        try? repository.saveAnalysis(failed, categories: [], embedding: nil)
    }

    /// Union local + remote categories, keeping the higher confidence per category.
    private func mergeCategories(local: [CategoryTag], remote: [CategoryTag]) -> [CategoryTag] {
        var best: [PhotoCategory: Double] = [:]
        for tag in local + remote {
            best[tag.category] = max(best[tag.category] ?? 0, tag.confidence)
        }
        return best.map { CategoryTag(category: $0.key, confidence: $0.value) }
            .sorted { $0.confidence > $1.confidence }
    }
}
