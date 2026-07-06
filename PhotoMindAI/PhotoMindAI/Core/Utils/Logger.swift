import Foundation
import os

/// Centralized structured logging. Subsystem is the bundle id so logs are filterable in
/// Console.app / `log stream`. Never log photo pixel data or full OCR bodies (privacy).
enum Log {
    private static let subsystem = Bundle.main.bundleIdentifier ?? "com.photomind.ai"

    static let photos    = Logger(subsystem: subsystem, category: "photos")
    static let analysis  = Logger(subsystem: subsystem, category: "analysis")
    static let ai        = Logger(subsystem: subsystem, category: "ai")
    static let search    = Logger(subsystem: subsystem, category: "search")
    static let db        = Logger(subsystem: subsystem, category: "database")
    static let ui        = Logger(subsystem: subsystem, category: "ui")
    static let security  = Logger(subsystem: subsystem, category: "security")
}
