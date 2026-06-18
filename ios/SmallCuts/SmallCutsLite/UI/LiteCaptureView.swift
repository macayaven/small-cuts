import AuthenticationServices
import SwiftUI
import UIKit

/// Drives the capture → upload state machine for one cut, for either capture
/// source. Both paths converge on the same `ModalUploadClient`, so the upload
/// contract is identical regardless of device.
@MainActor
final class LiteCaptureViewModel: ObservableObject {
    enum Source: String, CaseIterable, Identifiable {
        case phone = "Phone"
        case glasses = "Glasses"
        var id: String { rawValue }
    }

    enum Phase: Equatable {
        case idle
        case recording
        case uploading
        case done
        case failed(String)
    }

    @Published var source: Source = .phone
    @Published var styleKey: String = "deadpan"
    @Published private(set) var phase: Phase = .idle
    @Published private(set) var elapsed: Int = 0
    @Published private(set) var resultScene: ModalScene?
    /// Latest glasses frame, for the live preview (phone uses CameraPreview).
    @Published private(set) var latestGlassesImage: UIImage?

    let phoneRecorder = PhoneCameraRecorder()
    let glassesSession = GlassesSessionController()
    let maxSeconds = 60
    let styles = ["deadpan", "noir", "nature_doc", "trailer", "telenovela", "symmetrist"]

    private var ticker: Task<Void, Never>?
    private var glassesRecorder: GlassesClipRecorder?
    private var glassesSource: GlassesFrameSource?
    private var glassesDrain: Task<Void, Never>?

    var isRecording: Bool { phase == .recording }
    var isBusy: Bool { phase == .uploading }
    var canStart: Bool {
        switch phase {
        case .idle, .done, .failed: return true
        case .recording, .uploading: return false
        }
    }

    func onAppear() {
        if source == .phone { startPhonePreview() }
    }

    func handleSourceChange() {
        stopGlassesStream()
        latestGlassesImage = nil
        if source == .phone {
            startPhonePreview()
        } else {
            phoneRecorder.stopSession()
        }
    }

    func teardown() {
        phoneRecorder.stopSession()
        stopGlassesStream()
        ticker?.cancel()
    }

    func startRecording() {
        guard canStart else { return }
        resultScene = nil
        elapsed = 0
        do {
            switch source {
            case .phone: try phoneRecorder.startRecording()
            case .glasses: startGlassesTake()
            }
            phase = .recording
            startTicker()
        } catch {
            phase = .failed(Self.message(for: error))
        }
    }

    func cut(uploaderHandle: String) {
        guard isRecording else { return }
        ticker?.cancel()
        let currentSource = source
        Task {
            do {
                let url: URL
                switch currentSource {
                case .phone: url = try await phoneRecorder.stopRecording()
                case .glasses: url = try await finishGlassesTake()
                }
                await upload(url: url, uploaderHandle: uploaderHandle)
            } catch {
                phase = .failed(Self.message(for: error))
            }
        }
    }

    // MARK: - Phone

    private func startPhonePreview() {
        do {
            try phoneRecorder.configure()
            phoneRecorder.startSession()
        } catch {
            phase = .failed(Self.message(for: error))
        }
    }

    // MARK: - Glasses

    private func startGlassesTake() {
        let recorder = GlassesClipRecorder(frameRate: 7)
        glassesRecorder = recorder
        let source = GlassesFrameSource(controller: glassesSession)
        glassesSource = source
        glassesDrain = Task { [weak self] in
            guard let self else { return }
            do {
                try await source.start()
            } catch {
                self.ticker?.cancel()
                self.phase = .failed(Self.message(for: error))
                return
            }
            for await frame in source.frames {
                let image = Self.downscaled(frame.image)
                recorder.append(image)
                self.latestGlassesImage = image
            }
        }
    }

    private func finishGlassesTake() async throws -> URL {
        glassesSource?.stop()
        glassesDrain?.cancel()
        glassesDrain = nil
        guard let recorder = glassesRecorder else { throw GlassesClipRecorder.RecorderError.noFrames }
        let url = try await recorder.finish()
        glassesRecorder = nil
        glassesSource = nil
        return url
    }

