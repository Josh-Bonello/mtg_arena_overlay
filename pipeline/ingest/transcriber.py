"""Transcribe podcast audio with Whisper large-v3, seeded with MTG card names."""
import json
from datetime import datetime, timezone
from pathlib import Path

import requests
import tiktoken

TRANSCRIPT_DIR = Path("data/transcripts")
WHISPER_MODEL = "large-v3"
PROMPT_TOKEN_LIMIT = 448


def _get_set_card_names(set_code: str) -> list[str]:
    """Fetch card names for a set from Scryfall to use as Whisper prompt seed."""
    names = []
    url = "https://api.scryfall.com/cards/search"
    params = {"q": f"set:{set_code}", "unique": "names"}
    while url:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        names.extend(c["name"] for c in data.get("data", []))
        url = data.get("next_page")
        params = {}
    return names


def _build_whisper_prompt(card_names: list[str]) -> str:
    """Build comma-separated card name prompt, truncated to PROMPT_TOKEN_LIMIT tokens."""
    enc = tiktoken.get_encoding("cl100k_base")
    prompt_parts = []
    token_count = 0
    for name in card_names:
        candidate = f"{name}, " if prompt_parts else name
        tokens = len(enc.encode(candidate))
        if token_count + tokens > PROMPT_TOKEN_LIMIT:
            break
        prompt_parts.append(name)
        token_count += tokens
    return ", ".join(prompt_parts)


def transcribe(
    audio_path: Path,
    set_code: str | None = None,
    show: str | None = None,
    episode_number: int | None = None,
) -> dict:
    """Transcribe audio with Whisper large-v3. Returns transcript dict."""
    import whisper  # imported here so tests can mock without importing at module level

    audio_path = Path(audio_path)
    initial_prompt = None

    if set_code:
        print(f"  Fetching card names for {set_code} to seed Whisper prompt...")
        card_names = _get_set_card_names(set_code)
        initial_prompt = _build_whisper_prompt(card_names)
        enc = tiktoken.get_encoding("cl100k_base")
        token_count = len(enc.encode(initial_prompt))
        print(f"  Whisper prompt: {len(card_names)} cards, {token_count} tokens")

    print(f"  Loading Whisper {WHISPER_MODEL}...")
    model = whisper.load_model(WHISPER_MODEL)

    print(f"  Transcribing {audio_path.name}...")
    kwargs = {"language": "en", "task": "transcribe"}
    if initial_prompt:
        kwargs["initial_prompt"] = initial_prompt

    result = model.transcribe(str(audio_path), **kwargs)

    transcript = {
        "show": show,
        "episode_number": episode_number,
        "set_code": set_code,
        "transcribed_at": datetime.now(timezone.utc).isoformat(),
        "model": WHISPER_MODEL,
        "segments": [
            {"start": s["start"], "end": s["end"], "text": s["text"].strip()}
            for s in result["segments"]
        ],
        "full_text": result["text"].strip(),
    }

    # Console sample — first 3 segments
    print("\n  Transcript sample (first 3 segments):")
    for seg in transcript["segments"][:3]:
        print(f"    [{seg['start']:.1f}s] {seg['text'][:100]}")

    if show and episode_number:
        out_dir = TRANSCRIPT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{show}_{episode_number}.json"
        with open(out_path, "w") as f:
            json.dump(transcript, f, indent=2)
        print(f"\n  Saved transcript: {out_path}")

    return transcript
