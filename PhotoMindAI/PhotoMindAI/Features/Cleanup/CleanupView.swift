import SwiftUI

/// Cleanup / 整理: surfaces duplicate groups, blurry photos and screenshots, lets the user
/// review and delete (deletion always goes through the system PhotoKit confirmation).
struct CleanupView: View {
    @Environment(AppEnvironment.self) private var env
    @State private var model: CleanupViewModel?
    @State private var showDeleteConfirm = false

    private let columns = [GridItem(.adaptive(minimum: 90), spacing: 6)]

    var body: some View {
        NavigationStack {
            Group {
                if let model { content(model) } else { ProgressView() }
            }
            .navigationTitle("整理")
        }
        .task {
            if model == nil {
                model = CleanupViewModel(assetRepository: env.assetRepository, photos: env.photos)
            }
            await model?.load()
        }
    }

    @ViewBuilder
    private func content(_ model: CleanupViewModel) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                GlassCard {
                    HStack {
                        VStack(alignment: .leading) {
                            Text("\(model.reclaimable) 件").font(.title.weight(.bold))
                            Text("削除候補").font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Button {
                            showDeleteConfirm = true
                        } label: {
                            Label("選択を削除 (\(model.selectedForDeletion.count))", systemImage: "trash")
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(.red)
                        .disabled(model.selectedForDeletion.isEmpty)
                    }
                }
                .padding(.horizontal)

                if let suggestions = model.suggestions {
                    duplicateSection(model, suggestions)
                    simpleSection("ピンボケ", systemImage: "camera.filters", assets: suggestions.blurry, model: model)
                    simpleSection("スクリーンショット", systemImage: "iphone", assets: suggestions.screenshots, model: model)
                }
            }
            .padding(.vertical)
        }
        .overlay { if model.isLoading { ProgressView("解析中…") } }
        .confirmationDialog("選択した \(model.selectedForDeletion.count) 件を削除しますか？",
                            isPresented: $showDeleteConfirm, titleVisibility: .visible) {
            Button("削除", role: .destructive) { Task { await model.deleteSelected() } }
            Button("キャンセル", role: .cancel) {}
        }
    }

    private func duplicateSection(_ model: CleanupViewModel,
                                  _ suggestions: DuplicateDetector.CleanupSuggestions) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            if !suggestions.duplicateGroups.isEmpty {
                Label("重複・類似", systemImage: "square.on.square").font(.headline).padding(.horizontal)
            }
            ForEach(suggestions.duplicateGroups) { group in
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        cell(group.keep.localIdentifier, model: model, isKeep: true)
                        ForEach(group.discard) { cell($0.localIdentifier, model: model, isKeep: false) }
                    }
                    .padding(.horizontal)
                }
            }
        }
    }

    private func simpleSection(_ title: String, systemImage: String,
                               assets: [Asset], model: CleanupViewModel) -> some View {
        Group {
            if !assets.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Label(title, systemImage: systemImage).font(.headline).padding(.horizontal)
                    LazyVGrid(columns: columns, spacing: 6) {
                        ForEach(assets) { cell($0.localIdentifier, model: model, isKeep: false) }
                    }
                    .padding(.horizontal)
                }
            }
        }
    }

    private func cell(_ id: String, model: CleanupViewModel, isKeep: Bool) -> some View {
        let selected = model.selectedForDeletion.contains(id)
        return AsyncThumbnailView(localIdentifier: id, pointSize: 90)
            .frame(width: 88, height: 88)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(alignment: .topTrailing) {
                if isKeep {
                    Text("残す").font(.caption2.bold()).padding(4)
                        .background(.green, in: Capsule()).foregroundStyle(.white).padding(4)
                } else {
                    Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                        .foregroundStyle(selected ? .red : .white)
                        .padding(4).shadow(radius: 2)
                }
            }
            .overlay {
                RoundedRectangle(cornerRadius: 10)
                    .strokeBorder(selected ? Color.red : .clear, lineWidth: 2)
            }
            .onTapGesture { if !isKeep { model.toggle(id) } }
    }
}

#Preview {
    CleanupView().environment(AppEnvironment.preview())
}
