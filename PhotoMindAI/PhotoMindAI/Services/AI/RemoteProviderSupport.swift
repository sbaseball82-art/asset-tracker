import Foundation

/// Small shared HTTP helper for the remote AI providers. Keeps timeout/retry/error handling
/// in one place so each provider file stays focused on its request/response shape.
struct AIHTTPClient: Sendable {
    let session: URLSession

    init() {
        let config = URLSessionConfiguration.ephemeral   // no on-disk caching of AI traffic
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 60
        config.waitsForConnectivity = true
        self.session = URLSession(configuration: config)
    }

    func postJSON(_ url: URL, headers: [String: String], body: [String: Any]) async throws -> Data {
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        for (k, v) in headers { request.setValue(v, forHTTPHeaderField: k) }
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw AIError.http(status: -1, body: "no response")
        }
        guard (200..<300).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw AIError.http(status: http.statusCode, body: String(body.prefix(500)))
        }
        return data
    }
}

/// Parses a JSON category list of the shape `[{"category":"food","confidence":0.9}, ...]`
/// that we prompt every vision model to return. Tolerant of unknown categories.
enum CategoryJSONParser {
    static func parse(_ jsonText: String) -> [CategoryTag] {
        // Models sometimes wrap JSON in prose/markdown fences; extract the array.
        guard let start = jsonText.firstIndex(of: "["),
              let end = jsonText.lastIndex(of: "]") else { return [] }
        let slice = String(jsonText[start...end])
        guard let data = slice.data(using: .utf8),
              let arr = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
        else { return [] }

        return arr.compactMap { obj in
            guard let raw = obj["category"] as? String,
                  let category = PhotoCategory(rawValue: raw) else { return nil }
            let conf = (obj["confidence"] as? Double) ?? 0.5
            return CategoryTag(category: category, confidence: conf)
        }
        .filter { $0.confidence >= CategoryTag.acceptanceThreshold }
        .sorted { $0.confidence > $1.confidence }
    }
}

/// The shared instruction we send to every vision model so their output maps cleanly onto
/// `PhotoCategory`. Kept in one place so prompt tweaks apply to all providers at once.
enum AIPrompts {
    static let categoryList = PhotoCategory.allCases
        .filter { $0 != .other && $0 != .pet }
        .map(\.rawValue)
        .joined(separator: ", ")

    static var classify: String {
        """
        Classify this image. Respond with ONLY a JSON array of objects, each \
        {"category": <one of: \(categoryList)>, "confidence": <0..1>}. \
        Include every category that applies. No prose.
        """
    }

    static let caption =
        "Describe this image in one concise sentence for search indexing. " +
        "Mention subjects, food names, places, and any visible text. Reply with the sentence only."

    static func tripSummary(_ c: TripSummaryContext) -> String {
        let cats = c.categoryCounts.sorted { $0.value > $1.value }
            .map { "\($0.key.rawValue):\($0.value)" }.joined(separator: ", ")
        return """
        Write a short Japanese trip summary (max 40 chars, no line breaks) like \
        "京都旅行 2025年4月 写真128枚 食事12件 寺5件". \
        Title: \(c.title). Photos: \(c.totalCount). Place: \(c.placeName ?? "不明"). \
        Category counts: \(cats). Sample captions: \(c.sampleCaptions.prefix(5).joined(separator: " / ")).
        """
    }
}
