import Foundation

/// The narrated scene returned by the Modal `/v1/cuts` pipeline. Mirrors the
/// `scene` payload produced by `modal_app/small_cuts_postcut.py` — only
/// `scene_id` is guaranteed; everything else is optional so the client stays
/// tolerant of contract additions (decoded with `.convertFromSnakeCase`).
struct ModalScene: Decodable, Equatable {
    let sceneId: String
    let title: String?
    let narration: String?
    let styleKey: String?
    let createdAt: String?
    let duration: Double?
    let media: Media?

    struct Media: Decodable, Equatable {
        let frameUrl: String?
        let cardUrl: String?
        let clipUrl: String?
        let audioUrl: String?
    }
}
