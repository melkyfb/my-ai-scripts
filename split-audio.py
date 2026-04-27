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


def fmt_time_label(seconds):
    """Format seconds as HHhMMmSSs for use in filenames (e.g. 01h30m00s)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}h{m:02d}m{s:02d}s"


def make_filename(stem, suffix, i, total, start, end, name_fmt, title=None):
    pad = len(str(total))
    if title:
        return f"{stem}_{i:0{pad}d}_{sanitize_filename(title)}{suffix}"
    if name_fmt == "time":
        return f"{stem}_{fmt_time_label(start)}-{fmt_time_label(end)}{suffix}"
    if name_fmt == "part":
        return f"{stem}_part_{i:0{pad}d}_of_{total}{suffix}"
    if name_fmt == "chapter":
        return f"{stem}_chapter_{i:0{pad}d}{suffix}"
    return f"{stem}_{i:0{pad}d}{suffix}"  # index (default)


# ─── Title helpers ────────────────────────────────────────────────────────────

def sanitize_filename(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name or "untitled"


def fetch_video_title(url):
    try:
        import yt_dlp
    except ImportError:
        print("yt-dlp is required for --url. Install with: pip install yt-dlp", file=sys.stderr)
        sys.exit(1)
    print(f"Fetching title from {url} …")
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as e:
            print(f"Error fetching URL: {e}", file=sys.stderr)
            sys.exit(1)
    return sanitize_filename(info.get("title") or "untitled")


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

def get_embedded_chapters(file_path):
    """Return list of {start, end, title} from embedded metadata, or []."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_chapters", str(file_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    chapters = json.loads(result.stdout).get("chapters", [])
    if len(chapters) < 2:
        return []
    out = []
    for ch in chapters:
        start = float(ch.get("start_time", 0))
        end   = float(ch.get("end_time", 0))
        title = (ch.get("tags") or {}).get("title", "").strip()
        if end > start:
            out.append({"start": start, "end": end, "title": title})
    return out


def cluster_silence_levels(silences):
    """
    Group silence intervals into structural levels by finding natural ≥2×
    drops in the sorted duration distribution.

    Example: [10s, 9s, 8s | gap | 2.5s, 2s | gap | 0.7s, 0.6s]
    → chapter level (avg 9s), section level (avg 2.25s), short pauses (avg 0.65s)

    Returns list of {threshold, count, avg_dur} sorted longest → shortest.
    """
    if not silences:
        return []

    durations = sorted([e - s for s, e in silences], reverse=True)

    breaks = [
        i + 1
        for i in range(len(durations) - 1)
        if durations[i] / max(durations[i + 1], 0.01) >= 2.0
    ]

    groups, prev = [], 0
    for b in breaks:
        groups.append(durations[prev:b])
        prev = b
    groups.append(durations[prev:])

    return [
        {"threshold": grp[-1], "count": len(grp), "avg_dur": sum(grp) / len(grp)}
        for grp in groups if grp
    ]


def _boundaries_for_threshold(silences, threshold, duration, min_chapter):
    chapter_sils = [(s, e) for s, e in silences if (e - s) >= threshold]
    bounds = [0.0]
    for s, e in sorted(chapter_sils):
        mid = (s + e) / 2
        if mid - bounds[-1] >= min_chapter:
            bounds.append(mid)
    bounds.append(duration)
    return bounds


def choose_silence_level(levels, silences, duration, min_chapter):
    """
    Show the detected structural levels and ask the user which one to use.
    Returns the chosen boundaries list.
    """
    SANE_RANGE = (2, 80)  # reasonable chapter count for an audiobook

    all_bounds = [
        _boundaries_for_threshold(silences, lv["threshold"], duration, min_chapter)
        for lv in levels
    ]

    # Single level: use without prompting
    if len(levels) == 1:
        n = len(all_bounds[0]) - 1
        print(f"  Single structural level found: {n} segment(s)  "
              f"(silence ≥ {levels[0]['threshold']:.1f}s, avg {levels[0]['avg_dur']:.1f}s)")
        return all_bounds[0]

    # Multiple levels: display and ask
    LABELS = ["chapter-level (longest silences)", "section-level", "sub-section-level"]
    print("\n  Detected structural levels:\n")
    auto = None
    for i, (lv, bounds) in enumerate(zip(levels, all_bounds)):
        n = len(bounds) - 1
        label = LABELS[i] if i < len(LABELS) else f"level {i + 1}"
        marker = ""
        if auto is None and SANE_RANGE[0] <= n <= SANE_RANGE[1]:
            auto = i
            marker = "  ← recommended"
        print(f"    {i + 1}. {label:<38} {n:3d} parts  "
              f"(silence ≥ {lv['threshold']:.1f}s, avg {lv['avg_dur']:.1f}s){marker}")

    if auto is None:
        auto = 0  # fallback to coarsest level

    print()
    while True:
        raw = input(f"  Choose level [1–{len(levels)}] or Enter for recommended ({auto + 1}): ").strip()
        if raw == "":
            return all_bounds[auto]
        try:
            v = int(raw) - 1
            if 0 <= v < len(levels):
                return all_bounds[v]
        except ValueError:
            pass
        print(f"  Please enter a number between 1 and {len(levels)}.")


def build_chapter_boundaries(file_path, duration, args):
    """
    Discover chapter boundaries using the best available method:
      1. Embedded metadata chapters (most accurate — common in M4A/M4B audiobooks)
      2. Adaptive silence analysis — detects structural levels automatically
         and lets the user choose the desired granularity.

    Returns (boundaries, titles_or_None).
    """
    # ── 1. embedded metadata ────────────────────────────────────────────────
    print("Checking for embedded chapter metadata…")
    chapters = get_embedded_chapters(file_path)
    if chapters:
        n = len(chapters)
        has_titles = any(ch["title"] for ch in chapters)
        print(f"  Found {n} embedded chapter(s)"
              + (" with titles." if has_titles else " (no titles in metadata)."))

        starts = [ch["start"] for ch in chapters]
        if starts[0] > 0.5:
            starts.insert(0, 0.0)
            chapters.insert(0, {"start": 0.0, "end": chapters[0]["start"], "title": ""})

        boundaries = starts + [duration]
        titles = [ch["title"] or f"Chapter {i + 1}" for i, ch in enumerate(chapters)]
        # Keep titles only if at least one is non-generic
        if not has_titles:
            titles = None
        return boundaries, titles

    print("  No embedded chapters found.")

    # ── 2. adaptive silence analysis ────────────────────────────────────────
    print("Scanning silence structure across the entire file…")
    silences = detect_silences(file_path, noise_db=args.noise_db, min_duration=0.3)
    n_sil = len(silences)
    print(f"  Found {n_sil} silence interval(s).")

    if not silences:
        print("No silences detected — cannot split by chapters automatically.\n"
              "Try lowering --noise-db (e.g. --noise-db -50).", file=sys.stderr)
        sys.exit(1)

    levels = cluster_silence_levels(silences)
    boundaries = choose_silence_level(levels, silences, duration, args.min_chapter)

    if len(boundaries) < 3:
        print("Only 1 segment detected. Try lowering --noise-db or --min-chapter.",
              file=sys.stderr)
        sys.exit(1)

    return boundaries, None


# ─── AI chapter detection ─────────────────────────────────────────────────────

_CHAPTER_PROMPT = """\
Analyze this audiobook transcription and identify where chapter or section titles are announced.

Each line is: [HH:MM:SS.mmm] <spoken text>

<transcription>
{transcript}
</transcription>

Find ALL timestamps where the narrator reads a chapter title, part title, or structural heading.
Common patterns (any language): "Chapter N", "Part N", "Capítulo N", "Parte N", "Section N",
"Introduction", "Prologue", "Epilogue", "Interlude", standalone numbered headings, etc.

Return ONLY valid JSON with no markdown or explanation:
{{"chapters": [{{"time": "HH:MM:SS.mmm", "title": "exact spoken title"}}]}}
If no markers found: {{"chapters": []}}
"""


def _parse_ai_chapters(text):
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        return []
    try:
        return json.loads(match.group()).get("chapters", [])
    except (json.JSONDecodeError, AttributeError):
        return []


def _call_ai(transcript, provider, api_key, model):
    prompt = _CHAPTER_PROMPT.format(transcript=transcript)

    if provider == "anthropic":
        try:
            import anthropic
        except ImportError:
            print("anthropic package not installed.\nRun: pip install anthropic", file=sys.stderr)
            sys.exit(1)
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model or "claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_ai_chapters(resp.content[0].text)

    else:  # openai
        try:
            from openai import OpenAI
        except ImportError:
            print("openai package not installed.\nRun: pip install openai", file=sys.stderr)
            sys.exit(1)
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model or "gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_ai_chapters(resp.choices[0].message.content)


def _resolve_ai_config(args):
    """Return (provider, api_key) from args / env vars, or exit with instructions."""
    provider = getattr(args, "ai_provider", None)
    key      = getattr(args, "api_key", None) or ""

    ant_key = key or os.environ.get("ANTHROPIC_API_KEY", "")
    oai_key = key or os.environ.get("OPENAI_API_KEY", "")

    if provider == "anthropic" or (not provider and ant_key):
        if not ant_key:
            print("Anthropic API key required.\n"
                  "Set ANTHROPIC_API_KEY=sk-ant-... or pass --api-key KEY --ai-provider anthropic",
                  file=sys.stderr)
            sys.exit(1)
        return "anthropic", ant_key

    if provider == "openai" or (not provider and oai_key):
        if not oai_key:
            print("OpenAI API key required.\n"
                  "Set OPENAI_API_KEY=sk-... or pass --api-key KEY --ai-provider openai",
                  file=sys.stderr)
            sys.exit(1)
        return "openai", oai_key

    print(
        "AI provider not configured for --mode transcript.\n"
        "Options:\n"
        "  export ANTHROPIC_API_KEY=sk-ant-...   (uses Anthropic / Claude)\n"
        "  export OPENAI_API_KEY=sk-...           (uses OpenAI / GPT)\n"
        "  or: --api-key KEY --ai-provider anthropic|openai",
        file=sys.stderr,
    )
    sys.exit(1)


def _build_ai_transcript(segments):
    """Condensed transcript: one timestamped line per Whisper segment."""
    return "\n".join(
        f"[{fmt(seg['start'])}] {seg['text'].strip()}"
        for seg in segments if seg["text"].strip()
    )


def _snap_to_segment(t, segments, window=5.0):
    """Snap t to the nearest Whisper segment start within window seconds."""
    best = min(segments, key=lambda s: abs(s["start"] - t))
    return best["start"] if abs(best["start"] - t) <= window else t


def build_transcript_boundaries(file_path, duration, args):
    """
    Full-file Whisper transcription → AI identifies spoken chapter/section titles
    → cut exactly at those points.

    Requires:
      pip install openai-whisper
      pip install anthropic   (for --ai-provider anthropic, default)
      pip install openai      (for --ai-provider openai)
    API key: ANTHROPIC_API_KEY or OPENAI_API_KEY env var, or --api-key.
    """
    provider, api_key = _resolve_ai_config(args)
    ai_model = getattr(args, "ai_model", None)

    # Step 1: full-file Whisper transcription
    print(f"Transcribing with Whisper (model: {args.whisper_model})…")
    segments = transcribe(file_path, args.whisper_model, args.lang)
    print(f"  Transcribed {len(segments)} segment(s).")

    # Step 2: build condensed transcript string
    transcript = _build_ai_transcript(segments)
    chars = len(transcript)
    print(f"  Transcript size: {chars:,} characters (~{chars // 4:,} tokens).")

    # Step 3: ask AI to detect chapter markers
    print(f"Detecting chapter structure with {provider.title()} AI…")
    raw = _call_ai(transcript, provider, api_key, ai_model)

    if not raw:
        print("  AI found no chapter markers.")
        print("  Falling back to adaptive silence detection…")
        return build_chapter_boundaries(file_path, duration, args)

    print(f"  Detected {len(raw)} chapter marker(s).")

    # Step 4: map AI timestamps back to exact Whisper segment boundaries
    boundaries, titles = [0.0], []
    for ch in raw:
        try:
            t = parse_time(ch["time"])
        except (ValueError, KeyError):
            continue
        t = _snap_to_segment(t, segments)
        if t > boundaries[-1] + args.min_chapter:
            boundaries.append(t)
            titles.append(ch.get("title", "").strip() or f"Chapter {len(titles) + 1}")

    boundaries.append(duration)

    # Pad titles to match segment count (content before first detected chapter)
    while len(titles) < len(boundaries) - 1:
        titles.insert(0, "Introduction")

    if len(boundaries) < 3:
        print("  Not enough boundaries found after filtering.")
        print("  Falling back to adaptive silence detection…")
        return build_chapter_boundaries(file_path, duration, args)

    return boundaries, titles


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

def preview(boundaries, stem, suffix, name_fmt, titles=None):
    total = len(boundaries) - 1
    pad = len(str(total))
    names = [
        make_filename(stem, suffix, i, total, s, e, name_fmt,
                      title=titles[i - 1] if titles else None)
        for i, (s, e) in enumerate(zip(boundaries[:-1], boundaries[1:]), 1)
    ]
    nc = max(max(len(n) for n in names), 8)
    sep = "─" * (2 + pad + 2 + 12 + 2 + 12 + 2 + 12 + 2 + nc)
    print(f"\n{sep}")
    print(f"  {'#':>{pad}}  {'Start':>12}  {'End':>12}  {'Duration':>12}  {'Filename':<{nc}}")
    print(sep)
    for i, ((s, e), name) in enumerate(zip(zip(boundaries[:-1], boundaries[1:]), names), 1):
        print(f"  {i:>{pad}}  {fmt(s):>12}  {fmt(e):>12}  {fmt(e - s):>12}  {name}")
    print(sep)
    print(f"  Total: {total} segment(s)\n")


def confirm(prompt="Proceed with splitting? [y/n]: "):
    while True:
        answer = input(prompt).strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False


# ─── Splitting ────────────────────────────────────────────────────────────────

def split_file(file_path, boundaries, output_dir, stem, name_fmt, titles=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file_path).suffix
    total = len(boundaries) - 1

    print(f"Writing {total} file(s) to {output_dir}/\n")

    for i, (start, end) in enumerate(zip(boundaries[:-1], boundaries[1:]), 1):
        title    = titles[i - 1] if titles else None
        filename = make_filename(stem, suffix, i, total, start, end, name_fmt, title=title)
        out = output_dir / filename
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
  time        Split at a fixed interval; --split-at controls where exactly to cut (default)
  chapters    Smart chapter detection: reads embedded metadata first, then adaptive silence
  transcript  Whisper transcription + AI detects spoken chapter/section titles

split-at options (for --mode time):
  exact       Cut at the precise interval time
  silence     Cut at the nearest silence within the window (default)
  sentence    Cut at the nearest sentence end — requires Whisper
  paragraph   Cut at the nearest paragraph end — requires Whisper

filename patterns (--name):
  index       podcast_001.mp3  (default)
  time        podcast_00h00m00s-00h30m00s.mp3
  part        podcast_part_01_of_05.mp3
  chapter     podcast_chapter_01.mp3

examples:
  python split-audio.py podcast.mp3 --mode time --interval 30:00
  python split-audio.py lecture.mp3 --mode time --interval 1:00:00 --split-at sentence
  python split-audio.py audiobook.m4b --mode chapters
  python split-audio.py audiobook.mp3 --mode chapters --lang pt
  python split-audio.py audiobook.mp3 --mode transcript --lang pt
  python split-audio.py audiobook.mp3 --mode transcript --ai-provider openai --lang pt
  python split-audio.py interview.mp4 --mode time --interval 45:00 --split-at exact -o ./parts
""",
    )

    parser.add_argument("file", help="Input audio or video file")
    parser.add_argument(
        "--mode", choices=["chapters", "time", "transcript"], default="time",
        help="Split strategy: time | chapters | transcript (default: time)",
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

    # ── transcript mode ──
    g_tr = parser.add_argument_group("transcript mode (AI-powered)")
    g_tr.add_argument(
        "--ai-provider", choices=["anthropic", "openai"], metavar="PROVIDER",
        help="AI provider: anthropic (Claude) | openai (GPT). "
             "Auto-detected from ANTHROPIC_API_KEY / OPENAI_API_KEY env vars.",
    )
    g_tr.add_argument(
        "--api-key", metavar="KEY",
        help="API key for the chosen AI provider "
             "(or set ANTHROPIC_API_KEY / OPENAI_API_KEY env var)",
    )
    g_tr.add_argument(
        "--ai-model", metavar="MODEL",
        help="Override the AI model "
             "(default: claude-haiku-4-5-20251001 for Anthropic, gpt-4o-mini for OpenAI)",
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
        "--title", metavar="NAME",
        help="Custom base name for output files (e.g. 'My Podcast')",
    )
    g_shared.add_argument(
        "--url", metavar="URL",
        help="Fetch the base name from a video URL (YouTube, TikTok, etc.) via yt-dlp",
    )
    g_shared.add_argument(
        "--prefix", metavar="NAME",
        help="Alias for --title (kept for compatibility)",
    )
    g_shared.add_argument(
        "--name", choices=["index", "time", "part", "chapter"], default="index",
        metavar="PATTERN",
        help="Filename pattern: index (001), time (01h00m00s-01h30m00s), part (part_01_of_N), chapter (chapter_01) (default: index)",
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

    # Stem priority: --title > --url > --prefix > filename stem
    if args.title:
        stem = sanitize_filename(args.title)
    elif args.url:
        stem = fetch_video_title(args.url)
    else:
        stem = args.prefix or file_path.stem

    print(f"Input   : {file_path}")
    print(f"Stem    : {stem}")
    duration = get_duration(file_path)
    print(f"Duration: {fmt(duration)}")

    if args.mode == "chapters":
        boundaries, titles = build_chapter_boundaries(file_path, duration, args)
    elif args.mode == "transcript":
        boundaries, titles = build_transcript_boundaries(file_path, duration, args)
    else:
        if not args.interval:
            print("Error: --interval is required for --mode time.", file=sys.stderr)
            sys.exit(1)
        boundaries = build_time_boundaries(file_path, duration, args)
        titles = None

    preview(boundaries, stem, file_path.suffix, args.name, titles=titles)

    if not args.yes and not confirm():
        print("Cancelled.")
        sys.exit(0)

    split_file(file_path, boundaries, output_dir, stem, args.name, titles=titles)


if __name__ == "__main__":
    main()
