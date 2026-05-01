#!/usr/bin/env python3
# Requirements: pip install Pillow
"""
pdf-from-images — create a PDF from images with repetition control.

Usage:
  python pdf-from-images.py <path> <reps> [-o output.pdf]

  path   image file or folder containing images
  reps   repetition spec (comma-separated integers):
           "31"      single image 31 pages; or N images cycled 31 times
           "2,2"     first image x2, second image x2
           "3,1,2"   per-image counts; if count < images, cycles the pattern

Interactive prompts are routed through prompt_ui:
  - When run via web-ui.py, menus are rendered as clickable buttons.
  - When run directly from a terminal, menus are rendered as numbered prompts.
"""

import argparse
import sys
from pathlib import Path
from PIL import Image

from prompt_ui import choice, text

SUPPORTED = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}
MAX_PREVIEW = 12


def find_images(path: Path) -> list[Path]:
    if path.is_file():
        if path.suffix.lower() not in SUPPORTED:
            sys.exit(f"Unsupported format: {path.suffix}")
        return [path]
    if path.is_dir():
        imgs = sorted(
            f for f in path.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED
        )
        if not imgs:
            sys.exit(f"No images found in {path}")
        return imgs
    sys.exit(f"Path not found: {path}")


def parse_reps(rep_str: str) -> list[int] | None:
    try:
        values = [int(x.strip()) for x in rep_str.strip().split(",")]
    except ValueError:
        return None
    if any(v <= 0 for v in values):
        return None
    return values


def build_pages(images: list[Path], reps: list[int]) -> tuple[list[Path], str]:
    """
    Returns (page_list, human_description).

    Rules:
      1 rep,  1 image  → image repeated reps[0] times
      1 rep,  N images → whole sequence cycled reps[0] times
      N reps, N images → image[i] repeated reps[i] times
      M reps, N images → reps cycled across images (shown to user for confirmation)
    """
    n, r = len(images), len(reps)

    if r == 1 and n == 1:
        pages = [images[0]] * reps[0]
        desc = f"'{images[0].name}' × {reps[0]}"
        return pages, desc

    if r == 1:
        pages = images * reps[0]
        desc = f"sequence of {n} images cycled {reps[0]} time(s): " + " → ".join(
            f"'{i.name}'" for i in images
        )
        return pages, desc

    if r == n:
        pages: list[Path] = []
        parts = []
        for img, count in zip(images, reps):
            pages.extend([img] * count)
            parts.append(f"'{img.name}' × {count}")
        return pages, " + ".join(parts)

    # Cyclic pattern across images
    pages = []
    parts = []
    for idx, img in enumerate(images):
        count = reps[idx % r]
        pages.extend([img] * count)
        parts.append(f"'{img.name}' × {count}")
    rep_pattern = ",".join(str(v) for v in reps)
    desc = f"cyclic pattern [{rep_pattern}] across {n} images: " + " + ".join(parts)
    return pages, desc


def preview(pages: list[Path]) -> str:
    lines = []
    shown = min(len(pages), MAX_PREVIEW)
    for i, p in enumerate(pages[:shown], 1):
        lines.append(f"  {i:>4}. {p.name}")
    if len(pages) > MAX_PREVIEW:
        remaining = len(pages) - MAX_PREVIEW
        lines.append(f"        ... and {remaining} more page(s)")
    return "\n".join(lines)


def create_pdf(pages: list[Path], output: Path) -> None:
    print(f"\nLoading {len(pages)} image(s)...")
    pil_images: list[Image.Image] = []
    for p in pages:
        try:
            pil_images.append(Image.open(p).convert("RGB"))
        except Exception as e:
            sys.exit(f"Failed to open {p}: {e}")

    output.parent.mkdir(parents=True, exist_ok=True)
    print(f"Writing PDF...")
    pil_images[0].save(
        output,
        format="PDF",
        save_all=True,
        append_images=pil_images[1:],
    )
    print(f"Saved: {output}  ({len(pages)} page(s))")


def default_output(path: Path) -> Path:
    return Path(path.stem if path.is_file() else path.name).with_suffix(".pdf")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a PDF from images with repetition control.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("path", help="Image file or folder of images")
    parser.add_argument("reps", help="Repetitions: '31' or '2,2' or '3,1,2'")
    parser.add_argument("--output", "-o", default=None, help="Output PDF (default: <input_name>.pdf)")
    args = parser.parse_args()

    path = Path(args.path)
    output = Path(args.output) if args.output else default_output(path)
    if output.suffix.lower() != ".pdf":
        output = output.with_suffix(".pdf")

    if args.output is None:
        new_out = text("Output path:", default=str(output))
        if new_out:
            output = Path(new_out)
            if output.suffix.lower() != ".pdf":
                output = output.with_suffix(".pdf")

    images = find_images(path)

    print(f"\nFound {len(images)} image(s):")
    for i, img in enumerate(images, 1):
        print(f"  [{i}] {img.name}")

    rep_str = args.reps

    while True:
        reps = parse_reps(rep_str)
        if reps is None:
            print(f"\n  Invalid: '{rep_str}'. Use positive comma-separated integers (e.g. 3 or 2,2,1).")
            rep_str = text("Repetitions:", placeholder="3 or 2,2,1")
            continue

        pages, desc = build_pages(images, reps)

        print(f"\nInterpretation: {desc}")
        print(f"Total pages   : {len(pages)}")
        print(preview(pages))
        print(f"Output        : {output}")

        if len(reps) not in (1, len(images)):
            print("\n  (cyclic pattern applied — please confirm this is what you intended)")

        action = choice(
            "What now?",
            [
                "Confirm and create PDF",
                "Change repetitions",
                "Change output path",
                "Quit",
            ],
        )

        if action == 0:
            create_pdf(pages, output)
            break
        elif action == 1:
            rep_str = text("New repetitions:", default=rep_str, placeholder="e.g. 3 or 2,2,1")
        elif action == 2:
            new_out = text("New output path:", default=str(output))
            if new_out:
                output = Path(new_out)
                if output.suffix.lower() != ".pdf":
                    output = output.with_suffix(".pdf")
        elif action == 3:
            print("Aborted.")
            sys.exit(0)


if __name__ == "__main__":
    main()
