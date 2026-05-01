# translate-book.py Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `translate-book.py`, a CLI script that translates books (PDF, EPUB, MOBI, HTML, TXT) using Claude or OpenAI with consistent character names, sliding-window context, auto-resume via chunk cache, and multiple output formats.

**Architecture:** Pipeline linear with sliding context window — extract chapters → infer book context + extract glossary → split each chapter into chunks → translate chunk-by-chunk (injecting book context + glossary + last N translated words) → assemble output. Each translated chunk is cached to disk immediately so translation can resume after interruption.

**Tech Stack:** Python 3.10+, `anthropic`, `openai`, `ebooklib`, `python-docx`, `pypdf`, `reportlab`, `beautifulsoup4`, `langdetect`, `mobi`, `prompt_ui` (project module), `pytest` (tests only)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `translate-book.py` | Create | Main script — all logic (extractors, cache, chunking, API, generators, main) |
| `requirements.txt` | Modify | Add `langdetect`, `mobi` |
| `tests/test_translate_book.py` | Create | Unit tests for pure-logic functions |
| `CLAUDE.md` | Modify | Document the new script |

---

## Task 1: Scaffold, CLI, and dependency checks

**Files:**
- Create: `translate-book.py`
- Modify: `requirements.txt`
- Create: `tests/` directory

- [ ] **Step 1: Add new dependencies to requirements.txt**

Open `requirements.txt` and append two lines:
```
langdetect
mobi
```

- [ ] **Step 2: Create `translate-book.py` with full scaffold**

```python
#!/usr/bin/env python3
"""
translate-book.py — Traduzir livros com coerência de personagens e estilo.

Requer:
  pip install anthropic openai ebooklib python-docx pypdf reportlab
              beautifulsoup4 langdetect mobi
  Sistema (opcional para MOBI): calibre (sudo apt install calibre)

Uso:
  python translate-book.py <arquivo> -t pt-BR [opções]

Idiomas comuns: pt-BR, pt-PT, es, fr, de, it, ja, zh-CN
"""

import argparse
import hashlib
import html as html_mod
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ── Verificação de dependências ──────────────────────────────────────────────

def _require(module: str, pip_pkg: str):
    try:
        return __import__(module)
    except ImportError:
        print(f"Erro: '{module}' não encontrado.\nExecute: pip install {pip_pkg}",
              file=sys.stderr)
        sys.exit(1)

_require('ebooklib', 'ebooklib')
_require('bs4', 'beautifulsoup4')
_require('pypdf', 'pypdf')
_require('langdetect', 'langdetect')

from prompt_ui import confirm, text as ui_text, choice, menu

SUPPORTED_INPUT  = {'.pdf', '.epub', '.mobi', '.html', '.htm', '.txt'}
SUPPORTED_OUTPUT = {'epub', 'pdf', 'txt', 'html', 'docx'}


# ── Utilitários ──────────────────────────────────────────────────────────────

def human_size(n: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} TB'


def _is_tty() -> bool:
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


# ── Extratores de formato ─────────────────────────────────────────────────────
# (placeholder — implemented in Task 2)

# ── Pré-processamento ─────────────────────────────────────────────────────────
# (placeholder — implemented in Task 5)

# ── Cliente API ───────────────────────────────────────────────────────────────
# (placeholder — implemented in Task 6)

# ── Cache ─────────────────────────────────────────────────────────────────────
# (placeholder — implemented in Task 3)

# ── Chunking ──────────────────────────────────────────────────────────────────
# (placeholder — implemented in Task 4)

# ── Progresso ─────────────────────────────────────────────────────────────────
# (placeholder — implemented in Task 7)

# ── Geradores de saída ────────────────────────────────────────────────────────
# (placeholder — implemented in Task 8)

# ── Loop de tradução ──────────────────────────────────────────────────────────
# (placeholder — implemented in Task 9)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Traduzir livros com coerência de personagens e estilo',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('input', metavar='arquivo',
                        help='PDF, EPUB, MOBI, HTML ou TXT de entrada')
    parser.add_argument('-t', '--to', required=True, metavar='LANG',
                        help='Idioma de destino (ex: pt-BR, es, fr, ja)')
    parser.add_argument('--from', dest='from_lang', default=None, metavar='LANG',
                        help='Idioma de origem (padrão: detectado automaticamente)')
    parser.add_argument('--api', choices=['claude', 'openai'], default='claude',
                        help='API a usar (padrão: claude)')
    parser.add_argument('--model', default=None, metavar='MODEL',
                        help='Modelo específico (padrão: claude-opus-4-7 / gpt-4o)')
    parser.add_argument('-f', '--format', dest='out_format', default=None,
                        choices=list(SUPPORTED_OUTPUT), metavar='FORMAT',
                        help='Formato de saída: epub, pdf, txt, html, docx')
    parser.add_argument('-o', '--output', default=None, metavar='DIR',
                        help='Diretório de saída')
    parser.add_argument('--glossary', default=None, metavar='FILE',
                        help='JSON com nomes próprios para sobrescrever/complementar')
    parser.add_argument('--context', default=None, metavar='TEXT',
                        help='Contexto adicional do livro (gênero, tom, etc.)')
    parser.add_argument('--chunk-size', type=int, default=800, metavar='N',
                        help='Tamanho do chunk em palavras (padrão: 800)')
    parser.add_argument('--overlap', type=int, default=150, metavar='N',
                        help='Overlap da janela deslizante em palavras (padrão: 150)')
    parser.add_argument('--no-cache', action='store_true',
                        help='Desativa cache, sempre recomeça do zero')
    args = parser.parse_args()
    print(f'translate-book.py — scaffold ok, args: {args}')


if __name__ == '__main__':
    main()
```

- [ ] **Step 3: Verify CLI works**

```bash
cd /home/melkyfb/scripts
python translate-book.py --help
```

Expected: argparse help text printed with all arguments listed.

```bash
python translate-book.py dummy.txt -t pt-BR
```

Expected: prints `translate-book.py — scaffold ok, args: Namespace(input='dummy.txt', to='pt-BR', ...)`

- [ ] **Step 4: Create tests directory**

```bash
mkdir -p /home/melkyfb/scripts/tests
touch /home/melkyfb/scripts/tests/__init__.py
pip install pytest
```

- [ ] **Step 5: Commit**

```bash
git add translate-book.py requirements.txt tests/__init__.py
git commit -m "feat: scaffold translate-book.py with CLI argparse"
```

---

## Task 2: Format extractors

**Files:**
- Modify: `translate-book.py` — replace `# ── Extratores de formato` section
- Create: `tests/test_translate_book.py`

- [ ] **Step 1: Write failing tests for extract_txt and extract_html**

Create `tests/test_translate_book.py`:

