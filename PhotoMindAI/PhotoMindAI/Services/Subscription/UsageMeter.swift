import Foundation
import GRDB

/// Enforces the freemium search quota: free users get `freeMonthlyLimit` searches per calendar
/// month; Premium subscribers are unmetered. Counts persist in SQLite so they survive relaunch,
/// keyed by "YYYY-MM". Observed by the UI to show the remaining-searches pill and paywall.
@MainActor
@Observable
final class UsageMeter {
    let freeMonthlyLimit = 100
    private let db: AppDatabase
    private let entitlements: EntitlementStore

    private(set) var usedThisMonth = 0

    init(db: AppDatabase, entitlements: EntitlementStore) {
        self.db = db
        self.entitlements = entitlements
        usedThisMonth = (try? readCount(for: Self.periodKey())) ?? 0
    }

    var remaining: Int {
        entitlements.isPremium ? .max : max(0, freeMonthlyLimit - usedThisMonth)
    }

    var isUnlimited: Bool { entitlements.isPremium }

    func canSearch() -> Bool { isUnlimited || usedThisMonth < freeMonthlyLimit }

    /// Atomically checks and consumes one search. Returns false if the quota is exhausted.
    func consumeSearchIfAllowed() -> Bool {
        guard canSearch() else { return false }
        if !isUnlimited {
            usedThisMonth += 1
            try? writeCount(usedThisMonth, for: Self.periodKey())
        }
        return true
    }

    func refresh() {
        usedThisMonth = (try? readCount(for: Self.periodKey())) ?? 0
    }

    // MARK: - Persistence

    static func periodKey(_ date: Date = Date()) -> String {
        let comps = Calendar.current.dateComponents([.year, .month], from: date)
        return String(format: "%04d-%02d", comps.year ?? 0, comps.month ?? 0)
    }

    private func readCount(for key: String) throws -> Int {
        try db.writer.read { database in
            try UsageCounterRecord.fetchOne(database, key: key)?.searchCount ?? 0
        }
    }

    private func writeCount(_ count: Int, for key: String) throws {
        try db.writer.write { database in
            try UsageCounterRecord(periodKey: key, searchCount: count).upsert(database)
        }
    }
}
