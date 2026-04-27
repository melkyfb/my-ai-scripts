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

### `split-audio.py`
Requires: `ffmpeg` + `ffprobe` (system)
Optional for sentence/paragraph modes: `pip install openai-whisper`

```
python split-audio.py <file> [options]
```

- `--mode chapters` — detect chapter breaks via long silences; no Whisper needed
- `--mode time --interval TIME` — split at fixed intervals (HH:MM:SS / MM:SS / seconds)
- `--split-at silence|exact|sentence|paragraph` — where to cut near each interval boundary
  - `silence` (default): nearest silence within `--window` seconds
  - `exact`: precise time, no adjustment
  - `sentence` / `paragraph`: nearest Whisper-detected sentence or paragraph end
- `--window SECS` — search window around target times (default: 30)
- `--chapter-silence SECS` — min silence for chapter detection (default: 1.5)
- `--noise-db DB` — noise threshold in dB for silence detection (default: -35)
- `--whisper-model SIZE` — Whisper model size (default: base)
- `-o DIR` — output directory (default: same folder as input)
- `-y` — skip confirmation
- Always previews segments and confirms before writing; last segment is always the remainder
- Rejects `--interval` ≥ audio duration

### `download.py`
Requires: `pip install yt-dlp` + system `ffmpeg`

```
python download.py <url> [-o output_dir]
```

- Supports: YouTube, Instagram, TikTok, Facebook, Vimeo, Twitter/X, Twitch, Reddit, SoundCloud, Dailymotion, Rumble, and hundreds more via yt-dlp
- Analyzes the URL first (no download) to detect available formats and content type
- Interactive menu adapts to content: audio-focused sites (SoundCloud, YouTube Music) show audio options first
- Playlist support: detects playlists and offers bulk download
- Image support: detects photo posts (Instagram) and offers image download
- Video quality menu: shows all available resolutions with codec, container and estimated size
- Audio options: MP3 192/320kbps, M4A, Opus, WAV, or keep original codec
- Progress bar with speed and ETA during download

### `comptia-download.py`
Requires: `pip install playwright yt-dlp` + `playwright install chromium`

```
python comptia-download.py <course_url> -u EMAIL [-p PASSWORD] [-o DIR]
```

- `course_url` — URL of the course on certmaster.comptia.org
- `-u` / `--user` — login email
- `-p` / `--password` — password (prompted securely if omitted)
- `-o` — output directory (default: `comptia-course`)
- `--headless` — run without showing the browser window
- `--delay` — seconds between page loads (default: 2.0)
- `--skip-confirm` — skip the outline preview before downloading
- Logs in, navigates to the Outline tab, and discovers all numbered modules (1.0, 1.1, 1.1.1…)
- Shows a preview of all items and asks for confirmation before downloading
- Saves each module as a PDF in a mirrored directory hierarchy:
  `"1.0 Chapter"/"1.1 Section"/"1.1.1 Topic.pdf"`
- Detects embedded videos (HTML5, YouTube, Vimeo, Kaltura, Brightcove) and downloads via yt-dlp;
  video files use the same name as the PDF but with the video extension
- Skips already-downloaded files; safe to re-run after interruption
- Defaults to visible browser (no `--headless`) to allow manual SSO/2FA handling

### `claude-local.py`
Requires: `pip install 'litellm[proxy]'` + Ollama running locally

```
python claude-local.py [-m MODEL] [-c TOKENS] [--port PORT]
```

- `-m` / `--model` — Ollama model to use (default: `deepseek-v3`)
- `-c` / `--context` — context window in tokens (default: 64000)
- `--port` — litellm proxy port (default: 4001)
- Checks that Ollama is running and the model is pulled before starting
- Starts a litellm proxy that translates Anthropic Messages API ↔ Ollama
- All Claude model aliases are mapped to the chosen Ollama model so routing
  works regardless of which default model Claude Code is configured to use
- Proxy shuts down automatically when Claude Code exits

## Planned scripts

- **Image generation** — generate images from a terminal prompt (via API, e.g. OpenAI/Stability)
- **PDF tools** — reduce a PDF to plain text for AI ingestion
- **Web tools** — given a URL, extract a sitemap or scrape content for an AI knowledge base
- **Git wrapper** — simplified/aliased git commands to reduce friction in daily use

## Conventions

- **All scripts must be written in Python** — no shell scripts or other languages
- Each script is self-contained and runnable from the terminal
- Scripts that require API keys or external dependencies document them at the top of the file
- Python scripts use `argparse`
- Name scripts descriptively: `pdf-from-images.py`, `site-scraper.py`, `git-wrap.py`
- All pip dependencies must be listed in `requirements.txt`
