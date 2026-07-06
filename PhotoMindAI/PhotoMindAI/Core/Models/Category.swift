import Foundation
import SwiftUI

/// The controlled vocabulary PhotoMind classifies images into. Both the on-device Vision
/// classifier and the remote AI providers map their raw labels onto these buckets so the
/// rest of the app only ever deals with a stable, localized taxonomy.
enum PhotoCategory: String, Codable, CaseIterable, Identifiable, Sendable {
    case person
    case food
    case building
    case landscape
    case dog
    case cat
    case flower
    case receipt
    case qrCode
    case document
    case travel
    case drink
    case clothing
    case car
    case sport
    case screenshot
    case pet          // catch-all animal
    case other

    var id: String { rawValue }

    /// Localized display name (Japanese primary, matching the target market).
    var displayName: LocalizedStringKey {
        switch self {
        case .person:     return "人物"
        case .food:       return "料理"
        case .building:   return "建物"
        case .landscape:  return "風景"
        case .dog:        return "犬"
        case .cat:        return "猫"
        case .flower:     return "花"
        case .receipt:    return "レシート"
        case .qrCode:     return "QRコード"
        case .document:   return "書類"
        case .travel:     return "旅行"
        case .drink:      return "飲み物"
        case .clothing:   return "服"
        case .car:        return "車"
        case .sport:      return "スポーツ"
        case .screenshot: return "スクショ"
        case .pet:        return "ペット"
        case .other:      return "その他"
        }
    }

    var symbolName: String {
        switch self {
        case .person:     return "person.crop.circle"
        case .food:       return "fork.knife"
        case .building:   return "building.2"
        case .landscape:  return "mountain.2"
        case .dog:        return "dog"
        case .cat:        return "cat"
        case .flower:     return "leaf"
        case .receipt:    return "receipt"
        case .qrCode:     return "qrcode"
        case .document:   return "doc.text"
        case .travel:     return "airplane"
        case .drink:      return "cup.and.saucer"
        case .clothing:   return "tshirt"
        case .car:        return "car"
        case .sport:      return "sportscourt"
        case .screenshot: return "iphone"
        case .pet:        return "pawprint"
        case .other:      return "square.grid.2x2"
        }
    }

    var tint: Color {
        switch self {
        case .person:     return .pink
        case .food:       return .orange
        case .building:   return .brown
        case .landscape:  return .green
        case .dog, .cat, .pet: return .mint
        case .flower:     return .purple
        case .receipt, .document: return .gray
        case .qrCode:     return .indigo
        case .travel:     return .blue
        case .drink:      return .teal
        case .clothing:   return .cyan
        case .car:        return .red
        case .sport:      return .yellow
        case .screenshot: return .secondary
        case .other:      return .secondary
        }
    }
}

/// A category assignment for an asset with a confidence score from the classifier.
struct CategoryTag: Hashable, Codable, Sendable {
    let category: PhotoCategory
    let confidence: Double   // 0…1

    static let acceptanceThreshold: Double = 0.30
}
