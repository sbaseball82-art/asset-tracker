import Testing
@testable import PhotoMindAI

struct VectorIndexTests {
    @Test func topKReturnsMostSimilarFirst() async {
        let index = VectorIndex()
        await index.replaceAll([
            AssetEmbedding(assetLocalIdentifier: "same",     model: "m", vector: [1, 0, 0, 0]),
            AssetEmbedding(assetLocalIdentifier: "opposite", model: "m", vector: [-1, 0, 0, 0]),
            AssetEmbedding(assetLocalIdentifier: "orth",     model: "m", vector: [0, 1, 0, 0]),
        ])
        let hits = await index.topK([1, 0, 0, 0], k: 2)
        #expect(hits.first?.id == "same")
        #expect(hits.count == 2)
    }

    @Test func candidateFilterRestrictsResults() async {
        let index = VectorIndex()
        await index.replaceAll([
            AssetEmbedding(assetLocalIdentifier: "a", model: "m", vector: [1, 0]),
            AssetEmbedding(assetLocalIdentifier: "b", model: "m", vector: [0.9, 0.1]),
        ])
        let hits = await index.topK([1, 0], k: 5, candidates: ["b"])
        #expect(hits.map(\.id) == ["b"])
    }

    @Test func upsertAndRemoveMaintainCount() async {
        let index = VectorIndex()
        await index.upsert(AssetEmbedding(assetLocalIdentifier: "a", model: "m", vector: [1, 0]))
        await index.upsert(AssetEmbedding(assetLocalIdentifier: "a", model: "m", vector: [0, 1])) // update
        var count = await index.count
        #expect(count == 1)
        await index.remove("a")
        count = await index.count
        #expect(count == 0)
    }
}
