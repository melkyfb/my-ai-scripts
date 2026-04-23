# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Collection of small, focused utility scripts in various languages. Each script solves one task and is usable directly from the terminal.

## Scripts

### `pdf-from-images.py`
Requires: `pip install Pillow`

```
python pdf-from-images.py <path> <reps> [-o output.pdf]
```

- `path` — single image file or folder (scans non-recursively, sorted alphabetically)
- `reps` — comma-separated integers controlling repetition:
  - `31` + 1 image → 31 identical pages
  - `2` + N images → whole sequence cycled 2 times
  - `2,3` + 2 images → img1×2 then img2×3
  - `2,3` + 4 images → cyclic pattern applied across images (user prompted to confirm)
- Always shows a preview and asks for confirmation before writing; user can change reps or output path interactively.

### `transcribe.py`
Requires: `pip install openai-whisper` + system `ffmpeg`
Optional API mode: `pip install openai`

```
python transcribe.py <file> [--srt] [--lang pt] [--model medium] [-o output]
python transcribe.py <file> --api [--api-key sk-...]   # uses OpenAI Whisper API
```

- Supports: mp3, mp4, mov, ogg, wav, m4a, webm, mkv
- Cleans audio before transcribing: noise reduction (`afftdn`) + loudness normalization (`loudnorm`) via ffmpeg
- Always outputs a `.txt` file with the full transcription
- `--srt` generates a `.srt` subtitle file with timestamps
- `--lang` forces a language; omit for auto-detection
- `--model` selects Whisper model size: tiny/base/small/medium/large (default: medium)
- `--no-clean` skips the ffmpeg preprocessing step
- `--api` / `--api-key` uses OpenAI's hosted Whisper API instead of local model; key also read from `OPENAI_API_KEY` env var

## Planned scripts

- **Image generation** — generate images from a terminal prompt (via API, e.g. OpenAI/Stability)
- **PDF tools** — reduce a PDF to plain text for AI ingestion
- **Web tools** — given a URL, extract a sitemap or scrape content for an AI knowledge base
- **Git wrapper** — simplified/aliased git commands to reduce friction in daily use

## Conventions

- Each script is self-contained and runnable from the terminal
- Scripts that require API keys or external dependencies document them at the top of the file
- Python scripts use `argparse`; shell scripts use positional args + `getopts`
- Name scripts descriptively: `pdf-from-images.py`, `site-scraper.py`, `git-wrap.sh`
