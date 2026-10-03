from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from splitlens.models import AuditSettings, Finding, ImageRecord
from splitlens.report import AuditReport, load_json


@pytest.fixture
def report(tmp_path: Path) -> AuditReport:
    root = tmp_path / "source"
    root.mkdir()
    images = []
    for index, relative in enumerate(("train/cat/a.png", "test/cat/b.png", "other/broken.png")):
        source = root / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        content = b"original image bytes" if index < 2 else b"bad png bytes"
        source.write_bytes(content)
        images.append(
            ImageRecord(
                id=f"image-{index}",
                path=relative,
                split="train" if index == 0 else "test",
                label="cat",
                width=128,
                height=128,
                bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                dhash="aaaaaaaaaaaaaaaa",
                brightness=128.0,
                sharpness=80.0,
                mean_rgb=(128.0, 128.0, 128.0),
                thumbnail="data:image/png;base64,YQ==",
                error="Invalid PNG" if index == 2 else None,
            )
        )
    finding = Finding(
        id="finding-1",
        kind="leakage",
        image_ids=("image-0", "image-1"),
        title="Cross-split match",
        detail="Review both files",
        distance=0,
    )
    return AuditReport(
        root=root,
        images=tuple(images),
        findings=(finding,),
        settings=AuditSettings(),
        elapsed_seconds=0.125,
        warnings=("A warning",),
    )


def test_decisions_are_immutable_snapshot_and_path_based(report: AuditReport):
    decisions = {"train/cat/a.png": "exclude"}
    reviewed = replace(report, decisions=decisions)
    decisions.clear()
    assert reviewed.decisions["train/cat/a.png"] == "exclude"
    with pytest.raises(TypeError):
        reviewed.decisions["train/cat/a.png"] = "keep"
    with pytest.raises(FrozenInstanceError):
        reviewed.elapsed_seconds = 0
    assert report.decisions == {}
    assert reviewed.keep("train/cat/a.png").summary["excluded"] == 0
    assert reviewed.with_decisions({"train/cat/a.png": "unreviewed"}).summary["reviewed"] == 0
    with pytest.raises(ValueError, match="unknown image path"):
        report.exclude(["image-0"])
    with pytest.raises(ValueError, match="Unknown decision"):
        report.with_decisions({"train/cat/a.png": "remove"})


def test_summary_and_kind_filter(report: AuditReport):
    reviewed = report.exclude(["test/cat/b.png"]).keep(["train/cat/a.png"])
    assert reviewed.summary["images"] == 3
    assert reviewed.summary["findings"] == 1
    assert reviewed.summary["by_kind"]["leakage"] == 1
    assert reviewed.summary["excluded"] == 1
    assert reviewed.summary["reviewed"] == 2
    assert reviewed.findings_of("leakage") == report.findings
    assert reviewed.findings_of("dark") == ()
    with pytest.raises(ValueError, match="Unknown finding kind"):
        reviewed.findings_of("unreal")


def test_json_roundtrip_is_browser_schema_without_images(report: AuditReport, tmp_path: Path):
    reviewed = report.exclude(["test/cat/b.png"])
    filename = reviewed.save_json(tmp_path / "report.json")
    raw = json.loads(filename.read_text(encoding="utf-8"))
    assert raw["schemaVersion"] == 1
    assert raw["sourceRoot"] == str(report.root)
    assert raw["elapsedMs"] == 125
    assert raw["settings"]["minSize"] == 256
    assert raw["images"][0]["meanRgb"] == [128.0] * 3
    assert all("thumbnail" not in image for image in raw["images"])
    assert raw["findings"][0]["imageIds"] == ["image-0", "image-1"]
    loaded = load_json(filename)
    assert tuple(replace(image, thumbnail="") for image in reviewed.images) == loaded.images
    assert reviewed.decisions == loaded.decisions
    assert reviewed.findings == loaded.findings
    assert reviewed.warnings == loaded.warnings
    assert AuditReport.load_json(filename, root=tmp_path / "rebased").root == tmp_path / "rebased"


