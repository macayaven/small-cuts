"""M1 model-evaluation harness: candidate VLMs × images × styles → markdown report.

Designed to run on a CUDA box (DGX Spark) so results transfer to ZeroGPU:

    uv sync --extra local
    uv run python -m small_cuts.eval --images ~/eval-photos --out eval-report.md

Smoke test anywhere (no weights):

    uv run python -m small_cuts.eval --images ~/eval-photos --backend mock
"""

from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path

from PIL import Image

from .narrator import MockBackend, Narration, TransformersBackend, narrate

CANDIDATE_MODELS = [
    "HuggingFaceTB/SmolVLM2-2.2B-Instruct",
    "Qwen/Qwen2.5-VL-3B-Instruct",
    "Qwen/Qwen2.5-VL-7B-Instruct",
    "google/gemma-3-4b-it",
]

EVAL_STYLES = ["deadpan", "noir", "nature_doc"]

# .heic/.heif (iPhone default) decode via pillow-heif, registered in small_cuts/__init__.py
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}

# Real Small Cuts input is video (Ray-Ban / phone clips). When a directory holds
# videos, we sample frames so the model eval runs on representative stills.
VIDEO_SUFFIXES = {".mov", ".mp4", ".m4v", ".webm", ".avi", ".mkv"}

RUBRIC = (
    "Score each cell 1-5 on: **S**pecificity (names real visible things), "
    "**G**roundedness (no invented objects/people), **V**oice (style lands). "
    "A model needs S>=4 and G>=4 on most images to be the pick."
)


def _sample_video_frames(
    video: Path,
    every_n_seconds: float = 3.0,
    output_dir: Path | None = None,
) -> list[Path]:
    """Extract frames from a video into an output directory; return their paths."""
    from .frames import sample_frames

    images = sample_frames(video, every_n_seconds=every_n_seconds)
    output = output_dir or Path(tempfile.mkdtemp(prefix="small-cuts-eval-frames-"))
    output.mkdir(parents=True, exist_ok=True)
    out_paths: list[Path] = []
    for i, img in enumerate(images):
        out = output / f"{video.stem}_frame{i:06d}.jpg"
        img.save(out)
        out_paths.append(out)
    return out_paths


def load_images(images_dir: Path, frame_dir: Path | None = None) -> list[Path]:
    if not images_dir.exists():
        raise SystemExit(f"Directory does not exist: {images_dir}")
    entries = sorted(p for p in images_dir.iterdir() if p.is_file())
    paths = [p for p in entries if p.suffix.lower() in IMAGE_SUFFIXES]
    videos = [p for p in entries if p.suffix.lower() in VIDEO_SUFFIXES]
    for video in videos:
        print(f"Sampling frames from {video.name}")
        paths.extend(_sample_video_frames(video, output_dir=frame_dir))
    if not paths:
        listing = "\n".join(f"  {p.name}" for p in entries) or "  (directory is empty)"
        raise SystemExit(
            f"No images or videos found in {images_dir}.\n"
            f"Directory contains:\n{listing}\n"
            f"Recognized image suffixes: {sorted(IMAGE_SUFFIXES)}\n"
            f"Recognized video suffixes: {sorted(VIDEO_SUFFIXES)}"
        )
    return sorted(paths)


def run_model(
    model_id: str, image_paths: list[Path], styles: list[str], backend_name: str
) -> dict[tuple[str, str], Narration]:
    backend = MockBackend() if backend_name == "mock" else TransformersBackend(model_id=model_id)
    results: dict[tuple[str, str], Narration] = {}
    for path in image_paths:
        image = Image.open(path).convert("RGB")
        for style in styles:
            result = narrate(image, style_key=style, backend=backend)
            results[(path.name, style)] = result
            print(f"  {model_id} | {path.name} | {style} | {result.latency_s:.1f}s")
    return results


def render_report(
    all_results: dict[str, dict[tuple[str, str], Narration]],
    image_paths: list[Path],
    styles: list[str],
) -> str:
    lines = [
        "# Small Cuts — M1 Narrator Model Eval",
        "",
        f"Generated {time.strftime('%Y-%m-%d %H:%M:%S')}.",
        "",
        RUBRIC,
        "",
    ]
    for path in image_paths:
        lines.append(f"## {path.name}")
        lines.append("")
        lines.append("| Model | Style | Narration | Latency | S | G | V |")
        lines.append("|---|---|---|---|---|---|---|")
        for model_id, results in all_results.items():
            for style in styles:
                narration = results.get((path.name, style))
                if narration is None:
                    lines.append(f"| {model_id} | {style} | (failed) | - |  |  |  |")
                    continue
                text = narration.text.replace("\n", " ").replace("|", "\\|")
                lines.append(
                    f"| {model_id} | {style} | {text} | {narration.latency_s:.1f}s |  |  |  |"
                )
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, required=True, help="Directory of eval photos")
    parser.add_argument("--models", nargs="*", default=CANDIDATE_MODELS)
    parser.add_argument("--styles", nargs="*", default=EVAL_STYLES)
    parser.add_argument("--out", type=Path, default=Path("eval-report.md"))
    parser.add_argument("--backend", choices=["transformers", "mock"], default="transformers")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="small-cuts-eval-frames-") as frame_dir:
        image_paths = load_images(args.images, frame_dir=Path(frame_dir))
        models = args.models if args.backend == "transformers" else ["mock"]
        all_results = {}
        failures = []
        for model_id in models:
            try:
                all_results[model_id] = run_model(model_id, image_paths, args.styles, args.backend)
            except Exception as exc:  # one gated/broken model must not kill the eval
                failures.append(f"{model_id}: {type(exc).__name__}: {exc}")
                print(f"  FAILED {model_id}: {exc}")
        if not all_results:
            raise SystemExit("All models failed:\n" + "\n".join(failures))
        report = render_report(all_results, image_paths, args.styles)
        if failures:
            report += "\n## Failed models\n\n" + "\n".join(f"- {f}" for f in failures) + "\n"
        args.out.write_text(report)
    print(f"\nReport written to {args.out}")


if __name__ == "__main__":
    main()
