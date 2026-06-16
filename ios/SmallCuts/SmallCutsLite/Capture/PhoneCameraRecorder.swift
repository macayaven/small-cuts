@preconcurrency import AVFoundation
import Foundation

/// Records a finished clip from the phone camera to a temporary `.mov` file.
/// The 60 s cap is enforced by the view model's countdown (it calls `cut`),
/// keeping this type a thin, deprecation-free wrapper over AVFoundation.
@MainActor
final class PhoneCameraRecorder: NSObject, ObservableObject {
    enum RecorderError: LocalizedError {
        case cameraUnavailable
        case notConfigured
        case alreadyRecording
        case noActiveRecording

        var errorDescription: String? {
            switch self {
            case .cameraUnavailable: return "No camera is available on this device."
            case .notConfigured: return "The camera isn't ready yet."
            case .alreadyRecording: return "Already recording."
            case .noActiveRecording: return "No active recording to stop."
            }
        }
    }

    let session = AVCaptureSession()
    private let movieOutput = AVCaptureMovieFileOutput()
    private let sessionQueue = DispatchQueue(label: "com.macayaven.smallcutslite.camera")
    private var isConfigured = false
    private var stopContinuation: CheckedContinuation<URL, Error>?

    @Published private(set) var isRecording = false

    /// Wire camera + mic inputs and the movie output. Idempotent.
    func configure() throws {
        guard !isConfigured else { return }
        session.beginConfiguration()
        session.sessionPreset = .high
        defer { session.commitConfiguration() }

        guard
            let camera = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back),
            let videoInput = try? AVCaptureDeviceInput(device: camera),
            session.canAddInput(videoInput)
        else {
            throw RecorderError.cameraUnavailable
        }
        session.addInput(videoInput)

        if let mic = AVCaptureDevice.default(for: .audio),
           let audioInput = try? AVCaptureDeviceInput(device: mic),
           session.canAddInput(audioInput) {
            session.addInput(audioInput)
        }

        guard session.canAddOutput(movieOutput) else { throw RecorderError.notConfigured }
        session.addOutput(movieOutput)
        isConfigured = true
    }

    func startSession() {
        sessionQueue.async { [session] in
            if !session.isRunning { session.startRunning() }
        }
    }

    func stopSession() {
        sessionQueue.async { [session] in
            if session.isRunning { session.stopRunning() }
        }
    }

    func startRecording() throws {
        guard isConfigured else { throw RecorderError.notConfigured }
        guard !movieOutput.isRecording else { throw RecorderError.alreadyRecording }
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("lite-\(UUID().uuidString).mov")
        movieOutput.startRecording(to: url, recordingDelegate: self)
        isRecording = true
    }

    /// Stop recording and return the written file once the delegate confirms.
    func stopRecording() async throws -> URL {
        guard movieOutput.isRecording else { throw RecorderError.noActiveRecording }
        return try await withCheckedThrowingContinuation { continuation in
            stopContinuation = continuation
            movieOutput.stopRecording()
        }
    }
}

extension PhoneCameraRecorder: AVCaptureFileOutputRecordingDelegate {
    nonisolated func fileOutput(
        _ output: AVCaptureFileOutput,
        didFinishRecordingTo outputFileURL: URL,
        from connections: [AVCaptureConnection],
        error: Error?
    ) {
        Task { @MainActor in
            isRecording = false
            if let error {
                stopContinuation?.resume(throwing: error)
            } else {
                stopContinuation?.resume(returning: outputFileURL)
            }
            stopContinuation = nil
        }
    }
}
