"""Public, typed data structures shared by scanning and reporting."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

Split = Literal["train", "validation", "test", "unassigned"]
IssueKind = Literal["leakage", "duplicate", "similar", "blur", "dark", "bright", "small", "broken"]
Decision = Literal["keep", "exclude", "unreviewed"]
SPLITS = ("train", "validation", "test", "unassigned")
ISSUE_KINDS = ("leakage", "duplicate", "similar", "blur", "dark", "bright", "small", "broken")


@dataclass(frozen=True, slots=True)
class AuditSettings:
    """Review thresholds. Quality metrics use a 128 x 128 white-composited image."""

    similarity: int = 4
    blur: float = 60.0
    dark: float = 35.0
    bright: float = 225.0
    min_size: int = 256
    max_pairs: int = 2000

    def __post_init__(self) -> None:
        for name in ("similarity", "min_size", "max_pairs"):
            value = getattr(self, name)
            if type(value) is not int:
                raise ValueError(f"{name} must be an integer")
        if not 0 <= self.similarity <= 12:
            raise ValueError("similarity must be between 0 and 12")
        if self.min_size < 0 or self.max_pairs < 1:
            raise ValueError("min_size must be nonnegative and max_pairs must be positive")
        for name in ("blur", "dark", "bright"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(f"{name} must be a finite number")
        if self.blur < 0 or not 0 <= self.dark < self.bright <= 255:
            raise ValueError(
                "blur must be nonnegative; exposure must satisfy 0 <= dark < bright <= 255"
            )


@dataclass(frozen=True, slots=True)
class ScanLimits:
    """Resource bounds. Python callers can explicitly raise these for larger datasets."""

    max_images: int = 1500
    max_file_bytes: int = 30 * 1024 * 1024
    max_total_bytes: int = 300 * 1024 * 1024
    max_pixels: int = 40_000_000

    def __post_init__(self) -> None:
        for name in ("max_images", "max_file_bytes", "max_total_bytes", "max_pixels"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class ImageRecord:
    id: str
    path: str
    split: Split
    label: str
    width: int = 0
    height: int = 0
    bytes: int = 0
    sha256: str = ""
    dhash: str = ""
    brightness: float = 0.0
    sharpness: float = 0.0
    mean_rgb: tuple[float, float, float] | None = None
    thumbnail: str = ""
    error: str | None = None


@dataclass(frozen=True, slots=True)
class Finding:
    id: str
    kind: IssueKind
    image_ids: tuple[str, ...]
    title: str
    detail: str
    distance: int | None = None
