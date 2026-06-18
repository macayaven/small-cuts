import AuthenticationServices
import SwiftUI

/// Holds the uploader's display handle, derived from Sign in with Apple. The
/// handle is mapped into the `/v1/cuts` `uploader_hf_username` field (a naming
/// stretch on that contract field; a clean `uploader_provider`+`uploader_handle`
/// generalization is a deferred contract-change). Persisted across launches.
///
/// DEVICE TODO: Sign in with Apple needs the `com.apple.developer.applesignin`
/// entitlement to function on a real device. The code below compiles and the
/// simulator build is green without it; add the entitlement before device runs.
@MainActor
final class IdentityStore: ObservableObject {
    @Published private(set) var handle: String?

    private let defaultsKey = "smallcutslite.uploaderHandle"

    init() {
        handle = UserDefaults.standard.string(forKey: defaultsKey)
    }

    var isSignedIn: Bool { handle != nil }

    /// The handle sent as `uploader_hf_username`. Sign-in is optional, so this
    /// falls back to a default — recording/upload is never blocked on auth.
    var uploaderHandle: String { handle ?? "ios-user" }

    /// Configure the Apple ID request (only the name is needed to build a handle).
    func configure(_ request: ASAuthorizationAppleIDRequest) {
        request.requestedScopes = [.fullName]
    }

    /// Handle the Apple sign-in result, deriving and persisting a handle.
    func complete(_ result: Result<ASAuthorization, Error>) {
        guard case let .success(auth) = result,
              let credential = auth.credential as? ASAuthorizationAppleIDCredential
        else { return }
        let derived = Self.deriveHandle(from: credential)
        handle = derived
        UserDefaults.standard.set(derived, forKey: defaultsKey)
    }

    func signOut() {
        handle = nil
        UserDefaults.standard.removeObject(forKey: defaultsKey)
    }

    private static func deriveHandle(from credential: ASAuthorizationAppleIDCredential) -> String {
        if let given = credential.fullName?.givenName, !given.isEmpty {
            return given
        }
        return "user-" + credential.user.prefix(6)
    }
}
