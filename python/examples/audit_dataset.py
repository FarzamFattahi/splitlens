"""Run with: python examples/audit_dataset.py path/to/dataset path/to/reports."""

import argparse
from pathlib import Path

from splitlens import AuditSettings, audit

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("dataset", type=Path)
parser.add_argument("reports", type=Path)
args = parser.parse_args()
args.reports.mkdir(parents=True, exist_ok=True)

report = audit(args.dataset, settings=AuditSettings(min_size=224), thumbnails=True)
print(report.summary)
for finding in report.findings_of("leakage"):
    print(finding.title, finding.image_ids)

report.save_json(args.reports / "audit.json")
report.save_csv(args.reports / "manifest.csv")
report.save_html(args.reports / "review.html")
print(f"Review the report at {args.reports / 'review.html'} before choosing exclusions.")
