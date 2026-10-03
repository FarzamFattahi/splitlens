"""Immutable review reports and conservative, verified dataset exports.

Reports contain metadata, never source image bytes. Exporting creates a new tree
and fails if any retained source has changed since the audit.
"""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import math
import os
import re
import shutil
import stat
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from .models import ISSUE_KINDS, SPLITS, AuditSettings, Decision, Finding, ImageRecord

_DECISIONS = ("keep", "exclude", "unreviewed")
_RESERVED = re.compile(r"^(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)", re.I)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DHASH = re.compile(r"^[0-9a-f]{16}$")
_THUMBNAIL = re.compile(r"^data:image/(?:jpeg|png|webp);base64,[A-Za-z0-9+/]+={0,2}$")
_METHODOLOGY = (
    "SHA-256 byte equality; 64-bit difference hash from a 9 × 8 grayscale image; "
    "mean grayscale intensity and variance of a four-neighbor Laplacian on a "
    "128 × 128 image. Alpha is composited on white. Near pairs require compatible "
    "aspect ratio and exposure; low-information hashes are skipped. Findings "
    "are review suggestions, not automatic exclusions."
)


def _relative_path(value: object) -> str:
    """Accept portable literal paths, with no normalization that hides traversal."""
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("Image paths must be nonempty relative POSIX paths")
    if value.startswith("/"):
        raise ValueError(f"Absolute image path is not allowed: {value!r}")
    for part in value.split("/"):
        if part in ("", ".", "..") or part.endswith((" ", ".")):
            raise ValueError(f"Unsafe image path: {value!r}")
        if any(ord(char) < 32 or ord(char) == 127 or char in '<>:"|?*' for char in part):
            raise ValueError(f"Unsafe image path: {value!r}")
        if _RESERVED.match(part):
            raise ValueError(f"Reserved filename in image path: {value!r}")
    if value.split("/", 1)[0].casefold() == "_splitlens":
        raise ValueError("The _splitlens directory is reserved for export metadata")
    return value


def _no_links(path: Path) -> None:
    """Reject links and Windows junctions in every existing path component."""
    absolute = Path(os.path.abspath(path))
    for item in (absolute, *absolute.parents):
        junction = getattr(item, "is_junction", None)
        if item.is_symlink() or (junction is not None and junction()):
            raise ValueError(f"Symlinks and junctions are not allowed: {item}")
        try:
            attributes = getattr(item.lstat(), "st_file_attributes", 0)
        except FileNotFoundError:
            continue
        if attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise ValueError(f"Symlinks and junctions are not allowed: {item}")


def _number(value: object, name: str, *, minimum: float = 0, maximum: float | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"{name} is outside its allowed range")


