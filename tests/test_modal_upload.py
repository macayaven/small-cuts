from __future__ import annotations

import httpx
import pytest

from small_cuts.modal_upload import ModalUploadClient, ModalUploadError


def test_modal_client_default_timeout_matches_worker_budget():
    assert ModalUploadClient("https://modal.example", "secret").timeout_s == 900.0


def test_modal_client_submits_and_polls_result(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "POST":
            assert request.headers["authorization"] == "Bearer secret"
            body = request.content.decode("latin1")
            assert 'name="scene_hint"' in body
            assert "third coffee today" in body
            return httpx.Response(200, json={"job_id": "job-1"})
        if request.url.path.endswith("/job-1") and len(calls) == 2:
            return httpx.Response(202, json={"status": "running"})
        return httpx.Response(200, json={"status": "complete", "scene": {"scene_id": "s1"}})

    client = ModalUploadClient(
        "https://modal.example",
        "secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        poll_interval_s=0,
    )

    assert client.submit_video(video, scene_hint="third coffee today")["scene_id"] == "s1"
    assert calls == [
        ("POST", "/v1/cuts"),
        ("GET", "/v1/cuts/job-1"),
        ("GET", "/v1/cuts/job-1"),
    ]


def test_modal_client_v2_submits_to_v2_narrate_with_language(tmp_path):
    # The mid-cuts upload front door targets /v2/narrate and carries the chosen narration language
    # (the v1 /v1/cuts path has no language). style_key + language ride as form fields; the video is
    # multipart; completion polls /v2/narrate/{job_id} (202 while running) and returns the scene.
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "POST":
            assert request.headers["authorization"] == "Bearer secret"
            body = request.content.decode("latin1")
            assert 'name="style_key"' in body
            assert 'name="language"' in body
            assert "Catalan" in body
            return httpx.Response(200, json={"job_id": "job-9"})
        if request.url.path.endswith("/job-9") and len(calls) == 2:
            return httpx.Response(202, json={"status": "running"})
        return httpx.Response(200, json={"status": "complete", "scene": {"scene_id": "v2s"}})

    client = ModalUploadClient(
        "https://modal.example",
        "secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        poll_interval_s=0,
    )

    scene = client.submit_video_v2(video, style_key="deadpan", language="Catalan")
    assert scene["scene_id"] == "v2s"
    assert calls == [
        ("POST", "/v2/narrate"),
        ("GET", "/v2/narrate/job-9"),
        ("GET", "/v2/narrate/job-9"),
    ]


def test_modal_client_v2_forwards_context_steer(tmp_path):
    # The "Whisper context to the narrator" manner steer rides as a `context` form field on
    # /v2/narrate (Phase 5 step 1). v1's `scene_hint` was factual grounding; v2's `context` steers
    # HOW the moment is told, so it gets a distinct field name.
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            captured["body"] = request.content.decode("latin1")
            return httpx.Response(200, json={"job_id": "job-7"})
        return httpx.Response(200, json={"status": "complete", "scene": {"scene_id": "v2s"}})

    client = ModalUploadClient(
        "https://modal.example",
        "secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        poll_interval_s=0,
    )

    client.submit_video_v2(video, style_key="deadpan", language="English", context="like noir")
    assert 'name="context"' in captured["body"]
    assert "like noir" in captured["body"]


def test_modal_client_rejects_missing_scene(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"job_id": "job-1"})
        return httpx.Response(200, json={"status": "complete"})

    client = ModalUploadClient(
        "https://modal.example",
        "secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        poll_interval_s=0,
    )

    with pytest.raises(ModalUploadError, match="scene"):
        client.submit_video(video)


def test_modal_client_wraps_submit_http_detail(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        return httpx.Response(401, json={"detail": "unauthorized"})

    client = ModalUploadClient(
        "https://modal.example",
        "secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(
        ModalUploadError, match="Modal upload request failed \\(401\\).*unauthorized"
    ):
        client.submit_video(video)


def test_modal_client_wraps_poll_http_detail(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"job_id": "job-1"})
        return httpx.Response(422, json={"detail": [{"msg": "could not decode video"}]})

    client = ModalUploadClient(
        "https://modal.example",
        "secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(
        ModalUploadError, match="Modal upload status failed \\(422\\).*decode video"
    ):
        client.submit_video(video)


def test_modal_client_wraps_transport_error_without_raw_request(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = ModalUploadClient(
        "https://modal.example",
        "secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ModalUploadError) as exc_info:
        client.submit_video(video)

    assert "Modal upload request failed: ConnectError" in str(exc_info.value)
    assert exc_info.value.__cause__ is None
