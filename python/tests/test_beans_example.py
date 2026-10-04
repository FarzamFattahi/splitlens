"""Offline safety and integrity checks for the real-dataset reproduction example."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "beans_example", Path(__file__).parents[1] / "examples/beans_case_study.py"
)
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)


def archive(tmp_path, entries):
    path = tmp_path / "source.zip"
    with zipfile.ZipFile(path, "w") as output:
        for name, data in entries.items():
            output.writestr(name, data)
    return [({"split": "train"}, path)]


def item(data=b"archive"):
    return {
        "split": "train",
        "url": "https://example.com/train.zip",
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def test_download_preserves_existing_partial_file(tmp_path, monkeypatch):
    partial = tmp_path / "train.zip.part"
    partial.write_bytes(b"previous download")
    monkeypatch.setattr(
        example, "urlopen", lambda *_args, **_kwargs: pytest.fail("No request expected")
    )
    with pytest.raises(FileExistsError):
        example.fetch_archive(item(), tmp_path)
    assert partial.read_bytes() == b"previous download"


def test_failed_download_cleans_only_its_own_partial(tmp_path, monkeypatch):
    def fail(*_args, **_kwargs):
        raise OSError("offline")

    monkeypatch.setattr(example, "urlopen", fail)
    with pytest.raises(OSError, match="offline"):
        example.fetch_archive(item(), tmp_path)
    assert not list(tmp_path.iterdir())


def test_download_rejects_wrong_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(example, "urlopen", lambda *_args, **_kwargs: io.BytesIO(b"changed"))
    with pytest.raises(ValueError, match="SHA-256"):
        example.fetch_archive(item(), tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("name", ["../escape.jpg", "train/cat/../../escape.jpg", "test/cat/a.jpg"])
def test_unsafe_or_wrong_split_entry_fails_before_extraction(tmp_path, name):
    sources = archive(tmp_path, {name: b"image"})
    destination = tmp_path / "dataset"
    with pytest.raises(ValueError, match="Unexpected"):
        example.extract_archives(sources, destination)
    assert not destination.exists()
    assert not (tmp_path / "escape.jpg").exists()


def test_original_bytes_and_ignored_metadata_are_preserved(tmp_path):
    data = b"source image bytes"
    name = "train/cat/a.jpg"
    metadata = "train/healthy/healthy_train.120tore"
    sources = archive(tmp_path, {name: data, metadata: b"metadata"})
    destination = tmp_path / "dataset"
    example.extract_archives(sources, destination)
    assert (destination / name).read_bytes() == data
    report = SimpleNamespace(
        root=destination,
        images=[SimpleNamespace(path=name, sha256=hashlib.sha256(data).hexdigest())],
    )
    ignored = example.verify_originals(report, sources)
    assert ignored[0]["path"] == metadata
    (destination / name).write_bytes(b"changed")
    with pytest.raises(ValueError, match="differs"):
        example.verify_originals(report, sources)


def test_existing_dataset_is_never_overwritten(tmp_path):
    sources = archive(tmp_path, {"train/cat/a.jpg": b"image"})
    destination = tmp_path / "dataset"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("user data")
    with pytest.raises(FileExistsError):
        example.extract_archives(sources, destination)
    assert marker.read_text() == "user data"