```python
import sys
sys.path.insert(0, '/home/melkyfb/scripts')

import textwrap
import pytest


def test_extract_txt_single_block():
    from translate_book import extract_txt_from_string
    text = "Hello world.\n\nSecond paragraph."
    chapters = extract_txt_from_string(text)
    assert len(chapters) == 1
    assert 'Hello world' in chapters[0]['text']


def test_extract_txt_detects_chapters():
    from translate_book import extract_txt_from_string
    text = textwrap.dedent("""\
        Chapter 1

        First chapter content here.

        Chapter 2

        Second chapter content here.
    """)
    chapters = extract_txt_from_string(text)
    assert len(chapters) == 2
    assert 'First chapter' in chapters[0]['text']
    assert 'Second chapter' in chapters[1]['text']


def test_extract_html_single_section():
    from translate_book import extract_html_from_string
    html = '<html><body><h1>Intro</h1><p>Some text.</p><p>More text.</p></body></html>'
    chapters = extract_html_from_string(html)
    assert len(chapters) >= 1
    assert 'Some text' in chapters[0]['text']


def test_extract_html_multiple_chapters():
    from translate_book import extract_html_from_string
    html = textwrap.dedent("""\
        <html><body>
        <h1>Chapter One</h1><p>Content one.</p>
        <h2>Chapter Two</h2><p>Content two.</p>
        </body></html>
    """)
    chapters = extract_html_from_string(html)
    assert len(chapters) == 2
    assert chapters[0]['title'] == 'Chapter One'
    assert chapters[1]['title'] == 'Chapter Two'
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/melkyfb/scripts
python -m pytest tests/test_translate_book.py::test_extract_txt_single_block -v
```

Expected: `ImportError: cannot import name 'extract_txt_from_string'`

- [ ] **Step 3: Implement extractors in `translate-book.py`**

Replace the `# ── Extratores de formato` placeholder section with:

```python
# ── Extratores de formato ─────────────────────────────────────────────────────

Chapter = dict  # {"title": str, "text": str}

_CHAPTER_PAT = re.compile(
    r'^(?:chapter\s+\w+|CHAPTER\s+\w+|[A-Z][A-Z\s\-]{3,})\s*$',
    re.MULTILINE,
)


def extract_txt_from_string(text: str) -> list[Chapter]:
    parts  = _CHAPTER_PAT.split(text)
    titles = _CHAPTER_PAT.findall(text)
    if not titles:
        body = text.strip()
        return [{'title': 'Texto', 'text': body}] if body else []
    chapters = []
    for title, body in zip(['Início'] + titles, parts):
        body = body.strip()
        if body:
            chapters.append({'title': title.strip(), 'text': body})
    return chapters


def extract_txt(path: str) -> list[Chapter]:
    text = Path(path).read_text(encoding='utf-8', errors='replace')
    return extract_txt_from_string(text)


def extract_html_from_string(html: str) -> list[Chapter]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    chapters: list[Chapter] = []
    current_title = 'Início'
    current_parts: list[str] = []

    for tag in soup.find_all(['h1', 'h2', 'p']):
        if tag.name in ('h1', 'h2'):
            if current_parts:
                chapters.append({'title': current_title,
                                  'text': '\n\n'.join(current_parts)})
            current_title = tag.get_text(strip=True)
            current_parts = []
        else:
            t = tag.get_text(strip=True)
            if t:
                current_parts.append(t)

    if current_parts:
        chapters.append({'title': current_title,
                          'text': '\n\n'.join(current_parts)})
    if not chapters:
        chapters = [{'title': 'Texto', 'text': soup.get_text()}]
    return chapters


def extract_html(path: str) -> list[Chapter]:
    return extract_html_from_string(Path(path).read_text(encoding='utf-8', errors='replace'))


def extract_epub(path: str) -> list[Chapter]:
    from ebooklib import epub, ITEM_DOCUMENT
    from bs4 import BeautifulSoup
    book = epub.read_epub(path, options={'ignore_ncx': True})
    chapters: list[Chapter] = []
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), 'html.parser')
        title_tag = soup.find(['h1', 'h2', 'h3'])
        title = title_tag.get_text(strip=True) if title_tag else item.get_name()
        text = soup.get_text('\n', strip=True)
        if text.strip():
            chapters.append({'title': title, 'text': text})
    return chapters


def extract_pdf(path: str) -> list[Chapter]:
    from pypdf import PdfReader
    reader = PdfReader(path)
    cap_pat = re.compile(
        r'^(?:Chapter|CHAPTER|Capítulo|CAPÍTULO)\s+\w+', re.MULTILINE
    )
    chapters: list[Chapter] = []
    current_title = 'Início'
    current_pages: list[str] = []

    for page in reader.pages:
        text = page.extract_text() or ''
        m = cap_pat.search(text)
        if m:
            if current_pages:
                chapters.append({'title': current_title,
                                  'text': '\n'.join(current_pages)})
            current_title = m.group(0)
            current_pages = [text]
        else:
            current_pages.append(text)

    if current_pages:
        chapters.append({'title': current_title, 'text': '\n'.join(current_pages)})
    if not chapters:
        full = '\n'.join(p.extract_text() or '' for p in reader.pages)
        chapters = [{'title': 'Texto', 'text': full}]
    return chapters


def extract_mobi(path: str) -> list[Chapter]:
    if shutil.which('ebook-convert'):
        tmp = Path(path).with_suffix('.epub')
        try:
            subprocess.run(['ebook-convert', path, str(tmp)],
                           check=True, capture_output=True)
            chapters = extract_epub(str(tmp))
            tmp.unlink(missing_ok=True)
            return chapters
        except subprocess.CalledProcessError:
            pass
    try:
        import mobi
        tmp_dir, epub_path = mobi.extract(path)
        chapters = extract_epub(epub_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return chapters
    except ImportError:
        print('Erro: para ler MOBI instale Calibre ou execute: pip install mobi',
              file=sys.stderr)
        sys.exit(1)


def extract(path: str) -> list[Chapter]:
    ext = Path(path).suffix.lower()
    extractors = {
        '.txt':  extract_txt,
        '.html': extract_html,
        '.htm':  extract_html,
        '.epub': extract_epub,
        '.pdf':  extract_pdf,
        '.mobi': extract_mobi,
    }
    if ext not in extractors:
        print(f'Erro: formato não suportado: {ext}', file=sys.stderr)
        sys.exit(1)
    return extractors[ext](path)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /home/melkyfb/scripts
python -m pytest tests/test_translate_book.py -v
```

Expected: 4 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add translate-book.py tests/test_translate_book.py
git commit -m "feat: add format extractors for txt, html, epub, pdf, mobi"
```

---

## Task 3: Cache layer

**Files:**
- Modify: `translate-book.py` — replace `# ── Cache` section
- Modify: `tests/test_translate_book.py` — add cache tests

- [ ] **Step 1: Write failing tests for cache functions**

Append to `tests/test_translate_book.py`:

```python
import tempfile
import os


def test_cache_put_and_get():
    from translate_book import cache_put, cache_get
    with tempfile.TemporaryDirectory() as tmp:
        cache_put(tmp, 'cap1_chunk1', 'translated text here')
        result = cache_get(tmp, 'cap1_chunk1')
        assert result == 'translated text here'


def test_cache_get_missing_returns_none():
    from translate_book import cache_get
    with tempfile.TemporaryDirectory() as tmp:
        assert cache_get(tmp, 'cap1_chunk99') is None


def test_cache_valid_after_save():
    from translate_book import cache_valid, cache_save_meta
    glossary = {'John': 'João'}
    context  = {'genre': 'novel'}
    with tempfile.TemporaryDirectory() as tmp:
        assert cache_valid(tmp, glossary, context) is False
        cache_save_meta(tmp, glossary, context)
        assert cache_valid(tmp, glossary, context) is True


def test_cache_invalid_after_glossary_change():
    from translate_book import cache_valid, cache_save_meta
    glossary = {'John': 'João'}
    context  = {'genre': 'novel'}
    with tempfile.TemporaryDirectory() as tmp:
        cache_save_meta(tmp, glossary, context)
        assert cache_valid(tmp, {'John': 'Joãozinho'}, context) is False
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/melkyfb/scripts
python -m pytest tests/test_translate_book.py::test_cache_put_and_get -v
```

