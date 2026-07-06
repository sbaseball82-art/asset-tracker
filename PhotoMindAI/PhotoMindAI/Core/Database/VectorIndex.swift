import Foundation

/// A warm, in-memory brute-force vector index. For libraries up to ~100k assets a linear
/// scan of normalized Float32 vectors is well under a frame at 512-d thanks to the unrolled
/// dot product in `VectorMath`. When a library grows past that, swap this for an IVF/HNSW
/// index behind the same interface — callers only depend on `topK`.
///
/// The index is an actor so it can be safely populated on a background task while search
/// queries read from it.
actor VectorIndex {
    private struct Entry {
        let id: String
        let vector: [Float]
    }

    private var entries: [Entry] = []
    private var idToPosition: [String: Int] = [:]

    var count: Int { entries.count }

    func replaceAll(_ embeddings: [AssetEmbedding]) {
        entries = embeddings.map { Entry(id: $0.assetLocalIdentifier, vector: $0.vector) }
        idToPosition = Dictionary(
            uniqueKeysWithValues: entries.enumerated().map { ($1.id, $0) }
        )
        Log.search.info("VectorIndex loaded \(self.entries.count) vectors")
    }

    func upsert(_ embedding: AssetEmbedding) {
        let entry = Entry(id: embedding.assetLocalIdentifier, vector: embedding.vector)
        if let pos = idToPosition[embedding.assetLocalIdentifier] {
            entries[pos] = entry
        } else {
            idToPosition[embedding.assetLocalIdentifier] = entries.count
            entries.append(entry)
        }
    }

    func remove(_ id: String) {
        guard let pos = idToPosition[id] else { return }
        // Swap-remove to keep it O(1); fix up the moved element's index.
        let last = entries.count - 1
        if pos != last {
            entries[pos] = entries[last]
            idToPosition[entries[pos].id] = pos
        }
        entries.removeLast()
        idToPosition[id] = nil
    }

    /// Returns up to `k` (id, score) pairs sorted by descending cosine similarity, optionally
    /// restricted to `candidates` (e.g. a set that already passed date/category filters).
    func topK(_ query: [Float], k: Int, candidates: Set<String>? = nil) -> [(id: String, score: Float)] {
        let q = VectorMath.normalized(query)
        var heap: [(String, Float)] = []
        heap.reserveCapacity(k + 1)

        for entry in entries {
            if let candidates, !candidates.contains(entry.id) { continue }
            let score = VectorMath.cosine(q, entry.vector)
            if heap.count < k {
                heap.append((entry.id, score))
                if heap.count == k { heap.sort { $0.1 > $1.1 } }
            } else if score > heap[k - 1].1 {
                // Insert into the sorted top-k.
                var i = k - 1
                heap[i] = (entry.id, score)
                while i > 0 && heap[i].1 > heap[i - 1].1 {
                    heap.swapAt(i, i - 1); i -= 1
                }
            }
        }
        if heap.count < k { heap.sort { $0.1 > $1.1 } }
        return heap.map { (id: $0.0, score: $0.1) }
    }
}
