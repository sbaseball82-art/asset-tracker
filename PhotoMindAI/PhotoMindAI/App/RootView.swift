import SwiftUI

/// Top-level tab scaffold + the two global overlays: the Face ID lock gate and the
/// pre-send privacy confirmation. iOS 18+ `TabView` with the new bottom bar; on iOS 26 the
/// system renders it with Liquid Glass automatically.
struct RootView: View {
    @Environment(AppEnvironment.self) private var env

    var body: some View {
        ZStack {
            TabView {
                Tab("ライブラリ", systemImage: "photo.on.rectangle.angled") {
                    LibraryView()
                }
                Tab("検索", systemImage: "sparkle.magnifyingglass", role: .search) {
                    SearchView()
                }
                Tab("アルバム", systemImage: "rectangle.stack") {
                    AlbumsView()
                }
                Tab("カレンダー", systemImage: "calendar") {
                    CalendarScreen()
                }
                Tab("整理", systemImage: "wand.and.sparkles") {
                    CleanupView()
                }
            }

            LockOverlay()
        }
        .privacyConfirmationAlert()
    }
}

/// Face ID gate. Covers the whole app until authenticated when App Lock is on.
private struct LockOverlay: View {
    @Environment(AppEnvironment.self) private var env
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        Group {
            if env.biometrics.isEnabled && env.biometrics.state != .unlocked {
                ZStack {
                    Rectangle().fill(.ultraThickMaterial).ignoresSafeArea()
                    VStack(spacing: 16) {
                        Image(systemName: "faceid").font(.system(size: 56))
                        Text("PhotoMind はロックされています").font(.headline)
                        Button {
                            Task { await env.biometrics.authenticate() }
                        } label: {
                            Label("\(env.biometrics.biometryLabel) で解除", systemImage: "lock.open")
                                .padding(.horizontal)
                        }
                        .buttonStyle(.borderedProminent)
                    }
                }
                .task { await env.biometrics.authenticate() }
            }
        }
    }
}

/// Presents the "AI にこの写真を送信しますか？" confirmation whenever `PrivacyGuard` blocks.
private struct PrivacyConfirmationModifier: ViewModifier {
    @Environment(AppEnvironment.self) private var env

    func body(content: Content) -> some View {
        content.alert(
            "AI に画像を送信しますか？",
            isPresented: Binding(
                get: { env.privacy.pendingConfirmation != nil },
                set: { if !$0 { env.privacy.resolve(false) } }
            )
        ) {
            Button("送信を許可") { env.privacy.resolve(true) }
            Button("キャンセル", role: .cancel) { env.privacy.resolve(false) }
        } message: {
            Text("解析精度を上げるため、縮小した画像を選択中の AI プロバイダーに送信します。元の写真は端末から出ません。")
        }
    }
}

extension View {
    func privacyConfirmationAlert() -> some View { modifier(PrivacyConfirmationModifier()) }
}

#Preview {
    RootView().environment(AppEnvironment.preview())
}
