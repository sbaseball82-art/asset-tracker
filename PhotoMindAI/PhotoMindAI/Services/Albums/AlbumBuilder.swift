import Foundation
import CoreLocation

/// Generates smart albums from analyzed assets. The core is trip detection: assets are
/// clustered into trips by temporal gaps (and, when available, spatial jumps), then each
/// cluster is classified into an `Album.Kind` from its dominant categories. Category albums
/// (food/pet/receipt/family) are generated in parallel from the taxonomy.
///
/// Pure over `Asset` + category lookups, so trip clustering is unit-tested without any I/O.
struct AlbumBuilder: Sendable {
    /// A time gap larger than this starts a new trip cluster.
    var tripGap: TimeInterval = 60 * 60 * 18   // 18 hours
    /// Minimum assets for a cluster to become a trip album.
    var minTripSize = 6

    struct GeneratedAlbum: Sendable {
        let album: Album
        let memberIdentifiers: [String]
    }

    /// `categoryLookup` maps an asset id to its category tags (from the repository).
    func build(from assets: [Asset],
               categoryLookup: [String: [PhotoCategory]]) -> [GeneratedAlbum] {
        var result: [GeneratedAlbum] = []
        result.append(contentsOf: tripAlbums(from: assets, categoryLookup: categoryLookup))
        result.append(contentsOf: categoryAlbums(from: assets, categoryLookup: categoryLookup))
        return result
    }

    // MARK: - Trips

    func tripAlbums(from assets: [Asset],
                    categoryLookup: [String: [PhotoCategory]]) -> [GeneratedAlbum] {
        let dated = assets
            .filter { $0.creationDate != nil }
            .sorted { $0.creationDate! < $1.creationDate! }
        guard !dated.isEmpty else { return [] }

        var clusters: [[Asset]] = []
        var current: [Asset] = [dated[0]]
        for asset in dated.dropFirst() {
            let prev = current.last!.creationDate!
            let gap = asset.creationDate!.timeIntervalSince(prev)
            if gap > tripGap {
                clusters.append(current); current = [asset]
            } else {
                current.append(asset)
            }
        }
        clusters.append(current)

        return clusters
            .filter { $0.count >= minTripSize && spansMultipleDays($0) }
            .map { cluster in makeTripAlbum(cluster, categoryLookup: categoryLookup) }
    }

    private func spansMultipleDays(_ cluster: [Asset]) -> Bool {
        guard let first = cluster.first?.creationDate, let last = cluster.last?.creationDate else { return false }
        return last.timeIntervalSince(first) >= 60 * 60 * 6   // at least ~half a day of activity
    }

    private func makeTripAlbum(_ cluster: [Asset],
                               categoryLookup: [String: [PhotoCategory]]) -> GeneratedAlbum {
        let start = cluster.first?.creationDate
        let end = cluster.last?.creationDate
        let place = cluster.compactMap(\.placeName).first
        let counts = categoryCounts(cluster, categoryLookup: categoryLookup)

        let title: String
        if let place { title = "\(place)旅行" }
        else { title = "旅行" }

        // Cover = highest-quality photo in the cluster.
        let cover = cluster.max { $0.qualityScore < $1.qualityScore }?.localIdentifier

        let album = Album(
            id: nil,
            kind: .trip,
            title: title,
            subtitle: dateRangeSubtitle(start: start, end: end),
            coverAssetIdentifier: cover,
            startDate: start,
            endDate: end,
            latitude: cluster.compactMap(\.latitude).first,
            longitude: cluster.compactMap(\.longitude).first,
            assetCount: cluster.count,
            aiSummary: nil,       // filled in later by AIProvider.summarizeTrip
            createdAt: Date()
        )
        _ = counts // retained for summary context building by the caller
        return GeneratedAlbum(album: album, memberIdentifiers: cluster.map(\.localIdentifier))
    }

    // MARK: - Category albums

    private func categoryAlbums(from assets: [Asset],
                                categoryLookup: [String: [PhotoCategory]]) -> [GeneratedAlbum] {
        let mapping: [(kind: Album.Kind, categories: Set<PhotoCategory>)] = [
            (.food, [.food, .drink]),
            (.pet, [.dog, .cat, .pet]),
            (.receipt, [.receipt, .document]),
            (.family, [.person]),
        ]
        return mapping.compactMap { entry in
            let members = assets.filter { asset in
                let cats = Set(categoryLookup[asset.localIdentifier] ?? [])
                return !cats.isDisjoint(with: entry.categories)
            }
            guard members.count >= 10 else { return nil }
            let cover = members.max { $0.qualityScore < $1.qualityScore }?.localIdentifier
            let album = Album(
                id: nil, kind: entry.kind, title: entry.kind.title, subtitle: "\(members.count)枚",
                coverAssetIdentifier: cover, startDate: members.compactMap(\.creationDate).min(),
                endDate: members.compactMap(\.creationDate).max(), latitude: nil, longitude: nil,
                assetCount: members.count, aiSummary: nil, createdAt: Date()
            )
            return GeneratedAlbum(album: album, memberIdentifiers: members.map(\.localIdentifier))
        }
    }

    // MARK: - Helpers

    func categoryCounts(_ cluster: [Asset],
                        categoryLookup: [String: [PhotoCategory]]) -> [PhotoCategory: Int] {
        var counts: [PhotoCategory: Int] = [:]
        for asset in cluster {
            for category in categoryLookup[asset.localIdentifier] ?? [] {
                counts[category, default: 0] += 1
            }
        }
        return counts
    }

    private func dateRangeSubtitle(start: Date?, end: Date?) -> String? {
        guard let start else { return nil }
        let f = DateFormatter()
        f.locale = Locale(identifier: "ja_JP")
        f.dateFormat = "yyyy年M月d日"
        if let end, !Calendar.current.isDate(start, inSameDayAs: end) {
            let f2 = DateFormatter(); f2.locale = f.locale; f2.dateFormat = "M月d日"
            return "\(f.string(from: start)) 〜 \(f2.string(from: end))"
        }
        return f.string(from: start)
    }
}
