# translate-book.py — Design Spec

**Date:** 2026-05-01  
**Status:** Approved

---

## Overview

`translate-book.py` is a CLI script that translates books between languages with full context awareness: consistent character/place names throughout, preserved narrative style and tone, and automatic resume on interruption.

Supported input formats: PDF, EPUB, MOBI, HTML, TXT  
Supported output formats: EPUB, PDF, TXT, HTML, DOCX

---

## CLI Interface

```
python translate-book.py <arquivo> -t <idioma_destino> [opções]
```

| Argument | Description |
|---|---|
| `arquivo` | Input file (PDF, EPUB, MOBI, HTML, TXT) |
| `-t, --to LANG` | Target language (e.g. `pt-BR`, `es`, `fr`, `ja`) |
| `--from LANG` | Source language (default: auto-detected) |
| `--api {claude,openai}` | API to use (default: `claude`) |
| `--model MODEL` | Specific model (default: `claude-opus-4-7` / `gpt-4o`) |
| `-f, --format FORMAT` | Output format: `epub`, `pdf`, `txt`, `html`, `docx` (default: same as input; MOBI input defaults to `epub` since MOBI output is not supported) |
| `-o, --output DIR` | Output directory (default: `<name>_traduzido/`) |
| `--glossary FILE` | JSON with proper name overrides/additions |
| `--context TEXT` | Additional book context (genre, tone, etc.) |
| `--chunk-size N` | Chunk size in words (default: 800) |
| `--overlap N` | Sliding window overlap in words (default: 150) |
| `--no-cache` | Disable cache, always restart from scratch |

API keys are read from `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` environment variables.

---

## Pre-Processing Pipeline

Runs once before any translation. Results are cached in `<output_dir>/book_context.json` and `<output_dir>/glossary.json`.

### 1. Structured Text Extraction

Each input format is read by a dedicated extractor that preserves chapter structure, producing a list of `{"title": str, "text": str}` dicts:

- **EPUB** — `ebooklib`: reads chapters as separate spine items
- **PDF** — `pypdf`: detects chapter breaks by headings/patterns
- **MOBI** — converted to EPUB via Calibre `ebook-convert`; falls back to `mobi` library if Calibre is unavailable
- **HTML** — `BeautifulSoup`: splits on `<h1>`/`<h2>` tags
- **TXT** — direct read; detects chapters by all-caps lines or `Chapter N` patterns

### 2. Book Context Inference

One API call with the first ~500 words of the book returns:

```json
{
  "genre": "mystery novel",
  "tone": "dark, tense",
  "audience": "adult",
  "source_lang": "en",
  "style_notes": "first-person narrator, short sentences"
}
```

If `--context` is provided, its value is appended to the inferred context. The `langdetect` library confirms the detected source language locally before the API call.

### 3. Glossary Extraction

One API call with the first 2–3 chapters extracts all proper names (characters, places, organizations) with suggested translations for the target language. The user reviews and confirms the glossary interactively via `prompt_ui` (editable in both terminal and web-ui modes).

If `--glossary FILE` is provided, values from the JSON file take precedence over auto-extracted suggestions.

The final glossary is saved to `<output_dir>/glossary.json` and reused on resume.

---

## Translation Pipeline

### Chunking

Each chapter is split into chunks of `--chunk-size` words (default: 800), always breaking at paragraph boundaries — never mid-sentence. Chunk IDs follow the pattern `cap{N}_chunk{M}`.

### Cache

- Each translated chunk is saved immediately to `<output_dir>/.cache/<chunk_id>.txt`
- On resume, chunks with existing cache files are skipped without any API call
- Cache is invalidated if glossary or book context changes (a hash is stored in `<output_dir>/.cache/cache_meta.json`)
- `--no-cache` bypasses all cache logic

### Sliding Window

Each chunk's translation prompt includes, in order:

1. **Book context** — genre, tone, style notes (inferred + `--context`)
2. **Glossary** — all proper names with their fixed translations
3. **Overlap** — the last `--overlap` words of the previous chunk, already translated (ensures stylistic continuity across chunk boundaries)
4. **Translation instruction** — explicit rules: keep glossary names, preserve narrative style, do not add or omit content

### Progress Display

Progress is shown grouped by chapter:

```
  Capítulo 1 — A Tempestade [12 chunks]
    ✓ 1  ✓ 2 (cache)  ⟳ 3...  ✓ 4  ...
  Capítulo 1 — concluído em 1m23s

  Capítulo 2 — O Encontro [9 chunks]
    ⟳ 1...
```

After each chapter: tokens consumed and cumulative estimated cost.

### Error Handling

- Rate limit / network errors: exponential backoff, 3 retries
- Persistent failure on a chunk: pauses and asks the user via `prompt_ui` to skip, retry, or cancel

---

## Output Generation

After all chunks are translated, the script assembles the final file from cache. Dedicated generator per format:

| Format | Library | Notes |
|---|---|---|
| `TXT` | built-in | Chapter separators `── Capítulo N ──` |
| `HTML` | built-in | Styled page with per-chapter sections (same style as `ocr-pdf.py`) |
| `EPUB` | `ebooklib` | One spine item per chapter; original metadata (title, author, cover) preserved |
| `DOCX` | `python-docx` | Chapter titles as `Heading 1` |
| `PDF` | `reportlab` | Same approach as `ocr-pdf.py` |

**EPUB/MOBI → EPUB special case:** when both input and output are EPUB, translation is applied to the internal HTML using BeautifulSoup, preserving formatting tags (bold, italic, footnotes) rather than working from plain text.

### Output Directory Layout

```
<output_dir>/
  <name>_<lang>.<ext>      ← translated book
  glossary.json            ← glossary used (reusable for sequels)
  book_context.json        ← inferred + user context
  .cache/
    cap1_chunk1.txt
    cap1_chunk2.txt
    ...
    cache_meta.json
```

After a successful run, the script asks via `prompt_ui`: "Deseja apagar o cache?" — useful to free disk space.

---

## Module Structure

Single file `translate-book.py`, following the project convention. Internal sections:

```python
# ── Dependency checks ────────────
# ── Format extractors ────────────  extract_epub(), extract_pdf(), extract_mobi(), extract_html(), extract_txt()
# ── Pre-processing ───────────────  infer_context(), extract_glossary(), confirm_glossary()
# ── API client ───────────────────  translate_chunk()  — Claude or OpenAI
# ── Cache ────────────────────────  cache_get(), cache_put(), cache_valid()
# ── Output generators ────────────  gen_epub(), gen_txt(), gen_html(), gen_docx(), gen_pdf()
# ── Progress ─────────────────────  progress_chapter()
# ── Main ─────────────────────────  main()
```

Imports `prompt_ui` (already in the project) for all interactive prompts — compatible with both terminal and `web-ui.py`.

---

## New Dependencies

To add to `requirements.txt`:

| Package | Purpose |
|---|---|
| `mobi` | Direct MOBI reading as fallback when Calibre is unavailable |
| `langdetect` | Local source language detection |

Already present and reused: `anthropic`, `openai`, `ebooklib`, `python-docx`, `pypdf`, `reportlab`, `beautifulsoup4`

---

## web-ui.py Integration

Works automatically — `prompt_ui`-based prompts (glossary confirmation, cache deletion) are already compatible with the web UI. The `input` positional arg and `-o`/`--output` will render with the file browser in the web UI.
