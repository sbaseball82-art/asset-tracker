import SwiftUI

/// Auto-generated smart albums grouped by kind (旅行 / 仕事 / 家族 / 食事 / ペット / レシート).
/// Trip cards surface the AI summary line.
struct AlbumsView: View {
    @Environment(AppEnvironment.self) private var env
    @State private var model: AlbumsViewModel?

    var body: some View {
        NavigationStack {
            Group {
                if let model { content(model) } else { ProgressView() }
            }
            .navigationTitle("アルバム")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        Task { await model?.regenerate() }
                    } label: {
                        if model?.isRegenerating == true { ProgressView() }
                        else { Image(systemName: "arrow.triangle.2.circlepath") }
                    }
                }
            }
        }
        .task {
            if model == nil {
                model = AlbumsViewModel(albumRepository: env.albumRepository,
                                        albumService: env.albumService)
            }
            await model?.load()
        }
    }

    @ViewBuilder
    private func content(_ model: AlbumsViewModel) -> some View {
        if model.albums.isEmpty {
            ContentUnavailableView {
                Label("アルバムがまだありません", systemImage: "rectangle.stack")
            } description: {
                Text("解析が進むと、旅行・食事・ペットなどのアルバムが自動生成されます。")
            } actions: {
                Button("今すぐ生成") { Task { await model.regenerate() } }
                    .buttonStyle(.borderedProminent)
            }
        } else {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 24) {
                    ForEach(model.albumsByKind, id: \.kind) { section in
                        VStack(alignment: .leading, spacing: 10) {
                            Label(section.kind.title, systemImage: section.kind.symbolName)
                                .font(.title3.weight(.bold))
                                .padding(.horizontal)
                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack(spacing: 14) {
                                    ForEach(section.albums) { album in
                                        NavigationLink(value: album) {
                                            AlbumCard(album: album)
                                        }
                                        .buttonStyle(.plain)
                                    }
                                }
                                .padding(.horizontal)
                            }
                        }
                    }
                }
                .padding(.vertical)
            }
            .navigationDestination(for: Album.self) { AlbumDetailView(album: $0) }
        }
    }
}

struct AlbumCard: View {
    let album: Album

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ZStack {
                if let cover = album.coverAssetIdentifier {
                    AsyncThumbnailView(localIdentifier: cover, pointSize: 220)
                } else {
                    Rectangle().fill(.quaternary)
                }
            }
            .frame(width: 220, height: 150)
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))

            VStack(alignment: .leading, spacing: 3) {
                Text(album.title).font(.headline).lineLimit(1)
                if let summary = album.aiSummary {
                    Text(summary).font(.caption2).foregroundStyle(.secondary).lineLimit(2)
                } else if let subtitle = album.subtitle {
                    Text(subtitle).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
                Text("\(album.assetCount)枚").font(.caption2).foregroundStyle(.tertiary)
            }
            .padding(.top, 8)
            .frame(width: 220, alignment: .leading)
        }
    }
}

#Preview {
    AlbumsView().environment(AppEnvironment.preview())
}
