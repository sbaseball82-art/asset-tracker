import SwiftUI

/// The main library grid: a lazy, adaptive photo grid with a category filter rail and a
/// live analysis-progress header.
struct LibraryView: View {
    @Environment(AppEnvironment.self) private var env
    @State private var model: LibraryViewModel?
    @State private var showSettings = false

    private let columns = [GridItem(.adaptive(minimum: 108), spacing: 2)]

    var body: some View {
        NavigationStack {
            Group {
                if let model {
                    content(model)
                } else {
                    ProgressView()
                }
            }
            .navigationTitle("ライブラリ")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button { showSettings = true } label: { Image(systemName: "gearshape") }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { Task { await model?.refresh() } } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                }
            }
            .sheet(isPresented: $showSettings) { SettingsView() }
        }
        .task {
            if model == nil {
                model = LibraryViewModel(assetRepository: env.assetRepository,
                                         pipeline: env.analysisPipeline,
                                         progress: env.analysisProgress)
            }
            await model?.load()
        }
    }

    @ViewBuilder
    private func content(_ model: LibraryViewModel) -> some View {
        ScrollView {
            if model.progress.isRunning {
                AnalysisProgressHeader(progress: model.progress)
                    .padding(.horizontal)
            }
            categoryRail(model)
            LazyVGrid(columns: columns, spacing: 2) {
                ForEach(model.filteredAssets) { asset in
                    NavigationLink(value: asset) {
                        AsyncThumbnailView(localIdentifier: asset.localIdentifier)
                            .aspectRatio(1, contentMode: .fill)
                            .clipped()
                            .overlay(alignment: .bottomTrailing) { badge(asset) }
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .navigationDestination(for: Asset.self) { AssetDetailView(asset: $0) }
        .overlay {
            if model.assets.isEmpty && !model.isLoading {
                ContentUnavailableView("写真がありません",
                                       systemImage: "photo.on.rectangle",
                                       description: Text("写真ライブラリへのアクセスを許可すると、AI が自動で解析します。"))
            }
        }
    }

    private func categoryRail(_ model: LibraryViewModel) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                Button { Task { await model.select(category: nil) } } label: {
                    Text("すべて")
                        .font(.caption.weight(.medium))
                        .padding(.horizontal, 14).padding(.vertical, 7)
                        .background(Capsule().fill(model.selectedCategory == nil
                                                   ? Color.accentColor : Color.secondary.opacity(0.15)))
                        .foregroundStyle(model.selectedCategory == nil ? .white : .secondary)
                }
                ForEach(PhotoCategory.allCases.filter { $0 != .other && $0 != .pet }) { category in
                    Button { Task { await model.select(category: category) } } label: {
                        CategoryChip(category: category, isSelected: model.selectedCategory == category)
                    }
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 4)
        }
    }

    @ViewBuilder
    private func badge(_ asset: Asset) -> some View {
        if asset.mediaType != .photo {
            Image(systemName: asset.mediaType.symbolName)
                .font(.caption2)
                .padding(4)
                .foregroundStyle(.white)
                .shadow(radius: 2)
        }
    }
}

/// Glass header showing "AI が解析中 … 1,204 / 5,000".
struct AnalysisProgressHeader: View {
    let progress: AnalysisProgress

    var body: some View {
        GlassCard {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Image(systemName: "sparkles").symbolEffect(.pulse)
                    Text("AI が解析中").font(.subheadline.weight(.semibold))
                    Spacer()
                    Text("\(progress.processed.formatted()) / \(progress.total.formatted())")
                        .font(.caption).foregroundStyle(.secondary).monospacedDigit()
                }
                ProgressView(value: progress.fractionComplete)
                Text(progress.currentStage).font(.caption2).foregroundStyle(.secondary)
            }
        }
        .padding(.top, 8)
    }
}

#Preview {
    LibraryView().environment(AppEnvironment.preview())
}
