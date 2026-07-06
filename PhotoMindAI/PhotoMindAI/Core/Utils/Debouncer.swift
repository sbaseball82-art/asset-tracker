import Foundation

/// A simple async debouncer used by the search field so we only embed/query after the
/// user pauses typing. Actor-isolated so it is safe to call from any task.
actor Debouncer {
    private var task: Task<Void, Never>?
    private let delay: Duration

    init(delay: Duration = .milliseconds(300)) {
        self.delay = delay
    }

    /// Schedules `operation`, cancelling any previously-scheduled one.
    func call(_ operation: @escaping @Sendable () async -> Void) {
        task?.cancel()
        task = Task { [delay] in
            try? await Task.sleep(for: delay)
            if Task.isCancelled { return }
            await operation()
        }
    }

    func cancel() {
        task?.cancel()
        task = nil
    }
}
