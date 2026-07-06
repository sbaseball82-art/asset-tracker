import SwiftUI
import StoreKit

/// Premium paywall. Presented from the search quota gate and Settings. Uses StoreKit 2 through
/// `StoreService`; the button reflects the localized price when the product has loaded.
struct PaywallView: View {
    @Environment(AppEnvironment.self) private var env
    @Environment(\.dismiss) private var dismiss

    private let benefits: [(String, String)] = [
        ("infinity", "検索 無制限"),
        ("sparkles", "AI 旅行要約"),
        ("icloud", "CloudKit 同期"),
        ("nosign", "広告なし"),
        ("bolt", "優先バックグラウンド解析"),
    ]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    header
                    benefitList
                    purchaseButton
                    Button("購入を復元") { Task { await env.store.restore() } }
                        .font(.footnote)
                    Text("いつでもキャンセルできます。自動更新は App Store の設定から管理します。")
                        .font(.caption2).foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .padding()
            }
            .navigationTitle("PhotoMind Premium")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("閉じる") { dismiss() }
                }
            }
            .task { await env.store.loadProducts() }
            .onChange(of: env.entitlements.isPremium) { _, isPremium in
                if isPremium { dismiss() }
            }
        }
    }

    private var header: some View {
        GlassCard {
            VStack(spacing: 10) {
                Image(systemName: "sparkles").font(.system(size: 44)).foregroundStyle(.tint)
                Text("思い出を、もっと自由に。").font(.title2.weight(.bold))
                Text("無料プランは月 \(env.usageMeter.freeMonthlyLimit) 回まで検索できます。")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity)
        }
    }

    private var benefitList: some View {
        VStack(alignment: .leading, spacing: 14) {
            ForEach(benefits, id: \.1) { benefit in
                HStack(spacing: 14) {
                    Image(systemName: benefit.0).frame(width: 28).foregroundStyle(.tint)
                    Text(benefit.1).font(.body)
                    Spacer()
                    Image(systemName: "checkmark").foregroundStyle(.green)
                }
            }
        }
        .padding(.horizontal, 4)
    }

    private var purchaseButton: some View {
        Button {
            Task { await env.store.purchasePremium() }
        } label: {
            HStack {
                if env.store.purchaseInFlight { ProgressView().tint(.white) }
                Text(priceLabel).font(.headline)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 6)
        }
        .buttonStyle(.borderedProminent)
        .controlSize(.large)
        .disabled(env.store.purchaseInFlight)
    }

    private var priceLabel: String {
        if let product = env.store.premiumProduct {
            return "\(product.displayPrice) / 年で始める"
        }
        return "Premium を購入"
    }
}

#Preview {
    PaywallView().environment(AppEnvironment.preview())
}