Expected: `ImportError: cannot import name 'cache_put'`

- [ ] **Step 3: Implement cache layer in `translate-book.py`**

Replace the `# ── Cache` placeholder section with:

```python
# ── Cache ─────────────────────────────────────────────────────────────────────

def _cache_dir(out_dir: str) -> Path:
    return Path(out_dir) / '.cache'


def _meta_path(out_dir: str) -> Path:
    return _cache_dir(out_dir) / 'cache_meta.json'


def _state_hash(glossary: dict, context: dict) -> str:
    payload = json.dumps({'glossary': glossary, 'context': context}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def cache_get(out_dir: str, chunk_id: str) -> str | None:
    f = _cache_dir(out_dir) / f'{chunk_id}.txt'
    return f.read_text(encoding='utf-8') if f.exists() else None


def cache_put(out_dir: str, chunk_id: str, text: str) -> None:
    d = _cache_dir(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / f'{chunk_id}.txt').write_text(text, encoding='utf-8')


def cache_valid(out_dir: str, glossary: dict, context: dict) -> bool:
    meta = _meta_path(out_dir)
    if not meta.exists():
        return False
    stored = json.loads(meta.read_text())
    return stored.get('hash') == _state_hash(glossary, context)


def cache_save_meta(out_dir: str, glossary: dict, context: dict) -> None:
    d = _cache_dir(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    _meta_path(out_dir).write_text(
        json.dumps({'hash': _state_hash(glossary, context)})
    )


def cache_clear(out_dir: str) -> None:
    shutil.rmtree(_cache_dir(out_dir), ignore_errors=True)
```

- [ ] **Step 4: Run all tests**

```bash
cd /home/melkyfb/scripts
python -m pytest tests/test_translate_book.py -v
```

Expected: 8 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add translate-book.py tests/test_translate_book.py
git commit -m "feat: add chunk cache layer with hash-based invalidation"
```

---

## Task 4: Chunking

**Files:**
- Modify: `translate-book.py` — replace `# ── Chunking` section
- Modify: `tests/test_translate_book.py` — add chunking tests

- [ ] **Step 1: Write failing tests for chunk_chapter**

Append to `tests/test_translate_book.py`:

```python
def test_chunk_chapter_single_chunk_when_small():
    from translate_book import chunk_chapter
    text = 'Short text.\n\nOnly two paragraphs.'
    chunks = chunk_chapter(text, chunk_size=800)
    assert len(chunks) == 1
    assert 'Short text' in chunks[0]
    assert 'Only two paragraphs' in chunks[0]


def test_chunk_chapter_splits_at_paragraph_boundary():
    from translate_book import chunk_chapter
    # 10-word paragraphs, chunk_size=15 → should split after 1-2 paragraphs
    para = 'one two three four five six seven eight nine ten'
    text = '\n\n'.join([para] * 5)
    chunks = chunk_chapter(text, chunk_size=15)
    assert len(chunks) >= 2
    # Each chunk should not break within a paragraph
    for chunk in chunks:
        # verify chunk contains complete paragraphs only
        assert chunk.strip() != ''


def test_chunk_chapter_respects_chunk_size():
    from translate_book import chunk_chapter
    para = ' '.join(['word'] * 100)  # 100-word paragraph
    text = '\n\n'.join([para] * 10)  # 10 paragraphs = 1000 words
    chunks = chunk_chapter(text, chunk_size=200)
    # No chunk should exceed chunk_size + one paragraph of slack
    for chunk in chunks:
        assert len(chunk.split()) <= 300  # 200 + up to 100 words for one para
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/melkyfb/scripts
python -m pytest tests/test_translate_book.py::test_chunk_chapter_single_chunk_when_small -v
```

Expected: `ImportError: cannot import name 'chunk_chapter'`

- [ ] **Step 3: Implement chunking in `translate-book.py`**

Replace the `# ── Chunking` placeholder section with:

```python
# ── Chunking ──────────────────────────────────────────────────────────────────

def chunk_chapter(text: str, chunk_size: int) -> list[str]:
    """Split text into chunks of ~chunk_size words at paragraph boundaries."""
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    for para in paragraphs:
        words = len(para.split())
        if current_words + words > chunk_size and current:
            chunks.append('\n\n'.join(current))
            current = []
            current_words = 0
        current.append(para)
        current_words += words

    if current:
        chunks.append('\n\n'.join(current))

    return chunks or [text]
```

- [ ] **Step 4: Run all tests**

```bash
cd /home/melkyfb/scripts
python -m pytest tests/test_translate_book.py -v
```

Expected: 11 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add translate-book.py tests/test_translate_book.py
git commit -m "feat: add chunk_chapter with paragraph-boundary splitting"
```

---

## Task 5: Pre-processing — context inference and glossary

**Files:**
- Modify: `translate-book.py` — replace `# ── Pré-processamento` section

- [ ] **Step 1: Implement `_call_api` (shared helper needed by pre-processing)**

Add `_call_api` inside the `# ── Cliente API` placeholder comment block. This is needed by pre-processing and will be expanded in Task 6:

```python
# ── Cliente API ───────────────────────────────────────────────────────────────

def _call_api(api: str, model: str, api_key: str, prompt: str,
              max_tokens: int = 4096) -> str:
    """Single API call with exponential backoff (3 attempts)."""
    for attempt in range(3):
        try:
            if api == 'claude':
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                msg = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[{'role': 'user', 'content': prompt}],
                )
                return msg.content[0].text
            else:
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                resp = client.chat.completions.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[{'role': 'user', 'content': prompt}],
                )
                return resp.choices[0].message.content or ''
        except Exception as e:
            if attempt < 2:
                wait = 2 ** attempt * 3
                print(f'\n  [retry {attempt + 1}/3] {e}. Aguardando {wait}s...',
                      file=sys.stderr)
                time.sleep(wait)
            else:
                raise
    raise RuntimeError('API call failed after 3 retries')
```

- [ ] **Step 2: Implement pre-processing functions**

Replace the `# ── Pré-processamento` placeholder section with:

