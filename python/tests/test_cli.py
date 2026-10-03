"""Exercise the public CLI with real image files and retained original bytes."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from splitlens import AuditReport
from splitlens.cli import main


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    root = tmp_path / "dataset"
    original = root / "train" / "cats" / "original.png"
    original.parent.mkdir(parents=True)
    image = Image.new("RGB", (300, 300))
    image.putdata([(x % 256, (x // 300) % 256, (x * 7) % 256) for x in range(90000)])
    image.save(original)
    copied = root / "test" / "cats" / "copied.png"
    copied.parent.mkdir(parents=True)
    copied.write_bytes(original.read_bytes())
    return root


def test_audit_reports_and_leakage_gate(dataset: Path, tmp_path: Path, capsys) -> None:
    json_path, csv_path, html_path = (tmp_path / f"audit.{ext}" for ext in ("json", "csv", "html"))
    status = main(
        [
            "audit",
            str(dataset),
            "--json",
            str(json_path),
            "--csv",
            str(csv_path),
            "--html",
            str(html_path),
            "--fail-on",
            "leakage,broken",
        ]
    )
    assert status == 1
    assert json.loads(capsys.readouterr().out)["images"] == 2
    report = AuditReport.load_json(json_path)
    assert report.findings_of("leakage")
    # JSON stores portable metadata only; the live scan's previews go into HTML.
    assert all(not record.thumbnail for record in report.images)
    assert "original.png" in csv_path.read_text(encoding="utf-8")
    assert "data:image/" in html_path.read_text(encoding="utf-8")


def test_quiet_and_default_thumbnail_omission(dataset: Path, tmp_path: Path, capsys) -> None:
    json_path = tmp_path / "audit.json"
    assert main(["audit", str(dataset), "--quiet", "--json", str(json_path)]) == 0
    assert capsys.readouterr().out == ""
    assert all(not record.thumbnail for record in AuditReport.load_json(json_path).images)


def test_review_export_preserves_originals(dataset: Path, tmp_path: Path, capsys) -> None:
    original_bytes = {path: path.read_bytes() for path in dataset.rglob("*.png")}
    json_path = tmp_path / "audit.json"
    destination = tmp_path / "curated"
    assert main(["audit", str(dataset), "--quiet", "--json", str(json_path)]) == 0
    assert (
        main(
            [
                "export",
                str(json_path),
                str(destination),
                "--exclude",
                "test/cats/copied.png",
                "--keep",
                "train/cats/original.png",
            ]
        )
        == 0
    )
    assert (destination / "train/cats/original.png").read_bytes() == original_bytes[
        dataset / "train/cats/original.png"
    ]
    assert not (destination / "test/cats/copied.png").exists()
    assert all(path.read_bytes() == content for path, content in original_bytes.items())
    assert "excluded 1" in capsys.readouterr().out


def test_export_keeps_unreviewed_and_applies_saved_decisions(dataset: Path, tmp_path: Path) -> None:
    json_path = tmp_path / "audit.json"
    assert main(["audit", str(dataset), "--quiet", "--json", str(json_path)]) == 0
    report = AuditReport.load_json(json_path).exclude(["test/cats/copied.png"])
    report.save_json(json_path)
    assert main(["export", str(json_path), str(tmp_path / "saved")]) == 0
    assert not (tmp_path / "saved/test/cats/copied.png").exists()
    assert (
        main(
            [
                "export",
                str(json_path),
                str(tmp_path / "restored"),
                "--keep",
                "test/cats/copied.png",
            ]
        )
        == 0
    )
    assert (tmp_path / "restored/test/cats/copied.png").exists()


def test_export_with_no_decisions_copies_all(dataset: Path, tmp_path: Path) -> None:
    json_path = tmp_path / "audit.json"
    assert main(["audit", str(dataset), "--quiet", "--json", str(json_path)]) == 0
    assert main(["export", str(json_path), str(tmp_path / "all")]) == 0
    assert len(list((tmp_path / "all").rglob("*.png"))) == 2


def test_export_rebases_relocated_dataset(dataset: Path, tmp_path: Path) -> None:
    json_path = tmp_path / "audit.json"
    assert main(["audit", str(dataset), "--quiet", "--json", str(json_path)]) == 0
    relocated = tmp_path / "relocated"
    dataset.rename(relocated)
    assert (
        main(
            [
                "export",
                str(json_path),
                str(tmp_path / "curated"),
                "--root",
                str(relocated),
            ]
        )
        == 0
    )
    assert (tmp_path / "curated/train/cats/original.png").exists()


def test_export_changed_source_is_rejected(dataset: Path, tmp_path: Path, capsys) -> None:
    json_path = tmp_path / "audit.json"
    assert main(["audit", str(dataset), "--quiet", "--json", str(json_path)]) == 0
    (dataset / "train/cats/original.png").write_bytes(b"changed source")
    assert main(["export", str(json_path), str(tmp_path / "curated")]) == 2
    assert "Traceback" not in capsys.readouterr().err


def test_broken_file_gate(dataset: Path, capsys) -> None:
    (dataset / "train/cats/broken.png").write_bytes(b"not an image")
    assert main(["audit", str(dataset), "--fail-on", "broken", "--quiet"]) == 1
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize(
    "options",
    [
        ["--similarity", "13"],
        ["--blur", "nan"],
        ["--dark", "240", "--bright", "200"],
        ["--min-size", "-1"],
        ["--max-images", "0"],
        ["--max-file-mb", "nan"],
        ["--max-total-mb", "0"],
        ["--max-pixels", "0"],
        ["--fail-on", "misspelled"],
    ],
)
def test_invalid_audit_configuration(dataset: Path, options: list[str], capsys) -> None:
    assert main(["audit", str(dataset), *options]) == 2
    error = capsys.readouterr().err
    assert error
    assert "Traceback" not in error


def test_repeated_finding_gates(dataset: Path) -> None:
    assert (
        main(
            [
                "audit",
                str(dataset),
                "--quiet",
                "--fail-on",
                "broken",
                "--fail-on",
                "leakage",
            ]
        )
        == 1
    )


def test_bad_paths_and_json(tmp_path: Path, capsys) -> None:
    assert main(["audit", str(tmp_path / "missing")]) == 2
    malformed = tmp_path / "invalid.json"
    malformed.write_text("{", encoding="utf-8")
    assert main(["export", str(malformed), str(tmp_path / "output")]) == 2
    assert "Traceback" not in capsys.readouterr().err


def test_unknown_and_conflicting_decisions(dataset: Path, tmp_path: Path, capsys) -> None:
    json_path = tmp_path / "audit.json"
    assert main(["audit", str(dataset), "--quiet", "--json", str(json_path)]) == 0
    assert (
        main(
            [
                "export",
                str(json_path),
                str(tmp_path / "out"),
                "--exclude",
                "../outside.png",
            ]
        )
        == 2
    )
    assert (
        main(
            [
                "export",
                str(json_path),
                str(tmp_path / "out"),
                "--exclude",
                "missing.png",
            ]
        )
        == 2
    )
    assert (
        main(
            [
                "export",
                str(json_path),
                str(tmp_path / "out"),
                "--exclude",
                "test/cats/copied.png",
                "--keep",
                "test/cats/copied.png",
            ]
        )
        == 2
    )
    assert "Traceback" not in capsys.readouterr().err


def test_existing_export_destination_is_rejected(dataset: Path, tmp_path: Path, capsys) -> None:
    json_path = tmp_path / "audit.json"
    assert main(["audit", str(dataset), "--quiet", "--json", str(json_path)]) == 0
    destination = tmp_path / "existing"
    destination.mkdir()
    sentinel = destination / "preserve.txt"
    sentinel.write_text("untouched", encoding="utf-8")
    assert main(["export", str(json_path), str(destination)]) == 2
    assert sentinel.read_text(encoding="utf-8") == "untouched"
    assert "Traceback" not in capsys.readouterr().err


def test_report_output_cannot_overwrite_source_image(dataset: Path, capsys) -> None:
    source = dataset / "train/cats/original.png"
    original_bytes = source.read_bytes()
    assert main(["audit", str(dataset), "--quiet", "--json", str(source)]) == 2
    assert source.read_bytes() == original_bytes
    assert "Traceback" not in capsys.readouterr().err


def test_cli_help_version_and_invalid_command(capsys) -> None:
    assert main(["--version"]) == 0
    assert "splitlens 1.1.0" in capsys.readouterr().out
    assert main(["--help"]) == 0
    assert "audit" in capsys.readouterr().out
    assert main(["misspelled"]) == 2


def test_real_module_entrypoint(dataset: Path, tmp_path: Path) -> None:
    # Run outside the source tree to exercise the installed package entry point.
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "splitlens",
            "audit",
            str(dataset),
            "--quiet",
            "--fail-on",
            "leakage",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
