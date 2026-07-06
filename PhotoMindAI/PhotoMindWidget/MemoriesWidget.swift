import WidgetKit
import SwiftUI

/// A home-screen widget surfacing a "この日の思い出" prompt and library stats. It reads a small
/// snapshot the app writes to the shared App Group container after each analysis run (so the
/// widget never touches the Photos library or the SQLite DB directly).
struct MemoriesWidget: Widget {
    let kind = "MemoriesWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: MemoriesProvider()) { entry in
            MemoriesWidgetView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("思い出")
        .description("AI が選んだ今日の思い出とライブラリの統計を表示します。")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}

struct MemoriesEntry: TimelineEntry {
    let date: Date
    let totalPhotos: Int
    let tripCount: Int
    let headline: String
}

struct MemoriesProvider: TimelineProvider {
    func placeholder(in context: Context) -> MemoriesEntry {
        MemoriesEntry(date: .now, totalPhotos: 12840, tripCount: 18, headline: "去年の今日、京都にいました")
    }

    func getSnapshot(in context: Context, completion: @escaping (MemoriesEntry) -> Void) {
        completion(WidgetStore.shared.currentEntry())
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<MemoriesEntry>) -> Void) {
        let entry = WidgetStore.shared.currentEntry()
        // Refresh a few times a day; the app also reloads timelines after each analysis pass.
        let next = Calendar.current.date(byAdding: .hour, value: 6, to: .now) ?? .now
        completion(Timeline(entries: [entry], policy: .after(next)))
    }
}

struct MemoriesWidgetView: View {
    let entry: MemoriesEntry
    @Environment(\.widgetFamily) private var family

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("PhotoMind", systemImage: "sparkles").font(.caption2.weight(.bold))
                .foregroundStyle(.tint)
            Spacer(minLength: 0)
            Text(entry.headline)
                .font(family == .systemSmall ? .caption : .headline)
                .fontWeight(.semibold)
                .lineLimit(family == .systemSmall ? 3 : 2)
            Spacer(minLength: 0)
            HStack(spacing: 12) {
                stat("\(entry.totalPhotos)", "枚")
                stat("\(entry.tripCount)", "旅行")
            }
            .font(.caption2).foregroundStyle(.secondary)
        }
    }

    private func stat(_ value: String, _ label: String) -> some View {
        HStack(spacing: 3) {
            Text(value).fontWeight(.bold).foregroundStyle(.primary)
            Text(label)
        }
    }
}

/// Tiny App Group-backed snapshot store shared by app + widget.
struct WidgetStore {
    static let shared = WidgetStore()
    static let appGroup = "group.com.photomind.ai"
    private let defaults = UserDefaults(suiteName: WidgetStore.appGroup)

    func write(totalPhotos: Int, tripCount: Int, headline: String) {
        defaults?.set(totalPhotos, forKey: "totalPhotos")
        defaults?.set(tripCount, forKey: "tripCount")
        defaults?.set(headline, forKey: "headline")
    }

    func currentEntry() -> MemoriesEntry {
        MemoriesEntry(
            date: .now,
            totalPhotos: defaults?.integer(forKey: "totalPhotos") ?? 0,
            tripCount: defaults?.integer(forKey: "tripCount") ?? 0,
            headline: defaults?.string(forKey: "headline") ?? "写真を解析すると思い出が表示されます"
        )
    }
}
