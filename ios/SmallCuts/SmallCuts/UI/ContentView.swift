import SwiftUI

/// Capture UI: engine + style controls, source toggle, Connect/Start/Stop,
/// live preview, stats, narration caption. Off-Brand palette — near-black
/// background, gold accent. The full loop (gate → envelope → engine →
/// in-ear narration) runs in the simulator against a real local engine.
struct ContentView: View {

    enum SourceKind: String, CaseIterable, Identifiable {
        case simulated = "Simulated"
        case glasses = "Glasses"
        var id: String { rawValue }
    }

    /// The six director's-cut styles (engine `styles.py`).
    static let styleKeys = ["deadpan", "noir", "nature_doc", "trailer", "telenovela", "symmetrist"]

    private static let gold = Color(red: 212 / 255, green: 175 / 255, blue: 55 / 255)
    private static let background = Color(red: 0.06, green: 0.06, blue: 0.07)

    @StateObject private var controller = GlassesSessionController()
    @StateObject private var coordinator = CaptureCoordinator()
    #if DEBUG
    @StateObject private var mockGlasses = MockGlassesDebugController()
    #endif

    @AppStorage("engineURL") private var engineURLString = "ws://mac-studio:8077"
    @AppStorage("styleKey") private var styleKey = "deadpan"

    @State private var sourceKind: SourceKind = .simulated
    @State private var startError: String?

    var body: some View {
        VStack(spacing: 12) {
            Text("SMALL CUTS")
                .font(.system(.headline, design: .monospaced))
                .tracking(4)
                .foregroundStyle(Self.gold)

            HStack(spacing: 8) {
                Text("engine")
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.white.opacity(0.5))
                TextField("ws://mac-studio:8077", text: $engineURLString)
                    .font(.system(.footnote, design: .monospaced))
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                    .foregroundStyle(.white.opacity(0.9))
                    .disabled(coordinator.running)
            }

            HStack(spacing: 8) {
                Text("style")
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.white.opacity(0.5))
                Picker("Style", selection: $styleKey) {
                    ForEach(Self.styleKeys, id: \.self) { key in
                        Text(key).tag(key)
                    }
                }
                .pickerStyle(.menu)
                .tint(Self.gold)
                .disabled(coordinator.running)
                Spacer()
            }

            Picker("Source", selection: $sourceKind) {
                ForEach(SourceKind.allCases) { kind in
                    Text(kind.rawValue).tag(kind)
                }
            }
            .pickerStyle(.segmented)
            .disabled(coordinator.running)

            Text(statusText)
                .font(.system(.footnote, design: .monospaced))
                .foregroundStyle(.white.opacity(0.85))
                .lineLimit(2)
                .frame(maxWidth: .infinity, alignment: .leading)

            previewPane

            statsLine

            captionPane

            if let message = startError ?? coordinator.lastError {
                Text(message)
                    .font(.system(.caption2, design: .monospaced))
                    .foregroundStyle(.red.opacity(0.9))
                    .lineLimit(2)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }

            HStack(spacing: 12) {
                Button("Connect") { connectGlasses() }
                    .buttonStyle(GoldButtonStyle(filled: false))
                    .disabled(sourceKind != .glasses || coordinator.running || coordinator.starting)
                Button("Start") { start() }
                    .buttonStyle(GoldButtonStyle(filled: true))
                    .disabled(sourceKind == .glasses || coordinator.running || coordinator.starting)
                Button("Mark") { coordinator.fireManual() }
                    .buttonStyle(GoldButtonStyle(filled: false))
                    .disabled(!coordinator.running)
                Button("Stop") { stopTapped() }
                    .buttonStyle(GoldButtonStyle(filled: false))
                    .disabled(stopDisabled)
            }

