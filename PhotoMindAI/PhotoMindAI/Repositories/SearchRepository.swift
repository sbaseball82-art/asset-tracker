import Foundation
import GRDB

/// Read-side repository for the structured filters and FTS keyword matching used by
/// `SearchService`. Kept separate from `AssetRepository` so search-specific SQL stays together.
struct SearchRepository: Sendable {
    let db: AppDatabase

    func identifiers(in range: DateInterval) throws -> Set<String> {
        try db.writer.read { database in
            let sql = """
                SELECT localIdentifier FROM asset
                WHERE creationDate >= ? AND creationDate < ?
            """
            return Set(try String.fetchAll(database, sql: sql, arguments: [range.start, range.end]))
        }
    }

    func identifiers(placeContains keyword: String) throws -> Set<String> {
        try db.writer.read { database in
            let sql = "SELECT localIdentifier FROM asset WHERE placeName LIKE ?"
            return Set(try String.fetchAll(database, sql: sql, arguments: ["%\(keyword)%"]))
        }
    }

    func identifiers(mediaType: Asset.MediaType) throws -> Set<String> {
        try db.writer.read { database in
            let sql = "SELECT localIdentifier FROM asset WHERE mediaType = ?"
            return Set(try String.fetchAll(database, sql: sql, arguments: [mediaType.rawValue]))
        }
    }

    /// FTS5 keyword match over OCR text / caption / place. Returns id → matched snippet.
    func keywordMatches(_ text: String, limit: Int) throws -> [String: String] {
        let terms = text
            .split(whereSeparator: { $0.isWhitespace })
            .map { String($0) }
            .filter { $0.count >= 2 }
        guard !terms.isEmpty else { return [:] }
        // Prefix-match each term; FTS5 handles the ranking with bm25.
        let ftsQuery = terms.map { "\($0.replacingOccurrences(of: "\"", with: ""))*" }
            .joined(separator: " OR ")

        return try db.writer.read { database in
            let sql = """
                SELECT a.localIdentifier AS id,
                       snippet(asset_fts, 0, '⟪', '⟫', '…', 12) AS snip
                FROM asset_fts
                JOIN asset a ON a.rowid = asset_fts.rowid
                WHERE asset_fts MATCH ?
                ORDER BY bm25(asset_fts)
                LIMIT ?
            """
            var out: [String: String] = [:]
            let rows = try Row.fetchAll(database, sql: sql, arguments: [ftsQuery, limit])
            for row in rows {
                let id: String = row["id"]
                out[id] = row["snip"]
            }
            return out
        }
    }
}
