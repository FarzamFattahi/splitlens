"""Create a tiny reproducible dataset with intentional defects; never overwrite input."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="new dataset directory")
    destination = parser.parse_args().destination
    destination.mkdir(parents=True, exist_ok=False)
    for split in ("train", "val", "test"):
        (destination / split / "cup").mkdir(parents=True)
    with Image.new("RGB", (512, 384), "#e2e6e9") as scene:
        draw = ImageDraw.Draw(scene)
        draw.rounded_rectangle((130, 80, 300, 290), radius=30, fill="#316578")
        draw.ellipse((280, 120, 370, 230), outline="#316578", width=20)
        draw.rectangle((90, 300, 400, 312), fill="#969fa7")
        scene.save(destination / "train/cup/original.png")
        scene.resize((256, 192)).save(destination / "val/cup/resized.png")
    shutil.copyfile(destination / "train/cup/original.png", destination / "test/cup/copy.png")
    with Image.new("RGB", (320, 256), (5, 5, 5)) as dark:
        dark.save(destination / "train/cup/dark.png")
    (destination / "train/cup/broken.png").write_bytes(b"intentionally incomplete PNG")
    print(f"Created five images, including deliberate defects: {destination}")


if __name__ == "__main__":
    main()
