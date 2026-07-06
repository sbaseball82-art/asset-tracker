import Testing
import Foundation
@testable import PhotoMindAI

/// Round-trips through the real (in-memory) GRDB schema to exercise migrations, records, and
/// the embedding BLOB encoding.
struct PersistenceTests {
    private func makeRepo() throws -> AssetRepository {
        AssetRepository(db: try AppDatabase.makeInMemory())
    }

    private func sample(_ id: String) -> Asset {
        Asset.discovered(localIdentifier: id, mediaType: .photo, creationDate: Date(),
                         modificationDate: Date(), pixelWidth: 4032, pixelHeight: 3024,
                         durationSeconds: 0, isFavorite: false, latitude: 34.7, longitude: 135.5)
    }

    @Test func discoveredAssetsAreInsertedOnce() throws {
        let repo = try makeRepo()
        try repo.syncDiscovered([sample("a"), sample("b")])
        try repo.syncDiscovered([sample("a")])   // dedup
        #expect(try repo.totalCount() == 2)
        #expect(try repo.pendingCount() == 2)
    }

    @Test func savesAnalysisWithCategoriesAndEmbedding() throws {
        let repo = try makeRepo()
        try repo.syncDiscovered([sample("a")])
        var asset = try #require(try repo.asset(localIdentifier: "a"))
        asset.analysisState = .embedded
        asset.captionSummary = "ramen in osaka"

        let tags = [CategoryTag(category: .food, confidence: 0.9)]
        let embedding = AssetEmbedding(assetLocalIdentifier: "a", model: "test", vector: [0.1, 0.2, 0.3])
        try repo.saveAnalysis(asset, categories: tags, embedding: embedding)

        let reloaded = try #require(try repo.asset(localIdentifier: "a"))
        #expect(reloaded.captionSummary == "ramen in osaka")
        #expect(try repo.assetIDs(inCategory: .food).contains("a"))

        let embeddings = try repo.allEmbeddings()
        #expect(embeddings.count == 1)
        #expect(embeddings[0].dimension == 3)
    }

    @Test func embeddingBlobRoundTrips() {
        let vector: [Float] = [0.5, -0.25, 0.125, 1.0]
        let record = EmbeddingRecord(AssetEmbedding(assetLocalIdentifier: "x", model: "m", vector: vector))
        let decoded = record.floats
        // Values are normalized on construction; compare direction via cosine ≈ 1.
        #expect(abs(VectorMath.cosine(VectorMath.normalized(vector), decoded) - 1) < 1e-5)
    }

    @Test func pruneRemovesMissingAssets() throws {
        let repo = try makeRepo()
        try repo.syncDiscovered([sample("a"), sample("b"), sample("c")])
        let pruned = try repo.pruneMissing(keeping: ["a", "c"])
        #expect(pruned == ["b"])
        #expect(try repo.totalCount() == 2)
    }
}
