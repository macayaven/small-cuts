"""Video frame sampling utilities for Small Cuts."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFilter, ImageStat


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
    try:
        stream = container.streams.video[0]
        fps = float(stream.average_rate or stream.guessed_rate or 30)
        step = max(1, int(fps * every_n_seconds))
        for i, frame in enumerate(container.decode(stream)):
            if i % step == 0:
                img = frame.to_image().convert("RGB")
                kept.append(img)
                if max_frames is not None and len(kept) >= max_frames:
                    break
    finally:
        container.close()
    return kept


def pick_frame(frames: list[Image.Image]) -> Image.Image:
    """Return the middle frame (``frames[len(frames) // 2]``).

    Raises ``ValueError`` when *frames* is empty.
    """
    if not frames:
        raise ValueError("frames list is empty")
    return frames[len(frames) // 2]


def pick_key_frame(frames: list[Image.Image]) -> Image.Image:
    """Return the most useful library/poster frame from sampled video frames.

    The score is intentionally deterministic and dependency-light: prefer frames
    that are exposed near mid-brightness, have contrast, and have visible edges.
    A centrality bonus breaks near-ties toward the middle of the clip, which is
    usually more representative than the capture start or the trailing frame.
    """
    if not frames:
        raise ValueError("frames list is empty")
    middle = (len(frames) - 1) / 2
    best_index, _best_score = max(
        enumerate(frames),
        key=lambda item: (_frame_quality(item[1]) + _centrality(item[0], middle), -item[0]),
    )
    return frames[best_index]


def _frame_quality(frame: Image.Image) -> float:
    gray = frame.convert("L")
    gray.thumbnail((160, 160), Image.Resampling.LANCZOS)
    stats = ImageStat.Stat(gray)
    brightness = stats.mean[0] / 255.0
    contrast = min(stats.stddev[0] / 96.0, 1.0)
    exposure = 1.0 - min(abs(brightness - 0.5) / 0.5, 1.0)
    edges = ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).mean[0] / 255.0
    return exposure * 0.45 + contrast * 0.35 + min(edges * 3.0, 1.0) * 0.20


def _centrality(index: int, middle: float) -> float:
    if middle <= 0:
        return 0.0
    return (1.0 - min(abs(index - middle) / middle, 1.0)) * 0.08
