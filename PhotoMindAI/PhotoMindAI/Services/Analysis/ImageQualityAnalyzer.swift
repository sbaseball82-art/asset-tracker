import Foundation
import CoreImage
import Accelerate

/// Computes a perceptual hash and a sharpness/quality score from image data — the inputs to
/// duplicate detection, blur detection and the cleanup suggestions. All on-device.
struct ImageQualityAnalyzer: Sendable {
    struct Metrics: Sendable {
        let perceptualHash: UInt64   // 64-bit dHash
        let sharpness: Double        // variance of Laplacian, higher = sharper
        let qualityScore: Double     // normalized 0…1
    }

    private let context = CIContext(options: [.workingColorSpace: NSNull()])

    func analyze(imageJPEG: Data) -> Metrics {
        let hash = perceptualHash(imageJPEG: imageJPEG)
        let sharp = sharpness(imageJPEG: imageJPEG)
        // Map raw Laplacian variance to 0…1 with a soft knee around a "clearly sharp" value.
        let quality = min(1.0, sharp / 500.0)
        return Metrics(perceptualHash: hash, sharpness: sharp, qualityScore: quality)
    }

    /// Difference-hash (dHash): downscale to 9x8 grayscale, compare adjacent pixels.
    func perceptualHash(imageJPEG: Data) -> UInt64 {
        guard let gray = grayscalePixels(imageJPEG: imageJPEG, width: 9, height: 8) else { return 0 }
        var hash: UInt64 = 0
        var bit = 0
        for row in 0..<8 {
            for col in 0..<8 {
                let left = gray[row * 9 + col]
                let right = gray[row * 9 + col + 1]
                if left > right { hash |= (1 << UInt64(bit)) }
                bit += 1
            }
        }
        return hash
    }

    /// Variance of the Laplacian on a small grayscale buffer — the classic blur metric.
    func sharpness(imageJPEG: Data) -> Double {
        let w = 64, h = 64
        guard let gray = grayscalePixels(imageJPEG: imageJPEG, width: w, height: h) else { return 0 }
        var lap: [Double] = []
        lap.reserveCapacity((w - 2) * (h - 2))
        for y in 1..<(h - 1) {
            for x in 1..<(w - 1) {
                let c = Double(gray[y * w + x])
                let up = Double(gray[(y - 1) * w + x])
                let down = Double(gray[(y + 1) * w + x])
                let left = Double(gray[y * w + x - 1])
                let right = Double(gray[y * w + x + 1])
                lap.append(up + down + left + right - 4 * c)
            }
        }
        guard !lap.isEmpty else { return 0 }
        let mean = lap.reduce(0, +) / Double(lap.count)
        let variance = lap.reduce(0) { $0 + ($1 - mean) * ($1 - mean) } / Double(lap.count)
        return variance
    }

    /// Renders to a `width`x`height` grayscale UInt8 buffer via CoreImage/vImage-friendly path.
    private func grayscalePixels(imageJPEG: Data, width: Int, height: Int) -> [UInt8]? {
        guard let cg = ImageDownscaler.cgImage(from: imageJPEG, maxDimension: CGFloat(max(width, height) * 4)),
              let ci = Optional(CIImage(cgImage: cg)) else { return nil }
        let scaleX = CGFloat(width) / ci.extent.width
        let scaleY = CGFloat(height) / ci.extent.height
        let scaled = ci
            .transformed(by: CGAffineTransform(scaleX: scaleX, y: scaleY))
            .applyingFilter("CIPhotoEffectMono")

        var buffer = [UInt8](repeating: 0, count: width * height)
        let cs = CGColorSpaceCreateDeviceGray()
        buffer.withUnsafeMutableBytes { ptr in
            context.render(scaled,
                           toBitmap: ptr.baseAddress!,
                           rowBytes: width,
                           bounds: CGRect(x: 0, y: 0, width: width, height: height),
                           format: .R8,
                           colorSpace: cs)
        }
        return buffer
    }
}

extension UInt64 {
    /// Hamming distance between two perceptual hashes; ≤10 typically means "near-duplicate".
    func hammingDistance(to other: UInt64) -> Int {
        (self ^ other).nonzeroBitCount
    }
}
