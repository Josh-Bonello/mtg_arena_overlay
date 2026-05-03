"""Tests for pipeline/ingest/audio_downloader.py"""
import pytest
import responses as resp_lib
from pathlib import Path
from requests.exceptions import ConnectionError as ReqConnError

from pipeline.ingest.audio_downloader import download_episode, _safe_filename

EPISODE = {
    "show": "lords_of_limited",
    "episode_number": 423,
    "title": "Bloomburrow First Impressions",
    "audio_url": "https://example.com/ep423.mp3",
}


class TestSafeFilename:
    def test_numbered_episode(self):
        assert _safe_filename("lords_of_limited", 423, "Any Title") == "lords_of_limited_423.mp3"

    def test_no_number_slugifies_title(self):
        result = _safe_filename("limited_resources", None, "Strategy Episode!")
        assert result.startswith("limited_resources_")
        assert result.endswith(".mp3")
        assert "!" not in result


@resp_lib.activate
def test_download_writes_file(tmp_path):
    resp_lib.add(resp_lib.GET, "https://example.com/ep423.mp3",
                 body=b"FAKE_AUDIO_DATA", status=200)
    dest = download_episode(EPISODE, output_dir=tmp_path)
    assert dest.exists()
    assert dest.name == "lords_of_limited_423.mp3"
    assert dest.read_bytes() == b"FAKE_AUDIO_DATA"


@resp_lib.activate
def test_skip_if_exists(tmp_path):
    existing = tmp_path / "lords_of_limited_423.mp3"
    existing.write_bytes(b"ALREADY_HERE")
    dest = download_episode(EPISODE, output_dir=tmp_path)
    assert dest == existing
    assert len(resp_lib.calls) == 0


@resp_lib.activate
def test_retry_on_connection_error(tmp_path):
    resp_lib.add(resp_lib.GET, "https://example.com/ep423.mp3",
                 body=ReqConnError("connection reset"))
    resp_lib.add(resp_lib.GET, "https://example.com/ep423.mp3",
                 body=b"RECOVERED_AUDIO", status=200)

    from unittest.mock import patch
    with patch("pipeline.ingest.audio_downloader.time.sleep"):
        dest = download_episode(EPISODE, output_dir=tmp_path)

    assert dest.exists()
    assert dest.read_bytes() == b"RECOVERED_AUDIO"
    assert len(resp_lib.calls) == 2
