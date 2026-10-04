# Python API reference

Import public types from `splitlens`. Requires Python 3.11+. [Install and run an example](quickstart.md#python-and-terminal).

## Audit a folder

```python
from splitlens import AuditSettings, ScanLimits, audit

report = audit(
    "dataset",
    settings=AuditSettings(),
    limits=ScanLimits(),
    splits={"train/cats/a.png": "train"},
    on_progress=lambda done, total: print(f"{done}/{total}"),
    thumbnails=True,
)
```

`root` accepts a string or path-like directory. All other arguments are optional. `splits` maps existing relative POSIX paths to `train`, `validation`, `test`, or `unassigned`; unknown paths or split names raise an error. The progress callback runs after each image. `thumbnails` defaults to `False`; enable it for HTML image evidence.

Scanning is sequential and does not modify images or access the network. Supported still formats are JPEG, PNG, WebP, BMP, and AVIF. Symbolic links and junctions are skipped and recorded in `report.warnings`. Individual decoding failures become `broken` findings. An invalid directory, empty dataset, or exceeded count/encoded-byte limit fails the scan. A decoded-pixel limit violation becomes a broken-image finding.

## Settings

| `AuditSettings` field | Default | Meaning                                            |
| --------------------- | ------- | -------------------------------------------------- |
| `similarity`          | `4`     | Maximum 64-bit dHash distance, integer 0–12        |
| `blur`                | `60`    | Flag Laplacian variance below this threshold       |
| `dark`                | `35`    | Flag mean grayscale below this value               |
| `bright`              | `225`   | Flag mean grayscale above this value               |
| `min_size`            | `256`   | Flag shortest original side below this many pixels |
| `max_pairs`           | `2000`  | Detailed perceptual-pair cap per category          |

Exposure thresholds must satisfy `0 ≤ dark < bright ≤ 255`. `blur` and `min_size` are nonnegative; `max_pairs` is a positive integer. Dense matches beyond the pair cap receive explicit summary findings rather than an unlimited list.

| `ScanLimits` field | Default             |
| ------------------ | ------------------- |
| `max_images`       | `1500`              |
| `max_file_bytes`   | `30 * 1024 * 1024`  |
| `max_total_bytes`  | `300 * 1024 * 1024` |
| `max_pixels`       | `40_000_000`        |

All limits must be positive integers. Choose larger limits explicitly according to your hardware; these defaults are resource bounds, not dataset-quality guarantees.

## AuditReport

| Attribute or method                                      | Result                                                                          |
| -------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `root`                                                   | Absolute dataset `Path`                                                         |
| `images`                                                 | Tuple of `ImageRecord` values                                                   |
| `findings`                                               | Tuple of `Finding` values                                                       |
| `settings`                                               | Thresholds used for the current findings                                        |
| `elapsed_seconds`                                        | Scan duration                                                                   |
| `warnings`                                               | Tuple of scan warnings                                                          |
| `decisions`                                              | Immutable mapping of relative paths to explicit decisions                       |
| `summary`                                                | Counts: `images`, `findings`, `by_kind`, `excluded`, `reviewed`                 |
| `findings_of(kind)`                                      | Findings for a supported issue kind                                             |
| `exclude(paths)` / `keep(paths)`                         | New report with those explicit decisions                                        |
| `with_decisions(mapping)`                                | New report merging decisions; `unreviewed` resets a decision                    |
| `reanalyze(settings)`                                    | New report applying thresholds to cached measurements                           |
| `to_dict()`                                              | Version-1 JSON-shaped metadata dictionary                                       |
| `save_json(path)` / `save_csv(path)` / `save_html(path)` | Save a report; return its `Path`                                                |
| `AuditReport.load_json(path, root=None)`                 | Load and validate saved metadata; optionally relocate the source                |
| `export_dataset(destination)`                            | Verify retained originals and create a new dataset directory; return its `Path` |

Supported finding kinds are `leakage`, `duplicate`, `similar`, `blur`, `dark`, `bright`, `small`, and `broken`. A single image can participate in several findings.

`ImageRecord` exposes `id`, `path`, `split`, `label`, `width`, `height`, `bytes`, `sha256`, `dhash`, `brightness`, `sharpness`, `mean_rgb`, optional `thumbnail`, and optional `error`. `Finding` exposes `id`, `kind`, `image_ids`, `title`, `detail`, and optional `distance`. Finding IDs refer to image IDs, while decision helpers take relative file paths.

Reports and records are immutable snapshots. Keep the returned value when making decisions:

```python
reviewed = report.exclude(["test/cats/copy.png"])
reviewed = reviewed.with_decisions({"test/cats/copy.png": "unreviewed"})
```

## Save, relocate, and export

```python
from splitlens import AuditReport

reviewed.save_json("reviewed.json")
relocated = AuditReport.load_json("reviewed.json", root="new-dataset-location")
relocated.export_dataset("dataset-curated")
```

JSON omits previews and includes the original source root. A loaded report cannot reconstruct HTML thumbnails; scan with `thumbnails=True` to produce visual evidence. CSV protects cells from spreadsheet formula interpretation; HTML escapes text and uses no scripts.

Exports include kept and unreviewed images. Only explicit exclusions are omitted. The destination must be absent and outside the source tree; it also cannot be an ancestor of the source. Original relative paths and file bytes are retained. `_splitlens/audit.json` and `_splitlens/manifest.csv` record the review, including excluded rows.

Changed or missing sources, invalid digests, unsafe portable paths, case-insensitive collisions, and linked source/output paths cause an error. Export stages files before an exclusive rename, so a failed export does not leave a partially curated destination. Source originals remain untouched. macOS uses an exclusive system rename but is not part of the automated CI matrix; Windows and Linux are tested.

Reports may include private filenames, labels, absolute source paths, and optional image previews. Share them according to the dataset's sensitivity. See [methodology](methodology.md) for matching limitations and [troubleshooting](troubleshooting.md) for common errors.
