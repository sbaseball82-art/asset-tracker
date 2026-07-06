import Foundation
import StoreKit

/// Observable entitlement state (is the user Premium?). Kept tiny and separate from the store
/// front-end so `UsageMeter` can depend on entitlements without pulling in StoreKit UI.
@MainActor
@Observable
final class EntitlementStore {
    private(set) var isPremium = false
    func set(premium: Bool) { isPremium = premium }
}

/// StoreKit 2 wrapper for the single auto-renewable Premium subscription. Loads products,
/// runs purchase/restore, and keeps `EntitlementStore` in sync via a transaction listener.
@MainActor
@Observable
final class StoreService {
    static let premiumProductID = "com.photomind.ai.premium.yearly"

    private let entitlements: EntitlementStore
    private(set) var products: [Product] = []
    private(set) var purchaseInFlight = false
    var lastError: String?

    private var updatesTask: Task<Void, Never>?

    init(entitlements: EntitlementStore) {
        self.entitlements = entitlements
        updatesTask = listenForTransactions()
    }

    deinit { updatesTask?.cancel() }

    func loadProducts() async {
        do {
            products = try await Product.products(for: [Self.premiumProductID])
        } catch {
            lastError = error.localizedDescription
            Log.ai.error("StoreKit loadProducts failed: \(error.localizedDescription)")
        }
        await refreshEntitlements()
    }

    var premiumProduct: Product? { products.first { $0.id == Self.premiumProductID } }

    func purchasePremium() async {
        guard let product = premiumProduct else { return }
        purchaseInFlight = true
        defer { purchaseInFlight = false }
        do {
            let result = try await product.purchase()
            switch result {
            case .success(let verification):
                if case .verified(let transaction) = verification {
                    await transaction.finish()
                    entitlements.set(premium: true)
                }
            case .userCancelled, .pending:
                break
            @unknown default:
                break
            }
        } catch {
            lastError = error.localizedDescription
        }
    }

    func restore() async {
        try? await AppStore.sync()
        await refreshEntitlements()
    }

    /// Recomputes entitlement from the current set of verified entitlements.
    func refreshEntitlements() async {
        var premium = false
        for await result in Transaction.currentEntitlements {
            if case .verified(let transaction) = result,
               transaction.productID == Self.premiumProductID,
               transaction.revocationDate == nil {
                premium = true
            }
        }
        entitlements.set(premium: premium)
    }

    private func listenForTransactions() -> Task<Void, Never> {
        Task(priority: .background) { [weak self] in
            for await update in Transaction.updates {
                if case .verified(let transaction) = update {
                    await transaction.finish()
                    await self?.refreshEntitlements()
                }
            }
        }
    }
}
