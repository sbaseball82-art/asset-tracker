import Foundation
import CoreLocation

/// A single photo/video/Live Photo/RAW item mirrored from the Apple Photos library.
///
/// PhotoMind never copies the underlying pixel data out of the Photos library — it only
/// stores lightweight metadata plus locally-derived analysis results (categories, OCR text,
/// embeddings). The `localIdentifier` is the stable pointer back into `PHAsset`.
struct Asset: Identifiable, Hashable, Codable, Sendable {
    enum MediaType: Int, Codable, Sendable, CaseIterable {
        case photo = 0
        case video = 1
        case livePhoto = 2
        case raw = 3

        var symbolName: String {
            switch self {
            case .photo: return "photo"
            case .video: return "video"
            case .livePhoto: return "livephoto"
            case .raw: return "camera.aperture"
            }
        }
    }

    /// Progress of the on-device analysis pipeline for this asset.
    enum AnalysisState: Int, Codable, Sendable {
        case pending = 0        // discovered, not yet analyzed
        case classified = 1     // categories + quality computed
        case embedded = 2       // embedding vector generated, searchable
        case failed = 3
    }

    let id: Int64?                 // local DB row id (nil until inserted)
    let localIdentifier: String    // PHAsset.localIdentifier
    var mediaType: MediaType
    var creationDate: Date?
    var modificationDate: Date?
    var pixelWidth: Int
    var pixelHeight: Int
    var durationSeconds: Double     // 0 for stills
    var isFavorite: Bool
    var latitude: Double?
    var longitude: Double?
    var placeName: String?          // reverse-geocoded, cached
    var analysisState: AnalysisState
    var qualityScore: Double        // 0…1 sharpness/exposure heuristic
    var isScreenshot: Bool
    var perceptualHash: UInt64      // 64-bit dHash for near-duplicate detection
    var ocrText: String?            // recognized text, nil if none
    var captionSummary: String?     // one-line AI/local caption

    var location: CLLocationCoordinate2D? {
        guard let latitude, let longitude else { return nil }
        return CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }

    var aspectRatio: Double {
        guard pixelHeight > 0 else { return 1 }
        return Double(pixelWidth) / Double(pixelHeight)
    }
}

extension Asset {
    /// A freshly-discovered asset with defaults, before analysis has run.
    static func discovered(
        localIdentifier: String,
        mediaType: MediaType,
        creationDate: Date?,
        modificationDate: Date?,
        pixelWidth: Int,
        pixelHeight: Int,
        durationSeconds: Double,
        isFavorite: Bool,
        latitude: Double?,
        longitude: Double?
    ) -> Asset {
        Asset(
            id: nil,
            localIdentifier: localIdentifier,
            mediaType: mediaType,
            creationDate: creationDate,
            modificationDate: modificationDate,
            pixelWidth: pixelWidth,
            pixelHeight: pixelHeight,
            durationSeconds: durationSeconds,
            isFavorite: isFavorite,
            latitude: latitude,
            longitude: longitude,
            placeName: nil,
            analysisState: .pending,
            qualityScore: 0,
            isScreenshot: false,
            perceptualHash: 0,
            ocrText: nil,
            captionSummary: nil
        )
    }
}
