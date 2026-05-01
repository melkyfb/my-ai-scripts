#!/usr/bin/env python3
"""
web-ui.py — Web interface to run local python scripts.

Requires: pip install flask

Supports interactive prompts via the prompt_ui helper module: when a script
emits a `__UI_PROMPT__{...}` line on stdout, the UI parses the JSON, renders
buttons / inputs, and writes the user's response back to the script's stdin.
"""

import os
import sys
import ast
import json
import shlex
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from flask import (
    Flask, render_template_string, request, jsonify,
    Response, stream_with_context, send_file,
)

app = Flask(__name__)

IGNORED_DIRS    = {'venv', '__pycache__', 'node_modules', '.git', '.claude', 'include'}
IGNORED_EXTS    = {'.py', '.pyc', '.pyo', '.cfg', '.ini', '.toml'}
IGNORED_NAMES   = {'requirements.txt', 'CLAUDE.md', 'README.md', '.gitignore'}
# Modules imported by other scripts but not runnable on their own.
IGNORED_SCRIPTS = {'prompt_ui.py'}

PROMPT_MARKER = "__UI_PROMPT__"

# Tracks running subprocesses by session id, so /respond can write to stdin.
_active_runs: dict[str, subprocess.Popen] = {}
_runs_lock = threading.Lock()


def get_python_cmd():
    if os.path.exists('venv/bin/python'):
        return 'venv/bin/python'
    if os.path.exists('venv/Scripts/python.exe'):
        return 'venv/Scripts/python.exe'
    return sys.executable


PYTHON_CMD = get_python_cmd()


def list_scripts():
    me = os.path.basename(__file__)
    return sorted(
        f for f in os.listdir('.')
        if f.endswith('.py') and f != me and f not in IGNORED_SCRIPTS
    )


def extract_script_args(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
    except Exception:
        return []

    args_list = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, 'attr', '') == 'add_argument'):
            continue

        arg_data = {
            'name': '', 'flags': [], 'type': 'text',
            'choices': None, 'help': '', 'default': None, 'required': False,
        }

        for a in node.args:
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                if a.value.startswith('-'):
                    arg_data['flags'].append(a.value)
                else:
                    arg_data['name'] = a.value

        for kw in node.keywords:
            if kw.arg == 'action' and isinstance(kw.value, ast.Constant):
                if kw.value.value in ('store_true', 'store_false'):
                    arg_data['type'] = 'checkbox'
            elif kw.arg == 'choices' and isinstance(kw.value, ast.List):
                arg_data['choices'] = [e.value for e in kw.value.elts if isinstance(e, ast.Constant)]
            elif kw.arg == 'help' and isinstance(kw.value, ast.Constant):
                arg_data['help'] = kw.value.value
            elif kw.arg == 'default' and isinstance(kw.value, ast.Constant):
                arg_data['default'] = str(kw.value.value)
            elif kw.arg == 'required' and isinstance(kw.value, ast.Constant):
                arg_data['required'] = bool(kw.value.value)

        if not arg_data['name'] and arg_data['flags']:
            arg_data['name'] = arg_data['flags'][-1].lstrip('-')

        if not arg_data['flags'] and arg_data['name']:
            arg_data['required'] = True  # positional args are always required

        if arg_data['name']:
            args_list.append(arg_data)

    return args_list


def snapshot_dir(base='.'):
    snap = {}
    try:
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith('.')]
            for f in files:
                if f in IGNORED_NAMES:
                    continue
                if Path(f).suffix.lower() in IGNORED_EXTS:
                    continue
                path = os.path.normpath(os.path.join(root, f))
                try:
                    snap[path] = os.path.getmtime(path)
                except OSError:
                    pass
    except Exception:
        pass
    return snap


def file_entry(path):
    try:
        return {'path': path, 'size': os.path.getsize(path)}
    except OSError:
        return {'path': path, 'size': 0}


