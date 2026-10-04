# SplitLens for Python

Audit image datasets in scripts, notebooks, and CI. Find exact duplicates, potential
train/test leakage, visually similar images, unreadable files, and quality issues.
Review the findings, choose exclusions, and export a separate dataset with the
original files preserved.

This is the Python companion to the [SplitLens browser app](https://farzamfattahi.github.io/splitlens/).
Use the app for interactive review; use this package when your dataset already lives
in a Python workflow. Processing stays on your computer. No server, account, GPU,
PyTorch, model downloads, or network access is needed to audit a dataset.

[Start with a working example](../docs/quickstart.md#python-and-terminal) · [API reference](../docs/python-api.md) · [Troubleshooting](../docs/troubleshooting.md)

## Install

For a complete real-data example, see the [Makerere Beans case study](../docs/case-studies/beans/README.md): download verified source archives, audit 1,295 photographs, inspect threshold sensitivity, and test six controlled defects before exporting a byte-verified repair. The experiment uses the published wheel and pins its dependencies with Python 3.12+. Its [illustrated report](https://farzamfattahi.github.io/splitlens/case-studies/beans/) includes downloadable JSON and CSV evidence.

Python 3.11 or newer is required. Install the release wheel directly from GitHub:

```bash
python -m pip install https://github.com/FarzamFattahi/splitlens/releases/download/v1.1.0/splitlens-1.1.0-py3-none-any.whl
```

Or install from the repository:

```bash
git clone https://github.com/FarzamFattahi/splitlens.git
cd splitlens
python -m pip install ./python
```

For a specific version from source:

```bash
python -m pip install "git+https://github.com/FarzamFattahi/splitlens.git@v1.1.0#subdirectory=python"
```

The package is distributed through GitHub releases; it is **not published on PyPI**.
Its runtime dependencies are NumPy and Pillow.

## Audit from Python

A common directory layout is `dataset/train/cats/a.png`, `dataset/val/cats/b.png`,
and `dataset/test/cats/c.png`. Split and label metadata are inferred from directory
names. Images without a recognized split are marked `unassigned`.

```python
from splitlens import AuditSettings, audit

report = audit("dataset", settings=AuditSettings(min_size=224), thumbnails=True)
print(report.summary)

for finding in report.findings_of("leakage"):
    print(finding.title, finding.image_ids)

report.save_json("audit.json")
report.save_csv("manifest.csv")
report.save_html("review.html")
```

The standalone HTML report opens locally in a browser. Enable `thumbnails=True`
when scanning if you want image previews in it. JSON reports always omit previews;
generate HTML from the fresh scan to include them. The default scan avoids the
work of generating previews. `ImageRecord`, `Finding`, `AuditSettings`,
`ScanLimits`, and `AuditReport` are public typed dataclasses/helpers.

For datasets whose split lives in another manifest, pass relative image paths:

```python
report = audit("dataset", splits={"cats/a.png": "train", "cats/b.png": "test"})
```

Inspect `report.images` for records and `report.findings` for all findings. Findings
reference records by `image_ids`; each record also provides its relative `path`.
You can change review thresholds without decoding images again:

```python
report = report.reanalyze(AuditSettings(similarity=2, blur=40, min_size=224))
```

## Make explicit changes

SplitLens never chooses which duplicates to delete. After reviewing the report,
apply your decisions to relative image paths:

```python
from splitlens import AuditReport

report = AuditReport.load_json("audit.json")
reviewed = report.exclude(["test/cats/copied.png"])
reviewed = reviewed.keep(["train/cats/original.png"])
reviewed.save_json("reviewed.json")
reviewed.export_dataset("dataset-curated")  # must be a new directory
```

Decision helpers return a new report. Unreviewed and kept images are included;
only explicit exclusions are omitted. Exports preserve the source directory
structure and verify source content against the scan before copying. Changed or
missing source files cause an error; scan again before exporting them. The source
dataset is never modified. Rebase a saved report after relocating its dataset with
`AuditReport.load_json("audit.json", root="new-dataset-location")`.

## Command line

```bash
splitlens audit dataset --json audit.json --csv manifest.csv --html review.html
splitlens export audit.json dataset-curated --exclude test/cats/copied.png
python -m splitlens --version
```

Repeat `--exclude` or `--keep` to apply multiple decisions. Existing decisions in a
saved report are retained; command-line decisions override them. An export without
exclusions copies the whole dataset. Use `--root` to relocate the source when
exporting a saved report. The destination must not already exist.

Quality thresholds are adjustable:

```bash
splitlens audit dataset --similarity 2 --blur 40 --dark 25 --bright 235 --min-size 224
```

Use finding gates in CI, optionally retaining reports as CI artifacts:

```bash
splitlens audit dataset --json audit.json --fail-on leakage,broken --quiet
```

Exit codes are `0` for a completed audit/export, `1` when an audit finds a requested
gate kind, and `2` for invalid inputs or processing/export errors. Requested reports
are still written when the audit exits `1`. Repeat `--fail-on` or separate kinds
with commas. Supported kinds: `leakage`, `duplicate`, `similar`, `blur`, `dark`,
`bright`, `small`, and `broken`. A normal audit returns `0` even if it finds issues;
use `--fail-on` to enforce your own policy. `--quiet` suppresses the summary;
errors and scan warnings still appear on standard error.

## Limits and interpretation

Default scan bounds are 1,500 images, 30 MiB per file, 300 MiB total, and 40 million
pixels per image. These are resource limits, not image-quality thresholds. For a
larger local dataset, choose appropriate bounds explicitly:

```python
from splitlens import ScanLimits, audit

report = audit("dataset", limits=ScanLimits(max_images=5000, max_total_bytes=1024 * 1024 * 1024))
```

The CLI equivalents are `--max-images`, `--max-file-mb`, `--max-total-mb`, and
`--max-pixels`; the `mb` options use MiB (1,048,576 bytes). Pair findings are bounded
by `AuditSettings.max_pairs` (default 2,000), so a heavily duplicated dataset may
need a higher explicit setting for a complete list of pair findings.

The scanner accepts still JPEG, PNG, WebP, BMP, and AVIF images. Other file
extensions are ignored; animated images and image sequences receive a `broken`
finding. Symlinked images and linked directories are skipped with warnings.

Exact duplication uses SHA-256 of file bytes. Perceptual candidates use a 64-bit
difference hash; a low distance suggests a review candidate, not proof of a shared
subject. Leakage flags compare images across recognized dataset splits. They do
not detect semantic leakage, person identities, near-duplicate video sequences,
or undocumented split boundaries.

Quality checks use a normalized 128 × 128 white-composited image: brightness,
Laplacian variance for sharpness, and original dimensions for small images. A
perfectly valid illustration can trigger blur or exposure checks. Tune thresholds
to the task and review candidates before excluding anything.

The browser and Python companions share finding concepts, but Pillow and browser
image decoding/resizing can produce different numerical metrics and perceptual
candidates. Python JSON reports are a versioned package schema; they are not a
promise of direct browser import or byte-for-byte parity.

## Development

```bash
python -m pip install -e "./python[dev]"
python -m pytest python/tests
python -m ruff check python
python -m build python
```

See [`examples/audit_dataset.py`](examples/audit_dataset.py) for a runnable reporting
example. From a repository checkout, create a small demo with deliberate duplicates,
leakage, a dark image, and an unreadable file, then generate reports:

```bash
python python/examples/make_demo.py demo-dataset
python python/examples/audit_dataset.py demo-dataset demo-reports
splitlens audit demo-dataset --fail-on leakage,broken --quiet
```

The last command deliberately exits `1`; the fixture is designed to demonstrate
the CI gate. `make_demo.py` requires a new destination directory and preserves
existing data. Licensed under the repository's MIT license.