def _integer(value: object, name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")


def _string(value: object, name: str, *, nonempty: bool = False) -> None:
    if not isinstance(value, str) or (nonempty and not value):
        raise ValueError(f"{name} must be {'a nonempty' if nonempty else 'a'} string")


def _validate_image(record: ImageRecord) -> None:
    if not isinstance(record, ImageRecord):
        raise ValueError("images must contain ImageRecord values")
    _string(record.id, "Image id", nonempty=True)
    _relative_path(record.path)
    if record.split not in SPLITS:
        raise ValueError(f"Unknown split: {record.split!r}")
    _string(record.label, "Image label")
    _string(record.thumbnail, "Image thumbnail")
    for name in ("width", "height", "bytes"):
        _integer(getattr(record, name), name)
    if not isinstance(record.sha256, str) or (
        record.sha256 and not _SHA256.fullmatch(record.sha256)
    ):
        raise ValueError("sha256 must be empty or a lowercase 64-character hexadecimal digest")
    if not isinstance(record.dhash, str) or (record.dhash and not _DHASH.fullmatch(record.dhash)):
        raise ValueError("dhash must be empty or a lowercase 16-character hexadecimal digest")
    _number(record.brightness, "brightness", maximum=255)
    _number(record.sharpness, "sharpness")
    if record.mean_rgb is not None:
        if not isinstance(record.mean_rgb, tuple) or len(record.mean_rgb) != 3:
            raise ValueError("mean_rgb must contain three channels")
        for channel in record.mean_rgb:
            _number(channel, "mean_rgb channel", maximum=255)
    if record.error is not None:
        _string(record.error, "Image error")


@dataclass(frozen=True)
class AuditReport:
    """An immutable audit snapshot with explicit, path-based review decisions.

    Use :meth:`exclude` and :meth:`keep` to return updated reports. A finding
    never excludes anything automatically. Retained originals are verified and
    copied without re-encoding by :meth:`export_dataset`.
    """

    root: Path
    images: tuple[ImageRecord, ...]
    findings: tuple[Finding, ...]
    settings: AuditSettings
    elapsed_seconds: float = 0.0
    decisions: Mapping[str, Decision] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root).absolute())
        object.__setattr__(self, "images", tuple(self.images))
        object.__setattr__(self, "findings", tuple(self.findings))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        if not isinstance(self.settings, AuditSettings):
            raise ValueError("settings must be AuditSettings")
        _number(self.elapsed_seconds, "elapsed_seconds")
        ids: set[str] = set()
        paths: set[str] = set()
        for record in self.images:
            _validate_image(record)
            path_key = record.path.casefold()
            if record.id in ids or path_key in paths:
                raise ValueError("Image ids and case-insensitive paths must be unique")
            ids.add(record.id)
            paths.add(path_key)
        # A file and a parent directory cannot occupy the same export path.
        for record in self.images:
            if any(
                str(parent).casefold() in paths
                for parent in PurePosixPath(record.path).parents
                if str(parent) != "."
            ):
                raise ValueError("An image path collides with another image's parent directory")
        finding_ids: set[str] = set()
        for finding in self.findings:
            if not isinstance(finding, Finding):
                raise ValueError("findings must contain Finding values")
            _string(finding.id, "Finding id", nonempty=True)
            if finding.id in finding_ids:
                raise ValueError("Finding ids must be unique")
            finding_ids.add(finding.id)
            if finding.kind not in ISSUE_KINDS:
                raise ValueError(f"Unknown finding kind: {finding.kind!r}")
            if not isinstance(finding.image_ids, tuple) or not finding.image_ids:
                raise ValueError("Finding image_ids must be a nonempty tuple")
            if any(
                not isinstance(image_id, str) or image_id not in ids
                for image_id in finding.image_ids
            ):
                raise ValueError("Finding refers to an unknown image id")
            if len(set(finding.image_ids)) != len(finding.image_ids):
                raise ValueError("Finding image_ids must be unique")
            _string(finding.title, "Finding title")
            _string(finding.detail, "Finding detail")
            if finding.distance is not None:
                _integer(finding.distance, "Finding distance")
                if finding.distance > 64:
                    raise ValueError("Finding distance cannot exceed 64")
        real_paths = {record.path for record in self.images}
        checked: dict[str, Decision] = {}
        for path, decision in self.decisions.items():
            if not isinstance(path, str) or path not in real_paths:
                raise ValueError(f"Decision refers to an unknown image path: {path!r}")
            if decision not in _DECISIONS:
                raise ValueError(f"Unknown decision: {decision!r}")
            if decision != "unreviewed":
                checked[path] = decision
        object.__setattr__(self, "decisions", MappingProxyType(checked))
        for warning in self.warnings:
            _string(warning, "Warning")

    @property
    def summary(self) -> dict:
        """Counts of images, findings, each issue kind, and review decisions."""
        return {
            "images": len(self.images),
            "findings": len(self.findings),
            "by_kind": {kind: sum(f.kind == kind for f in self.findings) for kind in ISSUE_KINDS},
            "excluded": sum(decision == "exclude" for decision in self.decisions.values()),
            "reviewed": len(self.decisions),
        }

    def findings_of(self, kind: str) -> tuple[Finding, ...]:
        """Return findings of a supported issue kind."""
        if kind not in ISSUE_KINDS:
            raise ValueError(f"Unknown finding kind: {kind!r}")
        return tuple(finding for finding in self.findings if finding.kind == kind)

    def with_decisions(self, decisions: Mapping[str, Decision]) -> AuditReport:
        """Merge path-based decisions; ``unreviewed`` resets a decision."""
        return replace(self, decisions={**self.decisions, **decisions})

    def exclude(self, paths: Iterable[str]) -> AuditReport:
        """Explicitly exclude paths from future exports without changing files."""
        return self.with_decisions({path: "exclude" for path in _paths(paths)})

    def keep(self, paths: Iterable[str]) -> AuditReport:
        """Mark paths as reviewed and retained."""
        return self.with_decisions({path: "keep" for path in _paths(paths)})

    def reanalyze(self, settings: AuditSettings) -> AuditReport:
        """Reapply thresholds to saved metrics while preserving all decisions."""
        from .engine import reanalyze

        return replace(self, settings=settings, findings=tuple(reanalyze(self.images, settings)))

    def to_dict(self) -> dict:
        """Build browser-compatible version-1 metadata; omit thumbnails."""
        records = []
        for image in self.images:
            record = asdict(image)
            record.pop("thumbnail")
            mean_rgb = record.pop("mean_rgb")
            if mean_rgb is not None:
                record["meanRgb"] = list(mean_rgb)
            if record["error"] is None:
                record.pop("error")
            record["decision"] = self.decisions.get(image.path, "unreviewed")
            records.append(record)
        findings = []
        for finding in self.findings:
            record = asdict(finding)
            record["imageIds"] = list(record.pop("image_ids"))
            if record["distance"] is None:
                record.pop("distance")
            findings.append(record)
        settings = asdict(self.settings)
        settings["minSize"] = settings.pop("min_size")
        settings["maxPairs"] = settings.pop("max_pairs")
        return {
            "schemaVersion": 1,
            "tool": "SplitLens",
            "dataset": self.root.name,
            "sourceRoot": str(self.root),
            "exportedAt": datetime.now(UTC).isoformat(),
            "methodology": _METHODOLOGY,
            "settings": settings,
            "elapsedMs": self.elapsed_seconds * 1000,
            "images": records,
            "findings": findings,
            "warnings": list(self.warnings),
        }

    def _json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, allow_nan=False) + "\n"

    def _csv(self, *, archive: bool = False) -> str:
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
        writer.writerow(
            (
                "id",
                "path",
                "archive_path",
                "split",
                "label",
                "decision",
                "width",
                "height",
                "bytes",
                "sha256",
                "dhash",
                "brightness",
                "sharpness",
                "issues",
                "decode_error",
            )
        )
        issues: dict[str, set[str]] = {}
        for finding in self.findings:
            for image_id in finding.image_ids:
                issues.setdefault(image_id, set()).add(finding.kind)
        for image in self.images:
            decision = self.decisions.get(image.path, "unreviewed")
            row = (
                image.id,
                image.path,
                image.path if archive and decision != "exclude" else "",
                image.split,
                image.label,
                decision,
                image.width,
                image.height,
                image.bytes,
                image.sha256,
                image.dhash,
                image.brightness,
                image.sharpness,
                ";".join(sorted(issues.get(image.id, ()))),
                image.error or "",
            )
            writer.writerow(_csv_safe(value) for value in row)
        return "\ufeff" + buffer.getvalue()

    def save_json(self, path: str | Path) -> Path:
        """Atomically save versioned metadata with no image bytes."""
        return self._save(path, self._json())

    def save_csv(self, path: str | Path) -> Path:
        """Atomically save a formula-neutralized review manifest."""
        return self._save(path, self._csv())

    def save_html(self, path: str | Path) -> Path:
        """Save an offline HTML report, with cached thumbnails when available.

        Only validated PNG/JPEG/WebP data URIs are embedded. Loaded JSON reports
        contain no thumbnails and display an explicit unavailable message.
        """

        def escape(value: object) -> str:
            return html.escape(str(value), quote=True)

        image_map = {image.id: image for image in self.images}

        def preview(image: ImageRecord) -> str:
            if _THUMBNAIL.fullmatch(image.thumbnail):
                return f'<img src="{image.thumbnail}" alt="{escape(image.path)}" loading="lazy">'
            return "<small>Preview unavailable</small>"

        cards = []
        for finding in self.findings:
            names = "".join(
                f"<li>{preview(image_map[image_id])}{escape(image_map[image_id].path)}</li>"
                for image_id in finding.image_ids
            )
            cards.append(
                f"<article><span class='kind'>{escape(finding.kind)}</span><h2>{escape(finding.title)}</h2><p>{escape(finding.detail)}</p><ul>{names}</ul></article>"
            )
        rows = []
        for image in self.images:
            decision = self.decisions.get(image.path, "unreviewed")
            rows.append(
                f"<tr><td>{preview(image)}{escape(image.path)}</td><td>{escape(image.split)}</td><td>{image.width} × {image.height}</td><td>{escape(decision)}</td><td>{escape(image.error or '')}</td></tr>"
            )
        warnings = "".join(f"<li>{escape(warning)}</li>" for warning in self.warnings)
        content = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'"><title>{escape(self.root.name)} · SplitLens audit</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f5f6f8;color:#202b3e;font:16px/1.6 system-ui,sans-serif}}main{{max-width:1120px;margin:auto;padding:48px 24px}}h1{{font-size:clamp(28px,5vw,48px);line-height:1.2;letter-spacing:-1px}}.eyebrow,.kind{{font:12px monospace;text-transform:uppercase;letter-spacing:1px;color:#235fc5}}article,section{{padding:24px;margin:20px 0;background:white;border:1px solid #dde3ed;border-radius:12px}}h2{{margin:8px 0;font-size:21px}}.stats{{font-size:20px}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{text-align:left;padding:12px 8px;border-bottom:1px solid #e1e6ef;vertical-align:top;overflow-wrap:anywhere}}small{{display:block;color:#647085}}.scroll{{overflow-x:auto}}footer{{color:#647085;font-size:13px}}@media print{{main{{padding:0}}article{{break-inside:avoid}}}}
