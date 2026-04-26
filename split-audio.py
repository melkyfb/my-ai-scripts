#!/usr/bin/env python3
"""
split-audio.py — Split large audio/video files by chapters or timed intervals.

Requires: ffmpeg + ffprobe (system)
Optional: pip install openai-whisper  (for --split-at sentence/paragraph)

Usage:
  python split-audio.py podcast.mp3 --mode time --interval 30:00 --split-at silence
  python split-audio.py lecture.mp3 --mode time --interval 1:00:00 --split-at sentence
  python split-audio.py audiobook.mp3 --mode chapters
  python split-audio.py interview.mp4 --mode time --interval 45:00 --split-at exact -o ./parts
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


# ─── Time helpers ─────────────────────────────────────────────────────────────

def parse_time(t):
    """Parse HH:MM:SS, MM:SS, or raw seconds to float."""
    s = str(t).strip()
    parts = s.split(":")
    if len(parts) == 1:
        return float(parts[0])
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    raise ValueError(f"Unrecognized time format: {t!r}")


def fmt(seconds):
    """Format seconds as HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


# ─── System checks ────────────────────────────────────────────────────────────

def require_cmd(name):
    if subprocess.run(["which", name], capture_output=True).returncode != 0:
        print(f"Error: '{name}' not found. Install ffmpeg.", file=sys.stderr)
        sys.exit(1)


# ─── Audio info ───────────────────────────────────────────────────────────────

