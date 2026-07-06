import Foundation
import SwiftUI

@MainActor
@Observable
final class AlbumsViewModel {
    private let albumRepository: AlbumRepository
    private let albumService: AlbumService

    var albums: [Album] = []
    var isRegenerating = false

    init(albumRepository: AlbumRepository, albumService: AlbumService) {
        self.albumRepository = albumRepository
        self.albumService = albumService
    }

    var albumsByKind: [(kind: Album.Kind, albums: [Album])] {
        Dictionary(grouping: albums, by: \.kind)
            .map { (kind: $0.key, albums: $0.value) }
            .sorted { $0.kind.rawValue < $1.kind.rawValue }
    }

    func load() async {
        albums = (try? albumRepository.allAlbums()) ?? []
    }

    func regenerate() async {
        isRegenerating = true
        defer { isRegenerating = false }
        await albumService.regenerate()
        await load()
    }
}
