# tests/test_media_server.py
"""
Tests for local media server (media_server.py) and prepare_timeline_audio delivery.
"""

import os
import shutil
import urllib.request
import urllib.error
import urllib.parse
import pytest

from media_server import start_media_server

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def media_server():
    host, port, token = start_media_server(BASE_DIR)
    return host, port, token


def test_file_inside_projects_is_served(media_server):
    host, port, token = media_server
    proj_dir = os.path.join(BASE_DIR, "projects", "_test_media_server_proj")
    os.makedirs(proj_dir, exist_ok=True)
    test_file = os.path.join(proj_dir, "sample.mp3")
    sample_bytes = b"ID3\x03\x00\x00\x00\x00\x00#dummy mp3 bytes for test"
    with open(test_file, "wb") as f:
        f.write(sample_bytes)

    try:
        url = f"http://{host}:{port}/media?token={token}&path={urllib.parse.quote(test_file)}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            assert "audio/mpeg" in resp.headers.get("Content-Type", "")
            content = resp.read()
            assert content == sample_bytes
    finally:
        shutil.rmtree(proj_dir, ignore_errors=True)


def test_config_settings_json_is_refused_with_403(media_server):
    host, port, token = media_server
    settings_file = os.path.join(BASE_DIR, "config", "settings.json")
    url = f"http://{host}:{port}/media?token={token}&path={urllib.parse.quote(settings_file)}"
    req = urllib.request.Request(url)
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == 403, f"Expected 403 Forbidden for config/settings.json, got {exc_info.value.code}"


def test_dot_dot_traversal_out_of_projects_is_refused_with_403(media_server):
    host, port, token = media_server
    traversal_path = os.path.join(BASE_DIR, "projects", "..", "config", "settings.json")
    url = f"http://{host}:{port}/media?token={token}&path={urllib.parse.quote(traversal_path)}"
    req = urllib.request.Request(url)
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == 403, f"Expected 403 for traversal path, got {exc_info.value.code}"


def test_missing_or_wrong_token_is_refused_with_403(media_server):
    host, port, token = media_server
    proj_dir = os.path.join(BASE_DIR, "projects", "_test_token_proj")
    os.makedirs(proj_dir, exist_ok=True)
    test_file = os.path.join(proj_dir, "test.mp3")
    with open(test_file, "wb") as f:
        f.write(b"dummy")

    try:
        # 1. Missing token
        url_no_token = f"http://{host}:{port}/media?path={urllib.parse.quote(test_file)}"
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(url_no_token)
        assert exc_info.value.code == 403

        # 2. Wrong token
        url_wrong_token = f"http://{host}:{port}/media?token=wrong-token-value&path={urllib.parse.quote(test_file)}"
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(url_wrong_token)
        assert exc_info.value.code == 403
    finally:
        shutil.rmtree(proj_dir, ignore_errors=True)


def test_range_request_returns_206_and_exact_slice(media_server):
    host, port, token = media_server
    proj_dir = os.path.join(BASE_DIR, "projects", "_test_range_proj")
    os.makedirs(proj_dir, exist_ok=True)
    test_file = os.path.join(proj_dir, "range_test.mp3")
    data = bytes(range(256)) * 4  # 1024 bytes
    with open(test_file, "wb") as f:
        f.write(data)

    try:
        start_byte = 100
        end_byte = 299
        expected_len = end_byte - start_byte + 1
        expected_slice = data[start_byte:end_byte + 1]

        url = f"http://{host}:{port}/media?token={token}&path={urllib.parse.quote(test_file)}"
        req = urllib.request.Request(url, headers={"Range": f"bytes={start_byte}-{end_byte}"})
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 206
            assert resp.headers.get("Content-Range") == f"bytes {start_byte}-{end_byte}/1024"
            assert resp.headers.get("Accept-Ranges") == "bytes"
            assert int(resp.headers.get("Content-Length")) == expected_len
            body = resp.read()
            assert body == expected_slice, "Served bytes do not match expected slice!"
    finally:
        shutil.rmtree(proj_dir, ignore_errors=True)


def test_prepare_timeline_audio_returns_http_and_never_file():
    from app import Api
    from pipeline.composer import _find_ffmpeg
    import subprocess

    api = Api()
    proj_dir = os.path.join(BASE_DIR, "projects", "_test_api_proj")
    os.makedirs(proj_dir, exist_ok=True)
    audio_path = os.path.join(proj_dir, "seg1.mp3")

    # Generate a real valid mp3 with ffmpeg
    ffmpeg = _find_ffmpeg()
    subprocess.run([
        ffmpeg, "-y",
        "-f", "lavfi",
        "-i", "sine=frequency=440:duration=2.0",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        audio_path
    ], capture_output=True, check=True)

    try:
        script_data = {
            "project": {"title": "Test HTTP Audio"},
            "segments": [{
                "segment_id": 1,
                "narration_audio": audio_path,
                "narration_seconds": 2.0,
            }]
        }
        res = api.prepare_timeline_audio(script_data, proj_dir)
        assert res.get("ok") is True
        src = res.get("src", "")
        assert src.startswith("http://127.0.0.1:"), f"Expected http://127.0.0.1 URL, got {src}"
        assert not src.startswith("file:"), f"URL must never start with file: - got {src}"
        assert "token=" in src, f"URL must contain token - got {src}"
    finally:
        shutil.rmtree(proj_dir, ignore_errors=True)