def get_duration(file_path):
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(file_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"Error reading file: {file_path}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


# ─── Silence detection ────────────────────────────────────────────────────────

def detect_silences(file_path, noise_db=-35, min_duration=0.5):
    """Return list of (start, end) silence intervals."""
    cmd = [
        "ffmpeg", "-i", str(file_path),
        "-af", f"silencedetect=noise={noise_db}dB:d={min_duration}",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stderr

    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", output)]
    ends   = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", output)]

    silences = list(zip(starts, ends[:len(starts)]))

    # Audio may end mid-silence — last silence_end missing
    if len(starts) > len(ends):
        duration = get_duration(file_path)
        silences.append((starts[-1], duration))

    return silences


def nearest_silence(target, silences, window):
    """Return the midpoint of the silence closest to target within ±window seconds."""
    best, best_dist = None, float("inf")
    for s, e in silences:
        mid = (s + e) / 2
        d = abs(mid - target)
        if d < best_dist and d <= window:
            best, best_dist = mid, d
    return best


# ─── Whisper helpers ──────────────────────────────────────────────────────────

def transcribe(file_path, model_name, lang):
    try:
        import whisper
    except ImportError:
        print("openai-whisper is required for --split-at sentence/paragraph.", file=sys.stderr)
        print("Install with: pip install openai-whisper", file=sys.stderr)
        sys.exit(1)

    print(f"Loading Whisper model '{model_name}'…")
    model = whisper.load_model(model_name)
    kwargs = {"word_timestamps": True}
    if lang:
        kwargs["language"] = lang
    print("Transcribing — this may take a while for long files…")
    result = model.transcribe(str(file_path), **kwargs)
    return result["segments"]


def nearest_sentence_end(target, segments, window):
    candidates = [seg["end"] for seg in segments if seg["text"].strip().endswith((".", "!", "?"))]
    if not candidates:
        return None
    best = min(candidates, key=lambda t: abs(t - target))
    return best if abs(best - target) <= window else None


def nearest_paragraph_end(target, segments, window):
    """Paragraph boundary = long inter-segment gap or sentence-ending segment."""
    ends = set()
    for i in range(len(segments) - 1):
        if segments[i + 1]["start"] - segments[i]["end"] > 1.0:
            ends.add(segments[i]["end"])
    for seg in segments:
        if seg["text"].strip().endswith((".", "!", "?")):
            ends.add(seg["end"])
    if not ends:
        return None
    best = min(ends, key=lambda t: abs(t - target))
    return best if abs(best - target) <= window else None


# ─── Boundary builders ────────────────────────────────────────────────────────

def build_chapter_boundaries(file_path, duration, args):
    print("Detecting chapter boundaries via silence…")
    silences = detect_silences(file_path, noise_db=args.noise_db, min_duration=args.chapter_silence)
    print(f"  Found {len(silences)} silence interval(s).")

    boundaries = [0.0]
    for s, e in silences:
        mid = (s + e) / 2
        if mid - boundaries[-1] >= args.min_chapter:
            boundaries.append(mid)
    boundaries.append(duration)

    if len(boundaries) < 3:
        print("Only one chapter detected. Try lowering --chapter-silence or --min-chapter.")
        sys.exit(1)

    return boundaries


def build_time_boundaries(file_path, duration, args):
    interval = parse_time(args.interval)

    if interval <= 0:
        print("Error: --interval must be greater than 0.", file=sys.stderr)
        sys.exit(1)
    if interval >= duration:
        print(
            f"Error: interval {fmt(interval)} is ≥ audio duration {fmt(duration)}.",
            file=sys.stderr,
        )
        sys.exit(1)

    targets = []
    t = interval
    while t < duration:
        targets.append(t)
        t += interval

    silences = None
    segments = None

    if args.split_at == "silence":
        print("Detecting silences…")
        silences = detect_silences(file_path, noise_db=args.noise_db, min_duration=0.3)
        print(f"  Found {len(silences)} silence interval(s).")
    elif args.split_at in ("sentence", "paragraph"):
        segments = transcribe(file_path, args.whisper_model, args.lang)

    boundaries = [0.0]
    for target in targets:
        if args.split_at == "exact":
            boundaries.append(target)

        elif args.split_at == "silence":
            found = nearest_silence(target, silences, args.window)
            if found is not None:
                boundaries.append(found)
            else:
                print(f"  Warning: no silence near {fmt(target)}, using exact time.")
                boundaries.append(target)

        elif args.split_at == "sentence":
            found = nearest_sentence_end(target, segments, args.window)
            if found is not None:
                boundaries.append(found)
            else:
                print(f"  Warning: no sentence end near {fmt(target)}, using exact time.")
                boundaries.append(target)

        elif args.split_at == "paragraph":
            found = nearest_paragraph_end(target, segments, args.window)
            if found is not None:
                boundaries.append(found)
            else:
                print(f"  Warning: no paragraph end near {fmt(target)}, using exact time.")
                boundaries.append(target)

    boundaries.append(duration)
    return boundaries


# ─── Preview + confirm ────────────────────────────────────────────────────────

def preview(boundaries):
    w = 62
    print(f"\n{'─' * w}")
    print(f"  {'#':>4}  {'Start':>11}  {'End':>11}  {'Duration':>11}")
    print(f"{'─' * w}")
    for i, (s, e) in enumerate(zip(boundaries[:-1], boundaries[1:]), 1):
        print(f"  {i:>4}  {fmt(s):>11}  {fmt(e):>11}  {fmt(e - s):>11}")
    print(f"{'─' * w}")
    print(f"  Total: {len(boundaries) - 1} segment(s)\n")


def confirm(prompt="Proceed with splitting? [y/n]: "):
    while True:
        answer = input(prompt).strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False


# ─── Splitting ────────────────────────────────────────────────────────────────

def split_file(file_path, boundaries, output_dir, stem):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file_path).suffix
    total = len(boundaries) - 1

    print(f"Writing {total} file(s) to {output_dir}/\n")

    for i, (start, end) in enumerate(zip(boundaries[:-1], boundaries[1:]), 1):
        out = output_dir / f"{stem}_{i:03d}{suffix}"
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", str(file_path),
            "-t", str(end - start),
            "-c", "copy",
            str(out),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error on segment {i}:\n{result.stderr}", file=sys.stderr)
            sys.exit(1)

        print(f"  [{i:0{len(str(total))}d}/{total}] {fmt(start)} → {fmt(end)}  {out.name}")

    print(f"\nDone.")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Split large audio/video files by chapters or timed intervals.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
split modes:
  chapters   Auto-detect chapter breaks using silence gaps (no Whisper needed)
  time       Split at a fixed interval; --split-at controls where exactly to cut

split-at options (for --mode time):
  exact      Cut at the precise interval time
  silence    Cut at the nearest silence within the window (default)
  sentence   Cut at the nearest sentence end — requires Whisper
  paragraph  Cut at the nearest paragraph end — requires Whisper

examples:
  python split-audio.py podcast.mp3 --mode time --interval 30:00
  python split-audio.py lecture.mp3 --mode time --interval 1:00:00 --split-at sentence
  python split-audio.py audiobook.mp3 --mode chapters --chapter-silence 2.0
  python split-audio.py interview.mp4 --mode time --interval 45:00 --split-at exact -o ./parts
""",
    )

    parser.add_argument("file", help="Input audio or video file")

    parser.add_argument(
        "--mode", choices=["chapters", "time"], default="time",
        help="Split strategy (default: time)",
    )

    # ── time mode ──
    g_time = parser.add_argument_group("time mode")
    g_time.add_argument(
        "--interval", metavar="TIME",
        help="Split interval: HH:MM:SS, MM:SS, or seconds (e.g. 30:00, 1:30:00, 3600)",
    )
    g_time.add_argument(
        "--split-at", choices=["exact", "silence", "sentence", "paragraph"],
        default="silence", metavar="MODE",
        help="Where to cut near each interval: exact | silence | sentence | paragraph (default: silence)",
    )
    g_time.add_argument(
        "--window", type=float, default=30, metavar="SECS",
        help="Search window in seconds around each target time (default: 30)",
    )

    # ── chapters mode ──
    g_ch = parser.add_argument_group("chapters mode")
    g_ch.add_argument(
        "--chapter-silence", type=float, default=1.5, metavar="SECS",
        help="Min silence duration (s) to treat as a chapter boundary (default: 1.5)",
    )
    g_ch.add_argument(
        "--min-chapter", type=float, default=60, metavar="SECS",
        help="Min chapter duration in seconds (default: 60)",
    )

    # ── shared ──
    g_shared = parser.add_argument_group("shared options")
    g_shared.add_argument(
        "--noise-db", type=int, default=-35, metavar="DB",
        help="Noise threshold in dB for silence detection (default: -35)",
    )
    g_shared.add_argument(
        "--whisper-model", default="base", metavar="SIZE",
        help="Whisper model: tiny / base / small / medium / large (default: base)",
    )
    g_shared.add_argument("--lang", metavar="LANG", help="Language hint for Whisper (e.g. pt, en)")
    g_shared.add_argument(
        "-o", "--output", metavar="DIR",
        help="Output directory (default: same folder as input file)",
    )
    g_shared.add_argument(
        "--prefix", metavar="NAME",
        help="Output filename prefix (default: input filename without extension)",
    )
    g_shared.add_argument(
        "-y", "--yes", action="store_true",
        help="Skip confirmation prompt",
    )

    args = parser.parse_args()

    require_cmd("ffmpeg")
    require_cmd("ffprobe")

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: file not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output) if args.output else file_path.parent
    stem = args.prefix or file_path.stem

    print(f"Input   : {file_path}")
    duration = get_duration(file_path)
    print(f"Duration: {fmt(duration)}")

    if args.mode == "chapters":
        boundaries = build_chapter_boundaries(file_path, duration, args)
    else:
        if not args.interval:
            print("Error: --interval is required for --mode time.", file=sys.stderr)
            sys.exit(1)
        boundaries = build_time_boundaries(file_path, duration, args)

    preview(boundaries)

    if not args.yes and not confirm():
        print("Cancelled.")
        sys.exit(0)

    split_file(file_path, boundaries, output_dir, stem)


if __name__ == "__main__":
    main()
