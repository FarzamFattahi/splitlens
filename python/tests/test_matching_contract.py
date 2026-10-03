"""Shared fixture checks matching decisions in Python and TypeScript, not image decoders."""

import json
from pathlib import Path

from splitlens import AuditSettings, ImageRecord
from splitlens.engine import reanalyze


def test_shared_browser_python_matching_contract():
    fixture = json.loads((Path(__file__).parent / "fixtures/matching.json").read_text())
    images = []
    for item in fixture["images"]:
        fields = dict(item)
        fields["mean_rgb"] = tuple(fields.pop("meanRgb"))
        images.append(ImageRecord(label="class", **fields))
    findings = reanalyze(images, AuditSettings())
    actual = [{"kind": finding.kind, "imageIds": list(finding.image_ids)} for finding in findings]
    assert actual == fixture["expected"]
