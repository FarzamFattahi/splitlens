# What SplitLens measures

SplitLens is a review tool for image classification datasets. It computes reproducible, inexpensive image signals in your browser and helps you inspect candidates before changing your dataset. It does not train a model, infer semantic identity, inspect labels for correctness, or guarantee that a split is free of leakage.

## Processing and privacy

Original files stay in browser memory. A Web Worker reads file bytes, computes hashes, decodes images, and produces small JPEG previews. SplitLens sends neither originals nor previews to an inference service. Export downloads are created locally. Reports may contain filenames, class names and image previews; share those deliberately.

Decoding uses the browser's `createImageBitmap`. Images have a 40 megapixel decode limit. PNG, WebP, BMP and JPEG dimensions are checked before decoding when their headers can be parsed; AVIF receives the dimension check after decoding. Animated PNG, animated WebP, GIF, and AVIF sequences are excluded. An unsupported, corrupt, or oversized image appears as a decode finding. Originals remain available for export unless manually excluded. Canvas decoding and resizing can differ slightly across browsers, so perceptual metrics are not a cross-browser byte-level contract.

## Exact copies and cross-split leakage

The worker computes SHA-256 over the original encoded file bytes. Matching hashes are grouped as exact copies. A group that occupies at least two assigned splits is also a leakage finding. Copies within one split are duplicates. Unassigned images do not create a cross-split finding by themselves.

Identical pixels saved with different compression or metadata have different byte hashes. They may instead be found by the perceptual check. A matching SHA-256 establishes byte equality for practical dataset auditing, not correctness of labels or a history of the source capture.

## Near-duplicate candidates

Each decoded image is composited on white and resized to 9 × 8 pixels. Grayscale is computed as `0.299 R + 0.587 G + 0.114 B`. For each of the 64 horizontal neighboring pixel pairs, one bit records whether the left value is greater than the right value. The result is a 64-bit difference hash (dHash).

The engine compares hashes by Hamming distance with a BK-tree, searching within the chosen integer radius (clamped to 0–12; default 4). To reduce spurious matches:

- Hashes with fewer than 5 or more than 59 set bits are skipped as low-information images.
- Candidate images must satisfy `abs(log(aspect_ratio_A / aspect_ratio_B)) ≤ 0.04`.
- Their mean grayscale brightness must differ by at most 25 on a 0–255 scale.
- Mean RGB channels are measured on the same white-composited 128 × 128 canvas used for quality checks. When both records have this measurement, the maximum difference between luminance-subtracted mean channels must be at most 12: `max_c abs((mean_c_A − brightness_A) − (mean_c_B − brightness_B)) ≤ 12`. Older records lacking mean RGB skip this gate.
- Exact byte copies are handled by the exact-copy grouping instead of repeated near-pair findings.

A candidate spanning multiple assigned splits also receives a leakage finding. Different findings can involve the same image, so the number of findings is not the number of affected images.

This method works best for lightly edited, resized or re-encoded versions of the same image. It can miss crops, rotations, changed backgrounds and different views of the same subject. It can also group unrelated images with similar layouts. A low hash distance is evidence to inspect, not a semantic duplicate verdict. The aspect-ratio, brightness and color filters intentionally trade some recall for fewer false positives. The fixed 12-level color threshold is a conservative heuristic intended to reject strongly different hues with similar grayscale outlines while allowing modest color jitter; subtracting luminance tolerates additive exposure shifts. Mean color is only a coarse signal: balanced colors or small objects can still collide, and strong legitimate color edits may be missed. No benchmark recall or precision is claimed.

## Image quality signals

The browser stretches each image to a 128 × 128 analysis canvas after compositing transparency on white. Metrics describe this analysis image, not the full-resolution original.

| Check           | Calculation                                                                                                            | Default review threshold |
| --------------- | ---------------------------------------------------------------------------------------------------------------------- | ------------------------ |
| Low edge detail | Variance of the four-neighbor Laplacian `up + down + left + right − 4 center`, computed over interior grayscale pixels | Less than 60             |
| Dark exposure   | Mean grayscale intensity                                                                                               | Less than 35 / 255       |
| Bright exposure | Mean grayscale intensity                                                                                               | Greater than 225 / 255   |
| Small image     | Minimum original width or height                                                                                       | Less than 256 px         |
| Decode failure  | Browser decoding or dimensional safety error                                                                           | Any error                |

These thresholds are adjustable review aids. Smooth products, illustration, blank backgrounds and low-contrast subjects can have low Laplacian variance while being perfectly focused. High-key or low-key photography may intentionally trip an exposure check. Resizing affects sharpness scores, and stretching to a square affects anisotropic detail. Choose thresholds appropriate to the dataset and inspect evidence before excluding files.

## Split and class metadata

Folder segments identify `train`/`training`, `val`/`valid`/`validation`, and `test`/`testing` case-insensitively. The first recognized split segment determines the inferred split; its next folder segment is the class label when one exists. An explicit input split takes precedence. Files without split folders are unassigned, and files without class folders are unlabeled. SplitLens does not claim to support arbitrary annotation formats.

## Decisions and exports

Every image starts **unreviewed**. **Keep** and **Exclude** are manual decisions, independent of findings. Nothing is automatically deleted or excluded.

- **JSON audit:** all metadata, thresholds, findings and decisions; omits thumbnail image bytes.
- **CSV manifest:** all audited images and decisions. Cells are quoted and spreadsheet formula prefixes are neutralized. The ZIP manifest additionally maps each included original to its archive path.
- **HTML report:** a standalone, script-free report with escaped text, inline thumbnail evidence, settings and these interpretation limits. Only validated PNG/JPEG/WebP data URLs are accepted as previews.
- **Reviewed dataset ZIP:** original bytes for kept and unreviewed images; only manually excluded images are omitted. Broken files remain unless excluded. A missing included original produces an explicit error instead of a partial export. The manifest retains excluded rows for traceability.

ZIP originals appear under `images/`. Paths have traversal segments, filesystem-special characters and Windows reserved names removed or replaced. Case-insensitive collisions receive numeric suffixes. Safe paths may therefore differ from original names; the manifest records both. Originals are never re-encoded. Export generation uses browser memory and should not be treated as an unbounded dataset storage pipeline.

## Demo provenance

The demo contains 28 original procedural image files and one deliberately broken file (29 entries total). The canvas artwork depicts ceramic vessels, botanical bottles and copper canisters. The code and generated images are covered by this repository's MIT license; no stock imagery or third-party artwork is embedded.

The demo deliberately includes an exact copy across train and validation, a within-train exact copy, a retouched train/test candidate, an out-of-focus scene, under- and overexposed scenes, a 96 × 72 image, and an interrupted image file. It uses real generated PNG bytes and runs through the same worker and engine as user uploads. Finding counts are calculated, not canned; similarity results and quality scores can vary slightly by browser.
