import SwiftUI

/// A reusable "glass" container matching the iOS 26 Liquid Glass aesthetic. On iOS 18 it
/// degrades gracefully to a regular material card. Used across headers, summaries and the
/// paywall so the surface treatment is consistent app-wide.
struct GlassCard<Content: View>: View {
    var cornerRadius: CGFloat = 22
    @ViewBuilder var content: Content

    var body: some View {
        content
            .padding(16)
            .background {
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(.ultraThinMaterial)
                    .overlay {
                        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                            .strokeBorder(.white.opacity(0.12), lineWidth: 0.5)
                    }
                    .shadow(color: .black.opacity(0.15), radius: 12, y: 6)
            }
    }
}

/// A small capsule chip for a photo category, tinted by the category.
struct CategoryChip: View {
    let category: PhotoCategory
    var isSelected: Bool = false

    var body: some View {
        Label(category.displayName, systemImage: category.symbolName)
            .font(.caption.weight(.medium))
            .padding(.horizontal, 12)
            .padding(.vertical, 7)
            .background(
                Capsule().fill(isSelected ? category.tint.opacity(0.9) : category.tint.opacity(0.16))
            )
            .foregroundStyle(isSelected ? .white : category.tint)
    }
}

/// The freemium "残り 42 回" pill shown in the search bar area.
struct RemainingSearchesPill: View {
    let remaining: Int
    let isUnlimited: Bool
    var onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            if isUnlimited {
                Label("無制限", systemImage: "infinity")
            } else {
                Label("残り \(remaining) 回", systemImage: "sparkles")
            }
        }
        .font(.caption.weight(.semibold))
        .padding(.horizontal, 10).padding(.vertical, 6)
        .background(Capsule().fill(.ultraThinMaterial))
        .foregroundStyle(remaining == 0 && !isUnlimited ? .red : .secondary)
    }
}
