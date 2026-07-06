import Foundation
import ActivityKit

/// Shared between the app target (which starts/updates the activity) and the widget extension
/// (which renders it). Drives the Live Activity + Dynamic Island shown while the initial
/// library analysis is running.
struct AnalysisActivityAttributes: ActivityAttributes {
    public struct ContentState: Codable, Hashable {
        var processed: Int
        var total: Int
        var stage: String

        var fraction: Double {
            guard total > 0 else { return 0 }
            return min(1, Double(processed) / Double(total))
        }
    }

    /// Static title shown for the run.
    var title: String
}