            #if DEBUG
            Toggle(isOn: Binding(
                get: { mockGlasses.isActive },
                set: { mockGlasses.setActive($0) }
            )) {
                Text("Mock glasses (MockDeviceKit)")
                    .font(.system(.footnote, design: .monospaced))
                    .foregroundStyle(.white.opacity(0.6))
            }
            .tint(Self.gold)
            #endif
        }
        .padding(20)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Self.background.ignoresSafeArea())
        .preferredColorScheme(.dark)
    }

    private var previewPane: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 12)
                .fill(Color.black)
                .strokeBorder(Self.gold.opacity(0.35), lineWidth: 1)
            if let preview = coordinator.preview {
                Image(uiImage: preview)
                    .resizable()
                    .scaledToFit()
                    .clipShape(RoundedRectangle(cornerRadius: 12))
            } else {
                Text("no frames yet")
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.white.opacity(0.3))
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .overlay(alignment: .bottomTrailing) {
            if coordinator.frameCount > 0 {
                Text("\(coordinator.frameCount) frames")
                    .font(.system(.caption2, design: .monospaced))
                    .foregroundStyle(Self.gold)
                    .padding(8)
            }
        }
    }

    private var statsLine: some View {
        let stats = coordinator.stats
        return Text(
            "sent \(stats.sent) · ok \(stats.accepted) · coal \(stats.coalesced) · "
                + "rej \(stats.rejected) · err \(stats.errors) · played \(stats.scenesPlayed)"
        )
        .font(.system(.caption2, design: .monospaced))
        .foregroundStyle(.white.opacity(0.6))
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private var captionPane: some View {
        if case .playing(let narration) = coordinator.playback {
            Text("▶ \(narration)")
                .font(.system(.footnote, design: .monospaced))
                .foregroundStyle(Self.gold)
                .lineLimit(3)
                .frame(maxWidth: .infinity, alignment: .leading)
        } else if let caption = coordinator.caption {
            Text(caption)
                .font(.system(.footnote, design: .monospaced))
                .foregroundStyle(Self.gold.opacity(0.55))
                .lineLimit(3)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var statusText: String {
        let engine = coordinator.running ? " · \(coordinator.engineLink.label)" : ""
        switch sourceKind {
        case .simulated:
            return (coordinator.running ? "Simulated — streaming" : "Simulated — idle") + engine
        case .glasses:
            return controller.state.label + engine
        }
    }

    /// Stop must work even with no running coordinator: a Connect-only flow
    /// (registering/connecting/streaming) is cancelled via controller.stop().
    private var stopDisabled: Bool {
        if coordinator.running { return false }
        guard sourceKind == .glasses else { return true }
        switch controller.state {
        case .idle, .error:
            return true
        default:
            return false
        }
    }

    private func connectGlasses() {
        startError = nil
        start()
    }

    private func stopTapped() {
        let wasRunning = coordinator.running
        coordinator.stop()
        // No FrameSource was adopting the controller — stop it directly so an
        // in-flight or established connect is cancelled/torn down too.
        if !wasRunning, sourceKind == .glasses {
            controller.stop()
        }
    }

    private func start() {
        startError = nil
        guard let engineURL = URL(string: engineURLString.trimmingCharacters(in: .whitespaces)),
              let scheme = engineURL.scheme, scheme == "ws" || scheme == "wss"
        else {
            startError = "engine URL must look like ws://host:port"
            return
        }

        let source: any FrameSource
        switch sourceKind {
        case .simulated:
            source = SimulatedFrameSource()
        case .glasses:
            source = GlassesFrameSource(controller: controller)
        }

        Task {
            do {
                try await coordinator.start(source: source, engineURL: engineURL, styleKey: styleKey)
            } catch {
                startError = error.localizedDescription
                coordinator.stop()
            }
        }
    }
}

private struct GoldButtonStyle: ButtonStyle {
    let filled: Bool
    private static let gold = Color(red: 212 / 255, green: 175 / 255, blue: 55 / 255)

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(.subheadline, design: .monospaced).weight(.semibold))
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(filled ? Self.gold : Color.clear)
                    .strokeBorder(Self.gold, lineWidth: 1)
            )
            .foregroundStyle(filled ? Color.black : Self.gold)
            .opacity(configuration.isPressed ? 0.6 : 1.0)
    }
}

#Preview {
    ContentView()
}
