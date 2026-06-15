from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


class ModalUploadError(RuntimeError):
    """Raised when hosted post-cut inference fails."""


@dataclass
class ModalUploadClient:
    base_url: str
    token: str
    http_client: httpx.Client | None = None
    poll_interval_s: float = 1.0
    timeout_s: float = 900.0

    def submit_video(
        self,
        video_path: str | Path,
        *,
        uploader_hf_username: str,
        style_key: str = "deadpan",
        scene_hint: str = "",
    ) -> dict[str, Any]:
        close = self.http_client is None
        client = self.http_client or httpx.Client(timeout=30.0, follow_redirects=True)
        try:
            job_id = self._submit(
                client,
                Path(video_path),
                uploader_hf_username,
                style_key,
                scene_hint,
            )
            return self._poll(client, job_id)
        finally:
            if close:
                client.close()

    def _submit(
        self,
        client: httpx.Client,
        video_path: Path,
        uploader_hf_username: str,
        style_key: str,
        scene_hint: str,
    ) -> str:
        with video_path.open("rb") as handle:
            response = client.post(
                f"{self.base_url.rstrip('/')}/v1/cuts",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "style_key": style_key,
                    "scene_hint": scene_hint,
                    "uploader_hf_username": uploader_hf_username,
                },
                files={"video": (video_path.name, handle, "video/mp4")},
            )
        response.raise_for_status()
        job_id = response.json().get("job_id")
        if not isinstance(job_id, str) or not job_id:
            raise ModalUploadError("Modal did not return a job_id")
        return job_id

    def _poll(self, client: httpx.Client, job_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            response = client.get(
                f"{self.base_url.rstrip('/')}/v1/cuts/{job_id}",
                headers={"Authorization": f"Bearer {self.token}"},
            )
            if response.status_code == 202:
                time.sleep(self.poll_interval_s)
                continue
            response.raise_for_status()
            payload = response.json()
            scene = payload.get("scene")
            if not isinstance(scene, dict):
                raise ModalUploadError("Modal completed without a scene payload")
            return scene
        raise ModalUploadError("Modal upload timed out")
