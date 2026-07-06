import SwiftUI

/// Loads a thumbnail for an asset from the Photos library asynchronously, with a placeholder
/// and an in-memory cache to keep grid scrolling smooth at 100k-scale. Cancels the load when
/// the cell scrolls away.
struct AsyncThumbnailView: View {
    let localIdentifier: String
    var pointSize: CGFloat = 120

    @Environment(AppEnvironment.self) private var env
    @Environment(\.displayScale) private var displayScale
    @State private var image: UIImage?

    var body: some View {
        ZStack {
            if let image {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
            } else {
                Rectangle()
                    .fill(.quaternary)
                    .overlay { ProgressView().controlSize(.small) }
            }
        }
        .task(id: localIdentifier) {
            if let cached = ThumbnailCache.shared.image(for: localIdentifier) {
                image = cached; return
            }
            let data = await env.photos.thumbnailData(
                for: localIdentifier, pointSize: pointSize, scale: displayScale)
            if let data, let ui = UIImage(data: data) {
                ThumbnailCache.shared.insert(ui, for: localIdentifier)
                image = ui
            }
        }
    }
}

/// Bounded NSCache of decoded thumbnails.
final class ThumbnailCache: @unchecked Sendable {
    static let shared = ThumbnailCache()
    private let cache = NSCache<NSString, UIImage>()
    private init() { cache.countLimit = 600 }

    func image(for id: String) -> UIImage? { cache.object(forKey: id as NSString) }
    func insert(_ image: UIImage, for id: String) { cache.setObject(image, forKey: id as NSString) }
}
