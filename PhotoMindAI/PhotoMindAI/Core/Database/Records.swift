import Foundation
import GRDB

// MARK: - Asset persistence

/// GRDB record wrapper around `Asset`. We keep the domain model (`Asset`) free of GRDB so
/// it stays trivially `Sendable`/`Codable`; this record handles row<->model translation.
struct AssetRecord: Codable, FetchableRecord, MutablePersistableRecord {
    static let databaseTableName = "asset"

    var id: Int64?
    var localIdentifier: String
    var mediaType: Int
    var creationDate: Date?
    var modificationDate: Date?
    var pixelWidth: Int
    var pixelHeight: Int
    var durationSeconds: Double
    var isFavorite: Bool
    var latitude: Double?
    var longitude: Double?
    var placeName: String?
    var analysisState: Int
    var qualityScore: Double
    var isScreenshot: Bool
    var perceptualHash: Int64
    var ocrText: String?
    var captionSummary: String?

    mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }

    init(_ a: Asset) {
        id = a.id
        localIdentifier = a.localIdentifier
        mediaType = a.mediaType.rawValue
        creationDate = a.creationDate
        modificationDate = a.modificationDate
        pixelWidth = a.pixelWidth
        pixelHeight = a.pixelHeight
        durationSeconds = a.durationSeconds
        isFavorite = a.isFavorite
        latitude = a.latitude
        longitude = a.longitude
        placeName = a.placeName
        analysisState = a.analysisState.rawValue
        qualityScore = a.qualityScore
        isScreenshot = a.isScreenshot
        perceptualHash = Int64(bitPattern: a.perceptualHash)
        ocrText = a.ocrText
        captionSummary = a.captionSummary
    }

    var asModel: Asset {
        Asset(
            id: id,
            localIdentifier: localIdentifier,
            mediaType: Asset.MediaType(rawValue: mediaType) ?? .photo,
            creationDate: creationDate,
            modificationDate: modificationDate,
            pixelWidth: pixelWidth,
            pixelHeight: pixelHeight,
            durationSeconds: durationSeconds,
            isFavorite: isFavorite,
            latitude: latitude,
            longitude: longitude,
            placeName: placeName,
            analysisState: Asset.AnalysisState(rawValue: analysisState) ?? .pending,
            qualityScore: qualityScore,
            isScreenshot: isScreenshot,
            perceptualHash: UInt64(bitPattern: perceptualHash),
            ocrText: ocrText,
            captionSummary: captionSummary
        )
    }
}

// MARK: - Category tag persistence

struct CategoryTagRecord: Codable, FetchableRecord, MutablePersistableRecord {
    static let databaseTableName = "category_tag"
    var id: Int64?
    var assetId: Int64
    var category: String
    var confidence: Double

    mutating func didInsert(_ inserted: InsertionSuccess) { id = inserted.rowID }
}

// MARK: - Embedding persistence

struct EmbeddingRecord: Codable, FetchableRecord, PersistableRecord {
    static let databaseTableName = "embedding"
    var assetLocalIdentifier: String
    var model: String
    var dimension: Int
    var vector: Data          // Float32 little-endian

    init(_ e: AssetEmbedding) {
        assetLocalIdentifier = e.assetLocalIdentifier
        model = e.model
        dimension = e.dimension
        vector = EmbeddingRecord.encode(e.vector)
    }

    var floats: [Float] { EmbeddingRecord.decode(vector, count: dimension) }

    static func encode(_ v: [Float]) -> Data {
        v.withUnsafeBytes { Data($0) }
    }

    static func decode(_ data: Data, count: Int) -> [Float] {
        data.withUnsafeBytes { raw in
            let buf = raw.bindMemory(to: Float.self)
            return Array(buf.prefix(count))
        }
    }
}

// MARK: - Album persistence

struct AlbumRecord: Codable, FetchableRecord, MutablePersistableRecord {
    static let databaseTableName = "album"
    var id: Int64?
    var kind: Int
    var title: String
    var subtitle: String?
    var coverAssetIdentifier: String?
    var startDate: Date?
    var endDate: Date?
    var latitude: Double?
    var longitude: Double?
    var assetCount: Int
    var aiSummary: String?
    var createdAt: Date

    mutating func didInsert(_ inserted: InsertionSuccess) { id = inserted.rowID }

    init(_ a: Album) {
        id = a.id
        kind = a.kind.rawValue
        title = a.title
        subtitle = a.subtitle
        coverAssetIdentifier = a.coverAssetIdentifier
        startDate = a.startDate
        endDate = a.endDate
        latitude = a.latitude
        longitude = a.longitude
        assetCount = a.assetCount
        aiSummary = a.aiSummary
        createdAt = a.createdAt
    }

    var asModel: Album {
        Album(
            id: id,
            kind: Album.Kind(rawValue: kind) ?? .event,
            title: title,
            subtitle: subtitle,
            coverAssetIdentifier: coverAssetIdentifier,
            startDate: startDate,
            endDate: endDate,
            latitude: latitude,
            longitude: longitude,
            assetCount: assetCount,
            aiSummary: aiSummary,
            createdAt: createdAt
        )
    }
}

struct AlbumMembershipRecord: Codable, FetchableRecord, PersistableRecord {
    static let databaseTableName = "album_membership"
    var albumID: Int64
    var assetLocalIdentifier: String
}

struct UsageCounterRecord: Codable, FetchableRecord, PersistableRecord {
    static let databaseTableName = "usage_counter"
    var periodKey: String
    var searchCount: Int
}
