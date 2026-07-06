import Foundation
import Security

/// Thin, thread-safe wrapper over the iOS Keychain for storing AI provider API keys.
/// Keys are stored with `kSecAttrAccessibleWhenUnlockedThisDeviceOnly` so they never sync
/// to iCloud or leave the device, and are removed when the passcode is disabled.
struct KeychainStore: Sendable {
    let service: String

    init(service: String = (Bundle.main.bundleIdentifier ?? "com.photomind.ai") + ".keys") {
        self.service = service
    }

    private func account(for kind: AIProviderKind) -> String { "apikey.\(kind.rawValue)" }

    func apiKey(for kind: AIProviderKind) -> String? {
        read(account: account(for: kind)).flatMap { String(data: $0, encoding: .utf8) }
    }

    @discardableResult
    func setAPIKey(_ key: String?, for kind: AIProviderKind) -> Bool {
        let acct = account(for: kind)
        guard let key, !key.isEmpty else { return delete(account: acct) }
        return write(Data(key.utf8), account: acct)
    }

    // MARK: - Primitives

    private func write(_ data: Data, account: String) -> Bool {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(query as CFDictionary)
        var add = query
        add[kSecValueData as String] = data
        add[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        let status = SecItemAdd(add as CFDictionary, nil)
        if status != errSecSuccess { Log.security.error("Keychain write failed: \(status)") }
        return status == errSecSuccess
    }

    private func read(account: String) -> Data? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess else { return nil }
        return result as? Data
    }

    @discardableResult
    private func delete(account: String) -> Bool {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        let status = SecItemDelete(query as CFDictionary)
        return status == errSecSuccess || status == errSecItemNotFound
    }
}
