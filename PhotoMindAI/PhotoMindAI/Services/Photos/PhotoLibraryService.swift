import Foundation
import Photos
import UIKit

/// Wraps PhotoKit. Responsible for authorization, enumerating `PHAsset`s (photos, videos,
/// Live Photos, HEIC, RAW), observing library changes, and fetching image data for analysis
/// and thumbnails. It never mutates the library except for user-initiated deletes.
actor PhotoLibraryService {
    enum Authorization {
        case authorized, limited, denied, notDetermined
    }

    private let imageManager = PHCachingImageManager()

    func authorizationStatus() -> Authorization {
        switch PHPhotoLibrary.authorizationStatus(for: .readWrite) {
        case .authorized: return .authorized
        case .limited:    return .limited
        case .denied, .restricted: return .denied
        case .notDetermined: return .notDetermined
        @unknown default: return .denied
        }
    }

    func requestAuthorization() async -> Authorization {
        let status = await PHPhotoLibrary.requestAuthorization(for: .readWrite)
        switch status {
        case .authorized: return .authorized
        case .limited:    return .limited
        case .notDetermined: return .notDetermined
        default: return .denied
        }
    }

    /// Enumerate the whole library as lightweight `Asset` values (no pixel data). Handles all
    /// media subtypes; `isScreenshot` is detected from `PHAssetMediaSubtype`.
    func fetchAllAssets() -> [Asset] {
        let options = PHFetchOptions()
        options.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
        options.includeAssetSourceTypes = [.typeUserLibrary, .typeCloudShared, .typeiTunesSynced]
        let result = PHAsset.fetchAssets(with: options)

        var assets: [Asset] = []
        assets.reserveCapacity(result.count)
        result.enumerateObjects { phAsset, _, _ in
            assets.append(Self.map(phAsset))
        }
        Log.photos.info("Fetched \(assets.count) assets from Photos")
        return assets
    }

    private static func map(_ ph: PHAsset) -> Asset {
        let mediaType: Asset.MediaType
        if ph.mediaType == .video {
            mediaType = .video
        } else if ph.mediaSubtypes.contains(.photoLive) {
            mediaType = .livePhoto
        } else if ph.mediaSubtypes.contains(.photoHDR) == false,
                  let uti = ph.value(forKey: "uniformTypeIdentifier") as? String,
                  uti.contains("raw") {
            mediaType = .raw
        } else {
            mediaType = .photo
        }

        var asset = Asset.discovered(
            localIdentifier: ph.localIdentifier,
            mediaType: mediaType,
            creationDate: ph.creationDate,
            modificationDate: ph.modificationDate,
            pixelWidth: ph.pixelWidth,
            pixelHeight: ph.pixelHeight,
            durationSeconds: ph.duration,
            isFavorite: ph.isFavorite,
            latitude: ph.location?.coordinate.latitude,
            longitude: ph.location?.coordinate.longitude
        )
        asset.isScreenshot = ph.mediaSubtypes.contains(.photoScreenshot)
        return asset
    }

    // MARK: - Image data

    /// Full-image data suitable for analysis (Vision/OCR). Uses `.highQualityFormat` but
    /// requests a bounded target size to keep memory flat across 100k-scale batches.
    func imageData(for localIdentifier: String, targetMax: CGFloat = 1024) async -> Data? {
        guard let asset = phAsset(localIdentifier) else { return nil }
        return await withCheckedContinuation { continuation in
            let options = PHImageRequestOptions()
            options.isNetworkAccessAllowed = true        // fetch from iCloud if needed
            options.deliveryMode = .highQualityFormat
            options.resizeMode = .fast
            options.isSynchronous = false
            let target = CGSize(width: targetMax, height: targetMax)
            imageManager.requestImage(for: asset, targetSize: target,
                                      contentMode: .aspectFit, options: options) { image, _ in
                continuation.resume(returning: image?.jpegData(compressionQuality: 0.9))
            }
        }
    }

    /// Thumbnail data for grid display.
    func thumbnailData(for localIdentifier: String, pointSize: CGFloat, scale: CGFloat) async -> Data? {
        await imageData(for: localIdentifier, targetMax: pointSize * scale)
    }

    /// Delete assets from the Photos library (used by Cleanup). Triggers the system's
    /// confirmation UI; PhotoMind never deletes silently.
    func delete(localIdentifiers: [String]) async throws {
        let assets = PHAsset.fetchAssets(withLocalIdentifiers: localIdentifiers, options: nil)
        try await PHPhotoLibrary.shared().performChanges {
            PHAssetChangeRequest.deleteAssets(assets)
        }
    }

    private func phAsset(_ id: String) -> PHAsset? {
        PHAsset.fetchAssets(withLocalIdentifiers: [id], options: nil).firstObject
    }
}
