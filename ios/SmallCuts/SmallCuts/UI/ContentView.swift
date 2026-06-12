import SwiftUI

/// Minimal capture UI: status line, source toggle, Connect/Start/Stop, live
/// preview. Off-Brand palette — near-black background, gold accent.
struct ContentView: View {

    enum SourceKind: String, CaseIterable, Identifiable {
        case simulated = "Simulated"
        case glasses = "Glasses"
        var id: String { rawValue }
    }

    private static let gold = Color(red: 212 / 255, green: 175 / 255, blue: 55 / 255)
    private static let background = Color(red: 0.06, green: 0.06, blue: 0.07)

    @StateObject private var controller = GlassesSessionController()
    #if DEBUG
    @StateObject private var mockGlasses = MockGlassesDebugController()
    #endif

    @State private var sourceKind: SourceKind = .simulated
    @State private var activeSource: (any FrameSource)?
    @State private var preview: UIImage?
    @State private var frameCount = 0
    @State private var simulatedRunning = false
    @State private var startError: String?
    @State private var consumeTask: Task<Void, Never>?

    var body: some View {
        VStack(spacing: 16) {
            Text("SMALL CUTS")
                .font(.system(.headline, design: .monospaced))
                .tracking(4)
                .foregroundStyle(Self.gold)

            Picker("Source", selection: $sourceKind) {
                ForEach(SourceKind.allCases) { kind in
                    Text(kind.rawValue).tag(kind)
                }
            }
            .pickerStyle(.segmented)
            .disabled(activeSource != nil)

            Text(statusText)
                .font(.system(.footnote, design: .monospaced))
                .foregroundStyle(.white.opacity(0.85))
                .lineLimit(2)
                .frame(maxWidth: .infinity, alignment: .leading)

            previewPane

            HStack(spacing: 12) {
                Button("Connect") { connectGlasses() }
                    .buttonStyle(GoldButtonStyle(filled: false))
                    .disabled(sourceKind != .glasses)
                Button("Start") { start() }
                    .buttonStyle(GoldButtonStyle(filled: true))
                    .disabled(activeSource != nil)
                Button("Stop") { stopSource() }
                    .buttonStyle(GoldButtonStyle(filled: false))
                    .disabled(activeSource == nil)
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
            if let preview {
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
            if frameCount > 0 {
                Text("\(frameCount) frames")
                    .font(.system(.caption2, design: .monospaced))
                    .foregroundStyle(Self.gold)
                    .padding(8)
            }
        }
    }

    private var statusText: String {
        if let startError { return "Error: \(startError)" }
        switch sourceKind {
        case .simulated:
            return simulatedRunning ? "Simulated — streaming" : "Simulated — idle"
        case .glasses:
            return controller.state.label
        }
    }

    private func connectGlasses() {
        startError = nil
        Task { await controller.connect() }
    }

    private func start() {
        stopSource()
        startError = nil
        frameCount = 0

        let source: any FrameSource
        switch sourceKind {
        case .simulated:
            source = SimulatedFrameSource()
        case .glasses:
            source = GlassesFrameSource(controller: controller)
        }
        activeSource = source

        consumeTask = Task {
            do {
                try await source.start()
            } catch {
                startError = error.localizedDescription
                activeSource = nil
                return
            }
            if sourceKind == .simulated { simulatedRunning = true }
            for await frame in source.frames {
                preview = frame.image
                frameCount += 1
            }
            simulatedRunning = false
        }
    }

    private func stopSource() {
        consumeTask?.cancel()
        consumeTask = nil
        activeSource?.stop()
        activeSource = nil
        simulatedRunning = false
    }
}

private struct GoldButtonStyle: ButtonStyle {
    let filled: Bool
    private static let gold = Color(red: 212 / 255, green: 175 / 255, blue: 55 / 255)

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(.subheadline, design: .monospaced).weight(.semibold))
            .padding(.horizontal, 18)
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
