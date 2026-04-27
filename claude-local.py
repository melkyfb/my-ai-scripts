#!/usr/bin/env python3
"""
claude-local.py — Launch Claude Code backed by a local Ollama model.

Starts a litellm proxy that translates Anthropic Messages API calls into
Ollama requests, then runs the 'claude' CLI against it.

Default: deepseek-v3 with 64 k context window.

Requirements:
  pip install 'litellm[proxy]'
  ollama serve           (Ollama daemon must be running)
  ollama pull MODEL      (e.g. ollama pull deepseek-v3)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

DEFAULT_MODEL   = "deepseek-v3"
DEFAULT_CONTEXT = 64_000
PROXY_HOST      = "127.0.0.1"
PROXY_PORT      = 4001
OLLAMA_BASE     = "http://localhost:11434"

# Claude model names that Claude Code may send in requests; all get routed to
# the configured Ollama model so Claude Code works regardless of its default.
_CLAUDE_ALIASES = [
    "claude-opus-4-7",
    "claude-opus-4-5",
    "claude-sonnet-4-6",
    "claude-sonnet-4-5",
    "claude-haiku-4-5-20251001",
    "claude-haiku-4-5",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
]


def _die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def _get_json(url: str, timeout: int = 3) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def check_ollama(model: str) -> None:
    if _get_json(f"{OLLAMA_BASE}/api/tags") is None:
        _die(
            "Ollama is not running.\n"
            "  Start it with: ollama serve"
        )
    data = _get_json(f"{OLLAMA_BASE}/api/tags") or {}
    available = {m["name"].split(":")[0] for m in data.get("models", [])}
    if model.split(":")[0] not in available:
        _die(
            f"Model '{model}' is not available in Ollama.\n"
            f"  Pull it with: ollama pull {model}"
        )


def check_litellm() -> str:
    """Return path to the litellm binary, or exit with install instructions."""
    path = shutil.which("litellm")
    if path is None:
        _die(
            "litellm is not installed or not in PATH.\n"
            "  Install with: pip install 'litellm[proxy]'"
        )
    return path


def proxy_is_ready(port: int) -> bool:
    return _get_json(f"http://{PROXY_HOST}:{port}/health", timeout=2) is not None


def _write_config(model: str, context: int) -> str:
    """Write a litellm config that routes all Claude aliases → the Ollama model."""
    ollama_params = {
        "model": f"ollama/{model}",
        "api_base": OLLAMA_BASE,
        "num_ctx": context,
    }
    model_list = [
        {"model_name": model, "litellm_params": ollama_params},
        *[
            {"model_name": alias, "litellm_params": ollama_params}
            for alias in _CLAUDE_ALIASES
        ],
    ]
    config = {
        "model_list": model_list,
        "litellm_settings": {"drop_params": True},
    }
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="claude_local_", delete=False
    )
    json.dump(config, f)
    f.close()
    return f.name


def start_proxy(
    litellm_bin: str, model: str, port: int, context: int
) -> tuple[subprocess.Popen, str]:
    cfg = _write_config(model, context)
    proc = subprocess.Popen(
        [litellm_bin, "--config", cfg, "--port", str(port), "--host", PROXY_HOST],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(40):
        time.sleep(0.5)
        if proc.poll() is not None:
            os.unlink(cfg)
            _die(
                f"litellm proxy exited unexpectedly.\n"
                f"  Check if port {port} is already in use (try --port to change it)."
            )
        if proxy_is_ready(port):
            return proc, cfg
    proc.terminate()
    os.unlink(cfg)
    _die(f"Proxy did not become ready within 20 s (model: {model}, port: {port}).")
    raise SystemExit(1)  # unreachable; keeps type checker happy


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Launch Claude Code using a local Ollama model.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""\
defaults:
  model    {DEFAULT_MODEL}
  context  {DEFAULT_CONTEXT:,} tokens
  port     {PROXY_PORT}

examples:
  python claude-local.py
  python claude-local.py -m llama3.2
  python claude-local.py -m qwen2.5-coder:14b -c 32000
  python claude-local.py -m mistral --port 4002
""",
    )
    parser.add_argument(
        "-m", "--model", default=DEFAULT_MODEL, metavar="NAME",
        help=f"Ollama model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "-c", "--context", type=int, default=DEFAULT_CONTEXT, metavar="TOKENS",
        help=f"Context window in tokens (default: {DEFAULT_CONTEXT:,})",
    )
    parser.add_argument(
        "--port", type=int, default=PROXY_PORT, metavar="PORT",
        help=f"litellm proxy port (default: {PROXY_PORT})",
    )
    args = parser.parse_args()

    litellm_bin = check_litellm()
    check_ollama(args.model)

    proxy_proc: subprocess.Popen | None = None
    cfg_path: str | None = None

    if proxy_is_ready(args.port):
        print(
            f"  Warning: a service is already running on port {args.port}.\n"
            f"  It may not be configured for '{args.model}'. "
            f"Use --port to start a fresh proxy on a different port.\n"
        )
    else:
        print(
            f"  Starting litellm proxy  "
            f"model={args.model}  context={args.context:,} tokens  port={args.port}…",
            end=" ", flush=True,
        )
        proxy_proc, cfg_path = start_proxy(litellm_bin, args.model, args.port, args.context)
        print("ready.")

    env = os.environ.copy()
    env["ANTHROPIC_BASE_URL"] = f"http://{PROXY_HOST}:{args.port}"
    # The Anthropic SDK requires a non-empty key; the proxy ignores its value.
    env["ANTHROPIC_API_KEY"] = "ollama"

    print(f"\n  Claude Code → {args.model} @ Ollama\n")

    exit_code = 0
    try:
        result = subprocess.run(["claude"], env=env)
        exit_code = result.returncode
    except FileNotFoundError:
        print(
            "Error: 'claude' CLI not found.\n"
            "  Install Claude Code: https://claude.ai/code",
            file=sys.stderr,
        )
        exit_code = 1
    finally:
        if proxy_proc is not None:
            proxy_proc.terminate()
            proxy_proc.wait()
        if cfg_path is not None:
            try:
                os.unlink(cfg_path)
            except OSError:
                pass

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
