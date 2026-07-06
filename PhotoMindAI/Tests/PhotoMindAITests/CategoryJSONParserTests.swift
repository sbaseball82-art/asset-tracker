import Testing
@testable import PhotoMindAI

struct CategoryJSONParserTests {
    @Test func parsesPlainArray() {
        let json = #"[{"category":"food","confidence":0.92},{"category":"drink","confidence":0.6}]"#
        let tags = CategoryJSONParser.parse(json)
        #expect(tags.count == 2)
        #expect(tags.first?.category == .food)   // sorted by confidence desc
    }

    @Test func extractsArrayFromMarkdownFence() {
        let json = """
        Here you go:
        ```json
        [{"category":"dog","confidence":0.8}]
        ```
        """
        let tags = CategoryJSONParser.parse(json)
        #expect(tags.first?.category == .dog)
    }

    @Test func dropsUnknownCategoriesAndLowConfidence() {
        let json = #"[{"category":"unicorn","confidence":0.9},{"category":"cat","confidence":0.1}]"#
        // unicorn is unknown; cat below acceptance threshold.
        #expect(CategoryJSONParser.parse(json).isEmpty)
    }

    @Test func handlesGarbageGracefully() {
        #expect(CategoryJSONParser.parse("no json here").isEmpty)
    }
}
