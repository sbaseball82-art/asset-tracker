import Foundation

/// Turns a raw natural-language string into a structured `SearchQuery`. It extracts obvious
/// filters — relative dates ("去年", "先月"), categories ("犬", "寿司"), and media hints
/// ("動画") — and leaves the rest as `semanticText` to be embedded. Pure and deterministic so
/// it is fully unit-tested (see `QueryParserTests`).
struct QueryParser: Sendable {
    var calendar: Calendar
    var now: Date

    init(calendar: Calendar = Calendar(identifier: .gregorian), now: Date = Date()) {
        var cal = calendar
        cal.locale = Locale(identifier: "ja_JP")
        self.calendar = cal
        self.now = now
    }

    // Japanese/English keyword → category. Multiple keywords can map to one category.
    private static let categoryKeywords: [String: PhotoCategory] = [
        "犬": .dog, "いぬ": .dog, "dog": .dog,
        "猫": .cat, "ねこ": .cat, "cat": .cat,
        "花": .flower, "flower": .flower,
        "料理": .food, "食事": .food, "ごはん": .food, "ラーメン": .food, "寿司": .food,
        "すし": .food, "food": .food, "ramen": .food, "sushi": .food,
        "飲み物": .drink, "コーヒー": .drink, "ビール": .drink, "drink": .drink,
        "レシート": .receipt, "領収書": .receipt, "receipt": .receipt,
        "書類": .document, "名刺": .document, "document": .document,
        "qr": .qrCode, "qrコード": .qrCode,
        "人": .person, "友達": .person, "家族": .person, "people": .person,
        "建物": .building, "寺": .building, "神社": .building, "building": .building,
        "風景": .landscape, "夜景": .landscape, "景色": .landscape, "landscape": .landscape,
        "車": .car, "car": .car,
        "服": .clothing, "clothes": .clothing,
        "スポーツ": .sport, "運動会": .sport, "試合": .sport, "sport": .sport,
        "旅行": .travel, "travel": .travel, "trip": .travel,
        "スクショ": .screenshot, "スクリーンショット": .screenshot, "screenshot": .screenshot,
    ]

    func parse(_ raw: String) -> SearchQuery {
        var remaining = raw
        var categories: Set<PhotoCategory> = []

        for (keyword, category) in Self.categoryKeywords where remaining.localizedCaseInsensitiveContains(keyword) {
            categories.insert(category)
        }

        let dateRange = extractDateRange(from: raw)
        let mediaType: Asset.MediaType? = raw.contains("動画") || raw.localizedCaseInsensitiveContains("video")
            ? .video : nil

        // Strip the date tokens we understood so they don't pollute the semantic text.
        for token in Self.dateTokens.keys { remaining = remaining.replacingOccurrences(of: token, with: " ") }

        let semanticText = remaining.trimmingCharacters(in: .whitespacesAndNewlines)
        return SearchQuery(raw: raw,
                           semanticText: semanticText.isEmpty ? raw : semanticText,
                           categories: categories,
                           dateRange: dateRange,
                           placeKeyword: extractPlace(from: raw),
                           mediaType: mediaType)
    }

    // MARK: - Dates

    private static let dateTokens: [String: Void] = [
        "去年": (), "昨年": (), "今年": (), "先月": (), "今月": (),
        "先週": (), "今週": (), "昨日": (), "今日": (), "last year": (), "this year": (),
    ]

    private func extractDateRange(from raw: String) -> DateInterval? {
        let lower = raw.lowercased()
        if raw.contains("去年") || raw.contains("昨年") || lower.contains("last year") {
            return yearInterval(offset: -1)
        }
        if raw.contains("今年") || lower.contains("this year") {
            return yearInterval(offset: 0)
        }
        if raw.contains("先月") { return monthInterval(offset: -1) }
        if raw.contains("今月") { return monthInterval(offset: 0) }
        if raw.contains("先週") { return weekInterval(offset: -1) }
        if raw.contains("今週") { return weekInterval(offset: 0) }
        if raw.contains("昨日") { return dayInterval(offset: -1) }
        if raw.contains("今日") { return dayInterval(offset: 0) }

        // Explicit year like "2025" or "2025年".
        if let year = firstYear(in: raw) {
            var comps = DateComponents(); comps.year = year
            if let start = calendar.date(from: comps),
               let end = calendar.date(byAdding: .year, value: 1, to: start) {
                return DateInterval(start: start, end: end)
            }
        }
        return nil
    }

    private func firstYear(in raw: String) -> Int? {
        let scanner = Scanner(string: raw)
        while !scanner.isAtEnd {
            if let value = scanner.scanInt(), (1990...2100).contains(value) { return value }
            _ = scanner.scanCharacter()
        }
        return nil
    }

    private func yearInterval(offset: Int) -> DateInterval? {
        guard let base = calendar.date(byAdding: .year, value: offset, to: now) else { return nil }
        let start = calendar.dateInterval(of: .year, for: base)?.start
        return start.flatMap { s in calendar.date(byAdding: .year, value: 1, to: s).map { DateInterval(start: s, end: $0) } }
    }

    private func monthInterval(offset: Int) -> DateInterval? {
        guard let base = calendar.date(byAdding: .month, value: offset, to: now) else { return nil }
        return calendar.dateInterval(of: .month, for: base)
    }

    private func weekInterval(offset: Int) -> DateInterval? {
        guard let base = calendar.date(byAdding: .weekOfYear, value: offset, to: now) else { return nil }
        return calendar.dateInterval(of: .weekOfYear, for: base)
    }

    private func dayInterval(offset: Int) -> DateInterval? {
        guard let base = calendar.date(byAdding: .day, value: offset, to: now) else { return nil }
        return calendar.dateInterval(of: .day, for: base)
    }

    // MARK: - Place (kept simple: known place keywords fall through to semantic + FTS placeName)

    private static let places = ["大阪", "京都", "東京", "北海道", "沖縄", "名古屋", "福岡", "富士山", "横浜"]
    private func extractPlace(from raw: String) -> String? {
        Self.places.first { raw.contains($0) }
    }
}
