import Foundation
import ActivityKit

/// Starts / updates / ends the analysis Live Activity from the app. Safe no-op on devices or
/// OS versions where Live Activities are unavailable or disabled by the user.
@MainActor
final class LiveActivityController {
    private var activity: Activity<AnalysisActivityAttributes>?

    func start(total: Int) {
        guard ActivityAuthorizationInfo().areActivitiesEnabled, total > 0 else { return }
        let attributes = AnalysisActivityAttributes(title: "写真を解析中")
        let state = AnalysisActivityAttributes.ContentState(processed: 0, total: total, stage: "開始")
        do {
            activity = try Activity.request(
                attributes: attributes,
                content: .init(state: state, staleDate: nil))
        } catch {
            Log.analysis.error("Live Activity start failed: \(error.localizedDescription)")
        }
    }

    func update(processed: Int, total: Int, stage: String) async {
        guard let activity else { return }
        let state = AnalysisActivityAttributes.ContentState(processed: processed, total: total, stage: stage)
        await activity.update(.init(state: state, staleDate: nil))
    }

    func end() async {
        guard let activity else { return }
        await activity.end(nil, dismissalPolicy: .immediate)
        self.activity = nil
    }
}
