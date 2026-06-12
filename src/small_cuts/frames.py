"""Video frame sampling utilities for Small Cuts."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


def sample_frames(
    path: str | Path,
    every_n_seconds: float = 3.0,
    max_frames: int | None = None,
) -> list[Image.Image]:
    """Decode *path* with PyAV and return a list of RGB PIL Images.

    Every ``int(fps * every_n_seconds)``-th frame is kept (indices 0, step,
    2*step, …).  No files are written.  Decoding stops as soon as
    *max_frames* images have been collected (when *max_frames* is not None).
    """
    import av  # PyAV — ffmpeg-backed, reliable ARM64 wheels

    kept: list[Image.Image] = []
    container = av.open(str(path))
    stream = container.streams.video[0]
    fps = float(stream.average_rate or stream.guessed_rate or 30)
    step = max(1, int(fps * every_n_seconds))
    for i, frame in enumerate(container.decode(stream)):
        if i % step == 0:
            img = frame.to_image().convert("RGB")
            kept.append(img)
            if max_frames is not None and len(kept) >= max_frames:
                break
    container.close()
    return kept


def pick_frame(frames: list[Image.Image]) -> Image.Image:
    """Return the middle frame (``frames[len(frames) // 2]``).

    Raises ``ValueError`` when *frames* is empty.
    """
    if not frames:
        raise ValueError("frames list is empty")
    return frames[len(frames) // 2]
