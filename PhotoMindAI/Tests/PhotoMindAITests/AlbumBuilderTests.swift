import Testing
import Foundation
@testable import PhotoMindAI

struct AlbumBuilderTests {
    private func asset(_ id: String, daysFromNow: Double, hoursOffset: Double = 0,
                       place: String? = nil) -> Asset {
        let date = Date().addingTimeInterval(daysFromNow * 86_400 + hoursOffset * 3600)
        var a = Asset.discovered(localIdentifier: id, mediaType: .photo, creationDate: date,
                                 modificationDate: date, pixelWidth: 100, pixelHeight: 100,
                                 durationSeconds: 0, isFavorite: false, latitude: place != nil ? 35 : nil,
                                 longitude: place != nil ? 135 : nil)
        a.placeName = place
        a.qualityScore = 0.5
        return a
    }

    @Test func clustersAContiguousTrip() {
        // 8 photos across ~2 days, then a big gap, then 8 more: two trips.
        var assets: [Asset] = []
        for i in 0..<8 { assets.append(asset("t1-\(i)", daysFromNow: -30, hoursOffset: Double(i) * 3)) }
        for i in 0..<8 { assets.append(asset("t2-\(i)", daysFromNow: -10, hoursOffset: Double(i) * 3)) }

        let trips = AlbumBuilder().tripAlbums(from: assets, categoryLookup: [:])
        #expect(trips.count == 2)
        #expect(trips.allSatisfy { $0.album.kind == .trip })
    }

    @Test func ignoresTinyClusters() {
        // Only 3 photos — below minTripSize.
        let assets = (0..<3).map { asset("x-\($0)", daysFromNow: -5, hoursOffset: Double($0)) }
        #expect(AlbumBuilder().tripAlbums(from: assets, categoryLookup: [:]).isEmpty)
    }

    @Test func namesTripFromPlace() {
        let assets = (0..<8).map { asset("k-\($0)", daysFromNow: -20, hoursOffset: Double($0) * 2, place: "京都") }
        let trips = AlbumBuilder().tripAlbums(from: assets, categoryLookup: [:])
        #expect(trips.first?.album.title == "京都旅行")
    }

    @Test func buildsCategoryAlbumWhenEnoughMembers() {
        let assets = (0..<12).map { asset("f-\($0)", daysFromNow: Double(-$0)) }
        let lookup = Dictionary(uniqueKeysWithValues: assets.map { ($0.localIdentifier, [PhotoCategory.food]) })
        let generated = AlbumBuilder().build(from: assets, categoryLookup: lookup)
        #expect(generated.contains { $0.album.kind == .food })
    }

    @Test func categoryCountsAggregate() {
        let assets = [asset("a", daysFromNow: -1), asset("b", daysFromNow: -1)]
        let lookup = ["a": [PhotoCategory.food, .drink], "b": [PhotoCategory.food]]
        let counts = AlbumBuilder().categoryCounts(assets, categoryLookup: lookup)
        #expect(counts[.food] == 2)
        #expect(counts[.drink] == 1)
    }
}
