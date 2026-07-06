import Foundation

/// User settings backed by `UserDefaults` (non-secret) and `KeychainStore` (API keys).
/// `@Observable` so SwiftUI views react to changes.
@MainActor
@Observable
final class SettingsRepository {
    private let defaults = UserDefaults.standard
    private let keychain: KeychainStore

    init(keychain: KeychainStore) {
        self.keychain = keychain
        let raw = defaults.string(forKey: Keys.provider) ?? AIProviderKind.local.rawValue
        _provider = AIProviderKind(rawValue: raw) ?? .local
    }

    private enum Keys {
        static let provider = "settings.aiProvider"
        static let backgroundAnalysis = "settings.backgroundAnalysis"
        static let reverseGeocode = "settings.reverseGeocode"
    }

    private var _provider: AIProviderKind
    var provider: AIProviderKind {
        get { _provider }
        set { _provider = newValue; defaults.set(newValue.rawValue, forKey: Keys.provider) }
    }

    var backgroundAnalysisEnabled: Bool {
        get { defaults.object(forKey: Keys.backgroundAnalysis) as? Bool ?? true }
        set { defaults.set(newValue, forKey: Keys.backgroundAnalysis) }
    }

    var reverseGeocodeEnabled: Bool {
        get { defaults.object(forKey: Keys.reverseGeocode) as? Bool ?? true }
        set { defaults.set(newValue, forKey: Keys.reverseGeocode) }
    }

    // API keys proxy to Keychain.
    func apiKey(for kind: AIProviderKind) -> String { keychain.apiKey(for: kind) ?? "" }
    func setAPIKey(_ key: String, for kind: AIProviderKind) { keychain.setAPIKey(key, for: kind) }
}
