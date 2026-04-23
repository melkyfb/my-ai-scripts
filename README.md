# scripts

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

## Planned

- **Image generation** — generate images from a terminal prompt via API (OpenAI/Stability)
- **PDF tools** — extract plain text from a PDF for AI ingestion
- **Web tools** — extract a sitemap or scrape content from a URL for an AI knowledge base
- **Git wrapper** — simplified git aliases to reduce daily friction
