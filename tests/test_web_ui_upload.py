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