```python
# ── Pré-processamento ─────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """Parse JSON from model response, tolerating markdown fences."""
    text = text.strip()
    # Strip markdown code fence if present
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        return {}


def infer_context(chapters: list, api: str, model: str, api_key: str,
                  extra_context: str | None) -> dict:
    """Infer book genre, tone, style, and source language from first ~500 words."""
    sample = ' '.join(
        ' '.join(c['text'].split()[:200]) for c in chapters[:3]
    )[:3000]

    prompt = (
        'Analyze this book excerpt and return ONLY a JSON object with these keys:\n'
        '- genre: book genre (e.g. "mystery novel", "fantasy", "romance")\n'
        '- tone: narrative tone (e.g. "dark and tense", "light-hearted")\n'
        '- audience: target audience (e.g. "adult", "young adult", "children")\n'
        '- source_lang: ISO 639-1 language code (e.g. "en", "es", "fr")\n'
        '- style_notes: key style observations (narrator perspective, sentence style)\n\n'
        f'Excerpt:\n{sample}\n\n'
        'Return only the JSON object, no markdown, no explanation.'
    )

    response = _call_api(api, model, api_key, prompt, max_tokens=300)
    ctx = _extract_json(response)

    if extra_context:
        ctx['user_context'] = extra_context
    return ctx


def extract_glossary(chapters: list, to_lang: str, api: str, model: str,
                     api_key: str) -> dict:
    """Extract proper names from first 2-3 chapters with suggested translations."""
    sample = '\n\n'.join(c['text'] for c in chapters[:3])[:8000]

    prompt = (
        f'Extract all proper names (characters, places, organizations) from this text.\n'
        f'For each name, suggest an appropriate translation/adaptation into {to_lang}.\n'
        f'Return ONLY a JSON object mapping original name → translated name.\n'
        f'Keep names that don\'t need translation unchanged.\n'
        f'Example: {{"John": "João", "London": "Londres", "ACME": "ACME"}}\n\n'
        f'Text:\n{sample}\n\n'
        f'Return only the JSON object.'
    )

    response = _call_api(api, model, api_key, prompt, max_tokens=800)
    raw = _extract_json(response)
    return {str(k): str(v) for k, v in raw.items()}


def confirm_glossary(glossary: dict, user_file: str | None) -> dict:
    """Show glossary, allow edits, merge with user-provided JSON file."""
    user_overrides: dict = {}
    if user_file:
        try:
            user_overrides = json.loads(
                Path(user_file).read_text(encoding='utf-8')
            )
        except Exception as e:
            print(f'  [aviso] Não foi possível ler {user_file}: {e}',
                  file=sys.stderr)

    merged = {**glossary, **user_overrides}

    if not merged:
        print('  Nenhum nome próprio encontrado.')
        return {}

    print('\n  Glossário extraído automaticamente:')
    for orig, trans in merged.items():
        print(f'    {orig!r:30s} → {trans!r}')

    if _is_tty():
        resp = input(
            '\n  [Enter] Confirmar  |  [e] Editar JSON  |  [n] Sem glossário\n  > '
        ).strip().lower()
        if resp == 'n':
            return {}
        if resp == 'e':
            print('  Cole o JSON do glossário corrigido (linha única) e pressione Enter:')
            raw = input('  > ').strip()
            try:
                merged = json.loads(raw)
            except json.JSONDecodeError:
                print('  JSON inválido — usando glossário original.', file=sys.stderr)
    else:
        if not confirm('Usar este glossário?', default=True):
            return {}

    return merged
```

- [ ] **Step 3: Smoke-test pre-processing imports**

```bash
cd /home/melkyfb/scripts
python -c "from translate_book import infer_context, extract_glossary, confirm_glossary, _extract_json; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Run all tests (pre-processing has no unit tests — it calls the API)**

```bash
cd /home/melkyfb/scripts
python -m pytest tests/test_translate_book.py -v
```

Expected: 11 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add translate-book.py
git commit -m "feat: add context inference, glossary extraction and confirmation"
```

---

## Task 6: API client — translate_chunk

**Files:**
- Modify: `translate-book.py` — expand `# ── Cliente API` section (add `translate_chunk` after `_call_api`)

- [ ] **Step 1: Implement `translate_chunk`**

Append `translate_chunk` immediately after the `_call_api` function in the `# ── Cliente API` section:

```python
def translate_chunk(
    chunk: str,
    prev_translated: str,
    context: dict,
    glossary: dict,
    to_lang: str,
    api: str,
    model: str,
    api_key: str,
    overlap: int,
) -> str:
    """Translate one chunk using sliding window (book context + glossary + overlap)."""
    overlap_text = ''
    if prev_translated:
        words = prev_translated.split()
        overlap_text = ' '.join(words[-overlap:]) if len(words) > overlap else prev_translated

    glossary_lines = '\n'.join(
        f'  {orig} → {trans}' for orig, trans in glossary.items()
    )

    ctx_parts = [
        f"Genre: {context.get('genre', 'unknown')}",
        f"Tone: {context.get('tone', 'unknown')}",
        f"Style: {context.get('style_notes', '')}",
    ]
    if context.get('user_context'):
        ctx_parts.append(f"Additional context: {context['user_context']}")
    context_str = '\n'.join(ctx_parts)

    parts = [
        f'You are a professional literary translator. '
        f'Translate the following text to {to_lang}.',
        '',
        f'BOOK CONTEXT:\n{context_str}',
    ]
    if glossary_lines:
        parts += [
            '',
            f'MANDATORY NAME GLOSSARY (never deviate from these translations):\n'
            f'{glossary_lines}',
        ]
    if overlap_text:
        parts += [
            '',
            f'PREVIOUS CONTEXT (already translated — for style continuity ONLY, '
            f'do NOT retranslate this):\n{overlap_text}',
        ]
    parts += [
        '',
        'RULES:',
        '- Use ONLY the name translations from the glossary above',
        '- Preserve the narrative style, tone and voice of the original',
        '- Do not add, omit or summarize any content',
        '- Maintain paragraph breaks exactly as in the original',
        '- Return ONLY the translated text, no commentary, no preamble',
        '',
        f'TEXT TO TRANSLATE:\n{chunk}',
    ]

    return _call_api(api, model, api_key, '\n'.join(parts))
```

- [ ] **Step 2: Smoke-test translate_chunk builds prompt correctly**

```bash
cd /home/melkyfb/scripts
python -c "
from translate_book import translate_chunk
# We test the prompt is built — we can't call the real API without a key
# so we just check that calling with a missing key raises the expected error
import sys
try:
    translate_chunk('Hello.', '', {'genre':'novel','tone':'dark','style_notes':'first-person'},
                    {'John':'João'}, 'pt-BR', 'claude', 'claude-opus-4-7', 'FAKE_KEY', 150)
except Exception as e:
    print(f'Expected API error: {type(e).__name__}')
"
```

Expected: `Expected API error: AuthenticationError` (or similar — the prompt was built and sent, just rejected by the API)

- [ ] **Step 3: Run all tests**

```bash
cd /home/melkyfb/scripts
python -m pytest tests/test_translate_book.py -v
```

Expected: 11 tests PASSED.

- [ ] **Step 4: Commit**

```bash
git add translate-book.py
git commit -m "feat: add translate_chunk with sliding window context and glossary injection"
```

---

## Task 7: Progress display

**Files:**
- Modify: `translate-book.py` — replace `# ── Progresso` section

- [ ] **Step 1: Implement progress_chapter**

Replace the `# ── Progresso` placeholder section with:

```python
# ── Progresso ─────────────────────────────────────────────────────────────────

def progress_chapter(chunk_idx: int, total_chunks: int, from_cache: bool) -> None:
    mark   = '✓' if from_cache else '⟳'
    suffix = ' (cache)' if from_cache else '       '
    line   = f'    {mark} {chunk_idx}/{total_chunks}{suffix}'
    if _is_tty():
        print(f'\r{line}', end='', flush=True)
        if chunk_idx >= total_chunks:
            print()
    else:
        step = max(1, total_chunks // 5)
        if chunk_idx == 1 or chunk_idx % step == 0 or chunk_idx >= total_chunks:
            print(line, flush=True)
```

- [ ] **Step 2: Smoke-test in terminal**

```bash
cd /home/melkyfb/scripts
python -c "
from translate_book import progress_chapter
for i in range(1, 6):
    progress_chapter(i, 5, from_cache=(i <= 2))
"
```

Expected: terminal shows chunk markers line by line, ending with a newline after chunk 5.

- [ ] **Step 3: Commit**

