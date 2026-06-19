from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


class ModalUploadError(RuntimeError):
    """Raised when hosted post-cut inference fails."""


DEFAULT_UPLOAD_SOURCE_ID = "public-demo"
MAX_ERROR_DETAIL_CHARS = 240


def _safe_modal_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return _truncate_detail(response.text.strip() or response.reason_phrase)

    detail = payload.get("detail") if isinstance(payload, dict) else payload
    return _truncate_detail(_normalize_modal_detail(detail) or response.reason_phrase)


def _normalize_modal_detail(detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        for key in ("msg", "message", "error"):
            value = detail.get(key)
            if isinstance(value, str) and value:
                return value
        return str(detail)
    if isinstance(detail, list):
        messages = [_normalize_modal_detail(item) for item in detail[:3]]
        return "; ".join(message for message in messages if message)
    return str(detail) if detail is not None else ""


def _truncate_detail(detail: str) -> str:
    normalized = " ".join(detail.split())
    if len(normalized) <= MAX_ERROR_DETAIL_CHARS:
        return normalized
    return f"{normalized[: MAX_ERROR_DETAIL_CHARS - 1]}..."


def _raise_for_modal_status(response: httpx.Response, action: str) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError:
        detail = _safe_modal_detail(response)
        raise ModalUploadError(
            f"Modal upload {action} failed ({response.status_code}): {detail}"
        ) from None


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
        style_key: str = "deadpan",
        scene_hint: str = "",
    ) -> dict[str, Any]:
        close = self.http_client is None
        client = self.http_client or httpx.Client(timeout=30.0, follow_redirects=True)
        try:
            try:
                job_id = self._submit(
                    client,
                    Path(video_path),
                    DEFAULT_UPLOAD_SOURCE_ID,
                    style_key,
                    scene_hint,
                )
            except ModalUploadError:
                raise
            except httpx.HTTPError as exc:
                raise ModalUploadError(
                    f"Modal upload request failed: {type(exc).__name__}"
                ) from None
            try:
                return self._poll(client, job_id)
            except ModalUploadError:
                raise
            except httpx.HTTPError as exc:
                raise ModalUploadError(
                    f"Modal upload status failed: {type(exc).__name__}"
                ) from None
        finally:
            if close:
                client.close()

    def _submit(
        self,
        client: httpx.Client,
        video_path: Path,
        source_id: str,
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
                    "uploader_id": source_id,
                },
                files={"video": (video_path.name, handle, "video/mp4")},
            )
        _raise_for_modal_status(response, "request")
        job_id = response.json().get("job_id")
        if not isinstance(job_id, str) or not job_id:
            raise ModalUploadError("Modal did not return a job_id")
        return job_id

    def submit_video_v2(
        self,
        video_path: str | Path,
        *,
        style_key: str = "deadpan",
        language: str = "English",
    ) -> dict[str, Any]:
        """Upload a clip to the v2 ``/v2/narrate`` pipeline in the chosen narration language.

        Mirrors :meth:`submit_video` but targets the v2 endpoint (``style_key`` + ``language`` form
        fields, no ``scene_hint``) and polls ``/v2/narrate/{job_id}``. Kept as a separate method so
        the v1 ``/v1/cuts`` path used by the live Space is untouched.
        """
        close = self.http_client is None
        client = self.http_client or httpx.Client(timeout=30.0, follow_redirects=True)
        try:
            try:
                job_id = self._submit_v2(client, Path(video_path), style_key, language)
            except ModalUploadError:
                raise
            except httpx.HTTPError as exc:
                raise ModalUploadError(
                    f"Modal upload request failed: {type(exc).__name__}"
                ) from None
            try:
                return self._poll_status(client, f"{self.base_url.rstrip('/')}/v2/narrate/{job_id}")
            except ModalUploadError:
                raise
            except httpx.HTTPError as exc:
                raise ModalUploadError(
                    f"Modal upload status failed: {type(exc).__name__}"
                ) from None
        finally:
            if close:
                client.close()

    def _submit_v2(
        self,
        client: httpx.Client,
        video_path: Path,
        style_key: str,
        language: str,
    ) -> str:
        with video_path.open("rb") as handle:
            response = client.post(
                f"{self.base_url.rstrip('/')}/v2/narrate",
                headers={"Authorization": f"Bearer {self.token}"},
                data={"style_key": style_key, "language": language},
                files={"video": (video_path.name, handle, "video/mp4")},
            )
        _raise_for_modal_status(response, "request")
        job_id = response.json().get("job_id")
        if not isinstance(job_id, str) or not job_id:
            raise ModalUploadError("Modal did not return a job_id")
        return job_id

    def _poll(self, client: httpx.Client, job_id: str) -> dict[str, Any]:
        return self._poll_status(client, f"{self.base_url.rstrip('/')}/v1/cuts/{job_id}")

    def _poll_status(self, client: httpx.Client, status_url: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            response = client.get(
                status_url,
                headers={"Authorization": f"Bearer {self.token}"},
            )
            if response.status_code == 202:
                time.sleep(self.poll_interval_s)
                continue
            _raise_for_modal_status(response, "status")
            payload = response.json()
            scene = payload.get("scene")
            if not isinstance(scene, dict):
                raise ModalUploadError("Modal completed without a scene payload")
            return scene
        raise ModalUploadError("Modal upload timed out")
