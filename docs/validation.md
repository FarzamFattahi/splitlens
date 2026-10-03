# Validation

This release is validated as a working application and an implementation of documented image-processing heuristics. It is **not** a precision/recall benchmark on a labeled real-world duplicate dataset, and its findings are not a certificate of training-data quality.

## Automated checks

The repository includes pure unit tests and Playwright browser tests. GitHub Actions runs strict TypeScript compilation, the production build, unit tests, and Chromium browser integration tests before deploying to Pages.

| Area                       | Evidence                                                                                                                                                                           |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Numerical image processing | Known 64-bit Hamming distances; horizontal-gradient dHash fixtures; constant-image Laplacian variance; high-frequency edges; luminance coefficients                                |
| Candidate indexing         | BK-tree results compared with exhaustive pair comparison; exposure/aspect/flat-hash gates; dense candidate output bounds                                                           |
| Split logic                | SHA-256 groups across train/validation/test; unassigned handling; split aliases; broken-image exclusion from duplicate groups                                                      |
| Input handling             | Actual PNG decoding; corrupt image findings; real folder selection through workers; valid ZIP splits; traversal, empty, corrupt, implausibly expanded and excessive-count archives |
| Exports                    | JSON/CSV/HTML/ZIP downloaded through the UI; explicit exclusion is reflected in all formats; all remaining ZIP image bytes are verified against their original SHA-256 hashes      |
| Output safety              | HTML escaping and script-free report policy; CSV formula neutralization; safe archive paths, filename collisions and explicit failure for missing originals                        |
| Review behavior            | Individual keep/exclude decisions; filename search; split correction; settings reanalysis preserving decisions                                                                     |
| Privacy                    | Demo processing issues no third-party HTTP requests; image processing and ZIP import occur in workers                                                                              |
| Accessibility              | axe WCAG 2 A/AA and WCAG 2.1 AA checks on overview, findings, evidence dialog, settings dialog, image library and exports                                                          |
| Responsive layout          | No page overflow at 1,440 px, 390 px, and 320 px; actual desktop and mobile screenshots committed                                                                                  |

## Local release verification

Verified on Windows using the installed Microsoft Edge channel. All **34 unit tests** and **seven Playwright tests** passed; all 18 accessibility scans and all 18 page-overflow checks passed. The final browser suite exercised the optimized production bundle and its workers, completing in 19.5 seconds. The production build passed; its main JavaScript bundle was 93.44 KB compressed with gzip. `npm audit` reported zero known vulnerabilities in the locked dependency tree at release verification.

The 29-image synthetic demo completed its actual worker analysis in approximately 0.2–0.3 seconds on this development machine. This is a small-fixture observation, not a hardware-independent performance guarantee. No maximum-dataset latency or memory benchmark is claimed.

The demo contains self-created scenes, intentional defects and a corrupt file. It verifies the workflow and known defect cases, rather than measuring generalization to real photographs. Canvas interpolation and decoding can cause perceptual scores to vary slightly by browser.

## Python companion verification

Version 1.1.0 adds the independently installable Python library and CLI. On Windows with Python 3.12.14, **129 Python tests passed**. Three tests requiring symbolic-link privileges were skipped on this account; actual Windows junction tests passed. The browser suite now contains **35 passing unit tests**, including a matching-decision fixture shared with Python.

Python tests exercise actual JPEG, PNG, WebP, BMP, and AVIF images; corruption and animated sequences; EXIF orientation and transparency; configurable count/byte/pixel bounds; split overrides; exact and perceptual candidates; numerical gates; immutable decisions; report loading; escaped HTML previews; formula-safe CSV; pipeline exit codes; changed-source detection; and original-byte dataset export. Failure tests cover existing destinations, path traversal, source/report overwrite, and redirected sources. GitHub Actions runs Python tests and formatting checks on Windows and Linux with Python 3.11, 3.12, and 3.14, then builds and validates wheel/source distributions.

The shared fixture covers decisions from cached measurements. It does not assert identical pixel decoding between Pillow and Canvas, nor benchmark accuracy on real labeled datasets. The Python dependency environment passes `pip check`; distribution metadata is checked with Twine. Release validation also installs the wheel in a fresh environment and audits/exports the generated example dataset through the installed CLI.

## Reproduce

```bash
npm ci
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

```bash
python -m pip install -e "./python[dev]"
python -m pytest python/tests -q
python -m ruff check python
python -m ruff format --check python
python -m build python
python -m twine check python/dist/*
```

Windows browser tests use installed Edge by default. Set `PLAYWRIGHT_CHANNEL=chromium` to use the Playwright browser there. Linux CI uses bundled Chromium. The public static app runs over HTTPS; a local development server provides the secure context required by Web Crypto.

## Known limits

dHash can miss cropping, rotation, subject reuse, and semantic leakage. Domain-specific quality thresholds require visual review. Files remain unreviewed until a user makes a decision; exported datasets include those unreviewed files. Large or dense datasets are bounded by the documented image/byte/pixel and pair-detail limits.

Manual browser verification confirms a usable workspace; automated axe scans do not cover every aspect of accessibility. Mobile layout checks run at phone widths in desktop Chromium/Edge rather than on every physical device. Safari and Firefox are not part of this release's automated matrix. Unsupported decoding capabilities produce a clear browser-support error.