# ─────────────────────────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Scripts UI</title>
    {% raw %}
    <style>
        :root {
            --bg:        #0e0e14;
            --sidebar:   #13131b;
            --card:      #1a1a25;
            --card2:     #20202e;
            --border:    #28283c;
            --accent:    #7c6af7;
            --accent2:   #5a49d6;
            --success:   #34d399;
            --danger:    #f87171;
            --warn:      #fbbf24;
            --text:      #ddddf0;
            --muted:     #55557a;
            --terminal:  #08080d;
            --r:         8px;
            --r-sm:      5px;
        }

        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
            background: var(--bg);
            color: var(--text);
            display: flex;
            height: 100vh;
            overflow: hidden;
            font-size: 14px;
            line-height: 1.5;
        }

        /* ── Sidebar ── */
        #sidebar {
            width: 230px;
            min-width: 230px;
            background: var(--sidebar);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        #sb-header {
            padding: 14px 14px 10px;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        #sb-header a {
            flex: 1;
            color: var(--text);
            text-decoration: none;
            font-weight: 700;
            font-size: 0.95rem;
            letter-spacing: -0.3px;
        }
        #sb-header a:hover { color: var(--accent); }
        #sb-refresh {
            background: none;
            border: 1px solid var(--border);
            color: var(--muted);
            border-radius: var(--r-sm);
            width: 26px;
            height: 26px;
            cursor: pointer;
            font-size: 13px;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.15s;
        }
        #sb-refresh:hover { border-color: var(--accent); color: var(--accent); }

        #sb-search {
            padding: 8px 10px;
            border-bottom: 1px solid var(--border);
        }
        #search-input {
            width: 100%;
            background: var(--card2);
            border: 1px solid var(--border);
            border-radius: var(--r-sm);
            color: var(--text);
            padding: 6px 10px;
            font-size: 12px;
            outline: none;
            transition: border-color 0.15s;
        }
        #search-input:focus { border-color: var(--accent); }
        #search-input::placeholder { color: var(--muted); }

        #install-btn {
            margin: 8px 10px;
            padding: 7px 12px;
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: var(--r-sm);
            color: var(--muted);
            cursor: pointer;
            font-size: 12px;
            text-align: center;
            transition: all 0.15s;
        }
        #install-btn:hover { border-color: var(--accent); color: var(--text); }

        #script-list {
            flex: 1;
            overflow-y: auto;
            padding: 4px 6px 8px;
        }

        .script-item {
            padding: 8px 10px;
            border-radius: var(--r-sm);
            cursor: pointer;
            font-size: 12.5px;
            color: #7070a0;
            transition: all 0.12s;
            display: flex;
            align-items: center;
            gap: 8px;
            white-space: nowrap;
            overflow: hidden;
        }
        .script-item:hover { background: var(--card); color: var(--text); }
        .script-item.active { background: rgba(124,106,247,.15); color: var(--accent); font-weight: 600; }
        .si-icon { font-size: 10px; opacity: 0.5; flex-shrink: 0; }
        .si-name { overflow: hidden; text-overflow: ellipsis; }

        /* ── Main area ── */
        #main { flex: 1; overflow-y: auto; }
        #content { padding: 28px 32px; max-width: 860px; }

        #empty-state {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 60vh;
            gap: 12px;
            opacity: 0.25;
        }
        .empty-icon { font-size: 44px; }
        .empty-label { font-size: 1rem; }

        /* ── Script UI ── */
        #script-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 20px;
        }
        #script-title {
            font-size: 1.35rem;
            font-weight: 700;
            letter-spacing: -.4px;
        }
        .badge {
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 20px;
            font-weight: 600;
        }
        .badge-py { background: rgba(124,106,247,.15); color: var(--accent); }

        .help-btn {
            margin-left: auto;
            width: 24px;
            height: 24px;
            border-radius: 50%;
            background: var(--card);
            border: 1px solid var(--border);
            color: var(--muted);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            font-weight: 700;
            transition: all 0.15s;
            flex-shrink: 0;
        }
        .help-btn:hover { border-color: var(--accent); color: var(--accent); }

        #help-panel {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: var(--r);
            padding: 12px 16px;
            margin-bottom: 18px;
            font-family: 'Cascadia Code', 'Fira Code', monospace;
            font-size: 11.5px;
            line-height: 1.7;
            color: #8080a8;
            white-space: pre-wrap;
            max-height: 180px;
            overflow-y: auto;
        }

        /* ── Args grid ── */
        #args-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-bottom: 18px;
        }

        .arg-item {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: var(--r);
            padding: 11px 13px;
            transition: border-color 0.15s;
        }
        .arg-item:focus-within { border-color: rgba(124,106,247,.5); }
        .arg-item.full { grid-column: 1 / -1; }
        .arg-item.positional { border-left: 2px solid var(--accent); }

        .arg-item.is-check {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 9px 13px;
        }

        .arg-head {
            display: flex;
            align-items: center;
            gap: 6px;
            margin-bottom: 6px;
        }
        .arg-name { font-size: 12px; font-weight: 600; }
        .arg-flag { font-size: 11px; color: var(--muted); font-family: monospace; }
        .req-dot {
            width: 5px; height: 5px;
            border-radius: 50%;
            background: var(--accent);
            flex-shrink: 0;
        }
        .arg-help { font-size: 11px; color: var(--muted); margin-bottom: 7px; line-height: 1.4; }

        input[type="text"], select {
            width: 100%;
            background: var(--card2);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 6px 10px;
            border-radius: var(--r-sm);
            font-size: 13px;
            outline: none;
            transition: border-color 0.15s;
        }
        input[type="text"]:focus, select:focus { border-color: var(--accent); }
        input[type="text"]::placeholder { color: #35355a; }
        select option { background: var(--card2); }

        .input-row { display: flex; gap: 6px; }
        .input-row input { flex: 1; }

        input[type="checkbox"] {
            width: 15px; height: 15px;
            accent-color: var(--accent);
            cursor: pointer;
            flex-shrink: 0;
        }
        .check-label {
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            flex: 1;
        }
        .check-help { font-size: 11px; color: var(--muted); }

        /* ── Buttons ── */
        .btn {
            padding: 8px 16px;
            border: none;
            border-radius: var(--r-sm);
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        .btn-primary { background: var(--accent); color: #fff; }
        .btn-primary:hover:not(:disabled) { background: var(--accent2); }
        .btn-primary:disabled { opacity: 0.45; cursor: not-allowed; }
        .btn-ghost {
            background: var(--card);
            border: 1px solid var(--border);
            color: var(--muted);
        }
        .btn-ghost:hover { border-color: var(--accent); color: var(--text); }
        .btn-sm { padding: 5px 10px; font-size: 12px; }

        /* ── Run bar ── */
        #run-bar {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 16px;
        }
        #status-dot {
            width: 7px; height: 7px;
            border-radius: 50%;
            background: var(--border);
            transition: background 0.3s;
        }
        #status-dot.running { background: var(--warn); animation: blink 1s infinite; }
        #status-dot.success { background: var(--success); }
        #status-dot.error   { background: var(--danger); }
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:.3} }
        #status-text { font-size: 12px; color: var(--muted); }

        /* ── Prompt panel (interactive prompts from running script) ── */
        #prompt-panel {
            background: linear-gradient(180deg, rgba(124,106,247,.10), rgba(124,106,247,.04));
            border: 1px solid rgba(124,106,247,.4);
            border-radius: var(--r);
            padding: 14px 16px;
            margin-bottom: 14px;
            box-shadow: 0 0 0 4px rgba(124,106,247,.05);
        }
        #prompt-header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 10px;
        }
        #prompt-icon {
            color: var(--accent);
            font-size: 14px;
            font-weight: 700;
        }
        #prompt-text {
            font-size: 13.5px;
            font-weight: 600;
            color: var(--text);
            flex: 1;
        }
        #prompt-body { display: flex; flex-direction: column; gap: 10px; }
        .prompt-options {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
        .prompt-opt {
            justify-content: flex-start !important;
            text-align: left;
            white-space: normal;
            line-height: 1.4;
        }
        .prompt-opt.default {
            outline: 2px solid var(--accent);
            outline-offset: 1px;
        }
        .prompt-text-row { display: flex; gap: 8px; }
        .prompt-text-row input { flex: 1; }
        .prompt-cancel-row {
            margin-top: 4px;
            padding-top: 10px;
            border-top: 1px dashed var(--border);
            text-align: right;
        }

        /* ── Terminal ── */
        #terminal-panel {
            background: var(--terminal);
            border: 1px solid var(--border);
            border-radius: var(--r);
            overflow: hidden;
            margin-bottom: 14px;
        }
        #terminal-bar {
            background: var(--card);
            border-bottom: 1px solid var(--border);
            padding: 7px 14px;
            font-size: 11px;
            color: var(--muted);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        #terminal-bar .dot { width:10px; height:10px; border-radius:50%; }
        .dot-r { background: #ff5f57; }
        .dot-y { background: #febc2e; }
        .dot-g { background: #28c840; }
        #terminal-output {
            padding: 14px 16px;
            font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
            font-size: 12.5px;
            line-height: 1.65;
            color: #c0c0e0;
            white-space: pre-wrap;
            word-break: break-all;
            min-height: 100px;
            max-height: 380px;
            overflow-y: auto;
        }

        /* ── Files panel ── */
        #files-panel {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: var(--r);
            overflow: hidden;
        }
        #files-bar {
            padding: 9px 14px;
            border-bottom: 1px solid var(--border);
            font-size: 12px;
            font-weight: 600;
            color: var(--muted);
        }
        .file-row {
            display: flex;
            align-items: center;
            padding: 9px 14px;
            border-bottom: 1px solid rgba(255,255,255,.03);
            gap: 10px;
        }
        .file-row:last-child { border-bottom: none; }
        .f-icon  { font-size: 18px; flex-shrink: 0; }
        .f-info  { flex: 1; min-width: 0; }
        .f-name  { font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .f-meta  { font-size: 11px; color: var(--muted); margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .f-badge {
            font-size: 10px;
            padding: 2px 7px;
            border-radius: 10px;
            font-weight: 700;
            flex-shrink: 0;
        }
        .badge-new { background: rgba(52,211,153,.12); color: var(--success); }
        .badge-mod { background: rgba(251,191,36,.1);  color: var(--warn); }

        /* ── File browser modal ── */
        #fs-modal {
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,.65);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 1000;
            backdrop-filter: blur(4px);
        }
        #fs-box {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: var(--r);
            width: 540px;
            max-width: 92vw;
            max-height: 78vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        #fs-titlebar {
            padding: 13px 16px;
            border-bottom: 1px solid var(--border);
            font-weight: 600;
            font-size: 13px;
        }
        #fs-pathbar {
            padding: 9px 12px;
            border-bottom: 1px solid var(--border);
            display: flex;
            gap: 6px;
        }
        #fs-current-path {
            flex: 1;
            font-family: monospace;
            font-size: 12px;
            background: var(--card2);
        }
        #fs-list { flex: 1; overflow-y: auto; }
        .fs-item {
            padding: 9px 14px;
            cursor: pointer;
            border-bottom: 1px solid rgba(255,255,255,.03);
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 13px;
            color: #8080b0;
            transition: background 0.1s;
        }
        .fs-item:hover { background: rgba(255,255,255,.04); color: var(--text); }
        .fs-dir { color: var(--accent) !important; font-weight: 500; }
        .fs-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .fs-row-actions {
            display: none;
            gap: 4px;
            flex-shrink: 0;
        }
        .fs-item:hover .fs-row-actions { display: inline-flex; }
        .fs-act {
            width: 24px;
            height: 24px;
            border-radius: 4px;
            background: var(--card2);
            border: 1px solid var(--border);
            color: var(--muted);
            font-size: 12px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.12s;
        }
        .fs-act:hover { color: var(--text); border-color: var(--accent); }
        .fs-act.danger:hover { color: var(--danger); border-color: var(--danger); }
        #fs-actions {
            padding: 11px 14px;
            border-top: 1px solid var(--border);
            display: flex;
            justify-content: flex-end;
            gap: 8px;
        }

        /* ── Misc ── */
        .hidden { display: none !important; }
        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
        ::-webkit-scrollbar-thumb:hover { background: #3a3a55; }
    </style>
    {% endraw %}
</head>
<body>

<!-- File browser modal -->
<div id="fs-modal" class="hidden">
    <div id="fs-box">
        <div id="fs-titlebar">Selecionar Arquivo / Diretório</div>
        <div id="fs-pathbar">
            <input type="text" id="fs-current-path" readonly>
            <button class="btn btn-ghost btn-sm" onclick="fsGoUp()" title="Subir um nível">↑ Subir</button>
            <button class="btn btn-ghost btn-sm" onclick="fsMkdir()" title="Criar nova pasta aqui">＋ Nova pasta</button>
        </div>
        <div id="fs-list"></div>
        <div id="fs-actions">
            <button class="btn btn-ghost btn-sm" onclick="closeFsModal()">Cancelar</button>
            <button class="btn btn-primary btn-sm" onclick="fsSelectCurrent()">Selecionar Pasta Atual</button>
        </div>
    </div>
</div>

<!-- Sidebar -->
<div id="sidebar">
    <div id="sb-header">
        <a href="https://github.com/melkyfb/my-ai-scripts" target="_blank" title="GitHub">⚡ Meus Scripts</a>
        <button id="sb-refresh" title="Recarregar lista" onclick="refreshScripts()">↻</button>
    </div>
    <div id="sb-search">
        <input id="search-input" type="text" placeholder="Buscar script..." oninput="filterScripts(this.value)">
    </div>
    <div id="install-btn" onclick="installDeps()">📦 Instalar Dependências</div>
    <div id="script-list">
        {% for script in scripts %}
        <div class="script-item" onclick="selectScript('{{ script }}')" id="tab-{{ script|replace('.', '-') }}">
            <span class="si-icon">▸</span>
            <span class="si-name">{{ script }}</span>
        </div>
        {% endfor %}
    </div>
</div>

<!-- Main -->
<div id="main">
    <div id="content">

        <div id="empty-state">
            <div class="empty-icon">⚡</div>
            <div class="empty-label">Selecione um script no painel lateral</div>
        </div>

        <div id="script-ui" class="hidden">
            <div id="script-header">
                <div id="script-title"></div>
                <span class="badge badge-py">.py</span>
                <button class="help-btn" id="help-btn" onclick="toggleHelp()" title="Ajuda">?</button>
            </div>

            <pre id="help-panel" class="hidden"></pre>

            <div id="args-grid"></div>

            <div id="run-bar">
                <button class="btn btn-primary" id="run-btn" onclick="runScript()">▶ Executar</button>
                <div id="status-dot"></div>
                <span id="status-text"></span>
            </div>

            <div id="prompt-panel" class="hidden">
                <div id="prompt-header">
                    <span id="prompt-icon">›</span>
                    <span id="prompt-text"></span>
                </div>
                <div id="prompt-body"></div>
            </div>

            <div id="terminal-panel">
                <div id="terminal-bar">
                    <span class="dot dot-r"></span>
                    <span class="dot dot-y"></span>
                    <span class="dot dot-g"></span>
                    <span style="margin-left:6px">terminal</span>
                </div>
                <div id="terminal-output">Aguardando execução...</div>
            </div>

            <div id="files-panel" class="hidden">
                <div id="files-bar">📁 Arquivos gerados / modificados</div>
                <div id="files-list"></div>
            </div>
        </div>

    </div>
</div>

{% raw %}
<script>
    let currentScript = '';
    let fsTargetInput = null;
    let fsCurrentPath = '';
    let activeSession = null;
    let activePrompt = null;

    // ── Script list ──────────────────────────────────────────────────────────

    function filterScripts(query) {
        const q = query.trim().toLowerCase();
        document.querySelectorAll('.script-item').forEach(el => {
            const name = el.querySelector('.si-name').textContent.toLowerCase();
            el.classList.toggle('hidden', q !== '' && !name.includes(q));
        });
    }

    async function refreshScripts() {
        const btn = document.getElementById('sb-refresh');
        btn.style.opacity = '0.4';
        try {
            const res = await fetch('/scripts');
            const { scripts } = await res.json();
            const list = document.getElementById('script-list');
            list.innerHTML = '';
            scripts.forEach(s => {
                const el = document.createElement('div');
                el.className = 'script-item';
                el.id = 'tab-' + s.replace(/[.]/g, '-');
                if (s === currentScript) el.classList.add('active');
                el.onclick = () => selectScript(s);
                el.innerHTML = '<span class="si-icon">▸</span><span class="si-name">' + s + '</span>';
                list.appendChild(el);
            });
            // re-apply current search
            const q = document.getElementById('search-input').value;
            if (q) filterScripts(q);
        } catch (_) {}
        btn.style.opacity = '';
    }

    // ── Script selection ─────────────────────────────────────────────────────

    async function selectScript(script) {
        currentScript = script;
        document.querySelectorAll('.script-item').forEach(t => t.classList.remove('active'));
        document.getElementById('tab-' + script.replace(/[.]/g, '-'))?.classList.add('active');

        document.getElementById('empty-state').classList.add('hidden');
        document.getElementById('script-ui').classList.remove('hidden');
        document.getElementById('script-title').textContent = script;
        document.getElementById('help-panel').classList.add('hidden');
        document.getElementById('files-panel').classList.add('hidden');
        document.getElementById('prompt-panel').classList.add('hidden');
        document.getElementById('args-grid').innerHTML =
            '<div style="color:var(--muted);font-size:12px;padding:4px 0">Carregando...</div>';
        document.getElementById('terminal-output').textContent = 'Aguardando execução...';
        setStatus('idle', '');

        const res = await fetch('/schema?script=' + encodeURIComponent(script));
        const data = await res.json();
        document.getElementById('help-panel').textContent = data.help || 'Sem ajuda disponível.';
        buildForm(data.args || []);
    }

    // ── Form builder ─────────────────────────────────────────────────────────

    function isFileLike(arg) {
        const nameLower = arg.name.toLowerCase();
        const flagsLower = arg.flags.map(f => f.toLowerCase());
        return ['file', 'path', 'dir', 'output'].some(k => nameLower.includes(k))
            || flagsLower.some(f => ['-o', '--output', '--dir', '--file'].includes(f));
    }

    function isOutputLike(arg) {
        const nameLower = arg.name.toLowerCase();
        const flagsLower = (arg.flags || []).map(f => f.toLowerCase());
        return nameLower === 'output'
            || flagsLower.includes('-o')
            || flagsLower.includes('--output');
    }

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

    function buildForm(args) {
        const grid = document.getElementById('args-grid');
        if (!args.length) {
            grid.innerHTML = '<div style="color:var(--muted);font-size:12px;grid-column:1/-1">Este script não possui argumentos configuráveis.</div>';
            return;
        }

        let html = '';
        args.forEach((arg, i) => {
            const id = 'arg-' + i;
            const isPos   = arg.flags.length === 0;
            const isFile  = isFileLike(arg);
            const isFull  = isPos || isFile;
            const isCheck = arg.type === 'checkbox';

            const classes = ['arg-item'];
            if (isFull)  classes.push('full');
            if (isPos)   classes.push('positional');
            if (isCheck) classes.push('is-check');

            if (isCheck) {
                html += `<div class="${classes.join(' ')}">
                    <input type="checkbox" id="${id}" data-flag="${arg.flags[0] || ''}">
                    <label class="check-label" for="${id}">${arg.flags[0] || arg.name}</label>
                    ${arg.help ? `<span class="check-help">${arg.help}</span>` : ''}
                </div>`;
            } else {
                const flagStr = arg.flags.length
                    ? `<span class="arg-flag">${arg.flags.join(', ')}</span>` : '';
                const reqDot = arg.required
                    ? `<span class="req-dot" title="Obrigatório"></span>` : '';

                html += `<div class="${classes.join(' ')}">
                    <div class="arg-head">${reqDot}<span class="arg-name">${arg.name}</span>${flagStr}</div>`;
                if (arg.help) html += `<div class="arg-help">${arg.help}</div>`;

                if (arg.choices) {
                    html += `<select id="${id}" data-flag="${arg.flags[0] || ''}" data-pos="${isPos}">
                        <option value="">— Padrão —</option>
                        ${arg.choices.map(c => `<option value="${c}">${c}</option>`).join('')}
                    </select>`;
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
                } else {
                    const ph = arg.default ? `Padrão: ${arg.default}` : 'Valor...';
                    html += `<input type="text" id="${id}" placeholder="${ph}" data-flag="${arg.flags[0] || ''}" data-pos="${isPos}">`;
                }

                html += `</div>`;
            }
        });

        grid.innerHTML = html;
    }

    // ── Help ─────────────────────────────────────────────────────────────────

    function toggleHelp() {
        document.getElementById('help-panel').classList.toggle('hidden');
    }

    // ── Status ───────────────────────────────────────────────────────────────

    function setStatus(state, text) {
        document.getElementById('status-dot').className = state === 'idle' ? '' : state;
        document.getElementById('status-text').textContent = text;
    }

    // ── Run script (streaming) ────────────────────────────────────────────────

    async function runScript() {
        if (!currentScript) return;

        const btn     = document.getElementById('run-btn');
        const termOut = document.getElementById('terminal-output');
        const filesPan = document.getElementById('files-panel');

        // Reset session/prompt state
        activeSession = null;
        activePrompt = null;
        hidePrompt();

        // Collect args — positionals first, then optionals
        const positionals = [], optionals = [];
        document.getElementById('args-grid').querySelectorAll('input, select').forEach(el => {
            const flag  = el.getAttribute('data-flag') || '';
            const isPos = el.getAttribute('data-pos') === 'true';
            if (el.type === 'checkbox') {
                if (el.checked && flag) optionals.push(flag);
            } else if (el.value.trim()) {
                if (isPos) {
                    positionals.push(el.value.trim());
                } else {
                    if (flag) optionals.push(flag);
                    optionals.push(el.value.trim());
                }
            }
        });
        const argsArr = [...positionals, ...optionals];
        const argsStr = argsArr.map(a => a.includes(' ') ? `"${a}"` : a).join(' ');

        btn.disabled = true;
        btn.textContent = '⏳ Executando...';
        termOut.textContent = `$ python ${currentScript} ${argsStr}\n\n`;
        filesPan.classList.add('hidden');
        setStatus('running', 'rodando...');

        const fd = new FormData();
        fd.append('script', currentScript);
        fd.append('args', argsStr);

        try {
            const response = await fetch('/run', { method: 'POST', body: fd });
            const reader   = response.body.getReader();
            const decoder  = new TextDecoder();
            let buffer = '';

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\\n');
                buffer = lines.pop();
                for (const line of lines) {
                    if (!line.trim()) continue;
                    try { handleEvent(JSON.parse(line)); } catch (_) {}
                }
            }
            if (buffer.trim()) {
                try { handleEvent(JSON.parse(buffer)); } catch (_) {}
            }
        } catch (err) {
            termOut.textContent += `\n[Falha na comunicação: ${err}]\n`;
            setStatus('error', 'falha');
        }

        btn.disabled = false;
        btn.textContent = '▶ Executar';
    }

    function handleEvent(ev) {
        const termOut = document.getElementById('terminal-output');
        if (ev.type === 'started') {
            activeSession = ev.session;
        } else if (ev.type === 'line') {
            termOut.textContent += ev.text + '\\n';
            termOut.scrollTop = termOut.scrollHeight;
        } else if (ev.type === 'prompt') {
            showPrompt(ev.data);
        } else if (ev.type === 'done') {
            hidePrompt();
            const ok = ev.returncode === 0;
            setStatus(ok ? 'success' : 'error', ok ? 'concluído' : `erro (código ${ev.returncode})`);
            showFiles(ev.new_files || [], ev.modified_files || []);
        } else if (ev.type === 'error') {
            hidePrompt();
            termOut.textContent += `\n[Erro: ${ev.msg}]\n`;
            setStatus('error', 'erro na execução');
        }
    }

    // ── Interactive prompt panel ─────────────────────────────────────────────

    function showPrompt(p) {
        activePrompt = p;
        const panel = document.getElementById('prompt-panel');
        const ptxt  = document.getElementById('prompt-text');
        const body  = document.getElementById('prompt-body');

        ptxt.textContent = p.prompt || 'Entrada necessária';
        body.innerHTML = '';

        if (p.type === 'choice') {
            const wrap = document.createElement('div');
            wrap.className = 'prompt-options';
            (p.options || []).forEach((label, idx) => {
                const btn = document.createElement('button');
                btn.className = 'btn btn-primary prompt-opt';
                btn.textContent = `${idx + 1}.  ${label}`;
                btn.onclick = () => submitPrompt(String(idx));
                wrap.appendChild(btn);
            });
            if (p.allow_back) {
                const b = document.createElement('button');
                b.className = 'btn btn-ghost prompt-opt';
                b.textContent = '↶  Voltar';
                b.onclick = () => submitPrompt('__BACK__');
                wrap.appendChild(b);
            }
            body.appendChild(wrap);
        } else if (p.type === 'confirm') {
            const wrap = document.createElement('div');
            wrap.className = 'prompt-options';
            wrap.style.flexDirection = 'row';
            const yes = document.createElement('button');
            yes.className = 'btn btn-primary';
            yes.textContent = '✓  Sim';
            yes.style.flex = '1';
            yes.onclick = () => submitPrompt('y');
            const no = document.createElement('button');
            no.className = 'btn btn-ghost';
            no.textContent = '✗  Não';
            no.style.flex = '1';
            no.onclick = () => submitPrompt('n');
            if (p.default === true)  yes.classList.add('default');
            if (p.default === false) no.classList.add('default');
            wrap.appendChild(yes);
            wrap.appendChild(no);
            body.appendChild(wrap);
        } else if (p.type === 'text') {
            const row = document.createElement('div');
            row.className = 'prompt-text-row';
            const input = document.createElement('input');
            input.type = 'text';
            input.placeholder = p.placeholder || '';
            input.value = p.default || '';
            const ok = document.createElement('button');
            ok.className = 'btn btn-primary';
            ok.textContent = 'OK';
            const submit = () => submitPrompt(input.value);
            ok.onclick = submit;
            input.onkeydown = (e) => { if (e.key === 'Enter') submit(); };
            row.appendChild(input);
            row.appendChild(ok);
            body.appendChild(row);
            setTimeout(() => input.focus(), 50);
        } else if (p.type === 'menu') {
            const wrap = document.createElement('div');
            wrap.className = 'prompt-options';
            (p.options || []).forEach((opt) => {
                const btn = document.createElement('button');
                btn.className = 'btn btn-primary prompt-opt';
                btn.textContent = opt.label || opt.key;
                if (opt.hint) btn.title = opt.hint;
                btn.onclick = () => submitPrompt(opt.key);
                wrap.appendChild(btn);
            });
            body.appendChild(wrap);
        } else {
            const msg = document.createElement('div');
            msg.style.color = 'var(--danger)';
            msg.textContent = `Tipo de prompt desconhecido: ${p.type}`;
            body.appendChild(msg);
        }

        // Always-available cancel
        const cancelRow = document.createElement('div');
        cancelRow.className = 'prompt-cancel-row';
        const cancel = document.createElement('button');
        cancel.className = 'btn btn-ghost btn-sm';
        cancel.textContent = '✕  Cancelar execução';
        cancel.onclick = () => submitPrompt('__CANCEL__');
        cancelRow.appendChild(cancel);
        body.appendChild(cancelRow);

        panel.classList.remove('hidden');
        panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    function hidePrompt() {
        document.getElementById('prompt-panel').classList.add('hidden');
        activePrompt = null;
    }

    async function submitPrompt(response) {
        if (!activeSession) return;
        const fd = new FormData();
        fd.append('session', activeSession);
        fd.append('response', response);
        try {
            const res = await fetch('/respond', { method: 'POST', body: fd });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                const termOut = document.getElementById('terminal-output');
                termOut.textContent += `\n[Falha ao enviar resposta: ${data.error || res.status}]\n`;
            }
        } catch (e) {
            const termOut = document.getElementById('terminal-output');
            termOut.textContent += `\n[Erro de rede: ${e}]\n`;
        }
        hidePrompt();
    }

    // ── Files panel ──────────────────────────────────────────────────────────

    function fmtSize(bytes) {
        if (!bytes) return '';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
        if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
        return (bytes / 1073741824).toFixed(2) + ' GB';
    }

    function fileIcon(name) {
        const ext = name.split('.').pop().toLowerCase();
        return {
            mp4:'🎬', mkv:'🎬', mov:'🎬', webm:'🎬', avi:'🎬',
            mp3:'🎵', wav:'🎵', m4a:'🎵', ogg:'🎵', opus:'🎵', flac:'🎵',
            jpg:'🖼️', jpeg:'🖼️', png:'🖼️', gif:'🖼️', webp:'🖼️',
            pdf:'📕', txt:'📄', srt:'📄', md:'📄',
            zip:'📦', tar:'📦', gz:'📦', rar:'📦',
        }[ext] || '📄';
    }

    function showFiles(newFiles, modFiles) {
        if (!newFiles.length && !modFiles.length) return;

        const list  = document.getElementById('files-list');
        const panel = document.getElementById('files-panel');

        const renderRow = (f, badgeClass, badgeLabel) => {
            const name = f.path.split('/').pop();
            const size = fmtSize(f.size);
            return `<div class="file-row">
                <span class="f-icon">${fileIcon(name)}</span>
                <div class="f-info">
                    <div class="f-name">${name}</div>
                    <div class="f-meta">${f.path}${size ? '  ·  ' + size : ''}</div>
                </div>
                <span class="f-badge ${badgeClass}">${badgeLabel}</span>
                <a href="/download-file?path=${encodeURIComponent(f.path)}" download="${name}">
                    <button class="btn btn-ghost btn-sm">⬇ Baixar</button>
                </a>
            </div>`;
        };

        list.innerHTML =
            newFiles.map(f => renderRow(f, 'badge-new', 'novo')).join('') +
            modFiles.map(f => renderRow(f, 'badge-mod', 'modificado')).join('');

        panel.classList.remove('hidden');
    }

    // ── Install deps ─────────────────────────────────────────────────────────

    async function installDeps() {
        document.querySelectorAll('.script-item').forEach(t => t.classList.remove('active'));
        currentScript = '';
        document.getElementById('empty-state').classList.add('hidden');
        document.getElementById('script-ui').classList.remove('hidden');
        document.getElementById('script-title').textContent = 'Instalação de Dependências';
        document.getElementById('help-panel').classList.add('hidden');
        document.getElementById('args-grid').innerHTML = '';
        document.getElementById('files-panel').classList.add('hidden');
        document.getElementById('prompt-panel').classList.add('hidden');
        document.getElementById('run-btn').classList.add('hidden');
        setStatus('running', 'instalando...');

        const termOut = document.getElementById('terminal-output');
        termOut.textContent = '$ pip install -r requirements.txt\\n\\n...';

        try {
            const res  = await fetch('/install', { method: 'POST' });
            const data = await res.json();
            termOut.textContent = data.output;
            setStatus('success', 'instalação concluída');
        } catch (err) {
            termOut.textContent = 'Erro: ' + err;
            setStatus('error', 'falha');
        }

        document.getElementById('run-btn').classList.remove('hidden');
    }

    // ── File browser ─────────────────────────────────────────────────────────

    async function loadFs(path) {
        const res  = await fetch('/fs?path=' + encodeURIComponent(path));
        const data = await res.json();
        if (data.error) { alert(data.error); return; }
        fsCurrentPath = data.current;
        document.getElementById('fs-current-path').value = fsCurrentPath;

        const list = document.getElementById('fs-list');
        list.innerHTML = '';
        data.dirs.forEach(d  => list.appendChild(buildFsRow(d, true)));
        data.files.forEach(f => list.appendChild(buildFsRow(f, false)));
    }

    function buildFsRow(name, isDir) {
        const el = document.createElement('div');
        el.className = 'fs-item' + (isDir ? ' fs-dir' : '');

        const label = document.createElement('span');
        label.className = 'fs-name';
        label.textContent = (isDir ? '📁 ' : '📄 ') + name;
        el.appendChild(label);

        const actions = document.createElement('span');
        actions.className = 'fs-row-actions';

        const renameBtn = document.createElement('button');
        renameBtn.className = 'fs-act';
        renameBtn.textContent = '✎';
        renameBtn.title = 'Renomear';
        renameBtn.onclick = (ev) => { ev.stopPropagation(); fsRename(name); };

        const delBtn = document.createElement('button');
        delBtn.className = 'fs-act danger';
        delBtn.textContent = '🗑';
        delBtn.title = 'Deletar';
        delBtn.onclick = (ev) => { ev.stopPropagation(); fsDelete(name, isDir); };

        actions.appendChild(renameBtn);
        actions.appendChild(delBtn);
        el.appendChild(actions);

        el.onclick = () => {
            if (isDir) loadFs(fsCurrentPath + '/' + name);
            else       fsSelectFile(fsCurrentPath + '/' + name);
        };
        return el;
    }

    async function fsMkdir() {
        const name = prompt('Nome da nova pasta:');
        if (!name) return;
        const fd = new FormData();
        fd.append('parent', fsCurrentPath);
        fd.append('name', name.trim());
        try {
            const res  = await fetch('/fs/mkdir', { method: 'POST', body: fd });
            const data = await res.json();
            if (data.error) { alert(data.error); return; }
            loadFs(fsCurrentPath);
        } catch (e) { alert('Erro: ' + e); }
    }

    async function fsRename(oldName) {
        const newName = prompt('Renomear "' + oldName + '" para:', oldName);
        if (!newName || newName.trim() === '' || newName === oldName) return;
        const fd = new FormData();
        fd.append('parent', fsCurrentPath);
        fd.append('old_name', oldName);
        fd.append('new_name', newName.trim());
        try {
            const res  = await fetch('/fs/rename', { method: 'POST', body: fd });
            const data = await res.json();
            if (data.error) { alert(data.error); return; }
            loadFs(fsCurrentPath);
        } catch (e) { alert('Erro: ' + e); }
    }

    async function fsDelete(name, isDir) {
        const what = isDir ? 'a pasta "' + name + '" E TODO o seu conteúdo'
                           : 'o arquivo "' + name + '"';
        if (!confirm('Deletar ' + what + '?\\n\\nEsta ação não pode ser desfeita.')) return;
        const fd = new FormData();
        fd.append('parent', fsCurrentPath);
        fd.append('name', name);
        try {
            const res  = await fetch('/fs/delete', { method: 'POST', body: fd });
            const data = await res.json();
            if (data.error) { alert(data.error); return; }
            loadFs(fsCurrentPath);
        } catch (e) { alert('Erro: ' + e); }
    }

    function openFsModal(inputId) {
        fsTargetInput = inputId;
        document.getElementById('fs-modal').classList.remove('hidden');
        loadFs(document.getElementById(inputId).value || '.');
    }

    function closeFsModal() {
        document.getElementById('fs-modal').classList.add('hidden');
    }

    function fsGoUp() { loadFs(fsCurrentPath + '/..'); }

    function fsSelectFile(path) {
        document.getElementById(fsTargetInput).value = path;
        closeFsModal();
    }

    function fsSelectCurrent() {
        document.getElementById(fsTargetInput).value = fsCurrentPath;
        closeFsModal();
    }
