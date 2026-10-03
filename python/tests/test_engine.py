"""Numerical fixtures and matching behavior independent of browser/Pillow decoding."""

from dataclasses import replace

import numpy as np
import pytest

from splitlens import AuditSettings, ImageRecord, ScanLimits
from splitlens.engine import (
    difference_hash,
    grayscale,
    hamming,
    infer_metadata,
    quality_metrics,
    reanalyze,
)


def record(identifier="a", **changes):
    base = ImageRecord(
        identifier,
        f"train/cat/{identifier}.png",
        "train",
        "cat",
        width=640,
        height=480,
        bytes=123,
        sha256=identifier,
        dhash="a55aa55aa55aa55a",
        brightness=120,
        sharpness=100,
        mean_rgb=(120, 120, 120),
    )
    return replace(base, **changes)


@pytest.mark.parametrize(
    "path,expected",
    [
        ("dataset\\VALID\\dog\\x.png", ("validation", "dog")),
        ("training/cat/x.png", ("train", "cat")),
        ("test/x.png", ("test", "unlabeled")),
        ("my-training-images/x.png", ("unassigned", "unlabeled")),
    ],
)
def test_metadata_segments(path, expected):
    assert infer_metadata(path) == expected


def test_numerical_signals():
    assert hamming("ffffffffffffffff", "0000000000000000") == 64
    assert grayscale(np.array([[[255, 0, 0]]], dtype=np.uint8))[0, 0] == pytest.approx(76.245)
    assert quality_metrics(np.full((128, 128), 100.0)) == (100, 0)
    checkerboard = (np.indices((128, 128)).sum(axis=0) % 2) * 255.0
    assert quality_metrics(checkerboard)[1] > 100_000
    assert difference_hash(np.tile(np.arange(9.0), (8, 1))) == "0000000000000000"
    assert difference_hash(np.tile(np.arange(9.0)[::-1], (8, 1))) == "ffffffffffffffff"
    with pytest.raises(ValueError):
        difference_hash(np.zeros((8, 8)))
    with pytest.raises(ValueError):
        quality_metrics(np.zeros((2, 2)))


def test_exact_duplicate_group_and_unassigned_semantics():
    first = record(sha256="same")
    second = record("b", sha256="same", split="validation")
    findings = reanalyze([first, second], AuditSettings())
    assert [finding.kind for finding in findings] == ["leakage", "duplicate"]
    assert findings[0].image_ids == ("a", "b")
    assert [
        f.kind for f in reanalyze([first, replace(second, split="unassigned")], AuditSettings())
    ] == ["duplicate"]
    assert [
        f.kind for f in reanalyze([replace(first, error="broken"), second], AuditSettings())
    ] == ["broken"]


def test_near_candidates_and_false_positive_gates():
    first = record()
    second = record("b", dhash="a55aa55aa55aa55b", split="test")
    assert [f.kind for f in reanalyze([first, second], AuditSettings())] == ["leakage", "similar"]
    assert not reanalyze([first, second], AuditSettings(similarity=0))
    for change in (dict(width=900), dict(brightness=180), dict(mean_rgb=(190, 90, 100))):
        assert not reanalyze([first, replace(second, **change)], AuditSettings())
    assert not reanalyze(
        [record(dhash="0000000000000000"), record("b", dhash="0000000000000001")], AuditSettings()
    )
    # An additive exposure shift preserves brightness-normalized mean color.
    assert reanalyze(
        [first, replace(second, brightness=130, mean_rgb=(130, 130, 130))], AuditSettings()
    )


def test_index_matches_exhaustive_hamming_comparison():
    base = int("a55aa55aa55aa55a", 16)
    images = [
        record(str(i), dhash=f"{base ^ ((1 << i) | (1 << ((i + 7) % 64))):016x}") for i in range(30)
    ]
    expected = {
        frozenset((a.id, b.id))
        for i, a in enumerate(images)
        for b in images[i + 1 :]
        if hamming(a.dhash, b.dhash) <= 2
    }
    found = {
        frozenset(f.image_ids)
        for f in reanalyze(images, AuditSettings(similarity=2))
        if f.kind == "similar"
    }
    assert found == expected


def test_dense_results_preserve_explicit_overflow_summary():
    images = [record(str(i), split="test" if i % 2 else "train") for i in range(100)]
    findings = reanalyze(images, AuditSettings(max_pairs=20))
    assert len([f for f in findings if f.kind == "similar"]) == 21
    assert len([f for f in findings if f.kind == "leakage"]) == 21
    assert any(f.title == "4930 additional similar pairs" for f in findings)
    assert any(f.title == "2480 additional cross-split pairs" for f in findings)


@pytest.mark.parametrize(
    "changes",
    [
        {"similarity": 13},
        {"similarity": True},
        {"blur": -1},
        {"blur": float("nan")},
        {"dark": 240, "bright": 100},
        {"min_size": -1},
        {"max_pairs": 0},
    ],
)
def test_settings_reject_invalid_thresholds(changes):
    with pytest.raises(ValueError):
        AuditSettings(**changes)


def test_limits_validate_integer_positive_bounds():
    with pytest.raises(ValueError):
        ScanLimits(max_images=0)
    with pytest.raises(ValueError):
        ScanLimits(max_pixels=True)