    private func stopGlassesStream() {
        glassesSource?.stop()
        glassesDrain?.cancel()
        glassesDrain = nil
        glassesSource = nil
        glassesRecorder = nil
    }

    // MARK: - Upload (shared by both sources)

    private func upload(url: URL, uploaderHandle: String) async {
        guard let base = LiteConfig.modalBaseURL, LiteConfig.isConfigured else {
            phase = .failed("Modal endpoint/token not set — fill SmallCutsLite/Config/Secrets.swift.")
            return
        }
        phase = .uploading
        do {
            let client = ModalUploadClient(baseURL: base, token: LiteConfig.modalToken)
            resultScene = try await client.submitVideo(
                at: url,
                uploaderHandle: uploaderHandle,
                styleKey: styleKey
            )
            phase = .done
        } catch {
            phase = .failed(Self.message(for: error))
        }
    }

    // MARK: - Helpers

    private func startTicker() {
        ticker = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 1_000_000_000)
                guard let self else { return }
                self.elapsed += 1
            }
        }
    }

    private static func downscaled(_ image: UIImage, maxDimension: CGFloat = 960) -> UIImage {
        let size = image.size
        let longest = max(size.width, size.height)
        guard longest > maxDimension else { return image }
        let scale = maxDimension / longest
        let target = CGSize(width: size.width * scale, height: size.height * scale)
        return UIGraphicsImageRenderer(size: target).image { _ in
            image.draw(in: CGRect(origin: .zero, size: target))
        }
    }

    private static func message(for error: Error) -> String {
        if let recorderError = error as? PhoneCameraRecorder.RecorderError {
            return recorderError.errorDescription ?? "Camera error."
        }
        if let glassesError = error as? GlassesSessionError {
            return glassesError.errorDescription ?? "Glasses error."
        }
        if let uploadError = error as? ModalUploadError {
            switch uploadError {
            case .http(let code): return "Upload failed (HTTP \(code))."
            case .timedOut: return "Upload timed out — try again."
            case .missingScene: return "The server returned no scene."
            case .noJobID: return "The server did not accept the clip."
            case .invalidResponse: return "Unexpected server response."
            }
        }
        return error.localizedDescription
    }
}

/// The single screen: record (phone or glasses) → Cut! → upload to Modal.
struct LiteCaptureView: View {
    @StateObject private var vm = LiteCaptureViewModel()
    @StateObject private var identity = IdentityStore()

    var body: some View {
        ZStack {
            LiteTheme.ink.ignoresSafeArea()
            VStack(spacing: 16) {
                header
                previewArea
                statusArea
                Spacer(minLength: 0)
                controls
            }
            .padding()
        }
        .onAppear { vm.onAppear() }
        .onDisappear { vm.teardown() }
        .onChange(of: vm.source) { _, _ in vm.handleSourceChange() }
        .onChange(of: vm.elapsed) { _, value in
            if value >= vm.maxSeconds && vm.isRecording {
                vm.cut(uploaderHandle: identity.uploaderHandle)
            }
        }
    }

    private var header: some View {
        HStack {
            Text("SMALL CUTS LITE")
                .font(.system(.headline, design: .serif))
                .tracking(2)
                .foregroundStyle(LiteTheme.gold)
            Spacer()
            Picker("Source", selection: $vm.source) {
                ForEach(LiteCaptureViewModel.Source.allCases) { source in
                    Text(source.rawValue).tag(source)
                }
            }
            .pickerStyle(.segmented)
            .frame(width: 170)
            .disabled(vm.isRecording || vm.isBusy)
        }
    }