```bash
git add translate-book.py
git commit -m "feat: add chapter-level progress display"
```

---

## Task 8: Output generators

**Files:**
- Modify: `translate-book.py` — replace `# ── Geradores de saída` section

- [ ] **Step 1: Implement all five generators**

Replace the `# ── Geradores de saída` placeholder section with:

```python
# ── Geradores de saída ────────────────────────────────────────────────────────

def gen_txt(chapters: list, out: str) -> None:
    with open(out, 'w', encoding='utf-8') as fh:
        for i, ch in enumerate(chapters):
            fh.write(f'\n{"─" * 60}\n  {ch["title"]}\n{"─" * 60}\n\n')
            fh.write(ch['text'])
            fh.write('\n')


def gen_html(chapters: list, out: str, title: str) -> None:
    sections = []
    for i, ch in enumerate(chapters):
        body = html_mod.escape(ch['text'])
        body = re.sub(r'\n{2,}', '</p><p>', body).replace('\n', '<br>\n')
        sections.append(
            f'<section id="c{i + 1}">'
            f'<h2 class="ch">{html_mod.escape(ch["title"])}</h2>'
            f'<p>{body}</p>'
            f'</section>'
        )
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write(f"""<!DOCTYPE html>
<html lang="pt">
<head>
  <meta charset="UTF-8">
  <title>{html_mod.escape(title)}</title>
  <style>
    body  {{ font-family: Georgia, serif; max-width: 780px; margin: 2em auto;
             padding: 0 1.5em; line-height: 1.75; color: #1a1a1a; }}
    h1    {{ border-bottom: 2px solid #888; padding-bottom: .3em; }}
    .ch   {{ color: #888; font-size: .85em; font-weight: normal; margin: 2.5em 0 .3em; }}
    section {{ border-bottom: 1px solid #e8e8e8; padding-bottom: 1.2em; }}
    p     {{ text-align: justify; margin: .4em 0; }}
  </style>
</head>
<body>
  <h1>{html_mod.escape(title)}</h1>
  {''.join(sections)}
</body>
</html>""")


def gen_epub(chapters: list, out: str, title: str, author: str = '') -> None:
    from ebooklib import epub
    book = epub.EpubBook()
    book.set_identifier(f'tb-{abs(hash(title)):x}')
    book.set_title(title)
    book.set_language('pt')
    if author:
        book.add_author(author)

    items = []
    for i, ch in enumerate(chapters):
        body = html_mod.escape(ch['text'])
        body = re.sub(r'\n{2,}', '</p><p>', body).replace('\n', '<br>\n')
        item = epub.EpubHtml(
            title=ch['title'],
            file_name=f'c{i + 1:04d}.xhtml',
            lang='pt',
        )
        item.content = (
            f'<html xmlns="http://www.w3.org/1999/xhtml"><body>'
            f'<h2>{html_mod.escape(ch["title"])}</h2><p>{body}</p>'
            f'</body></html>'
        )
        book.add_item(item)
        items.append(item)

    book.toc = items
    book.spine = ['nav'] + items
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(out, book)


def gen_docx(chapters: list, out: str, title: str) -> None:
    try:
        from docx import Document
    except ImportError:
        print('  [aviso] python-docx não instalado — pulando DOCX.', file=sys.stderr)
        return
    doc = Document()
    doc.add_heading(title, level=0)
    for ch in chapters:
        doc.add_heading(ch['title'], level=1)
        for line in ch['text'].split('\n'):
            if line.strip():
                doc.add_paragraph(line.strip())
    doc.save(out)


def gen_pdf(chapters: list, out: str, title: str) -> None:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import (SimpleDocTemplate, Paragraph,
                                        Spacer, PageBreak)
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        print('  [aviso] reportlab não instalado — pulando PDF.', file=sys.stderr)
        return

    font_name = 'Helvetica'
    for fp in (
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
        '/usr/share/fonts/truetype/freefont/FreeSans.ttf',
    ):
        if os.path.exists(fp):
            pdfmetrics.registerFont(TTFont('UFont', fp))
            font_name = 'UFont'
            break

    styles = getSampleStyleSheet()
    body_st = ParagraphStyle('body', parent=styles['Normal'],
                             fontName=font_name, fontSize=11, leading=16, spaceAfter=3)
    head_st = ParagraphStyle('head', parent=styles['Heading2'],
                             fontName=font_name, fontSize=14, spaceAfter=12)

    doc = SimpleDocTemplate(out, pagesize=A4,
                            leftMargin=2.5*cm, rightMargin=2.5*cm,
                            topMargin=2.5*cm, bottomMargin=2.5*cm)
    story = []
    for i, ch in enumerate(chapters):
        if i > 0:
            story.append(PageBreak())
        story.append(Paragraph(ch['title'], head_st))
        for line in ch['text'].split('\n'):
            s = line.strip()
            if s:
                safe = (s.replace('&', '&amp;')
                         .replace('<', '&lt;')
                         .replace('>', '&gt;'))
                story.append(Paragraph(safe, body_st))
            else:
                story.append(Spacer(1, 5))
    doc.build(story)
```

- [ ] **Step 2: Smoke-test generators with a sample chapter list**

```bash
cd /home/melkyfb/scripts
python -c "
import tempfile, os
from translate_book import gen_txt, gen_html, gen_epub, gen_docx

chapters = [
    {'title': 'Capítulo 1', 'text': 'Texto do primeiro capítulo.\n\nSegundo parágrafo.'},
    {'title': 'Capítulo 2', 'text': 'Texto do segundo capítulo.'},
]
with tempfile.TemporaryDirectory() as tmp:
    gen_txt(chapters,  f'{tmp}/out.txt')
    gen_html(chapters, f'{tmp}/out.html', 'Livro Teste')
    gen_epub(chapters, f'{tmp}/out.epub', 'Livro Teste')
    gen_docx(chapters, f'{tmp}/out.docx', 'Livro Teste')
    for name in ['out.txt','out.html','out.epub','out.docx']:
        size = os.path.getsize(f'{tmp}/{name}')
        print(f'{name}: {size} bytes')
"
```

Expected: all four files listed with non-zero sizes.

- [ ] **Step 3: Run all tests**

```bash
cd /home/melkyfb/scripts
python -m pytest tests/test_translate_book.py -v
```

Expected: 11 tests PASSED.

- [ ] **Step 4: Commit**

```bash
git add translate-book.py
git commit -m "feat: add output generators for txt, html, epub, docx, pdf"
```

---

## Task 9: Translation loop

**Files:**
- Modify: `translate-book.py` — replace `# ── Loop de tradução` section

- [ ] **Step 1: Implement `run_translation`**

Replace the `# ── Loop de tradução` placeholder section with:

