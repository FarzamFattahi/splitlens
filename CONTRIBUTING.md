# Contributing to SplitLens

Use Node 22.12+ and `npm ci`. Run `npm test`, `npm run build`, and the Playwright browser suite before submitting changes. The CI workflow runs these checks.

Keep image processing local and claims transparent. New matching methods should explain their limitations and come with meaningful tests. Avoid automatic exclusions: the user must explicitly decide what leaves an exported dataset. Preserve original bytes and safe archive paths.

The UI uses locally bundled Geist fonts, a neutral palette with one blue action color, 7px controls and 10–12px panels, visible focus states, and reduced-motion support. Verify a narrow phone viewport and a desktop viewport, including import, errors, empty results, and dialogs. Use accessible labels and avoid conveying a finding only through color.

Bug reports: include browser/version, minimal steps, observed/expected result, and a non-sensitive synthetic example. Never attach private datasets or credentials to an issue. A report with a small reproducible image or archive is more useful than a screenshot alone.

Algorithm changes should include tests that could fail for an incorrect implementation: known Hamming distances, numerical fixtures, cross-split rules, false-positive gates, and archive/export integrity. Do not present synthetic checks as real-world precision/recall benchmarks.