    private var previewArea: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 18).fill(Color.black)
            switch vm.source {
            case .phone:
                CameraPreview(session: vm.phoneRecorder.session)
                    .clipShape(RoundedRectangle(cornerRadius: 18))
            case .glasses:
                if let image = vm.latestGlassesImage {
                    Image(uiImage: image)
                        .resizable()
                        .scaledToFill()
                        .clipShape(RoundedRectangle(cornerRadius: 18))
                } else {
                    VStack(spacing: 8) {
                        Image(systemName: "eyeglasses").font(.system(size: 40))
                        Text("Connect your glasses, then tap Action!")
                            .font(.footnote).multilineTextAlignment(.center)
                    }
                    .foregroundStyle(LiteTheme.parchment.opacity(0.7))
                    .padding()
                }
            }
            if vm.isRecording {
                VStack {
                    HStack(spacing: 8) {
                        Circle().fill(LiteTheme.cut).frame(width: 10, height: 10)
                        Text(timeString(vm.elapsed))
                            .font(.system(.callout, design: .monospaced))
                            .foregroundStyle(.white)
                        Spacer()
                    }
                    .padding(12)
                    Spacer()
                }
            }
        }
        .aspectRatio(9.0 / 16.0, contentMode: .fit)
    }

    @ViewBuilder private var statusArea: some View {
        switch vm.phase {
        case .uploading:
            HStack(spacing: 8) {
                ProgressView().tint(LiteTheme.gold)
                Text("Narrating your cut…").foregroundStyle(LiteTheme.parchment)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        case .done:
            VStack(alignment: .leading, spacing: 6) {
                if let title = vm.resultScene?.title {
                    Text(title).font(.headline).foregroundStyle(LiteTheme.gold)
                }
                if let narration = vm.resultScene?.narration {
                    Text(narration).font(.callout).foregroundStyle(LiteTheme.parchment)
                }
                Text("Sent — it'll appear in the library once curated.")
                    .font(.caption).foregroundStyle(LiteTheme.parchment.opacity(0.6))
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        case .failed(let message):
            Text(message)
                .font(.callout).foregroundStyle(LiteTheme.cut)
                .frame(maxWidth: .infinity, alignment: .leading)
        case .idle, .recording:
            Text("Tap Action! to start your cut.")
                .font(.callout).foregroundStyle(LiteTheme.parchment.opacity(0.7))
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // Recording is NEVER gated on sign-in — the core record→upload path always
    // works. Sign in with Apple is an optional enhancement that sets a nicer
    // uploader handle.
    private var controls: some View {
        VStack(spacing: 12) {
            stylePicker
            HStack(spacing: 14) {
                Button { vm.startRecording() } label: {
                    actionLabel("Action!", color: LiteTheme.gold)
                }
                .disabled(!vm.canStart)

                Button { vm.cut(uploaderHandle: identity.uploaderHandle) } label: {
                    actionLabel("Cut!", color: LiteTheme.cut)
                }
                .disabled(!vm.isRecording)
            }
            identityRow
        }
    }

    @ViewBuilder private var identityRow: some View {
        if identity.isSignedIn {
            HStack {
                Text("Signed in as \(identity.handle ?? "")")
                    .font(.caption).foregroundStyle(LiteTheme.parchment.opacity(0.6))
                Spacer()
                Button("Sign out") { identity.signOut() }
                    .font(.caption).tint(LiteTheme.parchment.opacity(0.7))
            }
        } else {
            HStack(spacing: 10) {
                SignInWithAppleButton(.signIn) { request in
                    identity.configure(request)
                } onCompletion: { result in
                    identity.complete(result)
                }
                .signInWithAppleButtonStyle(.whiteOutline)
                .frame(maxWidth: 210, minHeight: 36)
                Text("optional — credits your cut")
                    .font(.caption2).foregroundStyle(LiteTheme.parchment.opacity(0.5))
                Spacer()
            }
        }
    }

    private var stylePicker: some View {
        Menu {
            ForEach(vm.styles, id: \.self) { style in
                Button(style) { vm.styleKey = style }
            }
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "wand.and.stars")
                Text("Style: \(vm.styleKey)")
            }
            .font(.footnote).foregroundStyle(LiteTheme.parchment)
        }
        .disabled(vm.isRecording || vm.isBusy)
    }

    private func actionLabel(_ text: String, color: Color) -> some View {
        Text(text)
            .font(.system(.title3, design: .serif)).bold()
            .frame(maxWidth: .infinity, minHeight: 58)
            .background(color)
            .foregroundStyle(.black)
            .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    private func timeString(_ seconds: Int) -> String {
        String(format: "%02d:%02d", seconds / 60, seconds % 60)
    }
}
