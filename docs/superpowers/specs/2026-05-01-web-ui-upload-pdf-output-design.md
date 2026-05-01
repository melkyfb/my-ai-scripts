# Design: web-ui file upload + pdf-from-images output prompt

Date: 2026-05-01

## Scope

Two independent improvements:

1. `web-ui.py` — add real file/folder upload support alongside the existing filesystem browser.
2. `pdf-from-images.py` — prompt interactively for the output filename when `-o` is not given.

---

## 1. web-ui.py — File/folder upload

### Goal

Users can upload files and folders directly from their browser (e.g., from Windows into WSL2) instead of navigating the server-side filesystem.

### Backend: `/upload` endpoint

- Method: `POST`, multipart form data
- Field name: `files` (one or many)
- Storage: `uploads/<uuid>/` directory relative to the scripts folder
- Single file: saved as `uploads/<uuid>/<filename>`
- Folder (multiple files from `webkitdirectory`): each file's `filename` field carries the relative path (e.g., `myfolder/img.jpg`); saved preserving that structure under `uploads/<uuid>/`. The returned path is the top-level subfolder (`uploads/<uuid>/myfolder/`).
- Returns: `{"path": "<absolute_path>"}` on success, `{"error": "..."}` on failure.
- No automatic cleanup — local tool, manual cleanup acceptable.

### Frontend: upload dropdown button

Applies to all **file-like, non-output** fields. Detection rules:

- **Output-like** (no upload button): flag is `-o` or `--output`, OR arg name equals `output`. These fields keep only the `📁` filesystem browser button.
- **All other file-like fields** (upload button added): `['file', 'path', 'dir', 'output']` in name OR `['-o', '--output', '--dir', '--file']` in flags — but excluding the output-like case above.

UI change: the current `[input text] [📁]` row becomes `[input text] [📁] [⬆ ▾]`.

The `⬆ ▾` button opens a small inline dropdown with two options:
- **Arquivo** — triggers a hidden `<input type="file">` (single file)
- **Pasta** — triggers a hidden `<input type="file" webkitdirectory multiple>`

While uploading, the text field shows `"Enviando..."`. On completion, it is populated with the absolute server path returned by `/upload`.

Hidden file inputs are generated per-field in `buildForm` and referenced by the field's `id`.

### Error handling

- If `/upload` returns an error, show `alert()` with the message and leave the field unchanged.
- Empty file selection (user cancels picker): no-op.

---

## 2. pdf-from-images.py — Interactive output prompt

### Goal

When the user does not pass `-o`, the script prompts for the output filename before entering the main loop, so the output path is always explicit.

### Change

In `main()`, after `parse_args()`, after resolving `path = Path(args.path)`, and after computing `output = default_output(path)`, add:

```python
if args.output is None:
    new_out = text("Output path:", default=str(output))
    if new_out:
        output = Path(new_out)
    if output.suffix.lower() != ".pdf":
        output = output.with_suffix(".pdf")
```

This runs before image discovery and the repetition loop. The `text()` call routes through `prompt_ui`, so it renders as a text input with pre-filled value in the web-ui, and as a line prompt in the terminal.

The "Change output path" option in the action menu is retained for changing the path after seeing the preview.

When `-o` is passed, `args.output is not None` and the prompt is skipped entirely.

---

## Files changed

| File | Change |
|---|---|
| `web-ui.py` | Add `/upload` endpoint; add upload dropdown button in `buildForm`; add hidden file inputs; add `isOutputLike()` JS helper; add `handleUpload()` JS function |
| `pdf-from-images.py` | Add `text()` prompt after computing default output when `-o` is absent |
