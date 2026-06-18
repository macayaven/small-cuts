// Template for `SmallCutsLite/Config/Secrets.swift` (which is gitignored).
//
// Copy this file to `Secrets.swift` and paste the Modal API token before
// building on device. The token is the embedded service credential for the
// `/v1/cuts` endpoint (see the coordination note / plan: "embed Bearer token").
// It is extractable from the app binary — fine for TestFlight/internal/portfolio
// builds, NOT for a public App Store release.
//
// NOTE: this file is excluded from the SmallCutsLite target in project.yml, so
// it never collides with the real `Secrets` enum.
enum Secrets {
    static let modalAPIBaseURL = "https://macayaven--small-cuts-postcut-api.modal.run"
    static let modalAPIToken = ""
}
