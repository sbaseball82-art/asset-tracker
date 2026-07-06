import Testing
import Foundation
@testable import PhotoMindAI

struct QueryParserTests {
    // Fixed "now" so relative-date assertions are deterministic: 2026-07-06.
    private var parser: QueryParser {
        var comps = DateComponents()
        comps.year = 2026; comps.month = 7; comps.day = 6
        let cal = Calendar(identifier: .gregorian)
        let now = cal.date(from: comps)!
        return QueryParser(calendar: cal, now: now)
    }

    @Test func extractsCategoryFromJapanese() {
        let q = parser.parse("白い犬")
        #expect(q.categories.contains(.dog))
    }

    @Test func mapsRamenAndSushiToFood() {
        #expect(parser.parse("大阪 ラーメン").categories.contains(.food))
        #expect(parser.parse("寿司").categories.contains(.food))
    }

    @Test func lastYearProducesFullYearRange() {
        let q = parser.parse("去年 大阪 ラーメン")
        let range = try? #require(q.dateRange)
        let cal = Calendar(identifier: .gregorian)
        #expect(cal.component(.year, from: range!.start) == 2025)
    }

    @Test func lastMonthRangeIsJune2026() {
        let q = parser.parse("先月の写真")
        let range = try? #require(q.dateRange)
        let cal = Calendar(identifier: .gregorian)
        #expect(cal.component(.month, from: range!.start) == 6)
    }

    @Test func detectsVideoMediaType() {
        #expect(parser.parse("先月の動画").mediaType == .video)
    }

    @Test func extractsExplicitYear() {
        let q = parser.parse("2025 結婚式")
        let range = try? #require(q.dateRange)
        let cal = Calendar(identifier: .gregorian)
        #expect(cal.component(.year, from: range!.start) == 2025)
    }

    @Test func extractsKnownPlace() {
        #expect(parser.parse("京都 夜景").placeKeyword == "京都")
    }

    @Test func semanticTextSurvivesWhenNoFiltersMatch() {
        let q = parser.parse("なにか楽しいこと")
        #expect(!q.semanticText.isEmpty)
        #expect(q.categories.isEmpty)
    }
}
