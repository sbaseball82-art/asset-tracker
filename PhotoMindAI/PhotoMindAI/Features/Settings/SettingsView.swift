import SwiftUI

/// Settings: AI provider switch + API keys, privacy controls, App Lock, background analysis,
/// subscription management, and library stats.
struct SettingsView: View {
    @Environment(AppEnvironment.self) private var env
    @State private var showPaywall = false
    @State private var keyDrafts: [AIProviderKind: String] = [:]

    var body: some View {
        NavigationStack {
            Form {
                aiSection
                privacySection
                securitySection
                analysisSection
                subscriptionSection
                aboutSection
            }
            .navigationTitle("設定")
            .sheet(isPresented: $showPaywall) { PaywallView() }
            .onAppear { loadDrafts() }
        }
    }

    // MARK: AI provider

    private var aiSection: some View {
        Section("AI プロバイダー") {
            Picker("エンジン", selection: providerBinding) {
                ForEach(AIProviderKind.allCases) { kind in
                    Text(kind.displayName).tag(kind)
                }
            }
            ForEach(AIProviderKind.allCases.filter { $0.requiresAPIKey }) { kind in
                if env.settings.provider == kind {
                    SecureField("\(kind.displayName) API キー",
                                text: keyBinding(for: kind))
                        .textContentType(.password)
                        .autocorrectionDisabled()
                }
            }
        } footer: {
            Text("オンデバイスを選ぶと写真は一切外部に送信されません。外部 AI を使う場合も、送信前に確認・縮小されます。")
        }
    }

    private var providerBinding: Binding<AIProviderKind> {
        Binding(get: { env.settings.provider }, set: { env.settings.provider = $0 })
    }

    private func keyBinding(for kind: AIProviderKind) -> Binding<String> {
        Binding(
            get: { keyDrafts[kind] ?? env.settings.apiKey(for: kind) },
            set: { keyDrafts[kind] = $0; env.settings.setAPIKey($0, for: kind) }
        )
    }

    private func loadDrafts() {
        for kind in AIProviderKind.allCases where kind.requiresAPIKey {
            keyDrafts[kind] = env.settings.apiKey(for: kind)
        }
    }

    // MARK: Privacy

    private var privacySection: some View {
        Section("プライバシー") {
            Picker("AI 送信の確認", selection: consentBinding) {
                Text("毎回確認").tag(PrivacyGuard.Consent.ask)
                Text("起動ごとに一度").tag(PrivacyGuard.Consent.sessionOnce)
                Text("常に許可").tag(PrivacyGuard.Consent.always)
                Text("送信しない（ローカルのみ）").tag(PrivacyGuard.Consent.never)
            }
            LabeledContent("写真の保存先", value: "端末内のみ")
        }
    }

    private var consentBinding: Binding<PrivacyGuard.Consent> {
        Binding(get: { env.privacy.consent }, set: { env.privacy.consent = $0 })
    }

    // MARK: Security

    private var securitySection: some View {
        Section("セキュリティ") {
            Toggle(isOn: Binding(
                get: { env.biometrics.isEnabled },
                set: { env.biometrics.isEnabled = $0 }
            )) {
                Label("App ロック（\(env.biometrics.biometryLabel)）", systemImage: "faceid")
            }
        }
    }

    // MARK: Analysis

    private var analysisSection: some View {
        Section("解析") {
            Toggle("バックグラウンド解析", isOn: Binding(
                get: { env.settings.backgroundAnalysisEnabled },
                set: { env.settings.backgroundAnalysisEnabled = $0 }))
            Toggle("位置情報から地名を取得", isOn: Binding(
                get: { env.settings.reverseGeocodeEnabled },
                set: { env.settings.reverseGeocodeEnabled = $0 }))
            if env.analysisProgress.isRunning {
                LabeledContent("進捗",
                    value: "\(env.analysisProgress.processed) / \(env.analysisProgress.total)")
            }
        }
    }

    // MARK: Subscription

    private var subscriptionSection: some View {
        Section("サブスクリプション") {
            if env.entitlements.isPremium {
                Label("Premium 有効", systemImage: "checkmark.seal.fill").foregroundStyle(.green)
            } else {
                LabeledContent("今月の検索", value: "\(env.usageMeter.usedThisMonth) / \(env.usageMeter.freeMonthlyLimit)")
                Button("Premium にアップグレード") { showPaywall = true }
            }
            Button("購入を復元") { Task { await env.store.restore() } }
        }
    }

    private var aboutSection: some View {
        Section("情報") {
            LabeledContent("バージョン", value: Bundle.main.appVersion)
            Link("プライバシーポリシー", destination: URL(string: "https://photomind.ai/privacy")!)
            Link("利用規約", destination: URL(string: "https://photomind.ai/terms")!)
        }
    }
}

extension Bundle {
    var appVersion: String {
        let v = infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
        let b = infoDictionary?["CFBundleVersion"] as? String ?? "1"
        return "\(v) (\(b))"
    }
}

#Preview {
    SettingsView().environment(AppEnvironment.preview())
}
