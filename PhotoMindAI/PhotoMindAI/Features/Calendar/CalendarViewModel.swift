import Foundation
import SwiftUI

/// Groups assets by month for the calendar view. Also exposes event/trip groupings derived
/// from albums so the calendar can switch between "月別 / 旅行別 / イベント別".
@MainActor
@Observable
final class CalendarViewModel {
    enum Mode: String, CaseIterable, Identifiable {
        case month = "月別"
        case trip = "旅行別"
        case event = "イベント別"
        var id: String { rawValue }
    }

    struct MonthBucket: Identifiable {
        let id: String            // "2025-04"
        let date: Date
        let assets: [Asset]
        var title: String {
            let f = DateFormatter(); f.locale = Locale(identifier: "ja_JP"); f.dateFormat = "yyyy年 M月"
            return f.string(from: date)
        }
    }

    private let assetRepository: AssetRepository
    private let albumRepository: AlbumRepository

    var mode: Mode = .month
    var months: [MonthBucket] = []
    var trips: [Album] = []

    init(assetRepository: AssetRepository, albumRepository: AlbumRepository) {
        self.assetRepository = assetRepository
        self.albumRepository = albumRepository
    }

    func load() async {
        let assets = (try? assetRepository.allAssets()) ?? []
        let calendar = Calendar.current
        let grouped = Dictionary(grouping: assets) { asset -> DateComponents in
            calendar.dateComponents([.year, .month], from: asset.creationDate ?? .distantPast)
        }
        months = grouped.compactMap { comps, assets in
            guard let date = calendar.date(from: comps) else { return nil }
            let key = String(format: "%04d-%02d", comps.year ?? 0, comps.month ?? 0)
            return MonthBucket(id: key, date: date, assets: assets.sorted {
                ($0.creationDate ?? .distantPast) > ($1.creationDate ?? .distantPast)
            })
        }
        .sorted { $0.date > $1.date }

        trips = (try? albumRepository.albums(ofKind: .trip)) ?? []
    }
}
