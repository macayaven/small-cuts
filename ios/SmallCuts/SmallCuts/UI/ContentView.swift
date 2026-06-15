import SwiftUI

/// Wearer-facing capture UI.
///
/// The main surface is intentionally only a take recorder: Action starts a
/// POV take, Cut submits it, and narration returns through the existing engine
/// socket. Engine configuration and traces live in the Admin section.
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
    private static let panel = Color(red: 0.10, green: 0.10, blue: 0.12)

    @StateObject private var controller = GlassesSessionController()
    @StateObject private var coordinator = CaptureCoordinator()
    #if DEBUG
    @StateObject private var mockGlasses = MockGlassesDebugController()
    #endif

    @AppStorage("engineURL") private var engineURLString = "ws://mac-studio:8077"
    @AppStorage("styleKey") private var styleKey = "deadpan"

    @State private var sourceKind: SourceKind = .glasses
    @State private var startError: String?
    @State private var showAdmin = false

    var body: some View {
        GeometryReader { proxy in
            let metrics = layoutMetrics(for: proxy.size)

            ScrollView {
                VStack(spacing: metrics.spacing) {
                    header

                    TimelineView(.periodic(from: .now, by: 1)) { timeline in
                        statusBlock(now: timeline.date)
                    }

                    previewPane(maxHeight: metrics.previewHeight)

                    captionPane

                    takeControls

                    adminSection
                }
                .padding(.horizontal, 20)
                .padding(.vertical, metrics.verticalPadding)
                .frame(minHeight: proxy.size.height, alignment: .top)
            }
            .scrollIndicators(.hidden)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Self.background.ignoresSafeArea())
        .preferredColorScheme(.dark)
    }

    private var header: some View {
        HStack {
            Text("SMALL CUTS")
                .font(.system(.title2, design: .monospaced).weight(.semibold))
                .tracking(6)
                .foregroundStyle(Self.gold)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            Spacer()
            Button {
                showAdmin.toggle()
            } label: {
                Image(systemName: "gearshape")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundStyle(Self.gold)
                    .frame(width: 44, height: 44)
                    .contentShape(Rectangle())
            }
            .accessibilityLabel("Admin")
        }
    }

    private func statusBlock(now: Date) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(primaryStatus(now: now))
                .font(.system(.title3, design: .monospaced).weight(.semibold))
                .foregroundStyle(.white.opacity(0.92))
                .lineLimit(2)
                .minimumScaleFactor(0.75)
            Text(detailStatus)
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(.white.opacity(0.55))
                .lineLimit(2)
                .minimumScaleFactor(0.75)
            if let message = startError ?? coordinator.lastError {
                Text(message)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.red.opacity(0.9))
                    .lineLimit(3)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func previewPane(maxHeight: CGFloat) -> some View {
        ZStack {
            RoundedRectangle(cornerRadius: 14)
                .fill(Color.black)
                .overlay(
                    RoundedRectangle(cornerRadius: 14)
                        .stroke(Self.gold.opacity(0.35), lineWidth: 1)
                )
            if let preview = coordinator.preview {
                Image(uiImage: preview)
                    .resizable()
                    .scaledToFit()
                    .clipShape(RoundedRectangle(cornerRadius: 14))
            } else {
                Text("no frames yet")
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.white.opacity(0.3))
            }
        }
        .aspectRatio(9.0 / 16.0, contentMode: .fit)
        .frame(maxWidth: maxHeight * 9.0 / 16.0, maxHeight: maxHeight)
        .overlay(alignment: .bottomTrailing) {
            if coordinator.frameCount > 0 {
                Text("\(coordinator.frameCount) frames")
                    .font(.system(.caption2, design: .monospaced))
                    .foregroundStyle(Self.gold)
                    .padding(8)
            }
        }
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder
    private var captionPane: some View {
        if case .playing(let narration) = coordinator.playback {
            Text(narration)
                .font(.system(.footnote, design: .monospaced))
                .foregroundStyle(Self.gold)
                .lineLimit(4)
                .frame(maxWidth: .infinity, alignment: .leading)
        } else if let caption = coordinator.caption {
            Text(caption)
                .font(.system(.footnote, design: .monospaced))
                .foregroundStyle(Self.gold.opacity(0.7))
                .lineLimit(4)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var takeControls: some View {
        HStack(spacing: 14) {
            Button("Action!") { actionTapped() }
                .buttonStyle(TakeButtonStyle(role: .action))
                .disabled(actionDisabled)
            Button("Cut!") { cutTapped() }
                .buttonStyle(TakeButtonStyle(role: .cut))
                .disabled(!coordinator.running)
        }
    }

    private var adminSection: some View {
        DisclosureGroup(isExpanded: $showAdmin) {
            VStack(alignment: .leading, spacing: 14) {
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
                        .disabled(coordinator.running || coordinator.starting)
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
                    .disabled(coordinator.running || coordinator.starting)
                    Spacer()
                }

                Picker("Source", selection: $sourceKind) {
                    ForEach(SourceKind.allCases) { kind in
                        Text(kind.rawValue).tag(kind)
                    }
                }
                .pickerStyle(.segmented)
                .disabled(coordinator.running || coordinator.starting)

                statsLine

                HStack(spacing: 12) {
                    Button("Abort") { stopTapped() }
                        .buttonStyle(TakeButtonStyle(role: .secondary))
                        .disabled(stopDisabled)
                    Button("Submit Frame") { coordinator.fireManual() }
                        .buttonStyle(TakeButtonStyle(role: .secondary))
                        .disabled(!coordinator.running)
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
            .padding(.top, 10)
        } label: {
            Text("Admin")
                .font(.system(.caption, design: .monospaced).weight(.semibold))
                .foregroundStyle(Self.gold)
        }
        .tint(Self.gold)
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(Self.panel)
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(.white.opacity(0.08), lineWidth: 1)
                )
        )
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

    private var actionDisabled: Bool {
        coordinator.running || coordinator.starting || coordinator.awaitingNarration
    }

    private var detailStatus: String {
        let source = sourceKind.rawValue.lowercased()
        if coordinator.running || coordinator.awaitingNarration {
            return "\(source) · \(coordinator.engineLink.label)"
        }
        if coordinator.starting {
            return "\(source) · preparing capture"
        }
        return "\(source) · \(styleKey)"
    }

    private func primaryStatus(now: Date) -> String {
        if coordinator.running {
            if let started = coordinator.recordingStartedAt {
                return "Rolling \(formatElapsed(from: started, now: now))"
            }
            return "Rolling"
        }
        if coordinator.awaitingNarration {
            return "Cut sent - waiting"
        }
        if case .playing = coordinator.playback {
            return "Playing in glasses"
        }
        if coordinator.starting {
            return sourceKind == .glasses ? "Connecting glasses" : "Starting capture"
        }
        if startError != nil || coordinator.lastError != nil {
            return "Needs attention"
        }
        return "Ready"
    }

    /// Stop must work even with no running coordinator: an in-flight glasses
    /// connect is cancelled via controller.stop().
    private var stopDisabled: Bool {
        if coordinator.running || coordinator.awaitingNarration { return false }
        guard sourceKind == .glasses else { return true }
        switch controller.state {
        case .idle, .error:
            return true
        default:
            return false
        }
    }

    private func actionTapped() {
        start()
    }

    private func cutTapped() {
        Task {
            await coordinator.cutTake()
        }
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
                try await coordinator.start(
                    source: source,
                    engineURL: engineURL,
                    styleKey: styleKey,
                    capturePolicy: .manualTake
                )
            } catch {
                startError = error.localizedDescription
                coordinator.stop()
            }
        }
    }

    private func formatElapsed(from start: Date, now: Date) -> String {
        let elapsed = max(0, Int(now.timeIntervalSince(start)))
        return String(format: "%02d:%02d", elapsed / 60, elapsed % 60)
    }

    private struct LayoutMetrics {
        let spacing: CGFloat
        let verticalPadding: CGFloat
        let previewHeight: CGFloat
    }

    private func layoutMetrics(for size: CGSize) -> LayoutMetrics {
        let compact = size.height < 760
        let previewRatio = compact ? 0.38 : 0.44
        let previewCap: CGFloat = compact ? 300 : 390
        return LayoutMetrics(
            spacing: compact ? 10 : 14,
            verticalPadding: compact ? 10 : 16,
            previewHeight: min(size.height * previewRatio, previewCap)
        )
    }
}