def test_load_browser_report_needs_root(report: AuditReport, tmp_path: Path):
    raw = report.to_dict()
    raw.pop("sourceRoot")
    raw.pop("warnings")
    raw["settings"].pop("maxPairs")
    filename = tmp_path / "browser.json"
    filename.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="explicit source root"):
        load_json(filename)
    assert load_json(filename, root=report.root).images[0].path == "train/cat/a.png"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data.update(schemaVersion=True),
        lambda data: data.update(schemaVersion=2),
        lambda data: data.update(elapsedMs=float("nan")),
        lambda data: data.update(sourceRoot="relative"),
        lambda data: data.update(unexpected="field"),
        lambda data: data["images"][0].update(path="../escape.png"),
        lambda data: data["images"][0].update(width=True),
        lambda data: data["images"][0].update(sha256="not-a-digest"),
        lambda data: data["images"][0].update(meanRgb="wrong type"),
        lambda data: data["images"][0].update(decision="delete"),
        lambda data: data["images"][0].update(thumbnail="data:image/png;base64,YQ=="),
        lambda data: data["images"][1].update(id="image-0"),
        lambda data: data["findings"][0].update(imageIds=["unknown"]),
        lambda data: data["findings"][0].update(kind="not-an-issue"),
        lambda data: data["settings"].update(similarity=True),
    ],
)
def test_json_rejects_invalid_metadata(report: AuditReport, tmp_path: Path, mutation):
    raw = report.to_dict()
    mutation(raw)
    filename = tmp_path / "invalid.json"
    filename.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        load_json(filename)


