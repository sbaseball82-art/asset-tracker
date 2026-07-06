import SwiftUI

/// Calendar / timeline view. Switches between month, trip, and event groupings.
struct CalendarScreen: View {
    @Environment(AppEnvironment.self) private var env
    @State private var model: CalendarViewModel?

    private let columns = [GridItem(.adaptive(minimum: 80), spacing: 2)]

    var body: some View {
        NavigationStack {
            Group {
                if let model { content(model) } else { ProgressView() }
            }
            .navigationTitle("カレンダー")
        }
        .task {
            if model == nil {
                model = CalendarViewModel(assetRepository: env.assetRepository,
                                          albumRepository: env.albumRepository)
            }
            await model?.load()
        }
    }

    @ViewBuilder
    private func content(_ model: CalendarViewModel) -> some View {
        @Bindable var model = model
        VStack(spacing: 0) {
            Picker("表示", selection: $model.mode) {
                ForEach(CalendarViewModel.Mode.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .padding()

            ScrollView {
                switch model.mode {
                case .month: monthList(model)
                case .trip, .event: tripList(model)
                }
            }
            .navigationDestination(for: Asset.self) { AssetDetailView(asset: $0) }
            .navigationDestination(for: Album.self) { AlbumDetailView(album: $0) }
        }
    }

    private func monthList(_ model: CalendarViewModel) -> some View {
        LazyVStack(alignment: .leading, spacing: 20, pinnedViews: [.sectionHeaders]) {
            ForEach(model.months) { bucket in
                Section {
                    LazyVGrid(columns: columns, spacing: 2) {
                        ForEach(bucket.assets.prefix(30)) { asset in
                            NavigationLink(value: asset) {
                                AsyncThumbnailView(localIdentifier: asset.localIdentifier, pointSize: 90)
                                    .aspectRatio(1, contentMode: .fill).clipped()
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, 2)
                } header: {
                    HStack {
                        Text(bucket.title).font(.headline)
                        Spacer()
                        Text("\(bucket.assets.count)枚").font(.caption).foregroundStyle(.secondary)
                    }
                    .padding(.horizontal)
                    .padding(.vertical, 6)
                    .background(.bar)
                }
            }
        }
    }

    private func tripList(_ model: CalendarViewModel) -> some View {
        LazyVStack(spacing: 14) {
            ForEach(model.trips) { trip in
                NavigationLink(value: trip) {
                    HStack(spacing: 12) {
                        if let cover = trip.coverAssetIdentifier {
                            AsyncThumbnailView(localIdentifier: cover, pointSize: 140)
                                .frame(width: 88, height: 88)
                                .clipShape(RoundedRectangle(cornerRadius: 12))
                        }
                        VStack(alignment: .leading, spacing: 4) {
                            Text(trip.title).font(.headline)
                            if let summary = trip.aiSummary ?? trip.subtitle {
                                Text(summary).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                            }
                        }
                        Spacer()
                        Image(systemName: "chevron.right").foregroundStyle(.tertiary)
                    }
                    .padding(.horizontal)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.vertical)
    }
}

#Preview {
    CalendarScreen().environment(AppEnvironment.preview())
}
