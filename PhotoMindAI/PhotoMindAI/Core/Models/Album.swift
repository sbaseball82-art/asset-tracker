import Foundation

/// A smart album. Albums in PhotoMind are *generated*, not manually curated — the
/// `AlbumBuilder` clusters assets by time/place/category and materializes them here.
struct Album: Identifiable, Hashable, Codable, Sendable {
    enum Kind: Int, Codable, Sendable, CaseIterable {
        case trip = 0
        case work = 1
        case family = 2
        case food = 3
        case pet = 4
        case receipt = 5
        case event = 6

        var title: String {
            switch self {
            case .trip: return "旅行"
            case .work: return "仕事"
            case .family: return "家族"
            case .food: return "食事"
            case .pet: return "ペット"
            case .receipt: return "レシート"
            case .event: return "イベント"
            }
        }

        var symbolName: String {
            switch self {
            case .trip: return "airplane"
            case .work: return "briefcase"
            case .family: return "figure.2.and.child.holdinghands"
            case .food: return "fork.knife"
            case .pet: return "pawprint"
            case .receipt: return "receipt"
            case .event: return "calendar"
            }
        }
    }

    let id: Int64?
    var kind: Kind
    var title: String
    var subtitle: String?
    var coverAssetIdentifier: String?
    var startDate: Date?
    var endDate: Date?
    var latitude: Double?
    var longitude: Double?
    var assetCount: Int
    var aiSummary: String?          // e.g. "京都旅行 2025年4月 写真128枚 食事12件 寺5件"
    var createdAt: Date
}

/// A membership row linking an asset into an album (many-to-many).
struct AlbumMembership: Hashable, Codable, Sendable {
    let albumID: Int64
    let assetLocalIdentifier: String
}
