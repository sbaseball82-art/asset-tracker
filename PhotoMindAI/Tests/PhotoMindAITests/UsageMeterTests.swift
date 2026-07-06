import Testing
import Foundation
@testable import PhotoMindAI

@MainActor
struct UsageMeterTests {
    private func makeMeter(premium: Bool = false) throws -> UsageMeter {
        let db = try AppDatabase.makeInMemory()
        let entitlements = EntitlementStore()
        entitlements.set(premium: premium)
        return UsageMeter(db: db, entitlements: entitlements)
    }

    @Test func freeUserConsumesUntilLimit() throws {
        let meter = try makeMeter()
        for _ in 0..<meter.freeMonthlyLimit {
            #expect(meter.consumeSearchIfAllowed())
        }
        #expect(!meter.consumeSearchIfAllowed())   // limit reached
        #expect(meter.remaining == 0)
    }

    @Test func premiumUserIsUnmetered() throws {
        let meter = try makeMeter(premium: true)
        for _ in 0..<500 { #expect(meter.consumeSearchIfAllowed()) }
        #expect(meter.isUnlimited)
        #expect(meter.usedThisMonth == 0)          // never incremented for premium
    }

    @Test func countPersistsAcrossReload() throws {
        let db = try AppDatabase.makeInMemory()
        let entitlements = EntitlementStore()
        let meter = UsageMeter(db: db, entitlements: entitlements)
        _ = meter.consumeSearchIfAllowed()
        _ = meter.consumeSearchIfAllowed()

        let reloaded = UsageMeter(db: db, entitlements: entitlements)
        #expect(reloaded.usedThisMonth == 2)
    }

    @Test func periodKeyFormat() {
        var comps = DateComponents(); comps.year = 2026; comps.month = 3; comps.day = 15
        let date = Calendar.current.date(from: comps)!
        #expect(UsageMeter.periodKey(date) == "2026-03")
    }
}
