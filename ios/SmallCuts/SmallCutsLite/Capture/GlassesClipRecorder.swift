@preconcurrency import AVFoundation
import UIKit

/// Encodes a sequence of frames (as delivered by the Meta DAT camera stream) into
/// an H.264 MP4 on disk — the iOS analogue of the Modal worker's `_write_clip_mp4`.
/// The glasses SDK hands us discrete `UIImage` frames, so the Lite glasses path
/// buffers them here and produces a finished clip that feeds the same
/// `ModalUploadClient` the phone-camera path uses.
final class GlassesClipRecorder {
    enum RecorderError: Error {
        case noFrames
        case setupFailed
        case encodeFailed
    }

    private let frameRate: Int
    private let maxFrames: Int
    private let outputURL: URL
    private var frames: [UIImage] = []

    init(frameRate: Int = 8, maxFrames: Int = 600) {
        self.frameRate = max(1, frameRate)
        self.maxFrames = maxFrames
        self.outputURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("glasses-\(UUID().uuidString).mp4")
    }

    /// Buffer a frame. Bounded so a long take can't exhaust memory; callers
    /// should hand in already-downscaled frames for live use.
    func append(_ image: UIImage) {
        guard frames.count < maxFrames else { return }
        frames.append(image)
    }

    var frameCount: Int { frames.count }

    /// Encode the buffered frames to an MP4 and return its file URL.
    func finish() async throws -> URL {
        guard let firstFrame = frames.first?.cgImage else { throw RecorderError.noFrames }
        let width = evenized(firstFrame.width)
        let height = evenized(firstFrame.height)

        let writer = try AVAssetWriter(outputURL: outputURL, fileType: .mp4)
        let input = AVAssetWriterInput(
            mediaType: .video,
            outputSettings: [
                AVVideoCodecKey: AVVideoCodecType.h264,
                AVVideoWidthKey: width,
                AVVideoHeightKey: height,
            ]
        )
        input.expectsMediaDataInRealTime = false
        let adaptor = AVAssetWriterInputPixelBufferAdaptor(
            assetWriterInput: input,
            sourcePixelBufferAttributes: [
                kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32ARGB,
                kCVPixelBufferWidthKey as String: width,
                kCVPixelBufferHeightKey as String: height,
            ]
        )

        guard writer.canAdd(input) else { throw RecorderError.setupFailed }
        writer.add(input)
        guard writer.startWriting() else { throw RecorderError.setupFailed }
        writer.startSession(atSourceTime: .zero)

        // Append sequentially, yielding briefly when the writer's buffer is full.
        // (A plain async loop avoids capturing the non-Sendable writer objects in
        // a @Sendable requestMediaDataWhenReady closure.)
        var index = 0
        while index < frames.count {
            guard input.isReadyForMoreMediaData else {
                try? await Task.sleep(nanoseconds: 5_000_000)
                continue
            }
            if let cgImage = frames[index].cgImage,
               let buffer = Self.pixelBuffer(from: cgImage, width: width, height: height) {
                let presentationTime = CMTime(
                    value: CMTimeValue(index),
                    timescale: CMTimeScale(frameRate)
                )
                adaptor.append(buffer, withPresentationTime: presentationTime)
            }
            index += 1
        }
        input.markAsFinished()

        await writer.finishWriting()
        guard writer.status == .completed else { throw RecorderError.encodeFailed }
        return outputURL
    }

    // MARK: - Helpers

    private func evenized(_ value: Int) -> Int { value - (value % 2) }

    /// Draw a CGImage into a fresh ARGB pixel buffer for the writer.
    private static func pixelBuffer(from cgImage: CGImage, width: Int, height: Int) -> CVPixelBuffer? {
        let attributes: [String: Any] = [
            kCVPixelBufferCGImageCompatibilityKey as String: true,
            kCVPixelBufferCGBitmapContextCompatibilityKey as String: true,
        ]
        var pixelBuffer: CVPixelBuffer?
        let status = CVPixelBufferCreate(
            kCFAllocatorDefault, width, height,
            kCVPixelFormatType_32ARGB, attributes as CFDictionary, &pixelBuffer
        )
        guard status == kCVReturnSuccess, let buffer = pixelBuffer else { return nil }

        CVPixelBufferLockBaseAddress(buffer, [])
        defer { CVPixelBufferUnlockBaseAddress(buffer, []) }
        guard let context = CGContext(
            data: CVPixelBufferGetBaseAddress(buffer),
            width: width, height: height,
            bitsPerComponent: 8,
            bytesPerRow: CVPixelBufferGetBytesPerRow(buffer),
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.noneSkipFirst.rawValue
        ) else { return nil }
        context.draw(cgImage, in: CGRect(x: 0, y: 0, width: width, height: height))
        return buffer
    }
}
