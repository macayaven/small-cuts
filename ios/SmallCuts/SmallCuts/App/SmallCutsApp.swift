import MWDATCore
import SwiftUI
import UIKit

/// The AppDelegate exists for exactly one reason: launch Bug 1.
///
/// Calling `Wearables.configure()` too early (e.g. in `App.init`) crashes the
/// Bluetooth transport on hardware while passing every unit test. The verified
/// fix is to defer it to `didFinishLaunchingWithOptions` *and* push it one more
/// runloop turn out via `DispatchQueue.main.async`.
final class AppDelegate: NSObject, UIApplicationDelegate {

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        // Deferred SDK configuration — next runloop turn, once the app is responsive.
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
struct SmallCutsApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup {
            ContentView()
                .onOpenURL { url in
                    // Return leg of the DAT registration deep link
                    // (Meta AI app -> smallcuts://...). Await the configure gate
                    // (Bug 2) before touching Wearables.shared.
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
