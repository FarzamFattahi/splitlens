# Troubleshooting

## Installation and commands

**`No module named splitlens`**: install with the same interpreter you use to run the script: `python -m pip install ./python` from a cloned repository, or use the [release-wheel command](quickstart.md#python-and-terminal). Check `python -m pip show splitlens` and `python -m splitlens --version`. A notebook may use a different environment; install into its kernel's interpreter.

**`splitlens` is not recognized**: use `python -m splitlens` instead. This avoids depending on whether your environment's scripts directory is on `PATH`.

**A path with spaces is treated as multiple arguments**: quote it, for example `python -m splitlens audit "my dataset" --html review.html`.

**PowerShell blocks virtual-environment activation**: activation is optional. Run `.venv\Scripts\python.exe -m pip …` and `.venv\Scripts\python.exe -m splitlens …` directly.

**`pip install splitlens` does not install this release**: this project is distributed through its GitHub wheel and source archive, not PyPI. Use the exact install command in the guide. Python 3.11+ is required, and initial installation needs internet access for the package and dependencies. Auditing itself works offline.

## Dataset inputs

**No supported images found**: point the Python scanner at a folder containing still `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, or `.avif` files. Python does not open ZIP archives; extract the ZIP first, or use the browser workspace. Unsupported extensions are ignored. Linked files and directories are skipped with warnings.

**Everything is `unassigned` / no leakage appears**: leakage requires at least two assigned splits. Preserve a `train/`, `val/`, and `test/` directory structure when importing a folder or ZIP. Individual browser file selection usually loses folder paths. Correct splits in the browser's image library, or pass Python `splits` overrides using relative paths and canonical split names.

**Dataset exceeds an image-count or byte limit**: reduce the batch, or explicitly raise Python's `ScanLimits` / CLI limit flags according to available memory. Browser limits are fixed. A default scan accepts up to 1,500 images, 30 MiB per file, and 300 MiB total. Oversized decoded images become findings; animated sequences and corrupt encodings are rejected.

**An AVIF or other image fails in the browser**: decoding support depends on the browser. Try a current Chromium-based browser or the Python companion. Converting an original changes its byte hash; rescan converted datasets before exporting.

## Reports and decisions

**HTML has no image previews**: call `audit("dataset", thumbnails=True)` or request CLI `--html` during the scan. Saved JSON never contains previews; loading it cannot restore them. Rescan with previews enabled to generate visual HTML.

**Decisions did not change the export**: Python methods return new reports. Use `reviewed = report.exclude([...])`, then export `reviewed`. Decision paths are relative image paths such as `test/cats/copy.png`, not image IDs or absolute paths. Save `reviewed.save_json(...)` to persist the decisions.

**Finding counts look larger than image counts**: the same image may have leakage, duplication, and quality findings. Near pairs may create both similarity and leakage findings. `report.summary["findings"]` counts findings, not unique affected images.

**A sharp or useful image is flagged**: the signals are heuristics on a resized analysis image. Illustrations, smooth backgrounds, or intentional exposure choices can trigger them. Inspect evidence and adjust thresholds. A perceptual candidate is not proof of semantic identity; crops, rotations, and reused subjects may be missed.

**The browser forgot my dataset**: the session lives in memory. Reloading restores the demo. Download reports and your optional curated ZIP before closing; saved JSON is metadata for handoff, not a browser session backup.

## Dataset export

**Destination already exists**: choose a new name. Python exports never overwrite existing directories. Check any previous curated dataset before deleting it yourself.

**Source changed, missing, or SHA-256 mismatch**: exports verify the originals against the audit. Re-audit if you intentionally changed images. If you moved the whole dataset without changing bytes, load the report with `root="new-location"` or use CLI `export … --root new-location`.

**Unsafe path / collision / linked path**: Python exports require portable paths, reject Windows reserved names, traversal, `_splitlens/` source paths, and case-insensitive collisions. They also reject symlink/junction redirects. Use a regular dataset folder with portable names, then rescan. Browser ZIP exports can sanitize names and record their mappings; the Python export preserves literal paths and therefore rejects incompatible ones.

**A broken image prevents export**: an unreadable encoding can still be copied if its original bytes were hashed. A file that could not be read or verified cannot be exported. Review and explicitly exclude that path, or restore it and scan again.

**The curated dataset still has findings**: only your explicit exclusions are applied. Unreviewed images remain. Re-audit the result and review remaining issues before training; an export is not a dataset-quality certificate.

## CLI exit codes

| Code | Meaning                                        | Next action                                              |
| ---- | ---------------------------------------------- | -------------------------------------------------------- |
| `0`  | Completed audit/export                         | Review findings; a normal audit can return 0 with issues |
| `1`  | A requested `--fail-on` finding kind was found | Inspect the written report and decide your policy        |
| `2`  | Invalid input or processing/export error       | Read stderr and correct the input or environment         |

## Report an issue

Check [existing issues](https://github.com/FarzamFattahi/splitlens/issues) first. Include your browser or Python version, operating system, command/steps, expected behavior, and a small synthetic reproduction. Do not attach private images, full private reports, credentials, or sensitive paths. Use the [bug-report form](https://github.com/FarzamFattahi/splitlens/issues/new?template=bug_report.yml).