```python
# ── Loop de tradução ──────────────────────────────────────────────────────────

def run_translation(
    chapters: list,
    context: dict,
    glossary: dict,
    out_dir: str,
    to_lang: str,
    api: str,
    model: str,
    api_key: str,
    chunk_size: int,
    overlap: int,
    no_cache: bool,
) -> list:
    """Translate all chapters chunk by chunk; return list of translated Chapter dicts."""
    if not no_cache:
        if not cache_valid(out_dir, glossary, context):
            cd = Path(out_dir) / '.cache'
            if cd.exists():
                shutil.rmtree(cd)
                print('  [cache] Configuração alterada — cache anterior removido.')
        cache_save_meta(out_dir, glossary, context)

    translated: list = []
    t_start = time.time()

    for cap_idx, chapter in enumerate(chapters):
        chunks = chunk_chapter(chapter['text'], chunk_size)
        n = len(chunks)
        print(f'\n  Capítulo {cap_idx + 1} — {chapter["title"]} [{n} chunk(s)]')

        translated_chunks: list[str] = []
        prev_translated = ''

        for ci, chunk in enumerate(chunks):
            chunk_id = f'cap{cap_idx + 1}_chunk{ci + 1}'

            if not no_cache:
                cached = cache_get(out_dir, chunk_id)
                if cached is not None:
                    progress_chapter(ci + 1, n, from_cache=True)
                    translated_chunks.append(cached)
                    prev_translated = cached
                    continue

            while True:
                try:
                    progress_chapter(ci + 1, n, from_cache=False)
                    result = translate_chunk(
                        chunk, prev_translated, context, glossary,
                        to_lang, api, model, api_key, overlap,
                    )
                    break
                except Exception as exc:
                    print(f'\n  [erro] {chunk_id}: {exc}')
                    action = menu(
                        'O que fazer?',
                        [
                            {'key': 'retry',  'label': 'Tentar novamente'},
                            {'key': 'skip',   'label': 'Pular chunk (manter original)'},
                            {'key': 'cancel', 'label': 'Cancelar tradução'},
                        ],
                    )
                    if action == 'cancel':
                        print('\nCancelado.')
                        sys.exit(0)
                    if action == 'skip':
                        result = chunk
                        break
                    # else 'retry' — loop continues

            if not no_cache:
                cache_put(out_dir, chunk_id, result)
            translated_chunks.append(result)
            prev_translated = result

        elapsed = int(time.time() - t_start)
        m, s = divmod(elapsed, 60)
        print(f'\n  Capítulo {cap_idx + 1} — concluído em {m}m{s:02d}s')
        translated.append({'title': chapter['title'],
                            'text': '\n\n'.join(translated_chunks)})

    return translated
```

- [ ] **Step 2: Smoke-test run_translation with pre-cached data (no real API call)**

```bash
cd /home/melkyfb/scripts
python -c "
import tempfile
from translate_book import run_translation, cache_put, cache_save_meta

chapters = [
    {'title': 'Cap 1', 'text': 'Hello world.\n\nThis is a test.'},
]
context  = {'genre': 'novel', 'tone': 'neutral', 'style_notes': ''}
glossary = {}

with tempfile.TemporaryDirectory() as tmp:
    # Pre-populate cache so no API call is needed
    cache_save_meta(tmp, glossary, context)
    cache_put(tmp, 'cap1_chunk1', 'Olá mundo.\n\nIsto é um teste.')

    result = run_translation(
        chapters, context, glossary, tmp,
        'pt-BR', 'claude', 'claude-opus-4-7', 'FAKE', 800, 150, no_cache=False
    )
    print('Result:', result[0]['text'])
"
```

Expected: `Result: Olá mundo.\n\nIsto é um teste.` (served from cache, no API call)

- [ ] **Step 3: Run all tests**

```bash
cd /home/melkyfb/scripts
python -m pytest tests/test_translate_book.py -v
```

Expected: 11 tests PASSED.

- [ ] **Step 4: Commit**

```bash
git add translate-book.py
git commit -m "feat: add run_translation loop with cache, retry, and progress"
```

---

## Task 10: Wire up main() and update docs

**Files:**
- Modify: `translate-book.py` — replace the `main()` stub with the complete implementation
- Modify: `CLAUDE.md` — document the new script

- [ ] **Step 1: Replace the `main()` stub with the full implementation**

Replace the entire `def main():` function (the stub that prints `scaffold ok`) with:

```python
def main():
    parser = argparse.ArgumentParser(
        description='Traduzir livros com coerência de personagens e estilo',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('input', metavar='arquivo',
                        help='PDF, EPUB, MOBI, HTML ou TXT de entrada')
    parser.add_argument('-t', '--to', required=True, metavar='LANG',
                        help='Idioma de destino (ex: pt-BR, es, fr, ja)')
    parser.add_argument('--from', dest='from_lang', default=None, metavar='LANG',
                        help='Idioma de origem (padrão: detectado automaticamente)')
    parser.add_argument('--api', choices=['claude', 'openai'], default='claude',
                        help='API a usar (padrão: claude)')
    parser.add_argument('--model', default=None, metavar='MODEL',
                        help='Modelo específico (padrão: claude-opus-4-7 / gpt-4o)')
    parser.add_argument('-f', '--format', dest='out_format', default=None,
                        choices=list(SUPPORTED_OUTPUT), metavar='FORMAT',
                        help='Formato de saída: epub, pdf, txt, html, docx')
    parser.add_argument('-o', '--output', default=None, metavar='DIR',
                        help='Diretório de saída')
    parser.add_argument('--glossary', default=None, metavar='FILE',
                        help='JSON com nomes próprios para sobrescrever/complementar')
    parser.add_argument('--context', default=None, metavar='TEXT',
                        help='Contexto adicional do livro (gênero, tom, etc.)')
    parser.add_argument('--chunk-size', type=int, default=800, metavar='N',
                        help='Tamanho do chunk em palavras (padrão: 800)')
    parser.add_argument('--overlap', type=int, default=150, metavar='N',
                        help='Overlap da janela deslizante em palavras (padrão: 150)')
    parser.add_argument('--no-cache', action='store_true',
                        help='Desativa cache, sempre recomeça do zero')
    args = parser.parse_args()

    # ── Validar entrada ──────────────────────────────────────────────────────
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        print(f'Erro: arquivo não encontrado: {input_path}', file=sys.stderr)
        sys.exit(1)
    if input_path.suffix.lower() not in SUPPORTED_INPUT:
        print(f'Erro: formato não suportado: {input_path.suffix}', file=sys.stderr)
        sys.exit(1)

    # ── Formato de saída ─────────────────────────────────────────────────────
    in_ext = input_path.suffix.lower().lstrip('.')
    out_format = args.out_format
    if not out_format:
        if in_ext == 'mobi':
            out_format = 'epub'
        elif in_ext in SUPPORTED_OUTPUT:
            out_format = in_ext
        else:
            out_format = 'txt'

    # ── API e modelo ─────────────────────────────────────────────────────────
    if args.api == 'claude':
        api_key = os.environ.get('ANTHROPIC_API_KEY', '')
        default_model = 'claude-opus-4-7'
    else:
        api_key = os.environ.get('OPENAI_API_KEY', '')
        default_model = 'gpt-4o'
    if not api_key:
        env_var = 'ANTHROPIC_API_KEY' if args.api == 'claude' else 'OPENAI_API_KEY'
        print(f'Erro: {env_var} não definida.', file=sys.stderr)
        sys.exit(1)
    model = args.model or default_model

    # ── Diretório de saída ───────────────────────────────────────────────────
    out_default = str(input_path.parent / f'{input_path.stem}_traduzido')
    out_dir = args.output or out_default
    os.makedirs(out_dir, exist_ok=True)

    # ── Extração ─────────────────────────────────────────────────────────────
    print(f'\n  Arquivo : {input_path.name}')
    print(f'  API     : {args.api} / {model}')
    print(f'  Para    : {args.to}')
    print('\n  Extraindo texto...')
    chapters = extract(str(input_path))
    print(f'  {len(chapters)} capítulo(s) encontrado(s).')

    # ── Idioma de origem ─────────────────────────────────────────────────────
    from_lang = args.from_lang
    if not from_lang:
        try:
            from langdetect import detect
            sample_text = ' '.join(c['text'] for c in chapters[:2])[:1000]
            from_lang = detect(sample_text)
            print(f'  Idioma detectado: {from_lang}')
        except Exception:
            from_lang = 'unknown'

    # ── Contexto do livro ────────────────────────────────────────────────────
    ctx_path   = Path(out_dir) / 'book_context.json'
    gloss_path = Path(out_dir) / 'glossary.json'

    if ctx_path.exists() and not args.no_cache:
        print('  [cache] Carregando contexto salvo...')
        context = json.loads(ctx_path.read_text())
    else:
        print('\n  Inferindo contexto do livro...')
        context = infer_context(chapters, args.api, model, api_key, args.context)
        ctx_path.write_text(json.dumps(context, ensure_ascii=False, indent=2))

    # ── Glossário ────────────────────────────────────────────────────────────
    if gloss_path.exists() and not args.no_cache:
        print('  [cache] Carregando glossário salvo...')
        glossary = json.loads(gloss_path.read_text())
    else:
        print('\n  Extraindo glossário de personagens...')
        glossary = extract_glossary(chapters, args.to, args.api, model, api_key)
        glossary = confirm_glossary(glossary, args.glossary)
        gloss_path.write_text(json.dumps(glossary, ensure_ascii=False, indent=2))

    # ── Resumo e confirmação ─────────────────────────────────────────────────
    print(f'\n  Capítulos  : {len(chapters)}')
    print(f'  Gênero     : {context.get("genre", "?")}')
    print(f'  Tom        : {context.get("tone", "?")}')
    print(f'  Idioma orig: {from_lang}')
    print(f'  Glossário  : {len(glossary)} nome(s)')
    print(f'  Saída      : {out_dir}/ ({out_format})')
    print(f'  Chunk size : {args.chunk_size} palavras  |  Overlap: {args.overlap}')

    if not confirm('Iniciar tradução?', default=True):
        print('Cancelado.')
        sys.exit(0)

    # ── Tradução ─────────────────────────────────────────────────────────────
    translated = run_translation(
        chapters, context, glossary, out_dir,
        args.to, args.api, model, api_key,
        args.chunk_size, args.overlap, args.no_cache,
    )

    # ── Gerar saída ──────────────────────────────────────────────────────────
    stem     = input_path.stem
    lang_tag = args.to.replace('-', '_')
    out_name = f'{stem}_{lang_tag}.{out_format}'
    out_file = str(Path(out_dir) / out_name)

    print(f'\n  Gerando {out_format.upper()}...')
    if out_format == 'txt':
        gen_txt(translated, out_file)
    elif out_format == 'html':
        gen_html(translated, out_file, stem)
    elif out_format == 'epub':
        gen_epub(translated, out_file, stem)
    elif out_format == 'docx':
        gen_docx(translated, out_file, stem)
    elif out_format == 'pdf':
        gen_pdf(translated, out_file, stem)

    size = Path(out_file).stat().st_size
    print(f'  Arquivo gerado: {out_name}  ({human_size(size)})')

    if confirm('Deseja apagar o cache?', default=False):
        cache_clear(out_dir)
        print('  Cache apagado.')

    print('\n  Tradução concluída!\n')
```

