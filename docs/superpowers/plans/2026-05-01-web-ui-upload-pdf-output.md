# web-ui File Upload + pdf-from-images Output Prompt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add browser file/folder upload to web-ui.py and prompt interactively for output filename in pdf-from-images.py when -o is not given.

**Architecture:** Two independent changes. (1) pdf-from-images.py: a single `text()` call inserted in `main()` after the default output is computed but before image discovery. (2) web-ui.py: a new `/upload` Flask endpoint stores uploaded files under `uploads/<uuid>/`, and the frontend gains upload buttons next to file-like (non-output) arguments.

**Tech Stack:** Python 3.12, Flask, prompt_ui (existing), pytest, PIL (existing)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `pdf-from-images.py` | Modify `main()` | Prompt for output path when `-o` absent |
| `web-ui.py` | Add `/upload` endpoint; modify `HTML_TEMPLATE` JS | Upload storage; upload button UI |
| `tests/test_pdf_output_prompt.py` | Create | Tests for output prompt behavior |
| `tests/test_web_ui_upload.py` | Create | Tests for `/upload` endpoint |

---

## Task 1: pdf-from-images.py — output prompt (TDD)

**Files:**
- Modify: `pdf-from-images.py` (lines 136–148 in `main()`)
- Create: `tests/test_pdf_output_prompt.py`

- [ ] **Step 1: Create tests directory and write failing tests**

Create `tests/__init__.py` (empty) and `tests/test_pdf_output_prompt.py`:

```python
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image


def load_script():
    spec = importlib.util.spec_from_file_location(
        "pdf_from_images",
        Path(__file__).parent.parent / "pdf-from-images.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_image(path):
    Image.new("RGB", (1, 1)).save(path)


def test_output_prompt_called_when_no_flag(tmp_path):
    """main() must call text() for output path when -o is not given."""
    img = tmp_path / "photo.jpg"
    make_image(img)

    mod = load_script()
    text_calls = []

    def fake_text(prompt, default="", placeholder=""):
        text_calls.append({"prompt": prompt, "default": str(default)})
        return str(default)  # accept suggested name

    def fake_choice(prompt, options, allow_back=False):
        return 3  # Quit — avoids writing a real PDF

    with patch.object(mod, "text", fake_text), \
         patch.object(mod, "choice", fake_choice), \
         patch("sys.argv", ["pdf-from-images.py", str(img), "1"]):
        with pytest.raises(SystemExit):
            mod.main()

    assert any("Output" in c["prompt"] for c in text_calls), \
        "Expected text() called with output path prompt"
    assert any(c["default"].endswith(".pdf") for c in text_calls), \
        "Expected default output to end with .pdf"


def test_output_prompt_skipped_with_flag(tmp_path):
    """main() must NOT call text() for output path when -o is given."""
    img = tmp_path / "photo.jpg"
    make_image(img)
    out = tmp_path / "custom.pdf"

    mod = load_script()
    text_calls = []

    def fake_text(prompt, default="", placeholder=""):
        text_calls.append({"prompt": prompt})
        return str(default)

    def fake_choice(prompt, options, allow_back=False):
        return 3  # Quit

    with patch.object(mod, "text", fake_text), \
         patch.object(mod, "choice", fake_choice), \
         patch("sys.argv", ["pdf-from-images.py", str(img), "1", "-o", str(out)]):
        with pytest.raises(SystemExit):
            mod.main()

    output_prompts = [c for c in text_calls if "Output" in c.get("prompt", "")]
    assert len(output_prompts) == 0, \
        "Expected text() NOT called for output path when -o is given"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /home/melkyfb/scripts && venv/bin/python -m pytest tests/test_pdf_output_prompt.py -v
```

Expected: both tests FAIL because `main()` does not yet call `text()` for output.

- [ ] **Step 3: Implement the output prompt in main()**

In `pdf-from-images.py`, locate `main()`. Find these lines (around line 147–150):

```python
    path = Path(args.path)
    output = Path(args.output) if args.output else default_output(path)
    if output.suffix.lower() != ".pdf":
        output = output.with_suffix(".pdf")

    images = find_images(path)
```

Replace with:

```python
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
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd /home/melkyfb/scripts && venv/bin/python -m pytest tests/test_pdf_output_prompt.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add pdf-from-images.py tests/__init__.py tests/test_pdf_output_prompt.py
git commit -m "feat: prompt for output path in pdf-from-images when -o not given"
```

---

## Task 2: /upload endpoint (backend, TDD)

**Files:**
- Modify: `web-ui.py` (after the `/install` route, before `if __name__ == '__main__'`)
- Create: `tests/test_web_ui_upload.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_web_ui_upload.py`:

