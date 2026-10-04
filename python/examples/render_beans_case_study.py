"""Publish a compact, source-attributed snapshot of measured Beans audit results.

Run after beans_case_study.py --controls. Metadata is copied without source roots.
Only selected cached audit previews are included, not the full image dataset.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import shutil
from html.parser import HTMLParser
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


class Previews(HTMLParser):
    def __init__(self, needed: set[str]):
        super().__init__()
        self.needed = needed
        self.images: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag == "img" and data.get("alt") in self.needed:
            value = data.get("src", "")
            if value.startswith("data:image/jpeg;base64,"):
                self.images[data["alt"]] = value


def previews(path: Path, needed: set[str]) -> dict[str, str]:
    parser = Previews(needed)
    with path.open(encoding="utf-8") as source:
        while chunk := source.read(1024 * 1024):
            parser.feed(chunk)
    parser.close()
    return parser.images


CSS = """
:root{color-scheme:light;--ink:#18202b;--muted:#586271;--line:#dce1e8;--blue:#1659cf;--paper:#f6f7f9}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:var(--paper);color:var(--ink);line-height:1.6}
a{color:var(--blue);text-underline-offset:3px}a:focus-visible,summary:focus-visible{outline:3px solid var(--blue);outline-offset:5px;border-radius:3px}
.wrap{max-width:1160px;margin:auto;padding:0 28px}header{background:white;border-bottom:1px solid var(--line)}.top{display:flex;justify-content:space-between;gap:24px;align-items:center;padding:20px 0}.brand{font-weight:750;font-size:20px;text-decoration:none;color:var(--ink)}.brand span{color:var(--blue)}nav{display:flex;gap:20px;flex-wrap:wrap;font-size:13px}nav a{text-decoration:none}
.hero{padding:66px 0 30px}.eyebrow{font-size:12px;font-weight:750;letter-spacing:.14em;text-transform:uppercase;color:var(--blue)}h1{font-size:clamp(32px,4.5vw,54px);line-height:1.13;letter-spacing:-.04em;max-width:850px;margin:16px 0 20px}h2{font-size:26px;line-height:1.3;letter-spacing:-.025em;margin:0 0 14px}h3{font-size:17px;line-height:1.4;margin:0 0 8px}.lead{font-size:18px;color:var(--muted);max-width:800px;margin:0}.actions{display:flex;flex-wrap:wrap;gap:12px;margin-top:26px}.button{display:inline-flex;min-height:44px;align-items:center;border:1px solid var(--line);padding:10px 16px;border-radius:7px;background:white;text-decoration:none;font-size:14px;font-weight:650}.button.primary{background:var(--blue);border-color:var(--blue);color:white}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:30px 0 14px}.stat{background:white;border:1px solid var(--line);border-radius:10px;padding:20px}.value{font-size:32px;font-weight:750;letter-spacing:-.025em}.label{font-size:12px;color:var(--muted)}.note{font-size:13px;color:var(--muted)}section{margin:36px 0 0;padding-top:30px;border-top:1px solid var(--line);scroll-margin-top:20px}.two{display:grid;grid-template-columns:1fr 1fr;gap:24px}.panel{background:white;border:1px solid var(--line);border-radius:10px;padding:24px}.callout{border-left:3px solid var(--blue);background:#edf3ff;padding:16px 20px;border-radius:0 7px 7px 0;margin:20px 0}.callout.warning{border-color:#946500;background:#fff8e9}.callout p{margin:0}.table-scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:11px 12px;border-bottom:1px solid var(--line)}th{font-size:12px;font-weight:700;color:var(--muted)}td:not(:first-child){font-variant-numeric:tabular-nums}.gallery{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:24px 0}figure{margin:0;min-width:0}figure img{width:100%;aspect-ratio:1;object-fit:contain;display:block;background:#e8ebee;border-radius:6px}figcaption{font-size:12px;color:var(--muted);overflow-wrap:anywhere;margin-top:9px}.pairs{display:grid;gap:16px;margin:24px 0}details{background:white;border:1px solid var(--line);border-radius:10px;padding:16px 20px}summary{cursor:pointer;font-size:14px;font-weight:650;min-height:32px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:18px 0 0;max-width:780px}.pair img{max-height:280px}.pill{display:inline-block;background:#edf3ff;color:#1249a8;border-radius:4px;padding:2px 7px;font-size:11px;margin:3px 3px 3px 0;font-weight:650}.pill.amber{background:#fff3d9;color:#795300}.placeholder{display:grid;place-items:center;aspect-ratio:1;background:#eceff4;border:1px dashed #a8b1bf;border-radius:6px;text-align:center;padding:20px;font-size:14px;color:var(--muted)}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#18202b;color:#edf3ff;padding:20px;border-radius:8px;font-size:12px;line-height:1.8}code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere}.downloads{display:flex;gap:16px;flex-wrap:wrap;font-size:14px}footer{padding:35px 0 40px;margin-top:40px;border-top:1px solid var(--line);font-size:12px;color:var(--muted)}@media(max-width:700px){.wrap{padding:0 18px}.top{align-items:flex-start;flex-direction:column;gap:10px}.hero{padding-top:36px}.stats{grid-template-columns:repeat(2,1fr)}.stat{padding:14px}.value{font-size:27px}.two{grid-template-columns:1fr}.panel{padding:18px}.gallery{grid-template-columns:repeat(2,1fr);gap:12px}.pair{gap:10px}details{padding:14px}.pair figcaption{font-size:10px}h2{font-size:23px}}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, default=Path(".datasets/beans"))
    parser.add_argument("--output", type=Path, default=Path("public/case-studies/beans"))
    args = parser.parse_args()
    reports = args.workdir.resolve() / "reports"
    output = args.output.resolve()
    if output.is_relative_to(args.workdir.resolve()):
        raise ValueError("Publish to a separate directory, outside the downloaded dataset workdir")
    output.mkdir(parents=True, exist_ok=True)
    assets = output / "images"
    assets.mkdir(exist_ok=True)
    summary = load(reports / "summary.json")
    baseline = load(reports / "baseline.json")
    controlled = load(reports / "controlled.json")
    experiment = load(reports / "controlled-experiment.json")
    sensitivity = load(reports / "threshold-sensitivity.json")
    review = load(Path(__file__).with_name("beans-review.json"))
    base_images = {image["path"]: image for image in baseline["images"]}
    control_images = {image["path"]: image for image in controlled["images"]}
    samples = [
        next(
            image
            for image in baseline["images"]
            if image["split"] == split and image["label"] == label
        )
        for split in ("train", "validation", "test")
        for label in ("angular_leaf_spot", "bean_rust", "healthy")
    ]
    selected = {image["path"] for image in samples}
    selected.update(path for pair in review["pairs"] for path in pair["paths"])
    selected.update(change["source_path"] for change in experiment["injected_files"])
    injected = {change["path"] for change in experiment["injected_files"]}
    cached = previews(reports / "baseline.html", selected)
    cached.update(previews(reports / "controlled.html", injected))
    evidence = []
    urls = {}
    for path, value in cached.items():
        encoded = base64.b64decode(value.split(",", 1)[1], validate=True)
        checksum = hashlib.sha256(encoded).hexdigest()
        name = "images/" + checksum[:16] + ".jpg"
        (output / name).write_bytes(encoded)
        urls[path] = name
        record = control_images[path] if path in injected else base_images[path]
        evidence.append(
            {
                "path": path,
                "injected": path in injected,
                "preview": name,
                "preview_sha256": checksum,
                "original_sha256": record["sha256"],
                "method": "Cached SplitLens audit JPEG preview; white-composited, at most 280×280",
            }
        )

    def figure(path: str, label: str = "") -> str:
        record = control_images[path] if path in injected else base_images[path]
        image = (
            f'<img src="{escape(urls[path])}" alt="{escape(label or path)}" loading="lazy" width="280" height="280">'
            if path in urls
            else '<div class="placeholder">Deliberately unreadable image<br>No preview available</div>'
        )
        details = f"{record['width']} × {record['height']} px · brightness {record['brightness']:.1f} · sharpness {record['sharpness']:.1f}"
        return (
            f"<figure>{image}<figcaption>{escape(path)}<br>{escape(details)}</figcaption></figure>"
        )

    files = [
        "baseline.json",
        "baseline.csv",
        "controlled.json",
        "controlled.csv",
        "curated.json",
        "curated.csv",
        "summary.json",
        "controlled-experiment.json",
        "threshold-sensitivity.json",
    ]
    for name in files:
        shutil.copyfile(reports / name, output / name)
    dump(output / "source.json", summary["source"])
    dump(output / "visual-review.json", review)
    dump(output / "evidence.json", evidence)
    for radius in (8, 12):
        result = load(reports / f"radius-{radius}.json")
        image_map = {image["id"]: image["path"] for image in result["images"]}
        findings = [
            {**finding, "paths": [image_map[image_id] for image_id in finding["imageIds"]]}
            for finding in result["findings"]
        ]
        dump(output / f"radius-{radius}-findings.json", findings)
    license_path = Path(__file__).resolve().parents[2] / "docs/case-studies/beans/LICENSE.dataset"
    shutil.copyfile(license_path, output / "LICENSE.dataset")
    counts = summary["summary"]
    split_rows = "".join(
        f"<tr><td>{escape(split)}</td><td>{summary['images_by_split'][split]:,}</td></tr>"
        for split in ("train", "validation", "test")
    )
    label_rows = "".join(
        f"<tr><td>{escape(label.replace('_', ' '))}</td><td>{count:,}</td></tr>"
        for label, count in summary["images_by_label"].items()
    )
    sensitivity_rows = "".join(
        f"<tr><td>{row['similarity']}{' (default)' if row['similarity'] == 4 else ' (exploratory)'}</td><td>{row['summary']['by_kind']['similar']}</td><td>{row['summary']['by_kind']['leakage']}</td><td>{row['summary']['findings']}</td></tr>"
        for row in sensitivity
    )
    natural_pairs = "".join(
        f'<details{" open" if pair["status"] == "provenance_unresolved" else ""}><summary>Candidate {index} · distance 8/64 · {"Cross-split provenance unresolved" if pair["status"] == "provenance_unresolved" else "Distinct photographs on visual inspection"}</summary><div class="pair">{"".join(figure(path) for path in pair["paths"])}</div><p class="note">{escape(pair["note"])}</p></details>'
        for index, pair in enumerate(review["pairs"], 1)
    )
    control_cards = ""
    for change in experiment["injected_files"]:
        badges = "".join(
            f'<span class="pill">{escape(kind)}</span>' for kind in change["detected_kinds"]
        )
        control_cards += f'<details><summary><span class="pill amber">Injected control</span> {escape(change["description"])} — expected check passed</summary><div class="pair">{figure(change["source_path"], "Original field photograph")}{figure(change["path"], "Explicitly injected " + change["operation"] + " control")}</div><p>Detected: {badges}</p><p class="note">Source file is unchanged. This added path was explicitly excluded during repair.</p></details>'
    ignored = summary["ignored_archive_entries"][0]
    timestamp = baseline["exportedAt"].split("T")[0]
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="A reproducible SplitLens audit of 1,295 real Makerere bean-leaf photographs, threshold sensitivity, and a disclosed contamination-and-repair experiment."><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>Makerere Beans case study · SplitLens</title><style>{CSS}</style></head>
<body><header><div class="wrap top"><a class="brand" href="../../">Split<span>Lens</span></a><nav aria-label="Case-study sections"><a href="#baseline">Original data</a><a href="#sensitivity">Thresholds</a><a href="#controls">Controls &amp; repair</a><a href="#reproduce">Reproduce</a></nav></div></header>
<main class="wrap"><div class="hero"><div class="eyebrow">Real-data case study · {timestamp} · SplitLens {escape(summary["environment"]["splitlens"])}</div><h1>Makerere Beans dataset audit.</h1><p class="lead">Real field photographs, published dataset splits, measured findings, and a verified repair of six explicitly added defects. Original-source results and controlled results are reported separately.</p><div class="actions"><a class="button primary" href="baseline.json" download>Download original audit JSON</a><a class="button" href="baseline.csv" download>Download original manifest CSV</a><a class="button" href="https://github.com/FarzamFattahi/splitlens/blob/main/docs/case-studies/beans/README.md">Read the case study</a></div></div>
<div class="stats"><div class="stat"><div class="value">{counts["images"]:,}</div><div class="label">Original photographs audited</div></div><div class="stat"><div class="value">3</div><div class="label">Published train / validation / test splits</div></div><div class="stat"><div class="value">{counts["findings"]}</div><div class="label">Findings at default thresholds</div></div><div class="stat"><div class="value">{summary["elapsed_seconds"]:.2f}s</div><div class="label">Observed local scan with previews</div></div></div><p class="note">Single {escape(summary["environment"]["platform"])} run; Python {escape(summary["environment"]["python"])}, NumPy {escape(summary["environment"]["numpy"])}, Pillow {escape(summary["environment"]["pillow"])}. Scan time includes decoding, hashing, measurements, and optional previews; excludes download, extraction, verification, and report writing. Hardware and environment affect timings.</p>
<section id="baseline"><h2>1. Untouched source dataset</h2><p>Beans is a Makerere AI Lab / NaCRRI dataset of healthy and diseased bean leaves photographed in Uganda. All three archives were downloaded from the lab’s Hugging Face mirror at revision <code>{escape(summary["source"]["revision"])}</code> and verified against pinned SHA-256 hashes. Every audited image was then compared with the bytes inside its source archive.</p><div class="two"><div class="panel"><h3>Published splits</h3><table><thead><tr><th scope="col">Split</th><th scope="col">Images</th></tr></thead><tbody>{split_rows}</tbody></table></div><div class="panel"><h3>Published class labels</h3><table><thead><tr><th scope="col">Label</th><th scope="col">Images</th></tr></thead><tbody>{label_rows}</tbody></table></div></div><div class="callout"><p><strong>No configured signals triggered.</strong> The default radius is 4, blur threshold 60, exposure range 35–225, and minimum side 256 px. Zero findings does not establish an absence of semantic leakage, shared specimens, label errors, crops, or rotations.</p></div><p class="note">The archives contain 1,296 files: 1,295 supported JPEG photographs and one 6,148-byte non-image entry, <code>{escape(ignored["path"])}</code>. That entry remains in the local original dataset but is ignored by the image scanner. It was not counted as a broken JPEG.</p><div class="gallery">{"".join(figure(image["path"], image["label"].replace("_", " ") + " · " + image["split"]) for image in samples)}</div><p class="note">Gallery: the first filename in each split/class combination, sorted by path. These are cached audit previews, not generated illustrations. All 1,295 images contributed to the audit.</p></section>
<section id="sensitivity"><h2>2. More candidates require more review</h2><p>The original measured images were reanalyzed without changing files or decoding again. Only the perceptual radius changed; other gates and thresholds stayed fixed.</p><div class="panel table-scroll"><table><thead><tr><th scope="col">dHash radius</th><th scope="col">Similar pairs</th><th scope="col">Cross-split candidates</th><th scope="col">Total findings</th></tr></thead><tbody>{sensitivity_rows}</tbody></table></div><p class="note">A cross-split pair contributes a similarity finding and a leakage-candidate finding. Findings are not independent image counts. Radius-12 candidates were not individually reviewed.</p><div class="callout warning"><p><strong>Seven radius-8 pairs were inspected side by side.</strong> No duplicate photograph was confirmed. The one cross-split healthy-leaf pair has unresolved specimen/capture-session provenance. The qualitative review is AI-assisted, not expert duplicate ground truth; no original image was excluded.</p></div><div class="pairs">{natural_pairs}</div><div class="downloads"><a href="radius-8-findings.json" download>Radius-8 findings</a><a href="radius-12-findings.json" download>Radius-12 findings</a><a href="visual-review.json" download>Visual review notes</a></div></section>
<section id="controls"><h2>3. Disclosed contamination and verified repair</h2><p>A separate copy of the full dataset received six deliberately added files: an exact test-split copy, a JPEG re-encoding in validation, a blurred image, a dark image, a 96 × 96 image, and an unreadable JPEG. These are controlled defects, not defects claimed to exist naturally in the source dataset.</p><div class="stats"><div class="stat"><div class="value">{experiment["controlled"]["summary"]["images"]:,}</div><div class="label">Images in the controlled copy</div></div><div class="stat"><div class="value">{experiment["controlled"]["summary"]["findings"]}</div><div class="label">Findings in the controlled copy</div></div><div class="stat"><div class="value">6 / 6</div><div class="label">Added files triggered expected checks</div></div><div class="stat"><div class="value">{experiment["original_image_hashes_preserved"]:,}</div><div class="label">Original image hashes preserved after repair</div></div></div><div class="pairs">{control_cards}</div><div class="callout"><p><strong>Only the six injected paths were excluded.</strong> Verified export took {experiment["export_seconds"]:.2f}s on this machine. The resulting {experiment["curated"]["summary"]["images"]:,}-image folder was audited again and returned {experiment["curated"]["summary"]["findings"]} default findings. Its relative image paths and SHA-256 values exactly match the untouched baseline. Unsupported archive metadata is not an audited image and is not included in a curated-image export.</p></div><p class="note">Multiple findings can involve one file; the {experiment["controlled"]["summary"]["findings"]} findings are not {experiment["controlled"]["summary"]["findings"]} independently injected defects. Passing these controls establishes a working detection/review/export workflow on these examples, not real-world precision or recall.</p><div class="downloads"><a href="controlled-experiment.json" download>Control recipes and verification</a><a href="controlled.json" download>Controlled audit</a><a href="curated.json" download>Post-repair audit</a><a href="curated.csv" download>Post-repair manifest</a></div></section>
<section id="reproduce"><h2>4. Run it yourself</h2><p>Use Python 3.12+ for the recorded dependency versions. The package itself supports Python 3.11+. The example downloads about 180 MB and uses roughly 1 GB of local disk space for archives, separate dataset copies, and reports. Choose a new workdir for a full control run.</p><pre><code>git clone https://github.com/FarzamFattahi/splitlens.git
cd splitlens
python -m pip install -r python/examples/beans-requirements.txt
python python/examples/beans_case_study.py --workdir .datasets/beans --controls
python python/examples/render_beans_case_study.py --workdir .datasets/beans --output public/case-studies/beans</code></pre><p>The baseline JSON omits local absolute paths. To load it with the downloaded originals, call <code>AuditReport.load_json("baseline.json", root=".datasets/beans/dataset")</code>. The reproduction script downloads data only; it does not execute remote dataset-loader code. Generated JSON/CSV files are small enough to share; the full original dataset and large thumbnail reports stay local.</p><div class="downloads"><a href="source.json" download>Pinned source and archive hashes</a><a href="summary.json" download>Environment and baseline summary</a><a href="evidence.json" download>Preview provenance</a><a href="SHA256SUMS" download>Published artifact checksums</a><a href="https://github.com/FarzamFattahi/splitlens/blob/main/python/examples/beans_case_study.py">Reproduction script</a></div></section>
</main><footer><div class="wrap">Dataset photographs: Copyright © 2020 AIR Lab Makerere University. Released under the <a href="LICENSE.dataset">dataset MIT license</a>; selected previews are resized derivatives. <a href="https://github.com/AI-Lab-Makerere/ibean">Original dataset</a> · <a href="https://huggingface.co/datasets/AI-Lab-Makerere/beans">Lab mirror</a> · <a href="https://github.com/FarzamFattahi/splitlens">SplitLens repository</a>. This is a recorded case-study snapshot, not a precision/recall benchmark or a certificate of dataset quality.</div></footer></body></html>"""
    (output / "index.html").write_text(document, encoding="utf-8")
    checksums = []
    names = [
        *files,
        "source.json",
        "visual-review.json",
        "evidence.json",
        "radius-8-findings.json",
        "radius-12-findings.json",
        "LICENSE.dataset",
        "index.html",
        *sorted(set(urls.values())),
    ]
    for name in names:
        checksums.append(hashlib.sha256((output / name).read_bytes()).hexdigest() + "  " + name)
    (output / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    print(f"Published {len(names)} snapshot assets to {output}")


if __name__ == "__main__":
    main()
