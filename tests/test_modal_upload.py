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

    assert client.submit_video(video)["scene_id"] == "s1"
    assert calls == [
        ("POST", "/v1/cuts"),
        ("GET", "/v1/cuts/job-1"),
        ("GET", "/v1/cuts/job-1"),
    ]


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
