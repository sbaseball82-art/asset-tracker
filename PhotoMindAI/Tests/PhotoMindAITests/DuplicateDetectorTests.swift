import Testing
import Foundation
@testable import PhotoMindAI

struct DuplicateDetectorTests {
    private func asset(_ id: String, hash: UInt64, quality: Double,
                       date: Date, screenshot: Bool = false) -> Asset {
        var a = Asset.discovered(localIdentifier: id, mediaType: .photo, creationDate: date,
                                 modificationDate: date, pixelWidth: 100, pixelHeight: 100,
                                 durationSeconds: 0, isFavorite: false, latitude: nil, longitude: nil)
        a.perceptualHash = hash
        a.qualityScore = quality
        a.isScreenshot = screenshot
        return a
    }

    @Test func groupsNearDuplicatesAndKeepsHighestQuality() {
        let base: UInt64 = 0b1010_1010_1010_1010
        let now = Date()
        let assets = [
            asset("a", hash: base,        quality: 0.9, date: now),
            asset("b", hash: base ^ 0b11, quality: 0.4, date: now.addingTimeInterval(1)), // 2 bits diff
            asset("c", hash: base ^ 0b1,  quality: 0.6, date: now.addingTimeInterval(2)), // 1 bit diff
        ]
        let groups = DuplicateDetector().duplicateGroups(assets)
        #expect(groups.count == 1)
        #expect(groups[0].keep.localIdentifier == "a")   // highest quality kept
        #expect(groups[0].discard.count == 2)
    }

    @Test func distinctImagesAreNotGrouped() {
        let now = Date()
        let assets = [
            asset("a", hash: 0x0000_0000_0000_0000, quality: 0.8, date: now),
            asset("b", hash: 0xFFFF_FFFF_FFFF_FFFF, quality: 0.8, date: now.addingTimeInterval(1)),
        ]
        #expect(DuplicateDetector().duplicateGroups(assets).isEmpty)
    }

    @Test func flagsBlurryAndScreenshots() {
        let now = Date()
        let assets = [
            asset("sharp", hash: 1, quality: 0.9, date: now),
            asset("blur",  hash: 2, quality: 0.05, date: now),
            asset("shot",  hash: 3, quality: 0.9, date: now, screenshot: true),
        ]
        let s = DuplicateDetector().suggestions(for: assets)
        #expect(s.blurry.map(\.localIdentifier) == ["blur"])
        #expect(s.screenshots.map(\.localIdentifier) == ["shot"])
    }

    @Test func hammingDistanceIsSymmetric() {
        let a: UInt64 = 0b1100
        let b: UInt64 = 0b1010
        #expect(a.hammingDistance(to: b) == b.hammingDistance(to: a))
        #expect(a.hammingDistance(to: b) == 2)
    }
}