def test_json_duplicate_keys_rejected(tmp_path: Path):
    filename = tmp_path / "duplicate.json"
    filename.write_text('{"schemaVersion":1,"schemaVersion":2}', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate JSON field"):
        load_json(filename)


@pytest.mark.parametrize(
    "path",
    [
        "/absolute.png",
        "../escape.png",
        "a/../b.png",
        "a//b.png",
        "a\\b.png",
        "a/./b.png",
        "CON.png",
        "nul/a.png",
        "a:name.png",
        "a.png.",
        "bad /a.png",
        "_SPLITLENS/a.png",
    ],
)
def test_unsafe_portable_image_paths_rejected(report: AuditReport, path: str):
    with pytest.raises(ValueError):
        replace(report, images=(replace(report.images[0], path=path),), findings=())


def test_colliding_paths_rejected(report: AuditReport):
    first = report.images[0]
    with pytest.raises(ValueError, match="unique"):
        replace(
            report,
            images=(first, replace(first, id="another", path=first.path.upper())),
            findings=(),
        )
    with pytest.raises(ValueError, match="parent directory"):
        replace(
            report,
            images=(
                replace(first, path="train"),
                replace(first, id="another", path="train/file.png"),
            ),
            findings=(),
        )


def test_export_only_manual_exclusions_and_byte_integrity(report: AuditReport, tmp_path: Path):
    reviewed = report.exclude(["test/cat/b.png"]).keep(["train/cat/a.png"])
    destination = reviewed.export_dataset(tmp_path / "curated")
    assert (destination / "train/cat/a.png").read_bytes() == (
        report.root / "train/cat/a.png"
    ).read_bytes()
    assert not (destination / "test/cat/b.png").exists()
    # A broken file remains unless explicitly excluded, preserving original bytes.
    assert (destination / "other/broken.png").read_bytes() == b"bad png bytes"
    rows = list(
        csv.DictReader(
            (destination / "_splitlens/manifest.csv").open(encoding="utf-8-sig", newline="")
        )
    )
    assert rows[0]["archive_path"] == "train/cat/a.png"
    assert rows[1]["archive_path"] == ""
    assert rows[2]["decision"] == "unreviewed"
    assert load_json(destination / "_splitlens/audit.json").decisions == reviewed.decisions
    assert (report.root / "test/cat/b.png").exists()


@pytest.mark.parametrize("content", [b"different same size!!", b"longer mutated image content"])
def test_mutated_source_aborts_whole_export(report: AuditReport, tmp_path: Path, content: bytes):
    source = report.root / "test/cat/b.png"
    source.write_bytes(content)
    destination = tmp_path / "curated"
    with pytest.raises(ValueError, match="Source changed"):
        report.export_dataset(destination)
    assert not destination.exists()
    assert not list(tmp_path.glob(".curated.splitlens-*"))


def test_digest_mismatch_same_size_aborts_export(report: AuditReport, tmp_path: Path):
    source = report.root / "train/cat/a.png"
    content = source.read_bytes()
    source.write_bytes(b"X" * len(content))
    with pytest.raises(ValueError, match="SHA-256"):
        report.export_dataset(tmp_path / "curated")
    assert not (tmp_path / "curated").exists()


def test_missing_digest_is_explicit_export_failure(report: AuditReport, tmp_path: Path):
    report = replace(report, images=(replace(report.images[0], sha256=""),), findings=())
    with pytest.raises(ValueError, match="without an audited SHA-256"):
        report.export_dataset(tmp_path / "curated")
    assert not (tmp_path / "curated").exists()


def test_export_excluded_missing_file_is_not_read(report: AuditReport, tmp_path: Path):
    reviewed = report.exclude(["test/cat/b.png"])
    (report.root / "test/cat/b.png").unlink()
    assert reviewed.export_dataset(tmp_path / "curated").is_dir()


def test_export_never_overwrites_or_enters_source(report: AuditReport, tmp_path: Path):
    existing = tmp_path / "curated"
    existing.mkdir()
    sentinel = existing / "sentinel"
    sentinel.write_text("safe")
    with pytest.raises(FileExistsError):
        report.export_dataset(existing)
    assert sentinel.read_text() == "safe"
    for destination in (report.root, report.root / "curated", report.root.parent):
        with pytest.raises(ValueError, match="outside"):
            report.export_dataset(destination)


def test_reports_cannot_overwrite_audited_sources(report: AuditReport, tmp_path: Path):
    source = report.root / "train/cat/a.png"
    original = source.read_bytes()
    for method in (report.save_json, report.save_csv, report.save_html):
        with pytest.raises(ValueError, match="overwrite an audited image"):
            method(source)
    assert source.read_bytes() == original
    target = tmp_path / "report.json"
    target.write_text("old")
    report.save_json(target)
    assert load_json(target).summary == report.summary
    assert not list(tmp_path.glob(".report.json.*.tmp"))


def test_html_escapes_metadata_and_has_no_network_or_script(report: AuditReport, tmp_path: Path):
    finding = replace(
        report.findings[0],
        title='<script>alert("x")</script>',
        detail="<img src=https://evil.test>",
    )
    report = replace(
        report,
        findings=(finding,),
        images=tuple(
            replace(image, thumbnail="data:image/svg+xml;base64,PHN2Zz4=")
            for image in report.images
        ),
        warnings=("<script>danger</script>",),
    )
    content = report.save_html(tmp_path / "report.html").read_text(encoding="utf-8")
    assert "<script>" not in content
    assert "&lt;script&gt;" in content
    assert "<img" not in content
    assert "Content-Security-Policy" in content
    assert "Preview unavailable" in content
    assert "data:image" not in content


def test_html_cached_safe_previews_and_json_no_previews(report: AuditReport, tmp_path: Path):
    content = report.save_html(tmp_path / "with-previews.html").read_text(encoding="utf-8")
    assert '<img src="data:image/png;base64,YQ=="' in content
    assert "img-src data:" in content
    loaded = load_json(report.save_json(tmp_path / "metadata.json"))
    metadata_html = loaded.save_html(tmp_path / "no-previews.html").read_text(encoding="utf-8")
    assert "<img " not in metadata_html
    assert "Preview unavailable" in metadata_html


def test_atomic_export_destination_race_does_not_overwrite(
    report: AuditReport, tmp_path: Path, monkeypatch
):
    from splitlens import report as report_module

    original_rename = report_module._rename_exclusive
    destination = tmp_path / "curated"

    def introduce_conflicting_destination(source, target):
        target.mkdir()
        (target / "sentinel").write_text("existing data", encoding="utf-8")
        return original_rename(source, target)

    monkeypatch.setattr(report_module, "_rename_exclusive", introduce_conflicting_destination)
    with pytest.raises(FileExistsError):
        report.export_dataset(destination)
    assert (destination / "sentinel").read_text(encoding="utf-8") == "existing data"
    assert not (destination / "train").exists()
    assert not list(tmp_path.glob(".curated.splitlens-*"))


def test_reanalysis_preserves_decisions(report: AuditReport):
    reviewed = report.exclude(["test/cat/b.png"])
    adjusted = reviewed.reanalyze(AuditSettings(min_size=512))
    assert adjusted.decisions == reviewed.decisions
    assert adjusted.settings.min_size == 512
    assert adjusted.findings_of("small")
    assert reviewed.settings.min_size == 256


def test_csv_neutralizes_formulas_preserves_newlines(report: AuditReport, tmp_path: Path):
    report = replace(
        report,
        images=(replace(report.images[0], label='  =HYPERLINK("evil")', error="multiline\nerror"),),
        findings=(),
    )
    path = report.save_csv(tmp_path / "report.csv")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        row = next(csv.DictReader(stream))
    assert row["label"] == '\'  =HYPERLINK("evil")'
    assert row["decode_error"] == "multiline\nerror"


def _symlink_or_skip(link: Path, target: Path, *, directory: bool = False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks unavailable for this user/platform")


def test_symlink_input_and_output_are_rejected(report: AuditReport, tmp_path: Path):
    source = report.root / "train/cat/a.png"
    real_source = tmp_path / "real.png"
    source.rename(real_source)
    _symlink_or_skip(source, real_source)
    with pytest.raises(ValueError, match="Symlinks"):
        report.export_dataset(tmp_path / "curated")
    target = tmp_path / "linked-report.json"
    _symlink_or_skip(target, real_source)
    with pytest.raises(ValueError, match="Symlinks"):
        report.save_json(target)
    assert real_source.read_bytes() == b"original image bytes"


def test_symlink_output_parent_rejected(report: AuditReport, tmp_path: Path):
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-parent"
    _symlink_or_skip(linked_parent, real_parent, directory=True)
    with pytest.raises(ValueError, match="Symlinks"):
        report.export_dataset(linked_parent / "curated")
    assert not list(real_parent.iterdir())


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
def test_windows_junction_inputs_and_output_parents_rejected(report: AuditReport, tmp_path: Path):
    powershell = shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is unavailable to create the junction fixture")
    real = tmp_path / "real-folder"
    real.mkdir()
    junction = tmp_path / "linked-folder"
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
            "SPLITLENS_TEST_JUNCTION": str(junction),
            "SPLITLENS_TEST_TARGET": str(real),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        pytest.skip("Creating a junction fixture is unavailable: " + result.stderr)
    with pytest.raises(ValueError, match="junctions"):
        report.export_dataset(junction / "curated")
    with pytest.raises(ValueError, match="junctions"):
        report.save_json(junction / "report.json")
    filename = "original.png"
    (real / filename).write_bytes(b"image bytes")
    linked_root = replace(
        report, root=junction, images=(replace(report.images[0], path=filename),), findings=()
    )
    with pytest.raises(ValueError, match="junctions"):
        linked_root.export_dataset(tmp_path / "curated")
    assert sorted(path.name for path in real.iterdir()) == [filename]
