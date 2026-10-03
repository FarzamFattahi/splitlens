"""Pure matching and quality signals; independent of image decoding and file I/O."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from .models import AuditSettings, Finding, ImageRecord, IssueKind, Split

_SPLIT_ALIASES: dict[str, Split] = {
    "train": "train",
    "training": "train",
    "val": "validation",
    "valid": "validation",
    "validation": "validation",
    "test": "test",
    "testing": "test",
}
_PRIORITY = {
    "leakage": 0,
    "duplicate": 1,
    "similar": 2,
    "broken": 3,
    "blur": 4,
    "dark": 5,
    "bright": 6,
    "small": 7,
}


def infer_metadata(path: str) -> tuple[Split, str]:
    """Infer the first recognized split folder and its following label folder."""
    parts = [part for part in path.replace("\\", "/").split("/") if part]
    for index, part in enumerate(parts):
        if part.lower() in _SPLIT_ALIASES:
            label = parts[index + 1] if index < len(parts) - 2 else "unlabeled"
            return _SPLIT_ALIASES[part.lower()], label
    return "unassigned", "unlabeled"


def grayscale(rgb: NDArray[np.uint8]) -> NDArray[np.float64]:
    """Rec.601 luminance from an RGB array; transparency must be composited first."""
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("grayscale expects an H x W x 3 RGB array")
    return rgb.astype(np.float64) @ np.array([0.299, 0.587, 0.114])


def quality_metrics(pixels: NDArray[np.float64]) -> tuple[float, float]:
    """Return mean luminance and four-neighbor Laplacian variance."""
    if pixels.ndim != 2 or min(pixels.shape, default=0) < 3:
        raise ValueError("quality_metrics expects a 2D grayscale array at least 3 x 3")
    laplacian = (
        pixels[:-2, 1:-1]
        + pixels[2:, 1:-1]
        + pixels[1:-1, :-2]
        + pixels[1:-1, 2:]
        - 4 * pixels[1:-1, 1:-1]
    )
    return float(pixels.mean()), float(laplacian.var())


def difference_hash(pixels: NDArray[np.float64]) -> str:
    """A 64-bit horizontal difference hash from an 8-row, 9-column preview."""
    if pixels.shape != (8, 9):
        raise ValueError("difference_hash expects an 8 x 9 grayscale array")
    value = 0
    for bit in (pixels[:, :-1] > pixels[:, 1:]).flat:
        value = (value << 1) | int(bit)
    return f"{value:016x}"


def hamming(first: str, second: str) -> int:
    return (int(first, 16) ^ int(second, 16)).bit_count()


@dataclass(slots=True)
class _Node:
    value: int
    records: list[ImageRecord]
    children: dict[int, _Node] = field(default_factory=dict)


class _HashIndex:
    def __init__(self) -> None:
        self.root: _Node | None = None

    def add(self, record: ImageRecord) -> None:
        value = int(record.dhash, 16)
        if self.root is None:
            self.root = _Node(value, [record])
            return
        node = self.root
        while True:
            distance = (value ^ node.value).bit_count()
            if distance == 0:
                node.records.append(record)
                return
            if distance not in node.children:
                node.children[distance] = _Node(value, [record])
                return
            node = node.children[distance]

    def search(self, value: int, radius: int) -> Iterable[tuple[ImageRecord, int]]:
        stack = [self.root] if self.root is not None else []
        while stack:
            node = stack.pop()
            distance = (value ^ node.value).bit_count()
            if distance <= radius:
                for record in node.records:
                    yield record, distance
            for edge, child in node.children.items():
                if distance - radius <= edge <= distance + radius:
                    stack.append(child)


def reanalyze(images: Iterable[ImageRecord], settings: AuditSettings) -> tuple[Finding, ...]:
    """Retune findings from cached measurements without reading original image files."""
    records = tuple(images)
    findings: list[Finding] = []
    exact: dict[str, list[ImageRecord]] = defaultdict(list)

    def add(
        kind: IssueKind,
        group: Iterable[ImageRecord],
        title: str,
        detail: str,
        distance: int | None = None,
    ) -> None:
        ids = tuple(image.id for image in group)
        findings.append(Finding(f"{kind}:{':'.join(ids)}", kind, ids, title, detail, distance))

    def crosses_split(group: Iterable[ImageRecord]) -> bool:
        return len({image.split for image in group if image.split != "unassigned"}) > 1

    for image in records:
        if image.error:
            add("broken", [image], "Image could not be decoded", image.error)
            continue
        if image.sha256:
            exact[image.sha256].append(image)
        if image.sharpness < settings.blur:
            add(
                "blur",
                [image],
                "Low edge detail",
                f"Laplacian variance {image.sharpness:.1f} on a 128 x 128 grayscale preview. Smooth subjects can also trigger this check.",
            )
        if image.brightness < settings.dark:
            add(
                "dark",
                [image],
                "Dark exposure",
                f"Mean grayscale brightness {image.brightness:.1f} / 255.",
            )
        if image.brightness > settings.bright:
            add(
                "bright",
                [image],
                "Bright exposure",
                f"Mean grayscale brightness {image.brightness:.1f} / 255.",
            )
        if min(image.width, image.height) < settings.min_size:
            add(
                "small",
                [image],
                "Small image",
                f"{image.width} x {image.height} px; shortest side is below {settings.min_size} px.",
            )
    for group in exact.values():
        if len(group) < 2:
            continue
        add(
            "duplicate",
            group,
            "Identical file copies",
            f"{len(group)} files share the same SHA-256 digest.",
        )
        if crosses_split(group):
            add(
                "leakage",
                group,
                "Exact copies across splits",
                "Identical file bytes occur in multiple assigned splits. Review these copies before evaluating your model.",
            )

    index = _HashIndex()
    similar_pairs = leakage_pairs = 0
    omitted_similar: dict[str, ImageRecord] = {}
    omitted_leakage: dict[str, ImageRecord] = {}
    for image in records:
        if image.error or len(image.dhash) != 16 or image.height <= 0 or image.width <= 0:
            continue
        try:
            value = int(image.dhash, 16)
        except ValueError:
            continue
        if not 5 <= value.bit_count() <= 59:
            continue
        for other, distance in index.search(value, settings.similarity):
            if image.sha256 and image.sha256 == other.sha256:
                continue
            if abs(math.log((image.width / image.height) / (other.width / other.height))) > 0.04:
                continue
            if abs(image.brightness - other.brightness) > 25:
                continue
            if image.mean_rgb is not None and other.mean_rgb is not None:
                color_distance = max(
                    abs((a - image.brightness) - (b - other.brightness))
                    for a, b in zip(image.mean_rgb, other.mean_rgb, strict=True)
                )
                if color_distance > 12:
                    continue
            pair = (other, image)
            similar_pairs += 1
            if similar_pairs <= settings.max_pairs:
                add(
                    "similar",
                    pair,
                    "Visually similar pair",
                    f"64-bit dHash distance {distance} / 64 with compatible aspect ratio, exposure, and available mean-color measurements. A candidate, not proof of identity.",
                    distance,
                )
            else:
                omitted_similar.update((item.id, item) for item in pair)
            if crosses_split(pair):
                leakage_pairs += 1
                if leakage_pairs <= settings.max_pairs:
                    add(
                        "leakage",
                        pair,
                        "Similar images across splits",
                        f"Near-duplicate candidate spans assigned splits (dHash distance {distance} / 64). Confirm visually before moving or excluding files.",
                        distance,
                    )
                else:
                    omitted_leakage.update((item.id, item) for item in pair)
        index.add(image)
    if omitted_similar:
        add(
            "similar",
            omitted_similar.values(),
            f"{similar_pairs - settings.max_pairs} additional similar pairs",
            "Detailed pair limit reached. These images participate in additional candidates; they are not necessarily all mutually similar. Audit smaller batches or lower the similarity threshold.",
        )
    if omitted_leakage:
        add(
            "leakage",
            omitted_leakage.values(),
            f"{leakage_pairs - settings.max_pairs} additional cross-split pairs",
            "Detailed leakage pair limit reached. These images participate in additional cross-split candidates; full pair details are summarized. Audit smaller batches or lower the similarity threshold.",
        )
    return tuple(sorted(findings, key=lambda finding: _PRIORITY[finding.kind]))
