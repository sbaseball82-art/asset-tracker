import Foundation
import Vision

/// On-device OCR via Vision. Recognizes Japanese and English text — receipts, business cards,
/// documents, whiteboards. Runs entirely locally; the recognized text is stored on the asset
/// and indexed in FTS5 for keyword search.
struct OCRService: Sendable {
    struct Result: Sendable {
        let lines: [String]
        let averageConfidence: Double
        var joinedText: String { lines.joined(separator: "\n") }
        var isEmpty: Bool { lines.isEmpty }
    }

    func recognize(imageJPEG: Data) async throws -> Result {
        guard let cg = ImageDownscaler.cgImage(from: imageJPEG, maxDimension: 2048) else {
            return Result(lines: [], averageConfidence: 0)
        }
        return try await withCheckedThrowingContinuation { continuation in
            let request = VNRecognizeTextRequest { request, error in
                if let error {
                    continuation.resume(throwing: error); return
                }
                let observations = (request.results as? [VNRecognizedTextObservation]) ?? []
                var lines: [String] = []
                var confSum = 0.0
                for obs in observations {
                    guard let top = obs.topCandidates(1).first else { continue }
                    lines.append(top.string)
                    confSum += Double(top.confidence)
                }
                let avg = observations.isEmpty ? 0 : confSum / Double(observations.count)
                continuation.resume(returning: Result(lines: lines, averageConfidence: avg))
            }
            request.recognitionLevel = .accurate
            request.usesLanguageCorrection = true
            request.recognitionLanguages = ["ja-JP", "en-US"]

            let handler = VNImageRequestHandler(cgImage: cg, options: [:])
            do { try handler.perform([request]) }
            catch { continuation.resume(throwing: error) }
        }
    }
}
