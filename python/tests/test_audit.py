"""Integration tests using actual image bytes, rather than mocked scan records."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, features

from splitlens import ScanLimits, audit


def save_image(
    root: Path,
    relative: str,
    *,
    size: tuple[int, int] = (300, 300),
    color: tuple[int, int, int] = (120, 120, 120),
) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with Image.new("RGB", size, color) as image:
        image.save(path)
    return path


def kinds_for(report, path: str) -> set[str]:
    identifier = next(image.id for image in report.images if image.path == path)
    return {finding.kind for finding in report.findings if identifier in finding.image_ids}


def test_real_sha_duplicates_and_cross_split_leakage(tmp_path: Path) -> None:
    source = save_image(tmp_path, "train/cat/original.png")
    target = tmp_path / "test/cat/copied.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(source.read_bytes())
    report = audit(tmp_path)
    assert len(report.images) == 2
    assert {image.sha256 for image in report.images} == {
        hashlib.sha256(source.read_bytes()).hexdigest()
    }
    assert len(report.findings_of("duplicate")) == 1
    assert len(report.findings_of("leakage")) == 1
    assert set(report.findings_of("leakage")[0].image_ids) == {image.id for image in report.images}
    assert all(image.label == "cat" for image in report.images)


def test_same_split_exact_copies_are_not_leakage(tmp_path: Path) -> None:
    source = save_image(tmp_path, "training/cats/a.png")
    (source.parent / "b.png").write_bytes(source.read_bytes())
    report = audit(tmp_path)
    assert len(report.findings_of("duplicate")) == 1
    assert report.findings_of("leakage") == ()


@pytest.mark.parametrize(
    ("directory", "expected"),
    [
        ("TrAiN", "train"),
        ("training", "train"),
        ("val", "validation"),
        ("valid", "validation"),
        ("validation", "validation"),
        ("test", "test"),
        ("testing", "test"),
        ("other", "unassigned"),
    ],
)
def test_metadata_aliases(tmp_path: Path, directory: str, expected: str) -> None:
    save_image(tmp_path, f"{directory}/cats/image.png")
    record = audit(tmp_path).images[0]
    assert record.split == expected
    assert record.label == ("cats" if expected != "unassigned" else "unlabeled")


def test_split_override_can_explicitly_unassign(tmp_path: Path) -> None:
    save_image(tmp_path, "train/cats/a.png")
    record = audit(tmp_path, splits={"train/cats/a.png": "unassigned"}).images[0]
    assert record.split == "unassigned"
    assert record.label == "cats"


def test_unknown_split_override_rejected_before_scanning(tmp_path: Path) -> None:
    save_image(tmp_path, "a.png")
    with pytest.raises(ValueError, match="unknown paths"):
        audit(tmp_path, splits={"missing.png": "train"})


def test_invalid_split_override(tmp_path: Path) -> None:
    save_image(tmp_path, "a.png")
    with pytest.raises(ValueError, match="Split overrides"):
        audit(tmp_path, splits={"a.png": "eval"})


def test_decode_failure_retains_digest_and_scan_continues(tmp_path: Path) -> None:
    save_image(tmp_path, "healthy.png")
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"this is not a jpeg")
    report = audit(tmp_path)
    assert len(report.images) == 2
    image = next(image for image in report.images if image.path == "broken.jpg")
    assert image.error
    assert image.sha256 == hashlib.sha256(broken.read_bytes()).hexdigest()
    assert image.bytes == broken.stat().st_size
    assert kinds_for(report, "broken.jpg") == {"broken"}
    assert next(image for image in report.images if image.path == "healthy.png").error is None


def test_truncated_real_png_is_a_broken_finding(tmp_path: Path) -> None:
    path = save_image(tmp_path, "truncated.png")
    path.write_bytes(path.read_bytes()[:40])
    report = audit(tmp_path)
    assert report.images[0].error
    assert kinds_for(report, "truncated.png") == {"broken"}


@pytest.mark.parametrize(
    ("encoding", "extension", "feature"),
    [
        ("PNG", ".PNG", None),
        ("JPEG", ".jpeg", None),
        ("WEBP", ".webp", "webp"),
        ("BMP", ".bmp", None),
        ("AVIF", ".avif", "avif"),
    ],
)
def test_supported_encodings_decode(
    tmp_path: Path, encoding: str, extension: str, feature: str | None
) -> None:
    if feature is not None and not features.check(feature):
        pytest.skip(f"This Pillow build does not support {encoding}")
    with Image.new("RGB", (300, 280), (100, 140, 180)) as image:
        image.save(tmp_path / ("image" + extension), format=encoding)
    record = audit(tmp_path).images[0]
    assert record.error is None
    assert (record.width, record.height) == (300, 280)
    assert len(record.sha256) == 64
    assert len(record.dhash) == 16


def test_gif_disguised_as_png_is_rejected(tmp_path: Path) -> None:
    with Image.new("RGB", (32, 32), "red") as image:
        image.save(tmp_path / "disguised.png", format="GIF")
    image = audit(tmp_path).images[0]
    assert image.error and "Unsupported image encoding" in image.error


def test_real_animated_png_is_rejected(tmp_path: Path) -> None:
    with Image.new("RGB", (32, 32), "red") as first:
        with Image.new("RGB", (32, 32), "blue") as second:
            first.save(
                tmp_path / "animated.png",
                save_all=True,
                append_images=[second],
                duration=100,
                loop=0,
            )
    image = audit(tmp_path).images[0]
    assert image.error and "Animated images" in image.error


def test_max_pixels_records_broken_without_aborting_dataset(tmp_path: Path) -> None:
    save_image(tmp_path, "big.png", size=(20, 20))
    save_image(tmp_path, "small.png", size=(10, 10))
    report = audit(tmp_path, limits=ScanLimits(max_pixels=100))
    assert "max_pixels" in report.images[0].error
    assert report.images[1].error is None


def test_file_byte_limit_is_enforced(tmp_path: Path) -> None:
    path = save_image(tmp_path, "a.png")
    with pytest.raises(ValueError, match="max_file_bytes"):
        audit(tmp_path, limits=ScanLimits(max_file_bytes=path.stat().st_size - 1))


def test_total_byte_limit_is_enforced(tmp_path: Path) -> None:
    first = save_image(tmp_path, "a.png")
    second = save_image(tmp_path, "b.png")
    limit = first.stat().st_size + second.stat().st_size - 1
    with pytest.raises(ValueError, match="total-byte limit"):
        audit(tmp_path, limits=ScanLimits(max_total_bytes=limit))


def test_image_count_limit_is_enforced(tmp_path: Path) -> None:
    save_image(tmp_path, "a.png")
    save_image(tmp_path, "b.png")
    with pytest.raises(ValueError, match="image-count"):
        audit(tmp_path, limits=ScanLimits(max_images=1))


def test_quality_findings_on_actual_images(tmp_path: Path) -> None:
    save_image(tmp_path, "dark.png", color=(0, 0, 0))
    save_image(tmp_path, "bright.png", color=(255, 255, 255))
    save_image(tmp_path, "smooth.png", color=(120, 120, 120))
    save_image(tmp_path, "tiny.png", size=(12, 20), color=(120, 120, 120))
    checker = ((np.indices((128, 128)).sum(axis=0) % 2) * 255).astype(np.uint8)
    with Image.fromarray(np.repeat(checker[..., None], 3, axis=2)) as image:
        image.save(tmp_path / "detailed.png")
    report = audit(tmp_path)
    assert "dark" in kinds_for(report, "dark.png")
    assert "bright" in kinds_for(report, "bright.png")
    assert "blur" in kinds_for(report, "smooth.png")
    assert "small" in kinds_for(report, "tiny.png")
    assert "blur" not in kinds_for(report, "detailed.png")


def test_transparency_is_composited_on_white(tmp_path: Path) -> None:
    with Image.new("RGBA", (300, 300), (0, 0, 0, 0)) as image:
        image.save(tmp_path / "transparent.png")
    report = audit(tmp_path)
    record = report.images[0]
    assert record.brightness == pytest.approx(255)
    assert record.mean_rgb == pytest.approx((255, 255, 255))
    assert "bright" in kinds_for(report, "transparent.png")
    assert "dark" not in kinds_for(report, "transparent.png")


def test_exif_orientation_is_applied(tmp_path: Path) -> None:
    with Image.new("RGB", (80, 40), "red") as image:
        exif = Image.Exif()
        exif[274] = 6
        image.save(tmp_path / "rotated.jpg", exif=exif)
    record = audit(tmp_path).images[0]
    assert (record.width, record.height) == (40, 80)


def test_resized_reencoded_image_is_a_near_duplicate_candidate(tmp_path: Path) -> None:
    y, x = np.indices((300, 300))
    gray = (120 + 55 * np.sin(x / 19) + 45 * np.cos(y / 23)).clip(0, 255).astype(np.uint8)
    pixels = np.repeat(gray[..., None], 3, axis=2)
    (tmp_path / "train").mkdir()
    (tmp_path / "test").mkdir()
    with Image.fromarray(pixels) as image:
        image.save(tmp_path / "train/original.png")
        with image.resize((450, 450), Image.Resampling.BILINEAR) as resized:
            resized.save(tmp_path / "test/resized.jpg", quality=90)
    report = audit(tmp_path)
    assert report.images[0].sha256 != report.images[1].sha256
    assert len(report.findings_of("similar")) == 1
    assert len(report.findings_of("leakage")) == 1
    assert report.findings_of("duplicate") == ()


def test_progress_is_sequential_and_records_are_deterministic(tmp_path: Path) -> None:
    save_image(tmp_path, "z.png")
    save_image(tmp_path, "a.png")
    progress = []
    report = audit(tmp_path, on_progress=lambda current, total: progress.append((current, total)))
    assert progress == [(1, 2), (2, 2)]
    assert [image.path for image in report.images] == ["a.png", "z.png"]
    assert [image.id for image in report.images] == ["image-1", "image-2"]


def test_progress_callback_exception_is_not_swallowed(tmp_path: Path) -> None:
    save_image(tmp_path, "a.png")

    def cancel(current: int, total: int) -> None:
        raise RuntimeError("caller cancelled")

    with pytest.raises(RuntimeError, match="caller cancelled"):
        audit(tmp_path, on_progress=cancel)


def test_thumbnails_are_opt_in_and_source_bytes_unchanged(tmp_path: Path) -> None:
    source = save_image(tmp_path, "a.png")
    before = source.read_bytes()
    assert audit(tmp_path).images[0].thumbnail == ""
    report = audit(tmp_path, thumbnails=True)
    assert report.images[0].thumbnail.startswith("data:image/jpeg;base64,")
    assert source.read_bytes() == before
    assert list(tmp_path.iterdir()) == [source]


def test_unsupported_files_are_ignored(tmp_path: Path) -> None:
    save_image(tmp_path, "a.png")
    (tmp_path / "notes.txt").write_text("notes")
    (tmp_path / "photo.gif").write_bytes(b"not scanned")
    assert len(audit(tmp_path).images) == 1


def test_empty_dataset_and_missing_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No supported images"):
        audit(tmp_path)
    with pytest.raises(ValueError, match="existing directory"):
        audit(tmp_path / "missing")


@pytest.mark.parametrize(
    "options",
    [
        {"settings": {}},
        {"limits": {}},
        {"thumbnails": 1},
        {"on_progress": False},
    ],
)
def test_invalid_api_options(tmp_path: Path, options: dict) -> None:
    save_image(tmp_path, "a.png")
    with pytest.raises(TypeError):
        audit(tmp_path, **options)


def test_links_skipped_without_following_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "dataset"
    root.mkdir()
    save_image(root, "safe.png")
    outside = save_image(tmp_path, "outside.png")
    try:
        (root / "linked.png").symlink_to(outside)
    except OSError:
        pytest.skip("Creating symbolic links is not permitted on this host")
    report = audit(root)
    assert [image.path for image in report.images] == ["safe.png"]
    assert any("linked.png" in warning for warning in report.warnings)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
def test_windows_junction_directory_is_skipped(tmp_path: Path) -> None:
    powershell = shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is unavailable to create the junction fixture")
    root = tmp_path / "dataset"
    root.mkdir()
    save_image(root, "safe.png")
    outside = tmp_path / "outside"
    save_image(outside, "hidden.png")
    link = root / "linked"
    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "New-Item -ItemType Junction -Path $env:SPLITLENS_TEST_JUNCTION "
            "-Target $env:SPLITLENS_TEST_TARGET -ErrorAction Stop | Out-Null",
        ],
        env={
            **os.environ,
            "SPLITLENS_TEST_JUNCTION": str(link),
            "SPLITLENS_TEST_TARGET": str(outside),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        pytest.skip("Creating a junction fixture is unavailable: " + result.stderr)
    report = audit(root)
    assert [image.path for image in report.images] == ["safe.png"]
    assert any("linked" in warning for warning in report.warnings)
