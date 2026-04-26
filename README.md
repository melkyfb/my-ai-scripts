# scripts

## Setup

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

> System dependencies (`ffmpeg`, `ffprobe`) must be installed separately — see each script's section below.

---

Collection of small, focused utility scripts. Each one solves a single task and runs directly from the terminal.

---

## Scripts

### `pdf-from-images.py`

Combine images into a PDF with flexible repetition control.

**Requires:** `pip install Pillow`

```bash
python pdf-from-images.py <path> <reps> [-o output.pdf]
```

| Argument | Description |
|---|---|
| `path` | Single image file or folder (non-recursive, sorted alphabetically) |
| `reps` | Comma-separated integers controlling repetition (see below) |
| `-o` | Output file path (default: `output.pdf`) |

**Repetition logic:**

| Input | Result |
|---|---|
| `31` + 1 image | 31 identical pages |
| `2` + N images | Whole sequence repeated 2 times |
| `2,3` + 2 images | img1 × 2, then img2 × 3 |
| `2,3` + 4 images | Cyclic pattern across images (prompts confirmation) |

Always shows a preview and asks for confirmation before writing. The output path and repetition can be changed interactively.

---

### `transcribe.py`

Transcribe audio or video files to text, with optional SRT subtitle output.

**Requires:**
```bash
pip install openai openai-whisper
sudo apt install ffmpeg
```

```bash
python transcribe.py <file> [options]
```

**Options:**

| Flag | Description |
|---|---|
| `--srt` | Also generate a `.srt` subtitle file with timestamps |
| `--lang CODE` | Force language (e.g. `pt`, `en`, `es`). Auto-detected if omitted |
| `--model SIZE` | Whisper model: `tiny`, `base`, `small`, `medium` (default), `large` |
| `-o, --output` | Output base name without extension (default: same as input file) |
| `--no-clean` | Skip ffmpeg audio preprocessing |
| `--api` | Use OpenAI's hosted Whisper API instead of local model |
| `--api-key KEY` | OpenAI API key (or set `OPENAI_API_KEY` env var) |

**Supported formats:** mp3, mp4, mov, ogg, wav, m4a, webm, mkv

**Examples:**

```bash
# Basic transcription → entrevista.txt
python transcribe.py entrevista.mp3

# Portuguese transcription + subtitles → aula.txt + aula.srt
python transcribe.py aula.mp4 --srt --lang pt

# High accuracy, custom output name
python transcribe.py palestra.mov --model large --output palestra_transcrita --srt

# Via OpenAI API (no local model download needed)
OPENAI_API_KEY=sk-... python transcribe.py audio.wav --api --srt
```

The script cleans the audio before transcribing: converts to 16kHz mono, applies noise reduction (`afftdn`) and loudness normalization (`loudnorm`) via ffmpeg.

---

### `split-audio.py`

Split large audio or video files by auto-detected chapters or fixed time intervals, cutting at natural boundaries.

**Requires:** `ffmpeg` + `ffprobe` (system)
**Optional:** `pip install openai-whisper` (for `--split-at sentence/paragraph`)

```bash
python split-audio.py <file> [options]
```

**Modes:**

| `--mode` | Description |
|---|---|
| `time` (default) | Split at a fixed interval; `--split-at` controls where exactly to cut |
| `chapters` | Auto-detect chapter breaks using silence gaps (no Whisper needed) |

**`--split-at` options (for `--mode time`):**

| Value | Description |
|---|---|
| `silence` (default) | Cut at the nearest silence within the search window |
| `exact` | Cut at the precise interval time |
| `sentence` | Cut at the nearest sentence end — requires Whisper |
| `paragraph` | Cut at the nearest paragraph end — requires Whisper |

**Key options:**

| Flag | Description |
|---|---|
| `--interval TIME` | Split interval: `HH:MM:SS`, `MM:SS`, or seconds (e.g. `30:00`, `3600`) |
| `--window SECS` | Search window around each target time in seconds (default: 30) |
| `--chapter-silence SECS` | Min silence duration to detect as chapter boundary (default: 1.5s) |
| `--min-chapter SECS` | Min chapter duration in seconds (default: 60) |
| `--noise-db DB` | Noise threshold for silence detection in dB (default: -35) |
| `--whisper-model SIZE` | Whisper model: `tiny` / `base` / `small` / `medium` / `large` (default: base) |
| `--lang CODE` | Language hint for Whisper (e.g. `pt`, `en`) |
| `-o DIR` | Output directory (default: same folder as input) |
| `--prefix NAME` | Output filename prefix (default: input filename stem) |
| `-y` | Skip confirmation prompt |

**Examples:**

```bash
# Split every 30 min, cutting at the nearest silence
python split-audio.py podcast.mp3 --mode time --interval 30:00

# Split every hour at the nearest sentence end
python split-audio.py lecture.mp3 --mode time --interval 1:00:00 --split-at sentence --lang pt

# Auto-detect chapters from an audiobook
python split-audio.py audiobook.mp3 --mode chapters --chapter-silence 2.0

# Split exactly every 45 minutes into a specific folder
python split-audio.py interview.mp4 --mode time --interval 45:00 --split-at exact -o ./parts
```

Always shows a preview of all segments with start/end times and asks for confirmation before writing. The last segment always contains the remaining audio. Interval cannot exceed the total audio duration.

---

### `download.py`

Download videos, audio, or images from YouTube, Instagram, TikTok, Facebook, Vimeo and hundreds of other sites.

**Requires:**
```bash
pip install yt-dlp
sudo apt install ffmpeg
```

```bash
python download.py <url> [-o DIR]
```

| Argument | Description |
|---|---|
| `url` | URL to download from |
| `-o, --output` | Output directory (default: current directory) |

**What it does:**

1. Analyzes the URL without downloading — detects title, duration, available formats, and content type
2. Presents a smart interactive menu based on what's available:
   - Audio-focused sites (SoundCloud, YouTube Music) show audio options first
   - Instagram photo posts offer image download
   - Playlists are detected automatically with bulk download options
3. For video: choose quality (resolution + codec + estimated size shown) and audio format
4. For audio only: MP3 192/320kbps, M4A, Opus, WAV, or keep original codec
5. Shows a live progress bar with speed and ETA

**Supported sites:** YouTube, Instagram, TikTok, Facebook, Vimeo, Twitter/X, Twitch, Reddit, SoundCloud, Dailymotion, Rumble, Odysee, Bilibili, and [hundreds more](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md).

**Examples:**

```bash
# Download a YouTube video (interactive menu)
python download.py https://youtube.com/watch?v=...

# Download to a specific folder
python download.py https://www.tiktok.com/@user/video/... -o ~/Downloads

# Download audio from SoundCloud (audio menu shown first)
python download.py https://soundcloud.com/artist/track

# Download an Instagram photo post
python download.py https://www.instagram.com/p/...
```

---

## Planned

- **Image generation** — generate images from a terminal prompt via API (OpenAI/Stability)
- **PDF tools** — extract plain text from a PDF for AI ingestion
- **Web tools** — extract a sitemap or scrape content from a URL for an AI knowledge base
- **Git wrapper** — simplified git aliases to reduce daily friction
