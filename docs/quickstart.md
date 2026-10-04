# Start with SplitLens

SplitLens helps you inspect an image dataset before training. Findings are evidence for review; you choose what to exclude. All processing is local, and originals stay untouched.

## Browser: no installation

1. [Open SplitLens](https://farzamfattahi.github.io/splitlens/). The built-in synthetic demo is already analyzed, so you can explore before importing anything.
2. Choose **Import a folder** for a dataset on disk, or **Import dataset** for a ZIP or individual images. Folder/ZIP paths preserve split information.
3. Open **Review findings → Leakage** first. Inspect matching images and their measurements. Keep an authoritative original; decide whether a copy should be excluded or assigned to another split.
4. Check the remaining duplicate, similarity, quality, and decoding findings. **Image library** lets you correct split assignments. **Settings** adjusts review thresholds.
5. Use **Export & handoff** to save a report and optionally a curated ZIP. Only explicit exclusions are omitted; unreviewed files remain.

Download reports before reloading or closing the tab. The browser workspace does not persist your session or accept saved JSON reports for import.

## Python and terminal

Use Python 3.11 or newer. NumPy and Pillow are installed as dependencies; no GPU or model download is needed.

```bash
python -m pip install https://github.com/FarzamFattahi/splitlens/releases/download/v1.1.0/splitlens-1.1.0-py3-none-any.whl
python -m splitlens --version
```

On systems where the executable is named `python3`, use `python3` in these commands. An optional virtual environment keeps the package separate from other projects:

```bash
python -m venv .venv
```

Activate it with `.venv\Scripts\Activate.ps1` in Windows PowerShell, or `source .venv/bin/activate` on macOS/Linux, then run the installation command above. If PowerShell blocks activation, use `.venv\Scripts\python.exe` in place of `python`; activation is optional.

Scan your own dataset:

```bash
python -m splitlens audit dataset --html review.html --json audit.json --csv manifest.csv
```

Open `review.html` locally to compare thumbnails. The CLI generates previews when `--html` is requested. JSON stores metadata and decisions without image bytes.

### Try a complete sample

The repository includes a generator for five actual files: an original, an exact test-split copy, a resized validation-split candidate, a dark image, and an unreadable file.

```bash
git clone https://github.com/FarzamFattahi/splitlens.git
cd splitlens
python -m pip install ./python
python python/examples/make_demo.py demo-dataset
python -m splitlens audit demo-dataset --html review.html --json audit.json
```

Open the report. Its exact-copy leakage finding links `train/cup/original.png` and `test/cup/copy.png`. Review the evidence, then explicitly exclude the test copy and unreadable file:

```bash
python -m splitlens export audit.json demo-curated --exclude test/cup/copy.png --exclude train/cup/broken.png
```

The new directory contains:

```text
demo-curated/
  train/cup/original.png
  train/cup/dark.png
  val/cup/resized.png
  _splitlens/audit.json
  _splitlens/manifest.csv
```

All five originals remain in `demo-dataset`. The export contains three images; it still includes the dark image and resized candidate because those were not excluded. Exporting does not certify that all problems are resolved. Re-audit the curated folder and review the remaining findings before training.

Both demo destinations must be new directories. For a second run, choose names such as `demo-dataset-2` and `demo-curated-2`.

### Use from a script

```python
from splitlens import AuditSettings, audit

report = audit("demo-dataset", settings=AuditSettings(min_size=224), thumbnails=True)
images_by_id = {image.id: image for image in report.images}

for finding in report.findings_of("leakage"):
    paths = [images_by_id[image_id].path for image_id in finding.image_ids]
    print(finding.title, paths)

reviewed = report.exclude(["test/cup/copy.png", "train/cup/broken.png"])
reviewed.save_json("reviewed.json")
reviewed.export_dataset("demo-curated-python")
```

Decision methods return a new report. Save the reviewed report if you want to retain decisions for later use. See the [API reference](python-api.md) for loading, relocation, thresholds, and progress callbacks.

## Dataset layout

```text
dataset/
  train/cats/a.jpg
  val/cats/b.jpg
  test/cats/c.jpg
```

Split aliases are `train`, `training`, `val`, `valid`, `validation`, `test`, and `testing`, case-insensitively. The first matching directory determines the split; the next directory is the label. Images without an assigned split do not create cross-split leakage findings. For an external split manifest, use Python's `splits={"cats/a.jpg": "train"}` override.

## Run in CI

```bash
python -m splitlens audit dataset --json audit.json --fail-on leakage,broken --quiet
```

Exit `0` means the command completed; `1` means one of your requested finding kinds was detected; `2` means invalid inputs or a processing/export error. Reports are written before a finding gate returns `1`. A normal audit without `--fail-on` succeeds even when it finds issues.

## Next steps

[Python guide](../python/README.md) · [Troubleshooting](troubleshooting.md) · [How matching works](methodology.md) · [Validation](validation.md)
