import Foundation
import GRDB

/// Repository over `album` and `album_membership`.
struct AlbumRepository: Sendable {
    let db: AppDatabase

    func allAlbums() throws -> [Album] {
        try db.writer.read { database in
            try AlbumRecord
                .order(Column("startDate").desc)
                .fetchAll(database)
                .map(\.asModel)
        }
    }

    func albums(ofKind kind: Album.Kind) throws -> [Album] {
        try db.writer.read { database in
            try AlbumRecord
                .filter(Column("kind") == kind.rawValue)
                .order(Column("startDate").desc)
                .fetchAll(database)
                .map(\.asModel)
        }
    }

    func members(ofAlbumID id: Int64) throws -> [Asset] {
        try db.writer.read { database in
            let sql = """
                SELECT a.* FROM asset a
                JOIN album_membership m ON m.assetLocalIdentifier = a.localIdentifier
                WHERE m.albumID = ?
                ORDER BY a.creationDate ASC
            """
            return try AssetRecord.fetchAll(database, sql: sql, arguments: [id]).map(\.asModel)
        }
    }

    /// Replace all generated albums in a single transaction (albums are rebuilt, not edited).
    func replaceAll(_ albums: [(album: Album, memberIdentifiers: [String])]) throws {
        try db.writer.write { database in
            try AlbumMembershipRecord.deleteAll(database)
            try AlbumRecord.deleteAll(database)
            for entry in albums {
                var record = AlbumRecord(entry.album)
                try record.insert(database)
                guard let albumID = record.id else { continue }
                for identifier in entry.memberIdentifiers {
                    try AlbumMembershipRecord(albumID: albumID,
                                              assetLocalIdentifier: identifier).insert(database)
                }
            }
        }
    }

    func updateSummary(albumID: Int64, summary: String) throws {
        try db.writer.write { database in
            try database.execute(sql: "UPDATE album SET aiSummary = ? WHERE id = ?",
                                 arguments: [summary, albumID])
        }
    }
}
