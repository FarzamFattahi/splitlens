"""Download checksum-pinned real photographs and audit their original dataset.

Run from the repository root:
    python python/examples/beans_case_study.py --workdir .datasets/beans

This uses only SplitLens and the Python standard library. No dataset-loader code
is downloaded or executed. The three public archives total about 180 MB.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import time
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen

import numpy as np
import PIL
from PIL import Image, ImageEnhance, ImageFilter

import splitlens
from splitlens import AuditSettings, audit


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch_archive(item: dict, directory: Path) -> Path:
    path = directory / (item["split"] + ".zip")
    if path.exists():
        if (
            path.is_symlink()
            or path.stat().st_size != item["bytes"]
            or digest(path) != item["sha256"]
        ):
            raise ValueError(f"Existing archive failed verification: {path}")
        print(f"Verified cached {path.name}", flush=True)
        return path
    partial = path.with_suffix(".zip.part")
    # Never overwrite a previous download or a user file.
    downloaded = 0
    owned_partial = False
    last_print = time.monotonic()
    request = Request(item["url"], headers={"User-Agent": "SplitLens-real-dataset-case-study/1.1"})
    print(f"Downloading {path.name}: {item['bytes'] / 1_000_000:.1f} MB", flush=True)
    try:
        with partial.open("xb") as output:
            owned_partial = True
            with urlopen(request, timeout=60) as response:
                while chunk := response.read(1024 * 1024):
                    downloaded += len(chunk)
                    if downloaded > item["bytes"]:
                        raise ValueError(f"Download exceeded pinned size: {path.name}")
                    output.write(chunk)
                    if time.monotonic() - last_print >= 10:
                        print(f"  {path.name}: {downloaded / 1_000_000:.1f} MB", flush=True)
                        last_print = time.monotonic()
        if downloaded != item["bytes"] or digest(partial) != item["sha256"]:
            raise ValueError(f"Download failed SHA-256/size verification: {path.name}")
        os.rename(partial, path)
    except BaseException:
        if owned_partial and partial.is_file() and not partial.is_symlink():
            partial.unlink()
        raise
    print(f"Verified SHA-256: {path.name}", flush=True)
    return path


def extract_archives(archives: list[tuple[dict, Path]], destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(f"Choose a new dataset directory: {destination}")
    # Validate the whole archive inventory before creating any source images.
    inventory = []
    paths = set()
    total_bytes = 0
    for item, path in archives:
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                parts = member.filename.split("/")
                if member.is_dir():
                    continue
                mode = member.external_attr >> 16
                if (
                    len(parts) != 3
                    or parts[0] != item["split"]
                    or any(part in ("", ".", "..") for part in parts)
                    or "\\" in member.filename
                    or ":" in member.filename
                    or (
                        PurePosixPath(member.filename).suffix.lower() not in (".jpg", ".jpeg")
                        and member.filename != "train/healthy/healthy_train.120tore"
                    )
                    or stat.S_ISLNK(mode)
                    or member.flag_bits & 1
                ):
                    raise ValueError(f"Unexpected dataset archive entry: {member.filename!r}")
                key = member.filename.casefold()
                if key in paths:
                    raise ValueError(f"Colliding dataset path: {member.filename}")
                paths.add(key)
                total_bytes += member.file_size
                if (
                    member.file_size > 30 * 1024 * 1024
                    or total_bytes > 300 * 1024 * 1024
                    or len(paths) > 1500
                ):
                    raise ValueError("Dataset archive exceeds expected extraction bounds")
                inventory.append((path, member.filename, member.file_size))
    destination.mkdir()
    try:
        for archive_path, name, expected_size in inventory:
            output = destination.joinpath(*name.split("/"))
            output.parent.mkdir(parents=True, exist_ok=True)
            with (
                zipfile.ZipFile(archive_path) as archive,
                archive.open(name) as source,
                output.open("xb") as target,
            ):
                copied = 0
                while chunk := source.read(1024 * 1024):
                    copied += len(chunk)
                    if copied > expected_size:
                        raise ValueError(f"Expanded dataset entry: {name}")
                    target.write(chunk)
                if copied != expected_size:
                    raise ValueError(f"Truncated dataset entry: {name}")
    except BaseException:
        # This tree was created exclusively by this invocation, never reused.
        shutil.rmtree(destination)
        raise
    print(f"Extracted {len(paths)} original files; {total_bytes:,} encoded bytes", flush=True)


def verify_originals(report, archives: list[tuple[dict, Path]]) -> list[dict]:
    """Compare scanned originals to archive bytes, including ignored metadata."""
    expected = {}
    ignored = []
    for _, path in archives:
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                with archive.open(member) as stream:
                    value = hashlib.file_digest(stream, "sha256").hexdigest()
                source = report.root.joinpath(*member.filename.split("/"))
                if source.is_symlink() or digest(source) != value:
                    raise ValueError(
                        f"Extracted source differs from pinned archive: {member.filename}"
                    )
                if PurePosixPath(member.filename).suffix.lower() in (".jpg", ".jpeg"):
                    expected[member.filename] = value
                else:
                    ignored.append(
                        {
                            "path": member.filename,
                            "bytes": member.file_size,
                            "sha256": value,
                            "reason": "Unsupported extension; not an audited image",
                        }
                    )
    actual = {image.path: image.sha256 for image in report.images}
    if actual != expected:
        raise ValueError("Dataset image inventory or bytes differ from the pinned source archives")
    print("All audited originals verified against archive bytes", flush=True)
    return ignored


def write_json(path: Path, data: object) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8"
    )


def save_public_report(report, reports: Path, name: str, title: str) -> None:
    public = report.to_dict()
    public.pop("sourceRoot")
    public["dataset"] = title
    write_json(reports / f"{name}.json", public)
    report.save_csv(reports / f"{name}.csv")


def run_controls(baseline, workdir: Path, reports: Path) -> dict:
    """Add disclosed defects to a separate copy, then verify an explicit repair."""
    controlled_root = workdir / "controlled"
    curated_root = workdir / "curated"
    if controlled_root.exists() or curated_root.exists():
        raise FileExistsError("Controlled/curated directories must be new; choose another workdir")
    shutil.copytree(baseline.root, controlled_root)
    originals = {
        label: next(
            image for image in baseline.images if image.split == "train" and image.label == label
        )
        for label in ("healthy", "angular_leaf_spot", "bean_rust")
    }
    recipes = [
        ("exact", "healthy", "test/healthy/zz_splitlens_exact-copy.jpg", ["duplicate", "leakage"]),
        (
            "reencode",
            "angular_leaf_spot",
            "validation/angular_leaf_spot/zz_splitlens_reencoded.jpg",
            ["similar", "leakage"],
        ),
        ("blur", "bean_rust", "train/bean_rust/zz_splitlens_blurred.jpg", ["blur"]),
        ("dark", "healthy", "train/healthy/zz_splitlens_dark.jpg", ["dark"]),
        ("small", "bean_rust", "validation/bean_rust/zz_splitlens_small.jpg", ["small"]),
        (
            "broken",
            "angular_leaf_spot",
            "test/angular_leaf_spot/zz_splitlens_broken.jpg",
            ["broken"],
        ),
    ]
    changes = []
    for operation, label, relative, expected in recipes:
        source = originals[label]
        output = controlled_root / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        if operation == "exact":
            shutil.copyfile(baseline.root / source.path, output)
            description = "Original encoded bytes copied into the test split"
        elif operation == "broken":
            output.write_bytes(
                b"SplitLens explicitly injected corrupt-image control; not source data."
            )
            description = "Deliberately unreadable JPEG encoding"
        else:
            with Image.open(baseline.root / source.path) as image:
                image = image.convert("RGB")
                if operation == "blur":
                    changed = image.filter(ImageFilter.GaussianBlur(14))
                    description = "Gaussian blur, radius 14 pixels"
                elif operation == "dark":
                    changed = ImageEnhance.Brightness(image).enhance(0.08)
                    description = "Brightness multiplied by 0.08"
                elif operation == "small":
                    changed = image.resize((96, 96), Image.Resampling.LANCZOS)
                    description = "Resized to 96 × 96 pixels"
                else:
                    changed = image.copy()
                    description = "Same pixels re-encoded as JPEG quality 92"
                changed.save(output, format="JPEG", quality=92)
                changed.close()
                image.close()
        changes.append(
            {
                "injected": True,
                "path": relative,
                "source_path": source.path,
                "operation": operation,
                "description": description,
                "expected_kinds": expected,
                "sha256": digest(output),
            }
        )
    print("Added six disclosed control files to a separate dataset copy", flush=True)
    controlled = audit(controlled_root, thumbnails=True)
    controlled.save_json(reports / "controlled-local.json")
    controlled.save_html(reports / "controlled.html")
    save_public_report(controlled, reports, "controlled", "Beans — six explicitly injected defects")
    by_path = {image.path: image for image in controlled.images}
    for change in changes:
        identifier = by_path[change["path"]].id
        kinds = sorted(
            {finding.kind for finding in controlled.findings if identifier in finding.image_ids}
        )
        change["detected_kinds"] = kinds
        change["expected_detection_passed"] = set(change["expected_kinds"]) <= set(kinds)
        if not change["expected_detection_passed"]:
            raise ValueError(f"Control was not detected as expected: {change['path']}")
    retained = controlled.exclude([change["path"] for change in changes])
    print("Exporting only after six explicit exclusions", flush=True)
    start = time.perf_counter()
    retained.export_dataset(curated_root)
    export_seconds = time.perf_counter() - start
    curated = audit(curated_root)
    save_public_report(curated, reports, "curated", "Beans — repaired control dataset")
    expected = {image.path: image.sha256 for image in baseline.images}
    actual = {image.path: image.sha256 for image in curated.images}
    if expected != actual:
        raise ValueError("Curated original-image paths or bytes differ from the untouched baseline")
    if baseline.summary["by_kind"] != curated.summary["by_kind"]:
        raise ValueError("Repaired findings differ from original baseline")
    result = {
        "type": "controlled_contamination_not_natural_defects",
        "injected_files": changes,
        "controlled": {
            "summary": controlled.summary,
            "elapsed_seconds": controlled.elapsed_seconds,
        },
        "curated": {"summary": curated.summary, "elapsed_seconds": curated.elapsed_seconds},
        "export_seconds": export_seconds,
        "original_image_hashes_preserved": len(actual),
        "excluded_only_injected_paths": True,
        "no_source_images_modified": True,
    }
    write_json(reports / "controlled-experiment.json", result)
    print(json.dumps(result, indent=2), flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, default=Path(".datasets/beans"))
    parser.add_argument(
        "--controls",
        action="store_true",
        help="Also test six disclosed defects in a separate copy and verify repair",
    )
    args = parser.parse_args()
    workdir = args.workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    archives_dir = workdir / "archives"
    archives_dir.mkdir(exist_ok=True)
    manifest = json.loads(Path(__file__).with_name("beans-source.json").read_text(encoding="utf-8"))
    archives = [(item, fetch_archive(item, archives_dir)) for item in manifest["archives"]]
    dataset = workdir / "dataset"
    if not dataset.exists():
        extract_archives(archives, dataset)
    reports = workdir / "reports"
    reports.mkdir(exist_ok=True)

    def progress(done: int, total: int) -> None:
        if done % 200 == 0 or done == total:
            print(f"Audited {done}/{total}", flush=True)

    report = audit(dataset, thumbnails=True, on_progress=progress)
    ignored_entries = verify_originals(report, archives)
    report.save_json(reports / "baseline-local.json")
    report.save_csv(reports / "baseline.csv")
    report.save_html(reports / "baseline.html")
    public = report.to_dict()
    public.pop("sourceRoot")
    public["dataset"] = "Makerere Beans — original published splits"
    write_json(reports / "baseline.json", public)
    summary = {
        "source": manifest,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "splitlens": splitlens.__version__,
            "numpy": np.__version__,
            "pillow": PIL.__version__,
        },
        "settings": public["settings"],
        "summary": report.summary,
        "images_by_split": dict(Counter(image.split for image in report.images)),
        "images_by_label": dict(Counter(image.label for image in report.images)),
        "encoded_bytes": sum(image.bytes for image in report.images),
        "elapsed_seconds": report.elapsed_seconds,
        "warnings": list(report.warnings),
        "modified_source_files": 0,
        "ignored_archive_entries": ignored_entries,
    }
    write_json(reports / "summary.json", summary)
    sensitivity = []
    for radius in (4, 8, 12):
        result = report.reanalyze(AuditSettings(similarity=radius))
        sensitivity.append({"similarity": radius, "summary": result.summary})
        save_public_report(
            result, reports, f"radius-{radius}", f"Original Beans — exploratory radius {radius}"
        )
    write_json(reports / "threshold-sensitivity.json", sensitivity)
    if args.controls:
        run_controls(report, workdir, reports)
    print(json.dumps(summary, indent=2), flush=True)
    print(f"Reports: {reports}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        raise SystemExit(f"Beans case study failed: {error}") from error
