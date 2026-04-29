#!/usr/bin/env python3
"""
prompt_ui.py — Helper module for scripts that need interactive prompts.

This module supports TWO transport modes, auto-detected at call time:

1. **Web-UI mode (pipe)** — when stdin is NOT a TTY (i.e. the script is being
   driven by `web-ui.py`), prompts are emitted as `__UI_PROMPT__{json}` lines
   on stdout. The UI parses them, renders buttons/inputs, and writes the
   response into the running process's stdin.

2. **Terminal mode (TTY)** — when stdin IS a TTY (the user ran the script
   directly from a shell), prompts are rendered as readable numbered menus
   with `input()`-based responses. Empty input on a confirm uses the default;
   `q` / `quit` / Ctrl-C cancels.

Public helpers:
    choice(prompt, options, allow_back=False) -> int   # 0-based index, -1 = back
    confirm(prompt, default=True) -> bool
    text(prompt, default="", placeholder="") -> str
    menu(prompt, options) -> str                       # returns chosen key

This module is NOT a runnable script — it is imported by sibling scripts.
"""

import json
import sys
import uuid


PROMPT_MARKER = "__UI_PROMPT__"
CANCEL_TOKEN  = "__CANCEL__"
BACK_TOKEN    = "__BACK__"


# ── transport detection ──────────────────────────────────────────────────────

def _is_tty() -> bool:
    """True when running attached to a real terminal (not piped to web-ui)."""
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


# ── shared transport (web-ui pipe mode) ──────────────────────────────────────

def _ask_pipe(payload: dict) -> str:
    payload.setdefault("id", uuid.uuid4().hex[:8])
    sys.stdout.write(PROMPT_MARKER + json.dumps(payload) + "\n")
    sys.stdout.flush()

    line = sys.stdin.readline()
    if not line:
        # stdin closed — caller cancelled or web-ui detached
        print("\nCancelled (stdin closed).", file=sys.stderr)
        sys.exit(0)

    response = line.rstrip("\r\n")
    if response == CANCEL_TOKEN:
        print("\nCancelled.")
        sys.exit(0)
    return response


# ── TTY transport (direct terminal use) ──────────────────────────────────────

def _tty_input(prompt: str) -> str:
    """input() with Ctrl-C / EOF treated as cancel."""
    try:
        return input(prompt)
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        sys.exit(0)


def _tty_choice(prompt: str, options: list, allow_back: bool) -> int:
    print(f"\n  {prompt}")
    for i, opt in enumerate(options, 1):
        print(f"    {i}. {opt}")
    if allow_back:
        print(f"    b. ← Back")
    print(f"    q. ✕ Cancel")

    while True:
        resp = _tty_input("  > ").strip().lower()
        if resp in ("q", "quit", "cancel", "exit"):
            print("Cancelled.")
            sys.exit(0)
        if allow_back and resp in ("b", "back"):
            return -1
        if resp.isdigit():
            idx = int(resp) - 1
            if 0 <= idx < len(options):
                return idx
        print(f"  Invalid choice — type 1-{len(options)}"
              + (", b" if allow_back else "")
              + ", or q.")


def _tty_confirm(prompt: str, default: bool) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    while True:
        resp = _tty_input(f"\n  {prompt}{suffix} ").strip().lower()
        if resp == "":
            return default
        if resp in ("y", "yes", "1", "true"):
            return True
        if resp in ("n", "no", "0", "false"):
            return False
        if resp in ("q", "quit", "cancel"):
            print("Cancelled.")
            sys.exit(0)
        print("  Please answer y or n (Enter for default).")


def _tty_text(prompt: str, default: str, placeholder: str) -> str:
    hint = ""
    if default:
        hint = f" [{default}]"
    elif placeholder:
        hint = f" (e.g. {placeholder})"
    resp = _tty_input(f"\n  {prompt}{hint} ").rstrip("\r\n")
    if resp == "" and default:
        return default
    return resp


def _tty_menu(prompt: str, options: list) -> str:
    print(f"\n  {prompt}")
    for i, opt in enumerate(options, 1):
        label = opt.get("label", opt["key"])
        hint  = opt.get("hint", "")
        line  = f"    {i}. {label}"
        if hint:
            line += f"  — {hint}"
        print(line)
    print(f"    q. ✕ Cancel")

    while True:
        resp = _tty_input("  > ").strip().lower()
        if resp in ("q", "quit", "cancel"):
            print("Cancelled.")
            sys.exit(0)
        if resp.isdigit():
            idx = int(resp) - 1
            if 0 <= idx < len(options):
                return options[idx]["key"]
        # accept exact key match too
        for opt in options:
            if resp == opt["key"].lower():
                return opt["key"]
        print(f"  Invalid choice — type 1-{len(options)} or q.")


# ── public API ───────────────────────────────────────────────────────────────

def choice(prompt: str, options: list, allow_back: bool = False) -> int:
    """
    Numbered choice menu. Returns 0-based index of selected option.
    Returns -1 if `allow_back` is True and the user chose "back".
    """
    labels = [str(o) for o in options]

    if _is_tty():
        return _tty_choice(prompt, labels, allow_back)

    resp = _ask_pipe({
        "type":       "choice",
        "prompt":     prompt,
        "options":    labels,
        "allow_back": bool(allow_back),
    })
    if allow_back and resp == BACK_TOKEN:
        return -1
    try:
        idx = int(resp)
        if 0 <= idx < len(labels):
            return idx
    except ValueError:
        pass
    print(f"Invalid choice response: {resp!r}", file=sys.stderr)
    sys.exit(1)


def confirm(prompt: str, default: bool = True) -> bool:
    """Yes/no question."""
    if _is_tty():
        return _tty_confirm(prompt, default)

    resp = _ask_pipe({
        "type":    "confirm",
        "prompt":  prompt,
        "default": bool(default),
    }).strip().lower()
    if resp in ("y", "yes", "true", "1"):
        return True
    if resp in ("n", "no", "false", "0"):
        return False
    return default


def text(prompt: str, default: str = "", placeholder: str = "") -> str:
    """Free text input. Returns the user's string (may be empty)."""
    if _is_tty():
        return _tty_text(prompt, str(default), str(placeholder))

    return _ask_pipe({
        "type":        "text",
        "prompt":      prompt,
        "default":     str(default),
        "placeholder": str(placeholder),
    })


def menu(prompt: str, options: list) -> str:
    """
    Action menu with semantic keys (e.g. confirm/edit/quit). Returns the
    chosen key string.

    options: list of dicts with shape:
        {"key": "confirm", "label": "Confirm and proceed", "hint": "..."}
    """
    if _is_tty():
        return _tty_menu(prompt, options)

    resp = _ask_pipe({
        "type":    "menu",
        "prompt":  prompt,
        "options": options,
    }).strip()
    valid_keys = {opt["key"] for opt in options}
    if resp in valid_keys:
        return resp
    # accept exact label match too, for flexibility
    for opt in options:
        if resp == opt.get("label"):
            return opt["key"]
    print(f"Invalid menu response: {resp!r}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    print("prompt_ui.py is a helper module — import it from another script.",
          file=sys.stderr)
    sys.exit(1)
