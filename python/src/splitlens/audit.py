"""Local, sequential image scanning with bounded per-image decoding."""

from __future__ import annotations

import base64
import hashlib
import io
import os
import stat
import time
import warnings
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from .engine import difference_hash, grayscale, infer_metadata, quality_metrics, reanalyze
from .models import SPLITS, AuditSettings, ImageRecord, ScanLimits, Split

if TYPE_CHECKING:
    from .report import AuditReport

_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".avif"}
_FORMATS = {"JPEG", "PNG", "WEBP", "BMP", "AVIF"}


def _is_link(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _discover(root: Path, limits: ScanLimits) -> tuple[list[Path], list[str]]:
    candidates: list[Path] = []
    notices: list[str] = []
    total_bytes = 0

    def walk_error(error: OSError) -> None:
        raise error

    for directory, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
        kept_dirs = []
        for name in sorted(dirs):
            path = Path(directory) / name
            if _is_link(path):
                notices.append(f"Skipped linked directory: {path.relative_to(root).as_posix()}")
            else:
                kept_dirs.append(name)
        dirs[:] = kept_dirs
        for name in sorted(names):
            path = Path(directory) / name
            if path.suffix.lower() not in _EXTENSIONS:
                continue
            relative = path.relative_to(root).as_posix()
            if _is_link(path) or not path.is_file():
                notices.append(f"Skipped linked or non-regular image: {relative}")
                continue
            size = path.stat().st_size
            if size > limits.max_file_bytes:
                raise ValueError(f"{relative} exceeds max_file_bytes={limits.max_file_bytes}")
            total_bytes += size
            if total_bytes > limits.max_total_bytes or len(candidates) >= limits.max_images:
                raise ValueError("Dataset exceeds configured image-count or total-byte limit")
            candidates.append(path)
    return sorted(candidates, key=lambda path: path.relative_to(root).as_posix()), notices


def _read_bytes(path: Path, root: Path, limits: ScanLimits) -> bytes:
    for parent in (path, *path.parents):
        if parent == root:
            break
        if _is_link(parent):
            raise ValueError("Linked image paths are excluded")
    if not path.resolve().is_relative_to(root):
        raise ValueError("Image path escaped the dataset root")
    with path.open("rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limits.max_file_bytes:
            raise ValueError("File changed or exceeds the configured image-size limit")
        data = stream.read(limits.max_file_bytes + 1)
    if len(data) > limits.max_file_bytes:
        raise ValueError("File expanded beyond the configured image-size limit")
    return data


def _analyze(
    path: Path,
    root: Path,
    identifier: str,
    split: Split | None,
    limits: ScanLimits,
    thumbnails: bool,
) -> ImageRecord:
    relative = path.relative_to(root).as_posix()
    inferred_split, label = infer_metadata(relative)
    record = ImageRecord(identifier, relative, split or inferred_split, label)
    try:
        data = _read_bytes(path, root, limits)
        record = replace(record, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as original:
                if original.format not in _FORMATS:
                    raise ValueError(
                        "Unsupported image encoding; use a still JPEG, PNG, WebP, BMP, or AVIF"
                    )
                if getattr(original, "n_frames", 1) != 1:
                    raise ValueError("Animated images and image sequences are excluded")
                width, height = original.size
                if width * height > limits.max_pixels:
                    raise ValueError(f"Image exceeds max_pixels={limits.max_pixels}")
                oriented = ImageOps.exif_transpose(original)
                try:
                    rgba = oriented.convert("RGBA")
                    try:
                        white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                        try:
                            white.alpha_composite(rgba)
                            rgb = white.convert("RGB")
                        finally:
                            white.close()
                    finally:
                        rgba.close()
                    try:
                        preview = rgb.resize((128, 128), Image.Resampling.BILINEAR)
                        try:
                            pixels = np.asarray(preview, dtype=np.uint8)
                            brightness, sharpness = quality_metrics(grayscale(pixels))
                            mean = tuple(float(channel) for channel in pixels.mean(axis=(0, 1)))
                        finally:
                            preview.close()
                        hashed = rgb.resize((9, 8), Image.Resampling.BILINEAR)
                        try:
                            dhash = difference_hash(grayscale(np.asarray(hashed, dtype=np.uint8)))
                        finally:
                            hashed.close()
                        thumbnail = ""
                        if thumbnails:
                            small = rgb.copy()
                            try:
                                small.thumbnail((280, 280), Image.Resampling.BILINEAR)
                                buffer = io.BytesIO()
                                small.save(buffer, format="JPEG", quality=78)
                                thumbnail = "data:image/jpeg;base64," + base64.b64encode(
                                    buffer.getvalue()
                                ).decode("ascii")
                            finally:
                                small.close()
                        record = replace(
                            record,
                            width=rgb.width,
                            height=rgb.height,
                            dhash=dhash,
                            brightness=brightness,
                            sharpness=sharpness,
                            mean_rgb=mean,
                            thumbnail=thumbnail,
                        )
                    finally:
                        rgb.close()
                finally:
                    oriented.close()
    except (
        OSError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        record = replace(record, error=str(error) or type(error).__name__)
    return record


def audit(
    root: str | os.PathLike[str],
    *,
    settings: AuditSettings | None = None,
    limits: ScanLimits | None = None,
    splits: Mapping[str, Split] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    thumbnails: bool = False,
) -> AuditReport:
    """Audit a folder without modifying originals or sending image data anywhere.

    ``splits`` overrides inferred split assignments by relative POSIX file path.
    Optional thumbnails are generated during scanning, avoiding later source reads.
    """
    from .report import AuditReport

    start = time.perf_counter()
    settings = settings if settings is not None else AuditSettings()
    limits = limits if limits is not None else ScanLimits()
    if not isinstance(settings, AuditSettings) or not isinstance(limits, ScanLimits):
        raise TypeError("settings and limits must be AuditSettings and ScanLimits instances")
    if type(thumbnails) is not bool or (on_progress is not None and not callable(on_progress)):
        raise TypeError("thumbnails must be bool and on_progress must be callable")
    source = Path(root).expanduser()
    if not source.is_dir():
        raise ValueError(f"Dataset must be an existing directory: {source}")
    if _is_link(source):
        raise ValueError("Dataset root must not be a symbolic link or junction")
    source = source.resolve()
    files, notices = _discover(source, limits)
    if not files:
        raise ValueError("No supported images found in the dataset directory")
    overrides = dict(splits or {})
    paths = {path.relative_to(source).as_posix() for path in files}
    if overrides.keys() - paths:
        raise ValueError(
            f"Split overrides contain unknown paths: {sorted(overrides.keys() - paths)}"
        )
    if any(split not in SPLITS for split in overrides.values()):
        raise ValueError("Split overrides must use train, validation, test, or unassigned")
    records: list[ImageRecord] = []
    for number, path in enumerate(files, 1):
        relative = path.relative_to(source).as_posix()
        records.append(
            _analyze(path, source, f"image-{number}", overrides.get(relative), limits, thumbnails)
        )
        if on_progress is not None:
            on_progress(number, len(files))
    return AuditReport(
        root=source,
        images=tuple(records),
        findings=reanalyze(records, settings),
        settings=settings,
        elapsed_seconds=time.perf_counter() - start,
        warnings=tuple(notices),
    )
