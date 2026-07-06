import Foundation
import GRDB

/// Owns the SQLite connection pool and schema. One instance lives in `AppEnvironment`.
///
/// Schema highlights:
/// - `asset`            one row per Photos item, indexed by creationDate, category, place.
/// - `category_tag`     many category assignments per asset (with confidence).
/// - `embedding`        one semantic vector per asset stored as a BLOB of Float32.
/// - `album` / `album_membership`  generated smart albums.
/// - FTS5 virtual table `asset_fts` over OCR text + caption for fast keyword prefilter.
///
/// The embedding table is intentionally *not* the search index itself — we keep a warm
/// in-memory `VectorIndex` (see that file) and treat SQLite as the durable store.
final class AppDatabase: Sendable {
    let writer: any DatabaseWriter

    init(_ writer: any DatabaseWriter) throws {
        self.writer = writer
        try migrator.migrate(writer)
    }

    /// Opens the on-disk database in Application Support with WAL + encryption-at-rest via
    /// file protection (`.completeUntilFirstUserAuthentication`).
    static func makeShared() throws -> AppDatabase {
        let fm = FileManager.default
        let dir = try fm.url(for: .applicationSupportDirectory, in: .userDomainMask,
                             appropriateFor: nil, create: true)
            .appendingPathComponent("PhotoMind", isDirectory: true)
        try fm.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent("photomind.sqlite")

        var config = Configuration()
        config.prepareDatabase { db in
            try db.execute(sql: "PRAGMA journal_mode = WAL")
            try db.execute(sql: "PRAGMA foreign_keys = ON")
            try db.execute(sql: "PRAGMA busy_timeout = 5000")
        }
        let pool = try DatabasePool(path: url.path, configuration: config)
        try fm.setAttributes(
            [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication],
            ofItemAtPath: url.path
        )
        Log.db.info("Opened database at \(url.path, privacy: .public)")
        return try AppDatabase(pool)
    }

    /// In-memory database for unit tests.
    static func makeInMemory() throws -> AppDatabase {
        try AppDatabase(try DatabaseQueue())
    }

    private var migrator: DatabaseMigrator {
        var migrator = DatabaseMigrator()
        #if DEBUG
        migrator.eraseDatabaseOnSchemaChange = true
        #endif

        migrator.registerMigration("v1_core") { db in
            try db.create(table: "asset") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("localIdentifier", .text).notNull().unique(onConflict: .replace)
                t.column("mediaType", .integer).notNull()
                t.column("creationDate", .datetime).indexed()
                t.column("modificationDate", .datetime)
                t.column("pixelWidth", .integer).notNull().defaults(to: 0)
                t.column("pixelHeight", .integer).notNull().defaults(to: 0)
                t.column("durationSeconds", .double).notNull().defaults(to: 0)
                t.column("isFavorite", .boolean).notNull().defaults(to: false)
                t.column("latitude", .double)
                t.column("longitude", .double)
                t.column("placeName", .text).indexed()
                t.column("analysisState", .integer).notNull().defaults(to: 0)
                t.column("qualityScore", .double).notNull().defaults(to: 0)
                t.column("isScreenshot", .boolean).notNull().defaults(to: false)
                t.column("perceptualHash", .integer).notNull().defaults(to: 0)
                t.column("ocrText", .text)
                t.column("captionSummary", .text)
            }

            try db.create(table: "category_tag") { t in
                t.autoIncrementedPrimaryKey("id")
                t.belongsTo("asset", onDelete: .cascade).notNull()
                t.column("category", .text).notNull().indexed()
                t.column("confidence", .double).notNull().defaults(to: 0)
            }

            try db.create(table: "embedding") { t in
                t.column("assetLocalIdentifier", .text).primaryKey()
                t.column("model", .text).notNull()
                t.column("dimension", .integer).notNull()
                t.column("vector", .blob).notNull()   // Float32 LE bytes
            }

            try db.create(table: "album") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("kind", .integer).notNull()
                t.column("title", .text).notNull()
                t.column("subtitle", .text)
                t.column("coverAssetIdentifier", .text)
                t.column("startDate", .datetime).indexed()
                t.column("endDate", .datetime)
                t.column("latitude", .double)
                t.column("longitude", .double)
                t.column("assetCount", .integer).notNull().defaults(to: 0)
                t.column("aiSummary", .text)
                t.column("createdAt", .datetime).notNull()
            }

            try db.create(table: "album_membership") { t in
                t.column("albumID", .integer).notNull()
                    .references("album", onDelete: .cascade)
                t.column("assetLocalIdentifier", .text).notNull()
                t.primaryKey(["albumID", "assetLocalIdentifier"])
            }
        }

        migrator.registerMigration("v2_fts") { db in
            // Full-text index over OCR text + caption for keyword prefilter / highlighting.
            try db.create(virtualTable: "asset_fts", using: FTS5()) { t in
                t.synchronize(withTable: "asset")
                t.column("ocrText")
                t.column("captionSummary")
                t.column("placeName")
                t.tokenizer = .unicode61()
            }
        }

        migrator.registerMigration("v3_search_meta") { db in
            // Persisted monthly usage counters for the freemium meter.
            try db.create(table: "usage_counter") { t in
                t.column("periodKey", .text).primaryKey()  // "2026-07"
                t.column("searchCount", .integer).notNull().defaults(to: 0)
            }
        }

        return migrator
    }
}