</script>
{% endraw %}
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, scripts=list_scripts())


@app.route('/scripts')
def scripts_list():
    return jsonify({'scripts': list_scripts()})


@app.route('/fs')
def file_system():
    req_path = request.args.get('path', '.').strip() or '.'
    try:
        abs_path = os.path.abspath(req_path)
        if not os.path.exists(abs_path):
            abs_path = os.path.abspath('.')
        items = os.listdir(abs_path)
        dirs  = sorted(d for d in items if os.path.isdir(os.path.join(abs_path, d)))
        files = sorted(f for f in items if os.path.isfile(os.path.join(abs_path, f)))
        return jsonify({'current': abs_path, 'dirs': dirs, 'files': files})
    except Exception as e:
        return jsonify({'error': str(e)})


def _validate_fs_name(name: str) -> str | None:
    """Reject names that could escape the parent dir. Returns error msg or None."""
    if not name or name in ('.', '..'):
        return 'Nome inválido.'
    if any(c in name for c in '/\\'):
        return 'Nome não pode conter "/" nem "\\".'
    if any(c in name for c in '\x00'):
        return 'Nome contém caracteres inválidos.'
    return None


@app.route('/fs/mkdir', methods=['POST'])
def fs_mkdir():
    parent = request.form.get('parent', '').strip()
    name   = request.form.get('name', '').strip()
    if not parent:
        return jsonify({'error': 'parent obrigatório'}), 400
    err = _validate_fs_name(name)
    if err:
        return jsonify({'error': err}), 400
    try:
        target = os.path.join(os.path.abspath(parent), name)
        os.makedirs(target, exist_ok=False)
        return jsonify({'ok': True, 'path': target})
    except FileExistsError:
        return jsonify({'error': 'Já existe uma pasta/arquivo com esse nome.'}), 400
    except PermissionError:
        return jsonify({'error': 'Permissão negada.'}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/fs/rename', methods=['POST'])
def fs_rename():
    parent   = request.form.get('parent', '').strip()
    old_name = request.form.get('old_name', '').strip()
    new_name = request.form.get('new_name', '').strip()
    if not parent:
        return jsonify({'error': 'parent obrigatório'}), 400
    for label, value in (('old_name', old_name), ('new_name', new_name)):
        err = _validate_fs_name(value)
        if err:
            return jsonify({'error': f'{label}: {err}'}), 400
    if old_name == new_name:
        return jsonify({'ok': True})  # no-op
    try:
        parent_abs = os.path.abspath(parent)
        src = os.path.join(parent_abs, old_name)
        dst = os.path.join(parent_abs, new_name)
        if not os.path.exists(src):
            return jsonify({'error': 'Origem não encontrada.'}), 404
        if os.path.exists(dst):
            return jsonify({'error': 'Já existe uma pasta/arquivo com o novo nome.'}), 400
        os.rename(src, dst)
        return jsonify({'ok': True, 'path': dst})
    except PermissionError:
        return jsonify({'error': 'Permissão negada.'}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/fs/delete', methods=['POST'])
def fs_delete():
    parent = request.form.get('parent', '').strip()
    name   = request.form.get('name', '').strip()
    if not parent:
        return jsonify({'error': 'parent obrigatório'}), 400
    err = _validate_fs_name(name)
    if err:
        return jsonify({'error': err}), 400
    try:
        target = os.path.join(os.path.abspath(parent), name)
        if not os.path.exists(target):
            return jsonify({'error': 'Não encontrado.'}), 404
        if os.path.isdir(target):
            shutil.rmtree(target)
        else:
            os.remove(target)
        return jsonify({'ok': True})
    except PermissionError:
        return jsonify({'error': 'Permissão negada.'}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/schema')
def get_schema():
    script = request.args.get('script', '')
    if not script or not os.path.exists(script):
        return jsonify({'help': 'Script não encontrado.', 'args': []})
    try:
        res  = subprocess.run([PYTHON_CMD, script, '--help'], capture_output=True, text=True, timeout=5)
        help_text = res.stdout or res.stderr
        return jsonify({'help': help_text, 'args': extract_script_args(script)})
    except Exception as e:
        return jsonify({'help': f'Erro ao carregar: {e}', 'args': []})


@app.route('/run', methods=['POST'])
def run_script():
    script   = request.form.get('script', '')
    args_str = request.form.get('args', '').strip()

    if not script or not os.path.exists(script):
        def _err():
            yield json.dumps({'type': 'error', 'msg': 'Script não encontrado.'}) + '\n'
        return Response(stream_with_context(_err()), mimetype='application/x-ndjson')

    cmd = [PYTHON_CMD, script]
    if args_str:
        try:
            cmd.extend(shlex.split(args_str))
        except ValueError as e:
            def _err():
                yield json.dumps({'type': 'error', 'msg': f'Argumento inválido: {e}'}) + '\n'
            return Response(stream_with_context(_err()), mimetype='application/x-ndjson')

    def generate():
        session_id = uuid.uuid4().hex
        yield json.dumps({'type': 'started', 'session': session_id}) + '\n'

        before = snapshot_dir('.')
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        proc = None

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
            )
            with _runs_lock:
                _active_runs[session_id] = proc

            for line in proc.stdout:
                line = line.rstrip('\n')
                if line.startswith(PROMPT_MARKER):
                    try:
                        payload = json.loads(line[len(PROMPT_MARKER):])
                        # Nest the payload under `data` so its inner "type"
                        # (e.g. "choice", "confirm") doesn't collide with the
                        # outer event discriminator.
                        yield json.dumps({
                            'type':    'prompt',
                            'session': session_id,
                            'data':    payload,
                        }) + '\n'
                        continue
                    except json.JSONDecodeError:
                        # Malformed marker — fall through to display as text.
                        pass
                yield json.dumps({'type': 'line', 'text': line}) + '\n'

            proc.wait()

            after     = snapshot_dir('.')
            new_files = [file_entry(p) for p in sorted(after) if p not in before]
            mod_files = [file_entry(p) for p in sorted(after)
                         if p in before and after[p] > before[p] + 0.01]

            yield json.dumps({
                'type': 'done',
                'returncode':    proc.returncode,
                'new_files':     new_files,
                'modified_files': mod_files,
            }) + '\n'
        except Exception as e:
            yield json.dumps({'type': 'error', 'msg': str(e)}) + '\n'
        finally:
            with _runs_lock:
                _active_runs.pop(session_id, None)
            # Best-effort cleanup if the client disconnected mid-stream.
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass

    return Response(
        stream_with_context(generate()),
        mimetype='application/x-ndjson',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@app.route('/respond', methods=['POST'])
def respond():
    """Write a single line to the running subprocess's stdin."""
    session  = request.form.get('session', '').strip()
    response = request.form.get('response', '')

    if not session:
        return jsonify({'error': 'session required'}), 400

    with _runs_lock:
        proc = _active_runs.get(session)

    if proc is None or proc.poll() is not None:
        return jsonify({'error': 'session not active'}), 404

    try:
        proc.stdin.write(response + '\n')
        proc.stdin.flush()
        return jsonify({'ok': True})
    except (BrokenPipeError, OSError) as e:
        return jsonify({'error': str(e)}), 410


@app.route('/download-file')
def download_file():
    path = request.args.get('path', '')
    if not path:
        return 'Path required', 400
    abs_path = os.path.abspath(path)
    base     = os.path.abspath('.')
    if not abs_path.startswith(base + os.sep) and abs_path != base:
        return 'Access denied', 403
    if not os.path.isfile(abs_path):
        return 'File not found', 404
    return send_file(abs_path, as_attachment=True)


@app.route('/install', methods=['POST'])
def install_deps():
    try:
        res = subprocess.run(
            [PYTHON_CMD, '-m', 'pip', 'install', '-r', 'requirements.txt'],
            capture_output=True, text=True,
        )
        out = res.stdout
        if res.stderr:
            out += '\n--- ERROS / AVISOS ---\n' + res.stderr
        return jsonify({'output': out})
    except Exception as e:
        return jsonify({'output': f'Falha: {e}'})


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


if __name__ == '__main__':
    print('Iniciando interface web...')
    print('Acesse: http://127.0.0.1:5000')
    app.run(debug=True, port=5000, threaded=True, use_reloader=False)