</style></head><body><main><p class="eyebrow">SplitLens / Dataset quality audit</p><h1>{escape(self.root.name)}</h1><p class="stats">{len(self.images)} images · {len(self.findings)} findings · {self.summary["excluded"]} explicitly excluded</p><section><h2>How to use this report</h2><p>{escape(_METHODOLOGY)}</p><p>Quality heuristics need human review. A low sharpness score may reflect a low-detail subject, and visual similarity does not prove label correctness or shared provenance. Export retains every original except paths you explicitly exclude. Sources are verified against the audited SHA-256 digest.</p><p>Thresholds: similarity ≤ {self.settings.similarity}; blur &lt; {self.settings.blur}; dark &lt; {self.settings.dark}; bright &gt; {self.settings.bright}; shortest side &lt; {self.settings.min_size} pixels.</p><p>This offline report embeds cached previews only when thumbnails were explicitly enabled during the audit. JSON reports contain metadata only and have no previews. No files are uploaded.</p></section>{"<section><h2>Warnings</h2><ul>" + warnings + "</ul></section>" if warnings else ""}{"".join(cards)}<section><h2>Images and decisions</h2><div class="scroll"><table><thead><tr><th scope="col">Path</th><th scope="col">Split</th><th scope="col">Dimensions</th><th scope="col">Decision</th><th scope="col">Decode error</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></section><footer>SplitLens · Python audit · Offline metadata report</footer></main></body></html>"""
        return self._save(path, content)

    def _save(self, path: str | Path, content: str) -> Path:
        target = Path(path).absolute()
        _no_links(target)
        resolved = target.resolve()
        if any(resolved == (self.root / image.path).resolve() for image in self.images):
            raise ValueError("Cannot overwrite an audited image with a report")
        if not target.parent.is_dir():
            raise ValueError("The report's parent directory must already exist")
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            _no_links(target)
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return target

    @classmethod
    def load_json(cls, path: str | Path, *, root: str | Path | None = None) -> AuditReport:
        """Load strict metadata, optionally rebasing the audited source folder."""
        return load_json(path, root=root)

    def export_dataset(self, destination: str | Path) -> Path:
        """Copy retained source bytes into a new, verified dataset directory.

        The destination must be absent and outside the source tree. All copies
        are staged in a sibling folder; a failure removes the stage and leaves
        sources and the destination unchanged. Excluded files are never copied.
        """
        target = Path(destination).absolute()
        _no_links(self.root)
        _no_links(target)
        source_root = self.root.resolve()
        target_root = target.resolve()
        if target_root.is_relative_to(source_root) or source_root.is_relative_to(target_root):
            raise ValueError(
                "Export destination must be outside and cannot contain the source root"
            )
        if target.exists():
            raise FileExistsError(f"Export destination already exists: {target}")
        if not target.parent.is_dir():
            raise ValueError("Export destination's parent directory must already exist")
        if not source_root.is_dir():
            raise ValueError("Source root is not a directory")
        staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.splitlens-", dir=target.parent))
        try:
            for image in self.images:
                if self.decisions.get(image.path) == "exclude":
                    continue
                _relative_path(image.path)
                source = self.root / image.path
                _no_links(source)
                if not source.resolve().is_relative_to(source_root):
                    raise ValueError(f"Source escapes audit root: {image.path}")
                if not image.sha256:
                    raise ValueError(
                        f"Cannot export an image without an audited SHA-256 digest: {image.path}"
                    )
                output = staging / image.path
                output.parent.mkdir(parents=True, exist_ok=True)
                _copy_verified(source, output, image)
            metadata = staging / "_splitlens"
            metadata.mkdir()
            (metadata / "manifest.csv").write_text(
                self._csv(archive=True), encoding="utf-8", newline=""
            )
            (metadata / "audit.json").write_text(self._json(), encoding="utf-8")
            _no_links(target)
            # os.rename never replaces a directory on Windows. On POSIX,
            # renameat2(RENAME_NOREPLACE) provides the same atomic guarantee.
            _rename_exclusive(staging, target)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return target


def _paths(paths: Iterable[str]) -> Iterable[str]:
    if isinstance(paths, str):
        return (paths,)
    return paths


def _csv_safe(value: object) -> str:
    text = str(value)
    if re.match(r"^[\s\ufeff]*[=+@-]", text) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def _copy_verified(source: Path, output: Path, record: ImageRecord) -> None:
    digest = hashlib.sha256()
    count = 0
    if not source.is_file():
        raise ValueError(f"Source is not a regular file: {record.path}")
    with source.open("rb") as input_stream, output.open("xb") as output_stream:
        before = os.fstat(input_stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"Source is not a regular file: {record.path}")
        if before.st_size != record.bytes:
            raise ValueError(f"Source changed after audit (size): {record.path}")
        while chunk := input_stream.read(1024 * 1024):
            count += len(chunk)
            if count > record.bytes:
                raise ValueError(f"Source changed after audit (size): {record.path}")
            digest.update(chunk)
            output_stream.write(chunk)
        after = os.fstat(input_stream.fileno())
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise ValueError(f"Source changed during export: {record.path}")
    if count != record.bytes or digest.hexdigest() != record.sha256:
        raise ValueError(f"Source changed after audit (SHA-256): {record.path}")
    _no_links(source)
    current = source.stat()
    # On Windows, path.stat() and fstat() may expose different creation/change
    # times for the very same file. Compare ctime only on the same open handle.
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        current.st_dev,
        current.st_ino,
        current.st_size,
        current.st_mtime_ns,
    ):
        raise ValueError(f"Source changed during export: {record.path}")


def _rename_exclusive(source: Path, destination: Path) -> None:
    if os.name == "nt":
        os.rename(source, destination)
        return
    if os.name == "posix":
        import ctypes
        import errno
        import sys

        libc = ctypes.CDLL(None, use_errno=True)
        if sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
            result = libc.renameat2(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
        elif sys.platform == "darwin" and hasattr(libc, "renamex_np"):
            result = libc.renamex_np(os.fsencode(source), os.fsencode(destination), 4)
        else:
            raise OSError("This platform does not provide an exclusive atomic directory rename")
        if result:
            error = ctypes.get_errno()
            if error == errno.EEXIST:
                raise FileExistsError(f"Export destination already exists: {destination}")
            raise OSError(error, os.strerror(error), str(destination))
        return
    raise OSError("This platform does not provide an exclusive atomic directory rename")


def _object(
    value: object, name: str, *, required: set[str], optional: set[str] = frozenset()
) -> dict:
    if (
        not isinstance(value, dict)
        or not required <= value.keys()
        or value.keys() - required - optional
    ):
        raise ValueError(f"Invalid {name} fields")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def load_json(path: str | Path, *, root: str | Path | None = None) -> AuditReport:
    """Load a version-1 Python or browser metadata report with strict validation.

    Browser reports need an explicit ``root`` for filesystem exports. A loaded
    report is metadata only; exporting verifies its source file digests.
    """

    def reject_constant(value: str) -> None:
        raise ValueError(f"Non-finite JSON number: {value}")

    with Path(path).open("r", encoding="utf-8-sig") as stream:
        data = json.load(stream, object_pairs_hook=_unique_object, parse_constant=reject_constant)
    data = _object(
        data,
        "report",
        required={
            "schemaVersion",
            "tool",
            "dataset",
            "exportedAt",
            "methodology",
            "settings",
            "elapsedMs",
            "images",
            "findings",
        },
        optional={"sourceRoot", "warnings"},
    )
    if (
        type(data["schemaVersion"]) is not int
        or data["schemaVersion"] != 1
        or data["tool"] != "SplitLens"
    ):
        raise ValueError("Unsupported SplitLens report schema/version")
    for name in ("dataset", "exportedAt", "methodology"):
        _string(data[name], name)
    if "sourceRoot" in data:
        _string(data["sourceRoot"], "sourceRoot", nonempty=True)
        if not Path(data["sourceRoot"]).is_absolute():
            raise ValueError("sourceRoot must be an absolute path")
    if root is None and "sourceRoot" not in data:
        raise ValueError("Browser reports require an explicit source root")
    source_root = Path(root) if root is not None else Path(data["sourceRoot"])
    _number(data["elapsedMs"], "elapsedMs")
    raw_settings = _object(
        data["settings"],
        "settings",
        required={"similarity", "blur", "dark", "bright", "minSize"},
        optional={"maxPairs"},
    )
    settings = AuditSettings(
        similarity=raw_settings["similarity"],
        blur=raw_settings["blur"],
        dark=raw_settings["dark"],
        bright=raw_settings["bright"],
        min_size=raw_settings["minSize"],
        max_pairs=raw_settings.get("maxPairs", 2000),
    )
    if not isinstance(data["images"], list) or not isinstance(data["findings"], list):
        raise ValueError("images and findings must be arrays")
    images = []
    decisions = {}
    for value in data["images"]:
        item = _object(
            value,
            "image",
            required={
                "id",
                "path",
                "split",
                "label",
                "width",
                "height",
                "bytes",
                "sha256",
                "dhash",
                "brightness",
                "sharpness",
                "decision",
            },
            optional={"meanRgb", "error"},
        )
        if "meanRgb" in item and (
            not isinstance(item["meanRgb"], list) or len(item["meanRgb"]) != 3
        ):
            raise ValueError("meanRgb must be an array of three numbers")
        record = ImageRecord(
            id=item["id"],
            path=item["path"],
            split=item["split"],
            label=item["label"],
            width=item["width"],
            height=item["height"],
            bytes=item["bytes"],
            sha256=item["sha256"],
            dhash=item["dhash"],
            brightness=item["brightness"],
            sharpness=item["sharpness"],
            mean_rgb=tuple(item["meanRgb"]) if "meanRgb" in item else None,
            error=item.get("error"),
        )
        _validate_image(record)
        decision = item["decision"]
        if decision not in _DECISIONS:
            raise ValueError(f"Unknown decision: {decision!r}")
        images.append(record)
        decisions[record.path] = decision
    findings = []
    for value in data["findings"]:
        item = _object(
            value,
            "finding",
            required={"id", "kind", "imageIds", "title", "detail"},
            optional={"distance"},
        )
        if not isinstance(item["imageIds"], list):
            raise ValueError("imageIds must be an array")
        findings.append(
            Finding(
                id=item["id"],
                kind=item["kind"],
                image_ids=tuple(item["imageIds"]),
                title=item["title"],
                detail=item["detail"],
                distance=item.get("distance"),
            )
        )
    warnings = data.get("warnings", [])
    if not isinstance(warnings, list):
        raise ValueError("warnings must be an array")
    return AuditReport(
        root=source_root,
        images=tuple(images),
        findings=tuple(findings),
        settings=settings,
        elapsed_seconds=data["elapsedMs"] / 1000,
        decisions=decisions,
        warnings=tuple(warnings),
    )
