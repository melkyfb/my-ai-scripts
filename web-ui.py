#!/usr/bin/env python3
"""
web-ui.py — Web interface to run local python scripts.

Requires: pip install flask
"""

import os
import shlex
import subprocess
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

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
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input[type="text"] { width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
        button { background: #28a745; color: white; border: none; padding: 10px 20px; font-size: 16px; border-radius: 4px; cursor: pointer; }
        button:hover { background: #218838; }
        pre { background: #1e1e1e; color: #d4d4d4; padding: 15px; border-radius: 4px; overflow-x: auto; white-space: pre-wrap; }
        .help-block { background: #e9ecef; color: #333; padding: 15px; border-radius: 4px; font-size: 0.9em; }
    </style>
</head>
<body>

    <div id="sidebar">
        <h2>Meus Scripts</h2>
        {% for script in scripts %}
            <div class="tab" onclick="selectScript('{{ script }}')" id="tab-{{ script|replace('.', '-') }}">{{ script }}</div>
        {% endfor %}
    </div>

    <div id="content">
        <h1 id="script-title">Selecione um script</h1>
        
        <div id="script-ui" class="hidden">
            <div class="form-group">
                <label>Ajuda / Uso do Script:</label>
                <pre class="help-block" id="script-help">Carregando...</pre>
            </div>

            <div class="form-group">
                <label for="script-args">Argumentos (Ex: https://... --output ./videos):</label>
                <input type="text" id="script-args" placeholder="Insira o link e/ou opções aqui...">
            </div>

            <button onclick="runScript()" id="run-btn">Executar</button>

            <div class="form-group" style="margin-top: 20px;">
                <label>Saída (Output):</label>
                <pre id="script-output">Aguardando execução...</pre>
            </div>
        </div>
    </div>

    <script>
        let currentScript = "";

        async function selectScript(script) {
            currentScript = script;
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.getElementById('tab-' + script.replace('.', '-')).classList.add('active');
            
            document.getElementById('script-title').innerText = script;
            document.getElementById('script-ui').classList.remove('hidden');
            document.getElementById('script-help').innerText = "Carregando opções...";
            document.getElementById('script-output').innerText = "Aguardando execução...";
            document.getElementById('script-args').value = "";

            const res = await fetch('/help?script=' + encodeURIComponent(script));
            const data = await res.json();
            document.getElementById('script-help').innerText = data.help || "Sem ajuda disponível.";
        }

        async function runScript() {
            if (!currentScript) return;
            
            const btn = document.getElementById('run-btn');
            const outputBox = document.getElementById('script-output');
            const args = document.getElementById('script-args').value;

            btn.disabled = true;
            btn.innerText = "Executando...";
            outputBox.innerText = "Rodando: python " + currentScript + " " + args + "\\n\\n...";

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

@app.route('/help')
def get_help():
    script = request.args.get('script')
    if not script or not os.path.exists(script):
        return jsonify({"help": "Script não encontrado."})
    
    try:
        # Tenta pegar o help do argparse do script
        res = subprocess.run(['python', script, '--help'], capture_output=True, text=True, timeout=5)
        return jsonify({"help": res.stdout or res.stderr})
    except Exception as e:
        return jsonify({"help": f"Erro ao obter ajuda: {str(e)}"})

@app.route('/run', methods=['POST'])
def run_script():
    script = request.form.get('script')
    args_str = request.form.get('args', '')

    if not script or not os.path.exists(script):
        return jsonify({"output": "Script inválido."})

    cmd = ['python', script]
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

if __name__ == '__main__':
    print("Iniciando interface web...")
    print("Acesse no seu navegador: http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
