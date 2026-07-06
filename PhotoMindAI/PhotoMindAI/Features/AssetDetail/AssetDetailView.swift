import SwiftUI
import MapKit

/// Full-screen asset detail: large image, AI caption, category chips, recognized text (OCR),
/// location map, and metadata. Reads freshly-analyzed data from the repository.
struct AssetDetailView: View {
    let asset: Asset
    @Environment(AppEnvironment.self) private var env
    @State private var categories: [CategoryTag] = []
    @State private var fullImage: UIImage?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                image
                if let caption = asset.captionSummary {
                    GlassCard {
                        VStack(alignment: .leading, spacing: 6) {
                            Label("AI キャプション", systemImage: "sparkles")
                                .font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                            Text(caption).font(.body)
                        }
                    }
                    .padding(.horizontal)
                }
                if !categories.isEmpty {
                    FlowLayout(spacing: 8) {
                        ForEach(categories, id: \.category) { CategoryChip(category: $0.category) }
                    }
                    .padding(.horizontal)
                }
                if let ocr = asset.ocrText, !ocr.isEmpty {
                    GlassCard {
                        VStack(alignment: .leading, spacing: 6) {
                            Label("認識された文字", systemImage: "text.viewfinder")
                                .font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                            Text(ocr).font(.callout).textSelection(.enabled)
                        }
                    }
                    .padding(.horizontal)
                }
                if let lat = asset.latitude, let lon = asset.longitude {
                    Map(initialPosition: .region(MKCoordinateRegion(
                        center: .init(latitude: lat, longitude: lon),
                        span: .init(latitudeDelta: 0.02, longitudeDelta: 0.02)))) {
                        Marker(asset.placeName ?? "撮影地", coordinate: .init(latitude: lat, longitude: lon))
                    }
                    .frame(height: 160).clipShape(RoundedRectangle(cornerRadius: 16))
                    .padding(.horizontal).allowsHitTesting(false)
                }
                metadata
            }
            .padding(.vertical)
        }
        .navigationTitle(asset.creationDate?.formatted(date: .abbreviated, time: .shortened) ?? "写真")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            if let id = asset.id { categories = (try? env.assetRepository.categories(forAssetID: id)) ?? [] }
            if let data = await env.photos.imageData(for: asset.localIdentifier, targetMax: 1600) {
                fullImage = UIImage(data: data)
            }
        }
    }

    @ViewBuilder private var image: some View {
        ZStack {
            if let fullImage {
                Image(uiImage: fullImage).resizable().scaledToFit()
            } else {
                AsyncThumbnailView(localIdentifier: asset.localIdentifier, pointSize: 400)
                    .aspectRatio(asset.aspectRatio, contentMode: .fit)
            }
        }
        .frame(maxWidth: .infinity)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private var metadata: some View {
        VStack(alignment: .leading, spacing: 8) {
            metaRow("種類", value: mediaLabel)
            metaRow("サイズ", value: "\(asset.pixelWidth) × \(asset.pixelHeight)")
            if asset.mediaType == .video {
                metaRow("長さ", value: String(format: "%.0f 秒", asset.durationSeconds))
            }
            if let place = asset.placeName { metaRow("場所", value: place) }
            metaRow("品質スコア", value: String(format: "%.2f", asset.qualityScore))
        }
        .padding(.horizontal)
    }

    private func metaRow(_ label: String, value: String) -> some View {
        HStack {
            Text(label).foregroundStyle(.secondary)
            Spacer()
            Text(value)
        }
        .font(.callout)
    }

    private var mediaLabel: String {
        switch asset.mediaType {
        case .photo: return "写真"; case .video: return "動画"
        case .livePhoto: return "Live Photo"; case .raw: return "RAW"
        }
    }
}