private struct TakeButtonStyle: ButtonStyle {
    enum Role {
        case action
        case cut
        case secondary
    }

    let role: Role
    private static let gold = Color(red: 212 / 255, green: 175 / 255, blue: 55 / 255)

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(font)
            .lineLimit(1)
            .minimumScaleFactor(0.7)
            .frame(maxWidth: .infinity, minHeight: role == .secondary ? 42 : 62)
            .background(background(configuration: configuration))
            .foregroundStyle(foreground)
            .opacity(configuration.isPressed ? 0.65 : 1.0)
    }

    private var font: Font {
        switch role {
        case .action, .cut:
            return .system(.title3, design: .monospaced).weight(.bold)
        case .secondary:
            return .system(.subheadline, design: .monospaced).weight(.semibold)
        }
    }

    private var fill: Color {
        switch role {
        case .action:
            return Self.gold
        case .cut:
            return Color(red: 0.80, green: 0.22, blue: 0.22)
        case .secondary:
            return Color.clear
        }
    }

    private var foreground: Color {
        switch role {
        case .action:
            return .black
        case .cut:
            return .white
        case .secondary:
            return Self.gold
        }
    }

    private func background(configuration: Configuration) -> some View {
        RoundedRectangle(cornerRadius: 10)
            .fill(fill)
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(role == .secondary ? Self.gold : fill.opacity(0.85), lineWidth: 1.2)
            )
    }
}

#Preview {
    ContentView()
}