```python
import importlib.util
import io
import json
import os
from pathlib import Path

import pytest


def load_app():
    spec = importlib.util.spec_from_file_location(
        "web_ui",
        Path(__file__).parent.parent / "web-ui.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = load_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_upload_single_file(client, tmp_path):
    data = {"files": (io.BytesIO(b"fake image bytes"), "photo.jpg")}
    res = client.post("/upload", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    body = json.loads(res.data)
    assert "path" in body
    assert os.path.isfile(body["path"])
    assert body["path"].endswith("photo.jpg")


def test_upload_multiple_files_as_folder(client, tmp_path):
    data = {
        "files": [
            (io.BytesIO(b"img1"), "myfolder/img1.jpg"),
            (io.BytesIO(b"img2"), "myfolder/img2.jpg"),
        ]
    }
    res = client.post("/upload", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    body = json.loads(res.data)
    assert "path" in body
    assert os.path.isdir(body["path"])
    assert os.path.isfile(os.path.join(body["path"], "img1.jpg"))
    assert os.path.isfile(os.path.join(body["path"], "img2.jpg"))


def test_upload_no_files_returns_400(client):
    res = client.post("/upload", data={}, content_type="multipart/form-data")
    assert res.status_code == 400
    body = json.loads(res.data)
    assert "error" in body
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /home/melkyfb/scripts && venv/bin/python -m pytest tests/test_web_ui_upload.py -v
```

