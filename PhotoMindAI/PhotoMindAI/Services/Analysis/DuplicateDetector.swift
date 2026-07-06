import Foundation

/// Groups near-duplicate assets by perceptual-hash Hamming distance and surfaces cleanup
/// candidates (blurry, screenshots, duplicates). Pure logic over already-computed metadata so
/// it is fully unit-testable with no image I/O.
struct DuplicateDetector: Sendable {
    /// Two assets are considered near-duplicates when their dHash differs by ≤ this many bits.
    var duplicateThreshold: Int = 8
    /// Assets with quality below this are flagged as "blurry".
    var blurThreshold: Double = 0.12

    struct DuplicateGroup: Identifiable, Sendable {
        let id = UUID()
        /// The asset we recommend keeping (highest quality in the group).
        let keep: Asset
        /// Lower-quality near-duplicates recommended for deletion.
        let discard: [Asset]
        var reclaimCount: Int { discard.count }
    }

    struct CleanupSuggestions: Sendable {
        var duplicateGroups: [DuplicateGroup]
        var blurry: [Asset]
        var screenshots: [Asset]

        var totalReclaimable: Int {
            duplicateGroups.reduce(0) { $0 + $1.reclaimCount } + blurry.count + screenshots.count
        }
    }

    func suggestions(for assets: [Asset]) -> CleanupSuggestions {
        CleanupSuggestions(
            duplicateGroups: duplicateGroups(assets),
            blurry: assets.filter { !$0.isScreenshot && $0.qualityScore < blurThreshold && $0.perceptualHash != 0 },
            screenshots: assets.filter { $0.isScreenshot }
        )
    }

    /// Clusters via a simple union over hash proximity within a time-sorted window. Comparing
    /// only within a sliding window keeps this near-linear for large libraries.
    func duplicateGroups(_ assets: [Asset], window: Int = 30) -> [DuplicateGroup] {
        let candidates = assets.filter { $0.perceptualHash != 0 }
            .sorted { ($0.creationDate ?? .distantPast) < ($1.creationDate ?? .distantPast) }
        guard candidates.count > 1 else { return [] }

        var parent = Array(0..<candidates.count)
        func find(_ x: Int) -> Int {
            var r = x
            while parent[r] != r { parent[r] = parent[parent[r]]; r = parent[r] }
            return r
        }
        func union(_ a: Int, _ b: Int) { parent[find(a)] = find(b) }

        for i in 0..<candidates.count {
            let upper = min(candidates.count, i + 1 + window)
            for j in (i + 1)..<upper {
                if candidates[i].perceptualHash.hammingDistance(to: candidates[j].perceptualHash) <= duplicateThreshold {
                    union(i, j)
                }
            }
        }

        var clusters: [Int: [Asset]] = [:]
        for i in 0..<candidates.count { clusters[find(i), default: []].append(candidates[i]) }

        return clusters.values
            .filter { $0.count > 1 }
            .map { group in
                let sorted = group.sorted { $0.qualityScore > $1.qualityScore }
                return DuplicateGroup(keep: sorted[0], discard: Array(sorted.dropFirst()))
            }
            .sorted { $0.reclaimCount > $1.reclaimCount }
    }
}
