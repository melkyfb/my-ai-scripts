#!/usr/bin/env python3
"""
web-ui.py — Web interface to run local python scripts.

Requires: pip install flask
"""

import os
import sys
import ast
import shlex
import subprocess
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

def get_python_cmd():
    """Retorna o caminho do python dentro do venv se existir, senão usa o atual."""
    if os.path.exists('venv/bin/python'):
        return 'venv/bin/python'
    elif os.path.exists('venv/Scripts/python.exe'):
        return 'venv/Scripts/python.exe'
    return sys.executable

PYTHON_CMD = get_python_cmd()

def extract_script_args(filepath):
    """Lê o script e extrai os argumentos do argparse usando AST."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
    except Exception:
        return []

    args_list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, 'attr', '') == 'add_argument':
            arg_data = {'name': '', 'flags': [], 'type': 'text', 'choices': None, 'help': ''}
            
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if arg.value.startswith('-'):
                        arg_data['flags'].append(arg.value)
                    else:
                        arg_data['name'] = arg.value
                        
            for kw in node.keywords:
                if kw.arg == 'action' and isinstance(kw.value, ast.Constant) and kw.value.value in ('store_true', 'store_false'):
                    arg_data['type'] = 'checkbox'
                elif kw.arg == 'choices' and isinstance(kw.value, ast.List):
                    arg_data['choices'] = [el.value for el in kw.value.elts if isinstance(el, ast.Constant)]
                elif kw.arg == 'help' and isinstance(kw.value, ast.Constant):
                    arg_data['help'] = kw.value.value
                    
            if not arg_data['name'] and arg_data['flags']:
                arg_data['name'] = arg_data['flags'][-1].lstrip('-')
                
            if arg_data['name']:
                args_list.append(arg_data)
                
    return args_list

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Scripts UI</title>
    <style>
        body { font-family: system-ui, -apple-system, sans-serif; display: flex; margin: 0; height: 100vh; background: #f9f9f9; }
        #sidebar { width: 250px; background: #333; color: white; overflow-y: auto; }
        #sidebar h2 { text-align: center; font-size: 1.2rem; padding: 15px 0; margin: 0; border-bottom: 1px solid #444; }
        .tab { padding: 15px; cursor: pointer; border-bottom: 1px solid #444; }
        .tab:hover { background: #444; }
        .tab.active { background: #007bff; }
        #content { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; }
        .hidden { display: none !important; }
        .form-group { margin-bottom: 15px; background: #fff; padding: 15px; border-radius: 6px; border: 1px solid #ddd; }
        label { display: block; margin-bottom: 5px; font-weight: bold; color: #333; }
        .help-text { font-size: 0.85em; color: #666; margin-bottom: 8px; display: block; }
        input[type="text"], select { width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
        .input-group { display: flex; gap: 10px; }
        input[type="checkbox"] { transform: scale(1.2); margin-right: 10px; }
        button { background: #28a745; color: white; border: none; padding: 10px 20px; font-size: 16px; border-radius: 4px; cursor: pointer; font-weight: bold; }
        button:hover { background: #218838; }
        button.btn-secondary { background: #6c757d; }
        button.btn-secondary:hover { background: #5a6268; }
        pre { background: #1e1e1e; color: #d4d4d4; padding: 15px; border-radius: 4px; overflow-x: auto; white-space: pre-wrap; }
        .help-block { background: #e9ecef; color: #333; padding: 15px; border-radius: 4px; font-size: 0.9em; margin-bottom: 20px; }
        .title-container { display: flex; align-items: center; gap: 15px; }
        .help-icon { background: #007bff; color: white; border-radius: 50%; width: 30px; height: 30px; display: flex; justify-content: center; align-items: center; font-size: 18px; cursor: pointer; font-weight: bold; }
        .help-icon:hover { background: #0056b3; }
        
        #fs-modal { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); display: flex; justify-content: center; align-items: center; z-index: 1000; }
        #fs-content { background: white; padding: 20px; border-radius: 8px; width: 600px; max-width: 90%; max-height: 80vh; display: flex; flex-direction: column; }
        #fs-list { flex: 1; overflow-y: auto; border: 1px solid #ccc; margin: 15px 0; padding: 10px; border-radius: 4px; }
        .fs-item { padding: 8px; cursor: pointer; border-bottom: 1px solid #eee; display: flex; align-items: center; gap: 10px; }
        .fs-item:hover { background: #f0f0f0; }
        .fs-dir { font-weight: bold; color: #007bff; }
    </style>
</head>
<body>

    <div id="fs-modal" class="hidden">
        <div id="fs-content">
            <h3>Selecionar Arquivo / Diretório</h3>
            <div style="display:flex; gap:10px;">
                <input type="text" id="fs-current-path" readonly style="background:#eee;">
                <button type="button" class="btn-secondary" onclick="fsGoUp()">Subir</button>
            </div>
            <div id="fs-list"></div>
            <div style="display:flex; justify-content: space-between;">
                <button type="button" class="btn-secondary" onclick="closeFsModal()">Cancelar</button>
                <button type="button" onclick="fsSelectCurrent()">Selecionar Pasta Atual</button>
            </div>
        </div>
    </div>

    <div id="sidebar">
        <h2><a href="https://github.com/melkyfb/my-ai-scripts" target="_blank" style="color: white; text-decoration: none;" title="Abrir repositório no GitHub">Meus Scripts 🔗</a></h2>
        <div class="tab" onclick="installDeps()" style="background: #28a745; font-weight: bold; text-align: center; font-size: 0.9em; padding: 10px; margin: 10px; border-radius: 4px;">📦 Instalar Dependências</div>
        {% for script in scripts %}
            <div class="tab" onclick="selectScript('{{ script }}')" id="tab-{{ script|replace('.', '-') }}">{{ script }}</div>
        {% endfor %}
    </div>

    <div id="content">
        <div class="title-container">
            <h1 id="script-title">Selecione um script</h1>
            <div id="help-btn" class="help-icon hidden" onclick="toggleHelp()" title="Ver Ajuda">?</div>
        </div>
        
        <div id="script-ui" class="hidden">
            <pre class="help-block hidden" id="script-help">Carregando...</pre>

            <div id="dynamic-form"></div>

            <button onclick="runScript()" id="run-btn">Executar</button>

            <div class="form-group" style="margin-top: 20px;">
                <label>Saída (Output):</label>
                <pre id="script-output">Aguardando execução...</pre>
            </div>
        </div>
    </div>

    <script>
        let currentScript = "";
        let fsTargetInput = null;
        let fsCurrentPath = "";

        async function installDeps() {
            const outputBox = document.getElementById('script-output');
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            
            document.getElementById('script-ui').classList.remove('hidden');
            document.getElementById('script-title').innerText = "Instalação de Dependências";
            document.getElementById('help-btn').classList.add('hidden');
            document.getElementById('script-help').classList.add('hidden');
            document.getElementById('dynamic-form').innerHTML = "";
            document.getElementById('run-btn').classList.add('hidden');
            
            outputBox.innerText = "Instalando dependências (pip install -r requirements.txt)...\\nIsso pode demorar um pouco...";
            
            try {
                const res = await fetch('/install', { method: 'POST' });
                const data = await res.json();
                outputBox.innerText = data.output;
            } catch (err) {
                outputBox.innerText = "Erro ao instalar: " + err;
            }
        }

        function toggleHelp() {
            document.getElementById('script-help').classList.toggle('hidden');
        }

        async function selectScript(script) {
            currentScript = script;
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.getElementById('tab-' + script.replace('.', '-')).classList.add('active');
            
            document.getElementById('script-title').innerText = script;
            document.getElementById('help-btn').classList.remove('hidden');
            document.getElementById('script-ui').classList.remove('hidden');
            document.getElementById('run-btn').classList.remove('hidden');
            document.getElementById('script-help').classList.add('hidden');
            document.getElementById('script-help').innerText = "Carregando opções...";
            document.getElementById('script-output').innerText = "Aguardando execução...";
            document.getElementById('dynamic-form').innerHTML = "";

            const res = await fetch('/schema?script=' + encodeURIComponent(script));
            const data = await res.json();
            
            document.getElementById('script-help').innerText = data.help || "Sem ajuda disponível.";
            
            // Build dynamic form
            let html = "";
            data.args.forEach((arg, i) => {
                const id = "arg-" + i;
                html += `<div class="form-group">`;
                html += `<label for="${id}">${arg.name} ${arg.flags.length > 0 ? '(' + arg.flags.join(', ') + ')' : ''}</label>`;
                if (arg.help) html += `<span class="help-text">${arg.help}</span>`;
                
                if (arg.type === 'checkbox') {
                    html += `<input type="checkbox" id="${id}" data-flag="${arg.flags[0] || ''}"> Marcar para ativar`;
                } else if (arg.choices) {
                    html += `<select id="${id}" data-flag="${arg.flags[0] || ''}" data-is-pos="${arg.flags.length === 0}">`;
                    html += `<option value="">-- Padrão --</option>`;
                    arg.choices.forEach(c => { html += `<option value="${c}">${c}</option>`; });
                    html += `</select>`;
                } else {
                    const isFileOrDir = ['file', 'path', 'output', 'dir'].includes(arg.name.toLowerCase()) || arg.flags.some(f => ['-o', '--output'].includes(f));
                    
                    if (isFileOrDir) {
                        html += `<div class="input-group">
                            <input type="text" id="${id}" placeholder="Caminho do arquivo ou diretório..." data-flag="${arg.flags[0] || ''}" data-is-pos="${arg.flags.length === 0}">
                            <button type="button" class="btn-secondary" onclick="openFsModal('${id}')">Buscar</button>
                        </div>`;
                    } else {
                        html += `<input type="text" id="${id}" placeholder="Valor..." data-flag="${arg.flags[0] || ''}" data-is-pos="${arg.flags.length === 0}">`;
                    }
                }
                html += `</div>`;
            });
            document.getElementById('dynamic-form').innerHTML = html;
        }

        // --- File System Browser ---
        async function loadFs(path = "") {
            const res = await fetch('/fs?path=' + encodeURIComponent(path));
            const data = await res.json();
            if (data.error) {
                alert(data.error);
                return;
            }
            fsCurrentPath = data.current;
            document.getElementById('fs-current-path').value = fsCurrentPath;
            
            let listHtml = "";
            data.dirs.forEach(d => {
                listHtml += `<div class="fs-item fs-dir" onclick="loadFs('${fsCurrentPath}/${d}')">📁 ${d}</div>`;
            });
            data.files.forEach(f => {
                listHtml += `<div class="fs-item" onclick="fsSelectFile('${fsCurrentPath}/${f}')">📄 ${f}</div>`;
            });
            document.getElementById('fs-list').innerHTML = listHtml;
        }

        function openFsModal(inputId) {
            fsTargetInput = inputId;
            document.getElementById('fs-modal').classList.remove('hidden');
            loadFs(document.getElementById(inputId).value || ".");
        }

        function closeFsModal() {
            document.getElementById('fs-modal').classList.add('hidden');
        }

        function fsGoUp() {
            loadFs(fsCurrentPath + "/..");
        }

        function fsSelectFile(fullPath) {
            document.getElementById(fsTargetInput).value = fullPath;
            closeFsModal();
        }

        function fsSelectCurrent() {
            document.getElementById(fsTargetInput).value = fsCurrentPath;
            closeFsModal();
        }

        async function runScript() {
            if (!currentScript) return;
            
            const btn = document.getElementById('run-btn');
            const outputBox = document.getElementById('script-output');
            
            let argsArr = [];
            const formDiv = document.getElementById('dynamic-form');
            formDiv.querySelectorAll('input, select').forEach(el => {
                const flag = el.getAttribute('data-flag');
                const isPos = el.getAttribute('data-is-pos') === 'true';
                
                if (el.type === 'checkbox') {
                    if (el.checked && flag) argsArr.push(flag);
                } else if (el.value.trim() !== '') {
                    if (flag) argsArr.push(flag);
                    argsArr.push(el.value.trim());
                }
            });

            const argsStr = argsArr.map(a => a.includes(' ') ? `"${a}"` : a).join(' ');

            btn.disabled = true;
            btn.innerText = "Executando...";
            outputBox.innerText = "Rodando: venv python " + currentScript + " " + argsStr + "\\n\\n...";

            try {
                const formData = new FormData();
                formData.append('script', currentScript);
                formData.append('args', args);

                const res = await fetch('/run', { method: 'POST', body: formData });
                const data = await res.json();
                outputBox.innerText = data.output;
            } catch (err) {
                outputBox.innerText = "Erro ao executar: " + err;
            }

            btn.disabled = false;
            btn.innerText = "Executar";
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    # Pega todos os arquivos .py do diretório atual, exceto este próprio web-ui.py
    scripts = [f for f in os.listdir('.') if f.endswith('.py') and f != os.path.basename(__file__)]
    scripts.sort()
    return render_template_string(HTML_TEMPLATE, scripts=scripts)

@app.route('/fs')
def file_system():
    req_path = request.args.get('path', '.')
    if not req_path.strip():
        req_path = '.'
    try:
        abs_path = os.path.abspath(req_path)
        if not os.path.exists(abs_path):
            abs_path = os.path.abspath('.')
        items = os.listdir(abs_path)
        dirs = [d for d in items if os.path.isdir(os.path.join(abs_path, d))]
        files = [f for f in items if os.path.isfile(os.path.join(abs_path, f))]
        dirs.sort()
        files.sort()
        return jsonify({"current": abs_path, "dirs": dirs, "files": files})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/schema')
def get_schema():
    script = request.args.get('script')
    if not script or not os.path.exists(script):
        return jsonify({"help": "Script não encontrado.", "args": []})
    
    try:
        res = subprocess.run([PYTHON_CMD, script, '--help'], capture_output=True, text=True, timeout=5)
        help_text = res.stdout or res.stderr
        
        args_schema = extract_script_args(script)
        return jsonify({"help": help_text, "args": args_schema})
    except Exception as e:
        return jsonify({"help": f"Erro ao obter ajuda: {str(e)}", "args": []})

@app.route('/run', methods=['POST'])
def run_script():
    script = request.form.get('script')
    args_str = request.form.get('args', '')

    if not script or not os.path.exists(script):
        return jsonify({"output": "Script inválido."})

    cmd = [PYTHON_CMD, script]
    if args_str:
        cmd.extend(shlex.split(args_str))

    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        out = res.stdout
        if res.stderr:
            out += "\n--- ERROS / AVISOS ---\n" + res.stderr
        
        if not out.strip():
            out = "Comando executado sem retorno de texto."
            
        return jsonify({"output": out})
    except Exception as e:
        return jsonify({"output": f"Falha na execução: {str(e)}"})

@app.route('/install', methods=['POST'])
def install_deps():
    try:
        pip_cmd = [PYTHON_CMD, '-m', 'pip', 'install', '-r', 'requirements.txt']
        res = subprocess.run(pip_cmd, capture_output=True, text=True)
        out = res.stdout
        if res.stderr:
            out += "\n--- ERROS / AVISOS ---\n" + res.stderr
        return jsonify({"output": out})
    except Exception as e:
        return jsonify({"output": f"Falha na instalação: {str(e)}"})

if __name__ == '__main__':
    print("Iniciando interface web...")
    print("Acesse no seu navegador: http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
