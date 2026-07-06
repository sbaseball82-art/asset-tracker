import Foundation

/// Observable progress for the background analysis run. Drives the Library header progress
/// bar, the Settings status row, and the Live Activity / Dynamic Island.
@MainActor
@Observable
final class AnalysisProgress {
    var isRunning = false
    var processed = 0
    var total = 0
    var currentStage = ""

    var fractionComplete: Double {
        guard total > 0 else { return 0 }
        return min(1, Double(processed) / Double(total))
    }

    var remaining: Int { max(0, total - processed) }

    func begin(total: Int) {
        self.total = total
        processed = 0
        isRunning = total > 0
        currentStage = "解析を開始"
    }

    func advance(stage: String) {
        processed += 1
        currentStage = stage
    }

    func finish() {
        isRunning = false
        currentStage = "完了"
    }
}
