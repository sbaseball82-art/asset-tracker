import WidgetKit
import SwiftUI

/// The widget extension bundle: the home-screen "思い出" widget plus the analysis Live Activity
/// (Lock Screen + Dynamic Island).
@main
struct PhotoMindWidgetBundle: WidgetBundle {
    var body: some Widget {
        MemoriesWidget()
        AnalysisLiveActivity()
    }
}
