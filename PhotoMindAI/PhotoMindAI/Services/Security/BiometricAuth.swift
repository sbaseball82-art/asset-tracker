import Foundation
import LocalAuthentication

/// Face ID / Touch ID app lock. The app is gated behind this on launch and on return from
/// background when the user enables "App Lock" in Settings.
@MainActor
@Observable
final class BiometricAuth {
    enum State: Equatable {
        case locked
        case unlocked
        case unavailable
    }

    private(set) var state: State = .locked
    var isEnabled: Bool {
        didSet { UserDefaults.standard.set(isEnabled, forKey: Self.enabledKey) }
    }

    private static let enabledKey = "security.appLock.enabled"

    init() {
        isEnabled = UserDefaults.standard.bool(forKey: Self.enabledKey)
        state = isEnabled ? .locked : .unlocked
    }

    var biometryLabel: String {
        let context = LAContext()
        _ = context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: nil)
        switch context.biometryType {
        case .faceID: return "Face ID"
        case .touchID: return "Touch ID"
        default: return "パスコード"
        }
    }

    func lockIfNeeded() {
        if isEnabled { state = .locked }
    }

    func authenticate() async {
        guard isEnabled else { state = .unlocked; return }
        let context = LAContext()
        context.localizedFallbackTitle = "パスコードを使用"
        var error: NSError?
        guard context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error) else {
            Log.security.error("Biometrics unavailable: \(error?.localizedDescription ?? "")")
            state = .unavailable
            return
        }
        do {
            let ok = try await context.evaluatePolicy(
                .deviceOwnerAuthentication,
                localizedReason: "PhotoMind AI のロックを解除")
            state = ok ? .unlocked : .locked
        } catch {
            Log.security.info("Biometric auth cancelled/failed: \(error.localizedDescription)")
            state = .locked
        }
    }
}
