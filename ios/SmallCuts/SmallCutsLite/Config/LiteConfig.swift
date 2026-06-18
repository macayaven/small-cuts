import Foundation

/// Reads the embedded Modal configuration. The token is injected via the
/// gitignored `Secrets.swift` (build-config style), never hardcoded in tracked
/// source. `isConfigured` gates the upload so the UI can show a clear message
/// when the token has not been filled in.
enum LiteConfig {
    static var modalBaseURL: URL? { URL(string: Secrets.modalAPIBaseURL) }
    static var modalToken: String { Secrets.modalAPIToken }
    static var isConfigured: Bool { modalBaseURL != nil && !modalToken.isEmpty }
}
