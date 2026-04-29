#!/usr/bin/env python3
"""
scribd-download.py — Baixar documentos do Scribd.

Requer:
  pip install requests beautifulsoup4
  Sistema: node, npm, git (para o motor de download)

Uso:
  python scribd-download.py <url> [-o output_dir]

Os prompts interativos são roteados através do prompt_ui:
  - Quando executado via web-ui.py, viram botões na interface.
  - Quando executado no terminal, viram menus numerados.
"""

import argparse
import os
import re
import sys
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Erro: dependências ausentes.\nExecute: pip install requests beautifulsoup4", file=sys.stderr)
    sys.exit(1)

from prompt_ui import choice, text


def get_document_info(url: str) -> dict:
    try:
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        title_tag = soup.find('title')
        title = title_tag.text.replace(" | Scribd", "").strip() if title_tag else "Documento Desconhecido"
        
        match = re.search(r'scribd\.com/(?:doc|document|presentation)/(\d+)', url)
        doc_id = match.group(1) if match else "desconhecido"
        
        return {"title": title, "doc_id": doc_id, "url": url}
    except Exception as e:
        print(f"Erro ao analisar documento: {e}", file=sys.stderr)
        sys.exit(1)


def download_document(info: dict, output_dir: str):
    import shutil
    import subprocess
    
    if not shutil.which("node") or not shutil.which("npm"):
        print("Erro: node.js e npm são necessários para o motor de download.", file=sys.stderr)
        print("Instale o Node.js: https://nodejs.org/", file=sys.stderr)
        return

    if not shutil.which("git"):
        print("Erro: git é necessário para baixar a ferramenta base.", file=sys.stderr)
        return

    tool_dir = Path.home() / ".scribd-dl"
    if not tool_dir.exists():
        print("\nPrimeira execução: instalando o motor rkwyu/scribd-dl...")
        subprocess.run(["git", "clone", "https://github.com/rkwyu/scribd-dl.git", str(tool_dir)])
        print("\nInstalando dependências do scribd-dl (isso pode demorar um pouco)...")
        subprocess.run(["npm", "install"], cwd=tool_dir)

    print(f"\nBaixando '{info['title']}'...")
    
    # Configurar o scribd-dl para salvar no diretório escolhido via config.ini
    config_path = tool_dir / "config.ini"
    config_content = f"""[SCRIBD]
rendertime=100

[SLIDESHARE]
rendertime=100

[DIRECTORY]
output={Path(output_dir).absolute()}
filename=title
"""
    config_path.write_text(config_content, encoding="utf-8")
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    cmd = ["npm", "start", info['url']]
    subprocess.run(cmd, cwd=tool_dir)
        
    print(f"\nConcluído! Verifique o diretório: {output_dir}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Baixar documentos do scribd.com",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("url", help="URL do documento no Scribd")
    parser.add_argument("-o", "--output", default=".", metavar="DIR",
                        help="Diretório de saída (padrão: diretório atual)")
    args = parser.parse_args()

    if "scribd.com" not in args.url:
        print("Erro: A URL fornecida não parece ser do Scribd.", file=sys.stderr)
        sys.exit(1)

    # O scribd-dl exige que a URL comece com www.scribd.com (remover subdomínios como pt.)
    url = re.sub(r'https?://[^/]*scribd\.com', 'https://www.scribd.com', args.url)

    out = str(Path(args.output).expanduser().resolve())
    os.makedirs(out, exist_ok=True)

    print("\nAnalisando URL...")
    info = get_document_info(url)
    
    print(f"\n  Título : {info['title']}")
    print(f"  ID Doc : {info['doc_id']}")
    print(f"  Destino: {out}")
    
    opcoes = [
        "Baixar como PDF",
        "Mudar diretório de saída",
        "Cancelar"
    ]
    
    while True:
        idx = choice("O que você deseja fazer?", opcoes)
        
        if idx == 0:
            download_document(info, out)
            break
        elif idx == 1:
            novo_dir = text("Novo diretório de saída:", default=out)
            if novo_dir:
                out = str(Path(novo_dir).expanduser().resolve())
                os.makedirs(out, exist_ok=True)
                print(f"  Destino atualizado para: {out}")
        elif idx == 2:
            print("\nCancelado.")
            sys.exit(0)


if __name__ == "__main__":
    main()
