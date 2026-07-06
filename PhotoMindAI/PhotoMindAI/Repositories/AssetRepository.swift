import Foundation
import GRDB

/// Repository over the `asset`, `category_tag` and `embedding` tables. All feature code and
/// services go through repositories rather than touching GRDB directly — this is the seam we
/// mock in tests and the boundary where CloudKit sync hooks in (see docs/Database.md).
struct AssetRepository: Sendable {
    let db: AppDatabase

    // MARK: - Reads

    func allAssets() throws -> [Asset] {
        try db.writer.read { database in
            try AssetRecord
                .order(Column("creationDate").desc)
                .fetchAll(database)
                .map(\.asModel)
        }
    }

    func pendingAssets(limit: Int) throws -> [Asset] {
        try db.writer.read { database in
            try AssetRecord
                .filter(Column("analysisState") == Asset.AnalysisState.pending.rawValue)
                .limit(limit)
                .fetchAll(database)
                .map(\.asModel)
        }
    }

    func asset(localIdentifier: String) throws -> Asset? {
        try db.writer.read { database in
            try AssetRecord
                .filter(Column("localIdentifier") == localIdentifier)
                .fetchOne(database)?
                .asModel
        }
    }

    func categories(forAssetID id: Int64) throws -> [CategoryTag] {
        try db.writer.read { database in
            try CategoryTagRecord
                .filter(Column("assetId") == id)
                .fetchAll(database)
                .compactMap { rec in
                    PhotoCategory(rawValue: rec.category).map {
                        CategoryTag(category: $0, confidence: rec.confidence)
                    }
                }
        }
    }

    func assetIDs(inCategory category: PhotoCategory) throws -> Set<String> {
        try db.writer.read { database in
            let sql = """
                SELECT a.localIdentifier FROM asset a
                JOIN category_tag c ON c.assetId = a.id
                WHERE c.category = ?
            """
            return Set(try String.fetchAll(database, sql: sql, arguments: [category.rawValue]))
        }
    }

    func allEmbeddings() throws -> [AssetEmbedding] {
        try db.writer.read { database in
            try EmbeddingRecord.fetchAll(database).map {
                AssetEmbedding(assetLocalIdentifier: $0.assetLocalIdentifier,
                               model: $0.model, vector: $0.floats)
            }
        }
    }

    func pendingCount() throws -> Int {
        try db.writer.read { database in
            try AssetRecord
                .filter(Column("analysisState") == Asset.AnalysisState.pending.rawValue)
                .fetchCount(database)
        }
    }

    func totalCount() throws -> Int {
        try db.writer.read { try AssetRecord.fetchCount($0) }
    }

    // MARK: - Writes

    /// Upsert freshly-discovered assets, preserving analysis results for ones we already know.
    func syncDiscovered(_ assets: [Asset]) throws {
        try db.writer.write { database in
            for asset in assets {
                let exists = try AssetRecord
                    .filter(Column("localIdentifier") == asset.localIdentifier)
                    .fetchCount(database) > 0
                if !exists {
                    var record = AssetRecord(asset)
                    try record.insert(database)
                }
            }
        }
    }

    /// Persist the full analysis result for one asset in a single transaction.
    func saveAnalysis(_ asset: Asset, categories: [CategoryTag], embedding: AssetEmbedding?) throws {
        try db.writer.write { database in
            var record = AssetRecord(asset)
            try record.upsert(database)
            guard let assetID = try AssetRecord
                .filter(Column("localIdentifier") == asset.localIdentifier)
                .fetchOne(database)?.id else { return }

            try CategoryTagRecord.filter(Column("assetId") == assetID).deleteAll(database)
            for tag in categories {
                var tagRecord = CategoryTagRecord(id: nil, assetId: assetID,
                                                  category: tag.category.rawValue,
                                                  confidence: tag.confidence)
                try tagRecord.insert(database)
            }
            if let embedding {
                try EmbeddingRecord(embedding).upsert(database)
            }
        }
    }

    /// Remove assets that no longer exist in the Photos library (deleted by the user).
    func pruneMissing(keeping liveIdentifiers: Set<String>) throws -> [String] {
        try db.writer.write { database in
            let all = try AssetRecord.fetchAll(database).map(\.localIdentifier)
            let stale = all.filter { !liveIdentifiers.contains($0) }
            if !stale.isEmpty {
                try AssetRecord.filter(stale.contains(Column("localIdentifier"))).deleteAll(database)
                try EmbeddingRecord.filter(stale.contains(Column("assetLocalIdentifier"))).deleteAll(database)
            }
            return stale
        }
    }
}
