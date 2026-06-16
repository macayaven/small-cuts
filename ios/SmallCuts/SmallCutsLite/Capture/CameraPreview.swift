import AVFoundation
import SwiftUI
import UIKit

/// A thin SwiftUI wrapper around `AVCaptureVideoPreviewLayer` showing the live
/// phone-camera feed.
struct CameraPreview: UIViewRepresentable {
    let session: AVCaptureSession

    func makeUIView(context: Context) -> PreviewView {
        let view = PreviewView()
        view.videoPreviewLayer.session = session
        view.videoPreviewLayer.videoGravity = .resizeAspectFill
        return view
    }

    func updateUIView(_ uiView: PreviewView, context: Context) {}

    final class PreviewView: UIView {
        override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
        var videoPreviewLayer: AVCaptureVideoPreviewLayer {
            // Safe: layerClass guarantees this layer type.
            layer as! AVCaptureVideoPreviewLayer
        }
    }
}
