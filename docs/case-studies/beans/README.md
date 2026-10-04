# Real dataset: Makerere Beans

[Open the illustrated report](https://farzamfattahi.github.io/splitlens/case-studies/beans/) · [Download the audit JSON](https://farzamfattahi.github.io/splitlens/case-studies/beans/baseline.json)

We ran the **published SplitLens 1.1.0 wheel** on Makerere AI Lab's Beans dataset: real field photographs of healthy bean leaves, angular leaf spot, and bean rust in Uganda. The lab describes expert annotation by NaCRRI. This is a dataset audit and a controlled repair demonstration, not a disease classifier or an accuracy benchmark.

## What actually happened

The untouched source contains **1,295 JPEG images**: 1,034 training, 133 validation, and 128 test images. Classes contain 432 angular leaf spot, 436 bean rust, and 427 healthy images. The training archive also contains one unsupported, non-image metadata file, `train/healthy/healthy_train.120tore` (6,148 bytes). It is reported separately; it is not counted as a corrupt JPEG.

With default settings, SplitLens found **0 issues** in 39.66 seconds. This means no images crossed these particular checks; it does not establish that the dataset is free of specimen leakage, cropped duplicates, annotation errors, or every other problem. Every extracted original file was checked against its bytes in the pinned source archives.

| Similarity radius | Similar pairs | Cross-split candidates | Total findings |
| ----------------- | ------------: | ---------------------: | -------------: |
| 4 (default)       |             0 |                      0 |              0 |
| 8                 |             7 |                      1 |              8 |
| 12                |           119 |                     40 |            159 |

Only the similarity radius changed. A cross-split pair creates both a similarity finding and a leakage finding, so findings are not unique-image counts. All seven radius-8 pairs appear in the illustrated report with qualitative, AI-assisted review notes. **No duplicate photograph was confirmed.** The test/train healthy-leaf candidate has unresolved specimen provenance: similar silhouettes alone cannot settle whether the photographs show the same physical leaf. The radius-12 pairs have not been visually reviewed. These notes are not expert ground truth, and the experiment does not measure precision or recall.

## Controlled defects and repair

To exercise checks absent from the original source, we copied the dataset and added **six explicitly labeled files**. These are injected defects, not naturally occurring problems discovered in Beans.

| Added file                                                | Transformation                                           | Expected checks    | Actual findings on that file |
| --------------------------------------------------------- | -------------------------------------------------------- | ------------------ | ---------------------------- |
| `test/healthy/zz_splitlens_exact-copy.jpg`                | Byte copy of `train/healthy/healthy_train.0.jpg`         | Duplicate, leakage | Duplicate, leakage           |
| `validation/angular_leaf_spot/zz_splitlens_reencoded.jpg` | JPEG quality 92 from `angular_leaf_spot_train.0.jpg`     | Similar, leakage   | Similar, leakage             |
| `train/bean_rust/zz_splitlens_blurred.jpg`                | Gaussian blur radius 14 from `bean_rust_train.0.jpg`     | Blur               | Blur, similar, leakage       |
| `train/healthy/zz_splitlens_dark.jpg`                     | Brightness multiplied by 0.08 from `healthy_train.0.jpg` | Dark               | Dark, blur                   |
| `validation/bean_rust/zz_splitlens_small.jpg`             | 96 × 96 Lanczos resize from `bean_rust_train.0.jpg`      | Small              | Small, similar, leakage      |
| `test/angular_leaf_spot/zz_splitlens_broken.jpg`          | Deliberately unreadable bytes                            | Broken             | Broken                       |

All **6/6 expected checks passed**. The 1,301-image controlled copy produced **14 findings**: 1 duplicate, 4 similar, 4 leakage, 2 blur, 1 dark, 1 small, and 1 broken. Some controlled transformations also match each other; that explains additional findings.

We explicitly excluded only the six added paths and exported with the public Python API into a new directory. Export took 5.55 seconds. Rescanning the curated dataset took 36.25 seconds and returned **1,295 images and 0 default findings**. Its complete relative-path-to-SHA-256 mapping equals the original audit: **every retained image is byte-for-byte unchanged**. Originals were never modified. The image export omits the unsupported metadata file and adds its own `_splitlens` audit and decision manifest.

Timings are one local Windows 11 run with Python 3.12.14, NumPy 2.5.3, and Pillow 12.3.0. Scan timing includes preview generation, but excludes download, extraction, archive verification, and writing reports. The controlled scan took 40.27 seconds. These measurements are not general performance guarantees.

## Reproduce it

Clone the repository and run these commands from its root using **Python 3.12 or newer**. The package itself supports Python 3.11+, but this experiment pins newer dependencies for reproducibility.

```bash
python -m venv .beans-venv
# Windows: .beans-venv\Scripts\activate
# macOS/Linux: source .beans-venv/bin/activate
python -m pip install -r python/examples/beans-requirements.txt
python python/examples/beans_case_study.py --workdir .datasets/beans --controls
python python/examples/render_beans_case_study.py --workdir .datasets/beans --output .datasets/beans-public
python -m http.server 8768 --directory .datasets/beans-public
```

Open `http://localhost:8768/`. The commands download approximately **180 MB** and need approximately **1 GB of working disk space** for archives, copies, and reports. A fresh work directory is required for the controlled and curated copies; the script refuses to overwrite them. Downloads are checked for byte count and SHA-256. Extraction rejects unsafe paths and unexpected archive members.

The script writes full HTML reports, CSVs, JSONs, threshold comparisons, and a control recipe record under `.datasets/beans/reports`. Full HTML reports include cached previews and remain local. Published JSONs remove the machine-specific source root. To reload a public audit for export, supply the corresponding verified dataset directory through the `root` parameter described in the [API reference](../../python-api.md). Never interpret six injected files as evidence of six original-source defects.

The repository's **Real dataset reproduction** workflow can also be started manually from GitHub Actions. It downloads and runs the same published wheel, verifies the repair, and uploads the compact illustrated evidence as an artifact. It does not run the large download on every push.

## Source and license

- [Original Makerere project](https://github.com/AI-Lab-Makerere/ibean)
- [Official lab dataset mirror and card](https://huggingface.co/datasets/AI-Lab-Makerere/beans)
- Pinned mirror revision: `27aa014ce09b193e1a6f58112d4a66e0eddb69c5`
- Dataset license: [MIT, copyright 2020 AIR Lab Makerere University](LICENSE.dataset). The selected photographic previews retain this notice. No generated images substitute for dataset evidence.

| Archive        |       Bytes | SHA-256                                                            |
| -------------- | ----------: | ------------------------------------------------------------------ |
| train.zip      | 143,812,152 | `284fe8456ce20687f4367ae7ad94a64577e7f9fde2c2c6b1c74340ab5dc82715` |
| validation.zip |  18,504,213 | `90b7aa1c26d91d9afff07a30bbc67a5ea34f1f1397f068d8675be09d7d0c602d` |
| test.zip       |  17,708,541 | `ca67b15d960d1e2fd9d23fd8498ce86818ead90755c630a43baf19ec4af09312` |

The source project's table says 1,296, while its mirror card says 1,295. The downloaded archives explain the observed difference: 1,295 JPEGs plus one non-image member. The [source manifest](../../../python/examples/beans-source.json) records immutable download URLs and checksums. The [published report files](../../../public/case-studies/beans/) include original-image hashes, selected preview hashes, CSVs, review notes, experiment recipes, and a `SHA256SUMS` integrity manifest. Raw archives and the full dataset remain local rather than enlarging the Git repository.
