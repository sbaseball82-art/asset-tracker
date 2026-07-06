import Foundation

/// A dense semantic embedding for an asset, used for natural-language search.
///
/// Vectors are L2-normalized at write time so that cosine similarity reduces to a plain
/// dot product. Stored as raw `Float32` little-endian bytes in SQLite (see `AppDatabase`).
struct AssetEmbedding: Hashable, Sendable {
    let assetLocalIdentifier: String
    let model: String            // e.g. "text-embedding-3-small" or "NLEmbedding.ja"
    let dimension: Int
    let vector: [Float]          // normalized

    init(assetLocalIdentifier: String, model: String, vector: [Float]) {
        self.assetLocalIdentifier = assetLocalIdentifier
        self.model = model
        self.dimension = vector.count
        self.vector = VectorMath.normalized(vector)
    }
}

enum VectorMath {
    /// L2-normalize; returns the input unchanged if it is the zero vector.
    static func normalized(_ v: [Float]) -> [Float] {
        var sum: Float = 0
        for x in v { sum += x * x }
        let norm = sum.squareRoot()
        guard norm > 1e-8 else { return v }
        return v.map { $0 / norm }
    }

    /// Cosine similarity of two already-normalized vectors == dot product.
    /// Falls back to a safe value when dimensions differ.
    static func cosine(_ a: [Float], _ b: [Float]) -> Float {
        guard a.count == b.count, !a.isEmpty else { return -1 }
        var dot: Float = 0
        var i = 0
        // Unrolled by 4 for throughput on 100k-scale scans.
        let n = a.count
        while i + 4 <= n {
            dot += a[i]     * b[i]
            dot += a[i + 1] * b[i + 1]
            dot += a[i + 2] * b[i + 2]
            dot += a[i + 3] * b[i + 3]
            i += 4
        }
        while i < n { dot += a[i] * b[i]; i += 1 }
        return dot
    }
}
