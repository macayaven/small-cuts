import MWDATCore
import SwiftUI
import UIKit

/// Small Cuts Lite — the record→upload companion app.
///
/// Mission (and nothing more): record up to 60 s from the phone camera or paired
/// Meta Ray-Ban glasses and send the finished clip to the Modal `/v1/cuts`
/// endpoint exactly the way the Gradio upload feature does. The narrated result
/// is produced server-side and surfaces in the Gradio library.

/// The AppDelegate exists for one reason: defer `Wearables.configure()` to the
/// next runloop turn (configuring too early crashes the BLE transport on
/// hardware — see ios/SmallCuts/CLAUDE.md "Bug 1"). The DAT pipeline reuses the
/// same `WearablesConfigurator` gate shared from the SmallCuts target.
final class LiteAppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        DispatchQueue.main.async {
            MainActor.assumeIsolated {
                do {
                    try Wearables.configure()
                    WearablesConfigurator.shared.markConfigured()
                } catch {
                    WearablesConfigurator.shared.markFailed(
                        "Wearables.configure() failed: \(error.localizedDescription)"
                    )
                }
            }
        }
        return true
    }
}

@main
struct SmallCutsLiteApp: App {
    @UIApplicationDelegateAdaptor(LiteAppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup {
            LiteCaptureView()
                .onOpenURL { url in
                    // Return leg of the DAT registration deep link
                    // (Meta AI app -> smallcutslite://...). Wait for the configure
                    // gate before touching Wearables.shared (Bug 2).
                    Task { @MainActor in
                        guard (try? await WearablesConfigurator.shared.awaitConfigured()) != nil else {
                            return
                        }
                        _ = try? await Wearables.shared.handleUrl(url)
                    }
                }
        }
    }
}
