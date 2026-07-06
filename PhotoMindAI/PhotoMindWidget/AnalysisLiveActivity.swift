import WidgetKit
import SwiftUI
import ActivityKit

/// Lock Screen Live Activity + Dynamic Island for the background analysis run. Shares
/// `AnalysisActivityAttributes` with the app target.
struct AnalysisLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: AnalysisActivityAttributes.self) { context in
            // Lock Screen / banner presentation.
            HStack(spacing: 12) {
                Image(systemName: "sparkles").font(.title3).symbolEffect(.pulse)
                VStack(alignment: .leading, spacing: 4) {
                    Text(context.attributes.title).font(.subheadline.weight(.semibold))
                    ProgressView(value: context.state.fraction)
                    Text("\(context.state.processed) / \(context.state.total) 枚")
                        .font(.caption2).foregroundStyle(.secondary).monospacedDigit()
                }
            }
            .padding()
            .activityBackgroundTint(Color.black.opacity(0.4))

        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Image(systemName: "sparkles").foregroundStyle(.tint)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Text("\(Int(context.state.fraction * 100))%").font(.caption).monospacedDigit()
                }
                DynamicIslandExpandedRegion(.center) {
                    Text(context.attributes.title).font(.caption.weight(.semibold))
                }
                DynamicIslandExpandedRegion(.bottom) {
                    VStack(spacing: 4) {
                        ProgressView(value: context.state.fraction)
                        Text("\(context.state.processed) / \(context.state.total)")
                            .font(.caption2).foregroundStyle(.secondary).monospacedDigit()
                    }
                }
            } compactLeading: {
                Image(systemName: "sparkles").foregroundStyle(.tint)
            } compactTrailing: {
                Text("\(Int(context.state.fraction * 100))%").font(.caption2).monospacedDigit()
            } minimal: {
                Image(systemName: "sparkles").foregroundStyle(.tint)
            }
        }
    }
}