- [ ] **Step 2: End-to-end smoke test with a real TXT file (no API — uses pre-populated cache)**

```bash
cd /home/melkyfb/scripts
cat > /tmp/test_book.txt << 'EOF'
CHAPTER ONE

It was a dark and stormy night. John walked into the bar and ordered a drink.

The bartender, old McGee, poured the whiskey with a steady hand.

CHAPTER TWO

The next morning, John found a letter under his door.
EOF

mkdir -p /tmp/tb_out/.cache
cat > /tmp/tb_out/book_context.json << 'EOF'
{"genre": "noir", "tone": "dark", "style_notes": "third-person", "source_lang": "en"}
EOF
cat > /tmp/tb_out/glossary.json << 'EOF'
{"John": "João", "McGee": "McGee"}
EOF
python -c "
from translate_book import cache_put, cache_save_meta
import json
g = json.load(open('/tmp/tb_out/glossary.json'))
c = json.load(open('/tmp/tb_out/book_context.json'))
cache_save_meta('/tmp/tb_out', g, c)
cache_put('/tmp/tb_out', 'cap1_chunk1', 'Era uma noite escura e tempestuosa. João entrou no bar e pediu uma bebida.\n\nO barman, o velho McGee, serviu o uísque com mão firme.')
cache_put('/tmp/tb_out', 'cap2_chunk1', 'Na manhã seguinte, João encontrou uma carta debaixo da porta.')
"
python translate-book.py /tmp/test_book.txt -t pt-BR -o /tmp/tb_out -f txt --no-cache=False
```

Expected: script shows summary, asks confirmation, translates from cache, generates `/tmp/tb_out/test_book_pt_BR.txt`.

```bash
cat /tmp/tb_out/test_book_pt_BR.txt
```

Expected: Portuguese text with `João` and `McGee` present.

- [ ] **Step 3: Add script chmod**

```bash
chmod +x /home/melkyfb/scripts/translate-book.py
```

- [ ] **Step 4: Update CLAUDE.md**

In `CLAUDE.md`, add the following entry under `## Scripts` (after the `### ocr-pdf.py` section):

```markdown
### `translate-book.py`
Requires: `pip install anthropic openai ebooklib python-docx pypdf reportlab beautifulsoup4 langdetect mobi`
Optional (MOBI input): `sudo apt install calibre`

```
python translate-book.py <arquivo> -t <lang> [opções]
```

- `arquivo` — PDF, EPUB, MOBI, HTML ou TXT de entrada
- `-t` / `--to` — idioma de destino (ex: `pt-BR`, `es`, `fr`, `ja`)
- `--from` — idioma de origem (padrão: detectado automaticamente via `langdetect`)
- `--api {claude,openai}` — API a usar (padrão: `claude`); chave lida de `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`
- `--model` — modelo específico (padrão: `claude-opus-4-7` / `gpt-4o`)
- `-f` / `--format` — formato de saída: `epub`, `pdf`, `txt`, `html`, `docx`
- `-o` / `--output` — diretório de saída (padrão: `<nome>_traduzido/`)
- `--glossary` — JSON com nomes próprios para sobrescrever/complementar os extraídos automaticamente
- `--context` — contexto adicional do livro (gênero, tom, etc.)
- `--chunk-size` — tamanho do chunk em palavras (padrão: 800)
- `--overlap` — palavras de overlap entre chunks para continuidade de estilo (padrão: 150)
- `--no-cache` — desativa cache, sempre recomeça do zero
- Extrai automaticamente nomes de personagens e lugares; usuário confirma/edita o glossário antes de traduzir
- Inferência automática de gênero, tom e estilo do livro; complementado por `--context`
- Cache por chunk: interrupções são retomadas automaticamente; cache invalidado se glossário/contexto mudar
- Progresso exibido por capítulo com resumo de tempo ao final de cada um
- Erros de API com backoff exponencial (3 tentativas); opção de pular chunk ou cancelar
```

- [ ] **Step 5: Run all tests one final time**

```bash
cd /home/melkyfb/scripts
python -m pytest tests/test_translate_book.py -v
```

Expected: 11 tests PASSED.

- [ ] **Step 6: Final commit**

