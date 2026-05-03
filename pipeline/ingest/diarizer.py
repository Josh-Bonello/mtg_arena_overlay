"""Speaker diarization for podcast transcripts using pyannote.audio.

IMPORTANT: After running diarization, manual speaker verification is required
before corpus/formatter.py can process any episodes from that show.
See data/speaker_map/{show}.json and the MissingSpeakerMapError below.
"""
import json
import os
from pathlib import Path

DIARIZED_DIR = Path("data/diarized")
SPEAKER_MAP_DIR = Path("data/speaker_map")


class MissingSpeakerMapError(Exception):
    """Raised when corpus formatting is attempted without a verified speaker map."""


def _load_pyannote_pipeline():
    """Load pyannote diarization pipeline. Requires PYANNOTE_AUTH_TOKEN env var."""
    from pyannote.audio import Pipeline  # imported lazily so tests can mock

    token = os.environ.get("PYANNOTE_AUTH_TOKEN")
    if not token:
        raise EnvironmentError("PYANNOTE_AUTH_TOKEN environment variable not set.")
    return Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=token,
    )


def diarize(audio_path: Path, transcript: dict) -> dict:
    """Add speaker_id to each transcript segment. Returns updated transcript dict."""
    audio_path = Path(audio_path)
    pipeline = _load_pyannote_pipeline()

    diarization = pipeline(str(audio_path), num_speakers=2)

    # Build timeline: list of (start, end, speaker_label)
    timeline = [
        (turn.start, turn.end, speaker)
        for turn, _, speaker in diarization.itertracks(yield_label=True)
    ]

    segments = transcript.get("segments", [])
    for seg in segments:
        seg_mid = (seg["start"] + seg["end"]) / 2
        speaker = _assign_speaker(seg_mid, timeline)
        seg["speaker_id"] = speaker

    result = dict(transcript)
    result["segments"] = segments

    # Console sample — 5 diarized segments
    print("\n  Diarization sample (first 5 segments):")
    for seg in segments[:5]:
        print(f"    [{seg.get('speaker_id', '?')}] "
              f"[{seg['start']:.1f}s–{seg['end']:.1f}s] "
              f"{seg['text'][:80]}")

    show = transcript.get("show")
    episode_number = transcript.get("episode_number")
    if show and episode_number:
        DIARIZED_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DIARIZED_DIR / f"{show}_{episode_number}.json"
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\n  Saved diarized transcript: {out_path}")

    return result


def _assign_speaker(timestamp: float, timeline: list[tuple]) -> str:
    """Assign a speaker label to a timestamp using the diarization timeline."""
    for start, end, speaker in timeline:
        if start <= timestamp <= end:
            return speaker
    # Fall back to nearest segment
    if not timeline:
        return "SPEAKER_00"
    nearest = min(timeline, key=lambda t: abs((t[0] + t[1]) / 2 - timestamp))
    return nearest[2]


def load_speaker_map(show: str) -> dict:
    """Load verified speaker map for a show. Raises MissingSpeakerMapError if absent."""
    path = SPEAKER_MAP_DIR / f"{show}.json"
    if not path.exists():
        raise MissingSpeakerMapError(
            f"Speaker map for '{show}' not found at {path}.\n"
            f"Manual verification is required before corpus formatting:\n"
            f"  1. Run diarization on 3-5 episodes\n"
            f"  2. Listen to verify which SPEAKER_XX label is which host\n"
            f"  3. Create {path} with: {{\"SPEAKER_00\": \"ben\", \"SPEAKER_01\": \"ethan\"}}\n"
            f"  4. Re-run corpus formatting"
        )
    with open(path) as f:
        return json.load(f)
