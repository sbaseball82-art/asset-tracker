import SwiftUI
import MapKit

/// A single album: AI summary header, optional map of the trip location, and the member grid.
struct AlbumDetailView: View {
    let album: Album
    @Environment(AppEnvironment.self) private var env
    @State private var members: [Asset] = []

    private let columns = [GridItem(.adaptive(minimum: 108), spacing: 2)]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let summary = album.aiSummary {
                    GlassCard {
                        VStack(alignment: .leading, spacing: 6) {
                            Label("AI 要約", systemImage: "sparkles").font(.caption.weight(.semibold))
                                .foregroundStyle(.secondary)
                            Text(summary).font(.title3.weight(.semibold))
                        }
                    }
                    .padding(.horizontal)
                }

                if let lat = album.latitude, let lon = album.longitude {
                    Map(initialPosition: .region(MKCoordinateRegion(
                        center: .init(latitude: lat, longitude: lon),
                        span: .init(latitudeDelta: 0.4, longitudeDelta: 0.4)))) {
                        Marker(album.title, coordinate: .init(latitude: lat, longitude: lon))
                    }
                    .frame(height: 160)
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                    .padding(.horizontal)
                    .allowsHitTesting(false)
                }

                LazyVGrid(columns: columns, spacing: 2) {
                    ForEach(members) { asset in
                        NavigationLink(value: asset) {
                            AsyncThumbnailView(localIdentifier: asset.localIdentifier)
                                .aspectRatio(1, contentMode: .fill).clipped()
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .padding(.vertical)
        }
        .navigationTitle(album.title)
        .navigationBarTitleDisplayMode(.inline)
        .navigationDestination(for: Asset.self) { AssetDetailView(asset: $0) }
        .task {
            if let id = album.id {
                members = (try? env.albumRepository.members(ofAlbumID: id)) ?? []
            }
        }
    }
}
