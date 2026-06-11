import re
from pathlib import Path

from PIL import Image

from small_cuts.eval import load_images, render_report, run_model


def make_eval_dir(tmp_path: Path) -> Path:
    for name, color in [("a.jpg", (240, 240, 240)), ("b.png", (10, 10, 10))]:
        Image.new("RGB", (64, 48), color).save(tmp_path / name)
    (tmp_path / "notes.txt").write_text("ignored")
    return tmp_path


def test_load_images_filters_and_sorts(tmp_path):
    paths = load_images(make_eval_dir(tmp_path))
    assert [p.name for p in paths] == ["a.jpg", "b.png"]


def test_mock_eval_produces_report(tmp_path):
    image_paths = load_images(make_eval_dir(tmp_path))
    styles = ["deadpan", "noir"]
    results = {"mock": run_model("mock", image_paths, styles, backend_name="mock")}
    report = render_report(results, image_paths, styles)
    assert "## a.jpg" in report
    assert "## b.png" in report
    # one table row per model x style per image
    assert len(re.findall(r"^\| mock \|", report, flags=re.M)) == 4
    assert "**S**pecificity" in report