Expected: all three tests FAIL with 404 (route doesn't exist yet).

- [ ] **Step 3: Implement the /upload endpoint**

In `web-ui.py`, add this route after the `/install` route (around line 1590, before `if __name__ == '__main__':`):

```python
@app.route('/upload', methods=['POST'])
def upload_file():
    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        return jsonify({'error': 'Nenhum arquivo enviado.'}), 400

    uid = uuid.uuid4().hex
    upload_dir = os.path.join('uploads', uid)

    if len(files) == 1:
        f = files[0]
        os.makedirs(upload_dir, exist_ok=True)
        dest = os.path.join(upload_dir, os.path.basename(f.filename))
        f.save(dest)
        return jsonify({'path': os.path.abspath(dest)})

    # Multiple files — folder upload (webkitdirectory sends relative paths)
    os.makedirs(upload_dir, exist_ok=True)
    top_folder = None
    for f in files:
        rel = f.filename.replace('\\', '/')
        dest = os.path.join(upload_dir, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        f.save(dest)
        if top_folder is None and '/' in rel:
            top_folder = rel.split('/')[0]

    folder_path = os.path.join(upload_dir, top_folder) if top_folder else upload_dir
    return jsonify({'path': os.path.abspath(folder_path)})
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd /home/melkyfb/scripts && venv/bin/python -m pytest tests/test_web_ui_upload.py -v
```

Expected: all three tests PASS.

- [ ] **Step 5: Commit**

```bash
git add web-ui.py tests/test_web_ui_upload.py
git commit -m "feat: add /upload endpoint to web-ui for file and folder uploads"
```

---

## Task 3: Frontend upload UI

**Files:**
- Modify: `web-ui.py` — `HTML_TEMPLATE` (JavaScript section inside `{% raw %}...{% endraw %}`)

The changes are all inside `<script>` in `HTML_TEMPLATE`. There are four parts: (a) new helper `isOutputLike`, (b) new functions `triggerUpload` and `handleUpload`, (c) updated `buildForm` to add upload buttons, (d) hidden file inputs in the generated HTML.

- [ ] **Step 1: Add isOutputLike helper after the isFileLike function**

In `HTML_TEMPLATE`, locate this function (around line 840):

```javascript
    function isFileLike(arg) {
        const nameLower = arg.name.toLowerCase();
        const flagsLower = arg.flags.map(f => f.toLowerCase());
        return ['file', 'path', 'dir', 'output'].some(k => nameLower.includes(k))
            || flagsLower.some(f => ['-o', '--output', '--dir', '--file'].includes(f));
    }
```

Add `isOutputLike` immediately after it:

```javascript
    function isOutputLike(arg) {
        const nameLower = arg.name.toLowerCase();
        const flagsLower = (arg.flags || []).map(f => f.toLowerCase());
        return nameLower === 'output'
            || flagsLower.includes('-o')
            || flagsLower.includes('--output');
    }
```

- [ ] **Step 2: Add triggerUpload and handleUpload functions**

Add these two functions after `isOutputLike`, before `buildForm`:

```javascript
    function triggerUpload(inputId, isDir) {
        const el = document.getElementById((isDir ? 'uf-dir-' : 'uf-file-') + inputId);
        if (el) el.click();
    }

    async function handleUpload(inputId, isDir) {
        const el = document.getElementById((isDir ? 'uf-dir-' : 'uf-file-') + inputId);
        if (!el || !el.files.length) return;

        const fd = new FormData();
        for (const f of el.files) {
            fd.append('files', f, f.webkitRelativePath || f.name);
        }

        const textInput = document.getElementById(inputId);
        const prev = textInput.value;
        textInput.value = 'Enviando...';
        textInput.disabled = true;

        try {
            const res = await fetch('/upload', { method: 'POST', body: fd });
            const data = await res.json();
            if (data.error) {
                alert('Erro no upload: ' + data.error);
                textInput.value = prev;
            } else {
                textInput.value = data.path;
            }
        } catch (e) {
            alert('Erro de rede: ' + e);
            textInput.value = prev;
        } finally {
            textInput.disabled = false;
            el.value = '';
        }
    }
```

- [ ] **Step 3: Update buildForm to add upload buttons**

In `buildForm`, locate the `else if (isFile)` branch (around line 888):

```javascript
                } else if (isFile) {
                    const ph = arg.default || (isPos ? `Caminho para ${arg.name}...` : 'Caminho...');
                    html += `<div class="input-row">
                        <input type="text" id="${id}" placeholder="${ph}" data-flag="${arg.flags[0] || ''}" data-pos="${isPos}">
                        <button class="btn btn-ghost btn-sm" type="button" onclick="openFsModal('${id}')">📁</button>
                    </div>`;
```

Replace with:

```javascript
                } else if (isFile) {
                    const ph = arg.default || (isPos ? `Caminho para ${arg.name}...` : 'Caminho...');
                    const isOut = isOutputLike(arg);
                    const uploadBtns = isOut ? '' : `
                        <button class="btn btn-ghost btn-sm" type="button" onclick="triggerUpload('${id}', false)" title="Enviar arquivo">⬆ arq</button>
                        <button class="btn btn-ghost btn-sm" type="button" onclick="triggerUpload('${id}', true)" title="Enviar pasta">📂 pasta</button>
                        <input type="file" id="uf-file-${id}" style="display:none" onchange="handleUpload('${id}', false)">
                        <input type="file" id="uf-dir-${id}" style="display:none" webkitdirectory multiple onchange="handleUpload('${id}', true)">`;
                    html += `<div class="input-row">
                        <input type="text" id="${id}" placeholder="${ph}" data-flag="${arg.flags[0] || ''}" data-pos="${isPos}">
                        <button class="btn btn-ghost btn-sm" type="button" onclick="openFsModal('${id}')">📁</button>
                        ${uploadBtns}
                    </div>`;
```

- [ ] **Step 4: Manual test — verify upload buttons appear**

Run the web-ui:
```bash
cd /home/melkyfb/scripts && venv/bin/python web-ui.py
```

Open `http://127.0.0.1:5000` in the browser and select `pdf-from-images.py`. Verify:
- The `path` field shows `[📁] [⬆ arq] [📂 pasta]` buttons
- The `-o output` field shows only `[📁]` (no upload buttons — it's output-like)

- [ ] **Step 5: Manual test — single file upload**

Click `⬆ arq` on the `path` field. Select any image file from your machine. Verify:
- Field briefly shows "Enviando..."
- Field then shows an absolute server path like `/home/.../uploads/<uuid>/photo.jpg`

- [ ] **Step 6: Manual test — folder upload**

Click `📂 pasta` on the `path` field. Select a folder containing images. Verify:
- Field shows an absolute path to the uploaded folder on the server

- [ ] **Step 7: Commit**

```bash
git add web-ui.py
git commit -m "feat: add upload buttons to file-like fields in web-ui"
```

---

## Task 4: Run full test suite

- [ ] **Step 1: Run all tests**

```bash
cd /home/melkyfb/scripts && venv/bin/python -m pytest tests/ -v
```

Expected output:
```
tests/test_pdf_output_prompt.py::test_output_prompt_called_when_no_flag PASSED
tests/test_pdf_output_prompt.py::test_output_prompt_skipped_with_flag PASSED
tests/test_web_ui_upload.py::test_upload_single_file PASSED
tests/test_web_ui_upload.py::test_upload_multiple_files_as_folder PASSED
tests/test_web_ui_upload.py::test_upload_no_files_returns_400 PASSED

5 passed
```

- [ ] **Step 2: Commit if any fixes were needed; otherwise done**
