import Foundation

/// Builds the concrete `AIProvider` for the user's selected backend. The returned provider is
/// wrapped by `PrivacyGuard` at the call sites that transmit data, never here — the factory's
/// only job is construction.
struct AIProviderFactory: Sendable {
    let keychain: KeychainStore

    func make(_ kind: AIProviderKind) -> any AIProvider {
        switch kind {
        case .local:  return LocalAIProvider()
        case .openAI: return OpenAIProvider(keychain: keychain)
        case .gemini: return GeminiProvider(keychain: keychain)
        case .claude: return ClaudeProvider(keychain: keychain)
        }
    }

    /// Whether the given provider is ready to use (local always is; remote needs a key).
    func isConfigured(_ kind: AIProviderKind) -> Bool {
        guard kind.requiresAPIKey else { return true }
        return !(keychain.apiKey(for: kind) ?? "").isEmpty
    }
}
