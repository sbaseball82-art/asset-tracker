import SwiftUI

@main
struct PhotoMindAIApp: App {
    @State private var environment: AppEnvironment
    @Environment(\.scenePhase) private var scenePhase

    init() {
        // Open the durable database up front; fall back to in-memory if the disk store can't
        // be opened so the app still launches (degraded, logged) rather than crashing.
        let database: AppDatabase
        do {
            database = try AppDatabase.makeShared()
        } catch {
            Log.db.critical("Falling back to in-memory DB: \(error.localizedDescription)")
            database = try! AppDatabase.makeInMemory()   // last resort
        }
        _environment = State(initialValue: AppEnvironment(database: database))
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(environment)
                .tint(.accentColor)
                .task { await environment.bootstrap() }
        }
        .onChange(of: scenePhase) { _, phase in
            switch phase {
            case .background:
                environment.biometrics.lockIfNeeded()
                Task { await environment.analysisPipeline.pause() }
            case .active:
                environment.usageMeter.refresh()
            default:
                break
            }
        }
    }
}
