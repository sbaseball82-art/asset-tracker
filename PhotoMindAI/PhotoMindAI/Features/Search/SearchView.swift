import SwiftUI

/// Natural-language search screen. A prominent search field, suggestion chips when empty, and
/// a results grid ranked by semantic relevance. Shows the remaining-searches pill and routes
/// to the paywall when the free quota is exhausted.
struct SearchView: View {
    @Environment(AppEnvironment.self) private var env
    @State private var model: SearchViewModel?

    private let columns = [GridItem(.adaptive(minimum: 110), spacing: 2)]

    var body: some View {
        NavigationStack {
            Group {
                if let model { content(model) } else { ProgressView() }
            }
            .navigationTitle("AI 検索")
        }
        .task {
            if model == nil {
                model = SearchViewModel(searchService: env.makeSearchService(),
                                        usageMeter: env.usageMeter)
            }
        }
    }

    @ViewBuilder
    private func content(_ model: SearchViewModel) -> some View {
        @Bindable var model = model
        ScrollView {
            if model.results.isEmpty && !model.isSearching {
                emptyState(model)
            } else {
                LazyVGrid(columns: columns, spacing: 2) {
                    ForEach(model.results) { result in
                        NavigationLink(value: result.asset) {
                            AsyncThumbnailView(localIdentifier: result.asset.localIdentifier)
                                .aspectRatio(1, contentMode: .fill)
                                .clipped()
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .overlay { if model.isSearching { ProgressView("検索中…") } }
        .navigationDestination(for: Asset.self) { AssetDetailView(asset: $0) }
        .searchable(text: $model.queryText, prompt: "「去年 大阪 ラーメン」で検索")
        .onChange(of: model.queryText) { _, _ in model.onQueryChange() }
        .onSubmit(of: .search) { model.submit() }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                RemainingSearchesPill(remaining: env.usageMeter.remaining,
                                      isUnlimited: env.usageMeter.isUnlimited) {
                    model.showPaywall = true
                }
            }
        }
        .sheet(isPresented: $model.showPaywall) { PaywallView() }
    }

    private func emptyState(_ model: SearchViewModel) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            GlassCard {
                VStack(alignment: .leading, spacing: 6) {
                    Label("自然言語で思い出を検索", systemImage: "sparkle.magnifyingglass")
                        .font(.headline)
                    Text("日付・場所・被写体を自由に組み合わせて検索できます。")
                        .font(.subheadline).foregroundStyle(.secondary)
                }
            }
            Text("例").font(.caption).foregroundStyle(.secondary)
            FlowLayout(spacing: 8) {
                ForEach(model.suggestions, id: \.self) { suggestion in
                    Button { model.useSuggestion(suggestion) } label: {
                        Text(suggestion)
                            .font(.callout)
                            .padding(.horizontal, 14).padding(.vertical, 9)
                            .background(Capsule().fill(.ultraThinMaterial))
                    }
                    .buttonStyle(.plain)
                }
            }
            if let error = model.errorMessage {
                Text(error).font(.footnote).foregroundStyle(.red)
            }
        }
        .padding()
    }
}

/// Minimal flow layout for the suggestion chips (wraps to the next line).
struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxWidth = proposal.width ?? .infinity
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0
        for view in subviews {
            let size = view.sizeThatFits(.unspecified)
            if x + size.width > maxWidth { x = 0; y += rowHeight + spacing; rowHeight = 0 }
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        return CGSize(width: maxWidth, height: y + rowHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX, y = bounds.minY, rowHeight: CGFloat = 0
        for view in subviews {
            let size = view.sizeThatFits(.unspecified)
            if x + size.width > bounds.maxX { x = bounds.minX; y += rowHeight + spacing; rowHeight = 0 }
            view.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}

#Preview {
    SearchView().environment(AppEnvironment.preview())
}
