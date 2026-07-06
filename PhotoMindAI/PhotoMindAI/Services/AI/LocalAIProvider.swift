import Foundation
import Vision
import NaturalLanguage
import CoreImage

/// Fully on-device provider. Uses Vision for classification/captioning heuristics and
/// `NLEmbedding` for text vectors. This is the privacy-preserving default and the fallback
/// whenever a remote provider is unavailable or the user has not consented to sending data.
struct LocalAIProvider: AIProvider {
    let id: AIProviderKind = .local
    let displayName = "オンデバイス"
    let isLocal = true

    private let labelMapper = VisionLabelMapper()

    func classify(imageJPEG: Data) async throws -> [CategoryTag] {
        guard let image = CIImage(data: imageJPEG) else { return [] }
        let request = VNClassifyImageRequest()
        let handler = VNImageRequestHandler(ciImage: image, options: [:])
        try handler.perform([request])
        let observations = (request.results ?? [])
            .filter { $0.hasMinimumRecall(0.6, forPrecision: 0.5) }
        return labelMapper.map(observations)
    }

    func caption(imageJPEG: Data) async throws -> String {
        // Compose a lightweight caption from top categories + any OCR text. Good enough to
        // embed; remote providers produce richer captions when enabled.
        let tags = try await classify(imageJPEG: imageJPEG)
        let ocr = (try? await OCRService().recognize(imageJPEG: imageJPEG))?.joinedText ?? ""
        let labels = tags.prefix(3).map { $0.category.rawValue }.joined(separator: ", ")
        let trimmedOCR = ocr.prefix(120)
        return [labels, String(trimmedOCR)].filter { !$0.isEmpty }.joined(separator: " | ")
    }

    func embed(text: String) async throws -> AssetEmbedding {
        try EmbeddingService.localEmbed(text: text, assetLocalIdentifier: "")
    }

    func summarizeTrip(_ context: TripSummaryContext) async throws -> String {
        // Deterministic, template-based summary. Matches the spec example format:
        // "京都旅行 2025年4月 写真128枚 食事12件 寺5件"
        var parts: [String] = [context.title]
        if let start = context.startDate {
            let f = DateFormatter()
            f.locale = Locale(identifier: "ja_JP")
            f.dateFormat = "yyyy年M月"
            parts.append(f.string(from: start))
        }
        parts.append("写真\(context.totalCount)枚")
        let ranked = context.categoryCounts
            .sorted { $0.value > $1.value }
            .prefix(3)
            .filter { $0.value > 0 }
        for (cat, count) in ranked {
            parts.append("\(localizedCategory(cat))\(count)件")
        }
        return parts.joined(separator: " ")
    }

    private func localizedCategory(_ c: PhotoCategory) -> String {
        switch c {
        case .food: return "食事"
        case .building: return "建物"
        case .landscape: return "風景"
        case .person: return "人物"
        case .travel: return "観光"
        default: return c.rawValue
        }
    }
}

/// Maps Vision's raw ImageNet-style labels onto the PhotoMind taxonomy.
struct VisionLabelMapper: Sendable {
    // Substring → category. Ordered by specificity; first match wins per observation.
    private static let rules: [(needle: String, category: PhotoCategory)] = [
        ("receipt", .receipt), ("invoice", .receipt),
        ("qr", .qrCode),
        ("document", .document), ("paper", .document), ("text", .document),
        ("dog", .dog), ("puppy", .dog),
        ("cat", .cat), ("kitten", .cat),
        ("flower", .flower), ("blossom", .flower), ("petal", .flower),
        ("food", .food), ("meal", .food), ("dish", .food), ("ramen", .food),
        ("noodle", .food), ("sushi", .food), ("pizza", .food), ("cuisine", .food),
        ("drink", .drink), ("beverage", .drink), ("coffee", .drink), ("cocktail", .drink),
        ("car", .car), ("vehicle", .car), ("automobile", .car),
        ("building", .building), ("architecture", .building), ("temple", .building),
        ("mountain", .landscape), ("beach", .landscape), ("sky", .landscape),
        ("landscape", .landscape), ("sunset", .landscape), ("nature", .landscape),
        ("person", .person), ("people", .person), ("face", .person), ("portrait", .person),
        ("shirt", .clothing), ("clothing", .clothing), ("dress", .clothing),
        ("sport", .sport), ("ball", .sport), ("stadium", .sport),
        ("airplane", .travel), ("train", .travel), ("luggage", .travel),
    ]

    func map(_ observations: [VNClassificationObservation]) -> [CategoryTag] {
        var best: [PhotoCategory: Double] = [:]
        for obs in observations {
            let id = obs.identifier.lowercased()
            for rule in Self.rules where id.contains(rule.needle) {
                best[rule.category] = max(best[rule.category] ?? 0, Double(obs.confidence))
                break
            }
        }
        return best
            .map { CategoryTag(category: $0.key, confidence: $0.value) }
            .filter { $0.confidence >= CategoryTag.acceptanceThreshold }
            .sorted { $0.confidence > $1.confidence }
    }
}
