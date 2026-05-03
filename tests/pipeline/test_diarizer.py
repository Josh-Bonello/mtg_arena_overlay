"""Tests for pipeline/ingest/diarizer.py"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.ingest.diarizer import (
    MissingSpeakerMapError,
    _assign_speaker,
    diarize,
    load_speaker_map,
)

TRANSCRIPT = {
    "show": "lords_of_limited",
    "episode_number": 423,
    "segments": [
        {"start": 0.0, "end": 4.0, "text": "Welcome to Lords of Limited."},
        {"start": 4.0, "end": 8.5, "text": "Today we cover Bloomburrow."},
        {"start": 8.5, "end": 14.0, "text": "I think this card is really strong."},
    ],
}

FAKE_DIARIZATION = [
    (0.0, 5.0, "SPEAKER_00"),
    (5.0, 15.0, "SPEAKER_01"),
]


def _make_fake_pipeline(turns):
    mock_pipeline = MagicMock()
    fake_turn_list = []
    for start, end, speaker in turns:
        turn = MagicMock()
        turn.start = start
        turn.end = end
        fake_turn_list.append((turn, None, speaker))
    mock_pipeline.return_value.itertracks.return_value = fake_turn_list
    return mock_pipeline


class TestAssignSpeaker:
    def test_assigns_correct_speaker(self):
        timeline = [(0.0, 5.0, "SPEAKER_00"), (5.0, 10.0, "SPEAKER_01")]
        assert _assign_speaker(2.0, timeline) == "SPEAKER_00"
        assert _assign_speaker(7.0, timeline) == "SPEAKER_01"

    def test_empty_timeline_returns_default(self):
        assert _assign_speaker(5.0, []) == "SPEAKER_00"

    def test_nearest_when_outside_all_ranges(self):
        timeline = [(0.0, 2.0, "SPEAKER_00"), (3.0, 5.0, "SPEAKER_01")]
        result = _assign_speaker(2.4, timeline)
        assert result in ("SPEAKER_00", "SPEAKER_01")


def _make_mock_pipeline(fake_diarization):
    """Create a mock pyannote pipeline whose __call__ result has the given turns."""
    mock_pipeline = MagicMock()
    fake_turns = []
    for start, end, speaker in fake_diarization:
        turn = MagicMock()
        turn.start = start
        turn.end = end
        fake_turns.append((turn, None, speaker))
    # pipeline(audio) returns mock_pipeline.return_value; .itertracks() on that
    mock_pipeline.return_value.itertracks.return_value = fake_turns
    return mock_pipeline


def test_diarize_adds_speaker_id_to_all_segments(tmp_path):
    mock_pipeline = _make_mock_pipeline(FAKE_DIARIZATION)

    with patch("pipeline.ingest.diarizer._load_pyannote_pipeline",
               return_value=mock_pipeline), \
         patch("pipeline.ingest.diarizer.DIARIZED_DIR", tmp_path / "diarized"):

        audio = tmp_path / "ep423.mp3"
        audio.write_bytes(b"FAKE")
        result = diarize(audio, TRANSCRIPT)

    segs = result["segments"]
    assert len(segs) == 3
    for seg in segs:
        assert "speaker_id" in seg
        assert seg["speaker_id"] in ("SPEAKER_00", "SPEAKER_01")


def test_diarize_assigns_correct_speakers(tmp_path):
    mock_pipeline = _make_mock_pipeline(FAKE_DIARIZATION)

    with patch("pipeline.ingest.diarizer._load_pyannote_pipeline",
               return_value=mock_pipeline), \
         patch("pipeline.ingest.diarizer.DIARIZED_DIR", tmp_path / "diarized"):

        audio = tmp_path / "ep.mp3"
        audio.write_bytes(b"FAKE")
        result = diarize(audio, TRANSCRIPT)

    # Segment midpoint 2.0s falls in SPEAKER_00's range (0–5)
    assert result["segments"][0]["speaker_id"] == "SPEAKER_00"
    # Segment midpoint 6.25s falls in SPEAKER_01's range (5–15)
    assert result["segments"][1]["speaker_id"] == "SPEAKER_01"


def test_diarize_writes_output_file(tmp_path):
    mock_pipeline_instance = _make_mock_pipeline([])

    with patch("pipeline.ingest.diarizer._load_pyannote_pipeline",
               return_value=mock_pipeline_instance), \
         patch("pipeline.ingest.diarizer.DIARIZED_DIR", tmp_path / "diarized"):

        audio = tmp_path / "ep.mp3"
        audio.write_bytes(b"FAKE")
        diarize(audio, TRANSCRIPT)

    out = tmp_path / "diarized" / "lords_of_limited_423.json"
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["show"] == "lords_of_limited"


def test_load_speaker_map_success(tmp_path):
    speaker_map_dir = tmp_path / "speaker_map"
    speaker_map_dir.mkdir()
    (speaker_map_dir / "lords_of_limited.json").write_text(
        json.dumps({"SPEAKER_00": "ben", "SPEAKER_01": "ethan"})
    )
    with patch("pipeline.ingest.diarizer.SPEAKER_MAP_DIR", speaker_map_dir):
        result = load_speaker_map("lords_of_limited")
    assert result["SPEAKER_00"] == "ben"
    assert result["SPEAKER_01"] == "ethan"


def test_load_speaker_map_missing_raises(tmp_path):
    with patch("pipeline.ingest.diarizer.SPEAKER_MAP_DIR", tmp_path / "speaker_map"):
        with pytest.raises(MissingSpeakerMapError) as exc_info:
            load_speaker_map("lords_of_limited")
    assert "Manual verification is required" in str(exc_info.value)
    assert "lords_of_limited" in str(exc_info.value)