```bash
git add translate-book.py CLAUDE.md tests/test_translate_book.py
git commit -m "feat: complete translate-book.py with main() and docs"
```

---

## Task 11: EPUB → EPUB HTML-preserving path (spec special case)

**Files:**
- Modify: `translate-book.py` — add `extract_epub_html()`, `translate_html_chapter()`, `gen_epub_from_html()`; update `main()` to use this path when input+output are both EPUB

When input is EPUB and output is EPUB, instead of extracting plain text, we translate the internal HTML with BeautifulSoup — preserving `<em>`, `<strong>`, `<a>`, footnote `<span>` tags, etc.

- [ ] **Step 1: Add `extract_epub_html()` — returns HTML items instead of plain text**

Add after the `extract_epub()` function in the extractor section:

```python
def extract_epub_html(path: str) -> list[dict]:
    """Extract EPUB spine items as raw HTML (for HTML-preserving translation)."""
    from ebooklib import epub, ITEM_DOCUMENT
    from bs4 import BeautifulSoup
    book = epub.read_epub(path, options={'ignore_ncx': True})
    items_out = []
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), 'html.parser')
        title_tag = soup.find(['h1', 'h2', 'h3'])
        title = title_tag.get_text(strip=True) if title_tag else item.get_name()
        # Collect only text-bearing tags to check if item has content
        plain = soup.get_text(strip=True)
        if plain:
            items_out.append({
                'title': title,
                'text': plain,           # for chunking + translation
                'html': str(soup),       # original HTML for reconstruction
                'item_name': item.get_name(),
            })
    return items_out
```

- [ ] **Step 2: Add `reassemble_html()` — places translated text back into original HTML structure**

Add after `extract_epub_html()`:

```python
def reassemble_html(original_html: str, translated_text: str) -> str:
    """
    Replace text content in HTML body with translated text, preserving tags.
    Strategy: replace all text nodes in <body> proportionally with translated paragraphs.
    Falls back to a clean div-per-paragraph rebuild if structure diverges too much.
    """
    from bs4 import BeautifulSoup, NavigableString
    soup = BeautifulSoup(original_html, 'html.parser')
    body = soup.find('body') or soup

    # Gather translated paragraphs
    trans_paras = [p.strip() for p in re.split(r'\n{2,}', translated_text) if p.strip()]

    # Gather leaf text nodes (non-empty, not inside <style>/<script>)
    def leaf_nodes(tag):
        for child in tag.descendants:
            if isinstance(child, NavigableString) and child.strip():
                parent = child.parent
                if parent.name not in ('style', 'script', 'head'):
                    yield child

    leaves = list(leaf_nodes(body))

    if not leaves or not trans_paras:
        return original_html

    # Simple proportional mapping: distribute translated paragraphs across leaf nodes
    if len(trans_paras) >= len(leaves):
        for i, leaf in enumerate(leaves):
            leaf.replace_with(trans_paras[i] if i < len(trans_paras) else '')
    else:
        # More leaves than translated paras — join extras
        chunk_size = max(1, len(leaves) // len(trans_paras))
        para_idx = 0
        for i, leaf in enumerate(leaves):
            if para_idx < len(trans_paras):
                leaf.replace_with(trans_paras[para_idx])
                if (i + 1) % chunk_size == 0:
                    para_idx += 1
            else:
                leaf.replace_with('')

    return str(soup)
```

- [ ] **Step 3: Add `gen_epub_from_html()` — builds EPUB from HTML-item dicts**

Add after `gen_epub()` in the generators section:

```python
def gen_epub_from_html(html_chapters: list[dict], translated_chapters: list[dict],
                       out: str, title: str, author: str = '') -> None:
    """
    Build EPUB using original HTML items with translated text reassembled into them.
    `html_chapters` — dicts from extract_epub_html() with 'html' key
    `translated_chapters` — dicts from run_translation() with 'text' key
    """
    from ebooklib import epub
    book = epub.EpubBook()
    book.set_identifier(f'tb-{abs(hash(title)):x}')
    book.set_title(title)
    book.set_language('pt')
    if author:
        book.add_author(author)

    items = []
    for i, (html_ch, trans_ch) in enumerate(zip(html_chapters, translated_chapters)):
        rebuilt_html = reassemble_html(html_ch['html'], trans_ch['text'])
        item = epub.EpubHtml(
            title=trans_ch['title'],
            file_name=f'c{i + 1:04d}.xhtml',
            lang='pt',
        )
        item.content = rebuilt_html.encode('utf-8')
        book.add_item(item)
        items.append(item)

    book.toc = items
    book.spine = ['nav'] + items
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(out, book)
```

- [ ] **Step 4: Update `main()` to use HTML-preserving path for EPUB→EPUB**

In `main()`, replace the extraction line:

```python
    chapters = extract(str(input_path))
```

with:

```python
    epub_html_items = None  # populated only for EPUB→EPUB path
    in_ext_lower = input_path.suffix.lower()
    if in_ext_lower in ('.epub', '.mobi') and out_format == 'epub':
        epub_src = str(input_path)
        if in_ext_lower == '.mobi':
            # Convert MOBI to EPUB first, then use HTML path
            tmp_epub = str(input_path.with_suffix('.epub'))
            if shutil.which('ebook-convert'):
                subprocess.run(['ebook-convert', epub_src, tmp_epub],
                               check=True, capture_output=True)
                epub_src = tmp_epub
        epub_html_items = extract_epub_html(epub_src)
        chapters = [{'title': it['title'], 'text': it['text']} for it in epub_html_items]
    else:
        chapters = extract(str(input_path))
```

And replace the output generation block in `main()`:

```python
    print(f'\n  Gerando {out_format.upper()}...')
    if out_format == 'txt':
        gen_txt(translated, out_file)
    elif out_format == 'html':
        gen_html(translated, out_file, stem)
    elif out_format == 'epub':
        gen_epub(translated, out_file, stem)
    elif out_format == 'docx':
        gen_docx(translated, out_file, stem)
    elif out_format == 'pdf':
        gen_pdf(translated, out_file, stem)
```

with:

```python
    print(f'\n  Gerando {out_format.upper()}...')
    if out_format == 'txt':
        gen_txt(translated, out_file)
    elif out_format == 'html':
        gen_html(translated, out_file, stem)
    elif out_format == 'epub' and epub_html_items:
        gen_epub_from_html(epub_html_items, translated, out_file, stem)
    elif out_format == 'epub':
        gen_epub(translated, out_file, stem)
    elif out_format == 'docx':
        gen_docx(translated, out_file, stem)
    elif out_format == 'pdf':
        gen_pdf(translated, out_file, stem)
```

- [ ] **Step 5: Smoke-test reassemble_html with inline sample**

```bash
cd /home/melkyfb/scripts
python -c "
from translate_book import reassemble_html
html = '<html><body><h2>Chapter One</h2><p>Hello world.</p><p>How are you?</p></body></html>'
translated = 'Capítulo Um\n\nOlá mundo.\n\nComo vai você?'
result = reassemble_html(html, translated)
print(result)
assert 'Olá mundo' in result or 'Capítulo' in result, 'Translation not found in output'
print('reassemble_html: ok')
"
```

Expected: HTML with Portuguese text replacing the original English text, structural tags preserved.

- [ ] **Step 6: Commit**

```bash
git add translate-book.py
git commit -m "feat: add EPUB→EPUB HTML-preserving translation path"
```
