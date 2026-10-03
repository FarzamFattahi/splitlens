"""Command-line dataset auditing and explicit, verified exports."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__, audit
from .models import ISSUE_KINDS, AuditSettings, ScanLimits
from .report import AuditReport


def _megabytes(value: str) -> int:
    try:
        amount = float(value)
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError
        result = int(amount * 1024 * 1024)
        if result <= 0:
            raise ValueError
        return result
    except (ValueError, OverflowError) as exc:
        raise argparse.ArgumentTypeError("must be a positive, finite number of MiB") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="splitlens", description="Audit image datasets locally and export reviewed copies."
    )
    parser.add_argument("--version", action="version", version=f"splitlens {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("audit", help="scan an image directory")
    scan.add_argument("root", type=Path)
    for format_name in ("json", "csv", "html"):
        scan.add_argument(
            f"--{format_name}", type=Path, help=f"save a {format_name.upper()} report"
        )
    defaults = AuditSettings()
    scan.add_argument("--similarity", type=int, default=defaults.similarity, metavar="0..12")
    scan.add_argument("--blur", type=float, default=defaults.blur)
    scan.add_argument("--dark", type=float, default=defaults.dark)
    scan.add_argument("--bright", type=float, default=defaults.bright)
    scan.add_argument("--min-size", type=int, default=defaults.min_size, metavar="PIXELS")
    limits = ScanLimits()
    scan.add_argument("--max-images", type=int, default=limits.max_images)
    scan.add_argument(
        "--max-file-mb", type=_megabytes, default=limits.max_file_bytes, metavar="MIB"
    )
    scan.add_argument(
        "--max-total-mb", type=_megabytes, default=limits.max_total_bytes, metavar="MIB"
    )
    scan.add_argument("--max-pixels", type=int, default=limits.max_pixels)
    scan.add_argument(
        "--fail-on",
        action="append",
        default=[],
        metavar="KINDS",
        help=f"exit 1 for these findings; repeat or comma-separate: {', '.join(ISSUE_KINDS)}",
    )
    scan.add_argument("--quiet", action="store_true", help="suppress the summary")
    export = commands.add_parser("export", help="export an explicitly reviewed JSON report")
    export.add_argument("report", type=Path)
    export.add_argument("destination", type=Path, help="new output directory; must not exist")
    export.add_argument("--root", type=Path, help="rebase the report onto a relocated dataset")
    export.add_argument("--exclude", action="append", default=[], metavar="RELATIVE_PATH")
    export.add_argument("--keep", action="append", default=[], metavar="RELATIVE_PATH")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI. Return 0 for success, 1 for a finding gate, or 2 for invalid input."""
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    try:
        if args.command == "audit":
            gates = {kind.strip() for group in args.fail_on for kind in group.split(",")}
            unknown = gates.difference(ISSUE_KINDS)
            if unknown:
                raise ValueError(f"unknown --fail-on kind(s): {', '.join(sorted(unknown))}")
            settings = AuditSettings(
                similarity=args.similarity,
                blur=args.blur,
                dark=args.dark,
                bright=args.bright,
                min_size=args.min_size,
            )
            limits = ScanLimits(
                max_images=args.max_images,
                max_file_bytes=args.max_file_mb,
                max_total_bytes=args.max_total_mb,
                max_pixels=args.max_pixels,
            )
            report = audit(args.root, settings=settings, limits=limits, thumbnails=bool(args.html))
            for warning in report.warnings:
                print(f"splitlens: warning: {warning}", file=sys.stderr)
            for format_name in ("json", "csv", "html"):
                target = getattr(args, format_name)
                if target is not None:
                    getattr(report, f"save_{format_name}")(target)
            if not args.quiet:
                print(json.dumps(report.summary, indent=2))
            return 1 if any(finding.kind in gates for finding in report.findings) else 0

        conflicts = set(args.keep).intersection(args.exclude)
        if conflicts:
            raise ValueError(
                f"paths cannot be both kept and excluded: {', '.join(sorted(conflicts))}"
            )
        report = AuditReport.load_json(args.report, root=args.root)
        for warning in report.warnings:
            print(f"splitlens: warning: {warning}", file=sys.stderr)
        if args.exclude:
            report = report.exclude(args.exclude)
        if args.keep:
            report = report.keep(args.keep)
        destination = report.export_dataset(args.destination)
        excluded = report.summary["excluded"]
        included = report.summary["images"] - excluded
        print(
            f"Exported {included} images to {destination}; excluded {excluded} by explicit choice"
        )
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"splitlens: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
