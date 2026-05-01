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
