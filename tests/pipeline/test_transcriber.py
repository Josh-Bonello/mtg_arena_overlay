"""Tests for pipeline/ingest/transcriber.py"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import responses as resp_lib

from pipeline.ingest.transcriber import _build_whisper_prompt, _get_set_card_names, transcribe

SCRYFALL_PAGE1 = {
    "object": "list",
    "total_cards": 3,
    "has_more": False,
    "data": [
        {"name": "Abhorrent Oculus"},
        {"name": "Fear of Missing Out"},
        {"name": "Sheltered by Ghosts"},
    ],
}


class TestBuildWhisperPrompt:
    def test_basic_prompt(self):
        names = ["Lightning Bolt", "Counterspell", "Dark Ritual"]
        prompt = _build_whisper_prompt(names)
        assert "Lightning Bolt" in prompt
        assert "Counterspell" in prompt

    def test_truncates_at_token_limit(self):
        # Build a list big enough to exceed 448 tokens
        long_names = [f"Card Name Number {i} With Extra Words" for i in range(200)]
        prompt = _build_whisper_prompt(long_names)
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        assert len(enc.encode(prompt)) <= 448

    def test_empty_list(self):
        assert _build_whisper_prompt([]) == ""

    def test_single_name_no_trailing_comma(self):
        prompt = _build_whisper_prompt(["Lightning Bolt"])
        assert prompt == "Lightning Bolt"


@resp_lib.activate
def test_get_set_card_names():
    resp_lib.add(
        resp_lib.GET,
        "https://api.scryfall.com/cards/search",
        json=SCRYFALL_PAGE1,
        status=200,
    )
    names = _get_set_card_names("DSK")
    assert "Abhorrent Oculus" in names
    assert "Sheltered by Ghosts" in names
    assert len(names) == 3


@resp_lib.activate
def test_get_set_card_names_pagination():
    page1 = {
        "object": "list",
        "has_more": True,
        "next_page": "https://api.scryfall.com/cards/search?page=2",
        "data": [{"name": "Card A"}, {"name": "Card B"}],
    }
    page2 = {
        "object": "list",
        "has_more": False,
        "data": [{"name": "Card C"}],
    }
    resp_lib.add(resp_lib.GET, "https://api.scryfall.com/cards/search",
                 json=page1, status=200)
    resp_lib.add(resp_lib.GET, "https://api.scryfall.com/cards/search?page=2",
                 json=page2, status=200)
    names = _get_set_card_names("DSK")
    assert names == ["Card A", "Card B", "Card C"]


@resp_lib.activate
def test_transcribe_with_set_code(tmp_path):
    resp_lib.add(
        resp_lib.GET,
        "https://api.scryfall.com/cards/search",
        json=SCRYFALL_PAGE1,
        status=200,
    )

    fake_whisper_result = {
        "text": "Welcome to Lords of Limited. Today we cover Bloomburrow.",
        "segments": [
            {"start": 0.0, "end": 4.2, "text": " Welcome to Lords of Limited."},
            {"start": 4.2, "end": 8.0, "text": " Today we cover Bloomburrow."},
        ],
    }
    mock_model = MagicMock()
    mock_model.transcribe.return_value = fake_whisper_result

    audio_file = tmp_path / "test_audio.mp3"
    audio_file.write_bytes(b"FAKE")

    with patch("pipeline.ingest.transcriber.TRANSCRIPT_DIR", tmp_path / "transcripts"), \
         patch.dict("sys.modules", {"whisper": MagicMock(load_model=MagicMock(return_value=mock_model))}):
        result = transcribe(
            audio_path=audio_file,
            set_code="DSK",
            show="lords_of_limited",
            episode_number=423,
        )

    assert result["set_code"] == "DSK"
    assert result["show"] == "lords_of_limited"
    assert result["episode_number"] == 423
    assert result["model"] == "large-v3"
    assert len(result["segments"]) == 2
    assert result["segments"][0]["text"] == "Welcome to Lords of Limited."
    assert "Welcome" in result["full_text"]

    # Whisper was called with initial_prompt containing card names
    call_kwargs = mock_model.transcribe.call_args[1]
    assert "initial_prompt" in call_kwargs
    assert "Abhorrent Oculus" in call_kwargs["initial_prompt"]


@resp_lib.activate
def test_transcribe_no_set_code(tmp_path):
    fake_result = {
        "text": "Just talking strategy.",
        "segments": [{"start": 0.0, "end": 5.0, "text": " Just talking strategy."}],
    }
    mock_model = MagicMock()
    mock_model.transcribe.return_value = fake_result

    audio_file = tmp_path / "test.mp3"
    audio_file.write_bytes(b"FAKE")

    with patch.dict("sys.modules", {"whisper": MagicMock(load_model=MagicMock(return_value=mock_model))}):
        result = transcribe(audio_path=audio_file)

    # No initial_prompt when set_code is None
    call_kwargs = mock_model.transcribe.call_args[1]
    assert "initial_prompt" not in call_kwargs
    assert result["set_code"] is None


def test_transcript_written_to_disk(tmp_path):
    fake_result = {
        "text": "Hello world.",
        "segments": [{"start": 0.0, "end": 2.0, "text": " Hello world."}],
    }
    mock_model = MagicMock()
    mock_model.transcribe.return_value = fake_result
    audio_file = tmp_path / "test.mp3"
    audio_file.write_bytes(b"FAKE")

    with patch("pipeline.ingest.transcriber.TRANSCRIPT_DIR", tmp_path / "transcripts"), \
         patch.dict("sys.modules", {"whisper": MagicMock(load_model=MagicMock(return_value=mock_model))}):
        transcribe(audio_path=audio_file, show="lords_of_limited", episode_number=50)

    out = tmp_path / "transcripts" / "lords_of_limited_50.json"
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["episode_number"] == 50
    assert data["model"] == "large-v3"
