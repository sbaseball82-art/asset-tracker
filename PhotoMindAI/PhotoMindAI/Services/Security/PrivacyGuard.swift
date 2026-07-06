import Foundation

/// Enforces PhotoMind's privacy promises around AI:
///
/// 1. **Local-first** — if the active provider is on-device, no gate is ever shown.
/// 2. **Pre-send confirmation** — the first time (per session, or always if the user chooses)
///    image data would leave the device, we require explicit confirmation.
/// 3. **Photos stay put** — providers only ever receive a down-scaled JPEG produced here,
///    never the original file, and nothing is written to any server-side store by the app.
///
/// UI observes `pendingConfirmation`; `AnalysisPipeline`/`SearchService` call `authorizeUpload`.
@MainActor
@Observable
final class PrivacyGuard {
    enum Consent: String {
        case ask          // confirm every batch
        case sessionOnce  // confirm once per launch
        case always       // user trusts remote provider
        case never        // never send off-device (force local)
    }

    var consent: Consent {
        didSet { UserDefaults.standard.set(consent.rawValue, forKey: Self.key) }
    }
    private var confirmedThisSession = false
    private static let key = "privacy.consent"

    /// Set by the guard when confirmation is required; the root view presents an alert bound
    /// to this and resumes the continuation via `resolve`.
    private(set) var pendingConfirmation: CheckedContinuation<Bool, Never>?

    init() {
        let raw = UserDefaults.standard.string(forKey: Self.key) ?? Consent.ask.rawValue
        consent = Consent(rawValue: raw) ?? .ask
    }

    /// Gate an off-device upload. Returns true if the caller may proceed.
    func authorizeUpload(provider: any AIProvider) async -> Bool {
        if provider.isLocal { return true }
        switch consent {
        case .never:  return false
        case .always: return true
        case .sessionOnce where confirmedThisSession: return true
        case .sessionOnce, .ask:
            let approved = await withCheckedContinuation { cont in
                pendingConfirmation = cont
            }
            if approved && consent == .sessionOnce { confirmedThisSession = true }
            return approved
        }
    }

    /// Called by the confirmation UI.
    func resolve(_ approved: Bool) {
        pendingConfirmation?.resume(returning: approved)
        pendingConfirmation = nil
    }

    /// Produces the JPEG that is the ONLY representation ever sent off-device. Down-scaled and
    /// recompressed so no original pixels / embedded metadata leave the library.
    static func downscaledJPEG(from data: Data, maxDimension: CGFloat = 512, quality: CGFloat = 0.7) -> Data? {
        ImageDownscaler.jpeg(from: data, maxDimension: maxDimension, quality: quality)
    }
}
