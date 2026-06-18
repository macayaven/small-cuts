import Foundation

/// A `URLProtocol` that intercepts every request so `ModalUploadClient` can be
/// exercised against scripted HTTP responses without touching the network. It
/// records the method + path of each request so tests can assert the
/// submit→poll sequence.
final class StubURLProtocol: URLProtocol {
    /// Returns `(statusCode, jsonBody)` for a given request.
    nonisolated(unsafe) static var handler: ((URLRequest) -> (Int, Data))?
    nonisolated(unsafe) static private(set) var recorded: [(method: String, path: String)] = []

    static func reset() {
        handler = nil
        recorded = []
    }

    static func session() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubURLProtocol.self]
        return URLSession(configuration: config)
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let request = self.request
        StubURLProtocol.recorded.append(
            (method: request.httpMethod ?? "", path: request.url?.path ?? "")
        )
        let (status, body) = StubURLProtocol.handler?(request) ?? (500, Data())
        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: status,
            httpVersion: "HTTP/1.1",
            headerFields: ["Content-Type": "application/json"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}
