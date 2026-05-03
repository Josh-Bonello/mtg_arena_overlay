"""Verify repository structure: required dirs exist and __init__.py files are present."""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent

EXPECTED_PACKAGES = [
    "pipeline",
    "pipeline/ingest",
    "pipeline/cards",
    "pipeline/seventeen_lands",
    "pipeline/video",
    "pipeline/corpus",
    "agent",
    "agent/personas",
    "agent/cube",
    "tests",
    "tests/pipeline",
    "tests/agent",
]

EXPECTED_DATA_DIRS = [
    "data/format_profiles",
    "data/card_cache",
    "data/seventeen_lands_cache",
    "data/corpus",
    "data/transcripts",
    "data/audio",
    "data/video",
    "data/episode_metadata",
    "data/diarized",
    "data/speaker_map",
]


def test_package_dirs_exist():
    for pkg in EXPECTED_PACKAGES:
        assert (ROOT / pkg).is_dir(), f"Missing package directory: {pkg}"


def test_init_files_present():
    for pkg in EXPECTED_PACKAGES:
        init = ROOT / pkg / "__init__.py"
        assert init.exists(), f"Missing __init__.py in: {pkg}"


def test_data_dirs_exist():
    for d in EXPECTED_DATA_DIRS:
        assert (ROOT / d).is_dir(), f"Missing data directory: {d}"


def test_claude_md_present():
    assert (ROOT / "CLAUDE.md").exists(), "CLAUDE.md is missing from repo root"


def test_makefile_present():
    assert (ROOT / "Makefile").exists(), "Makefile is missing from repo root"


def test_example_format_profile_valid():
    path = ROOT / "data/format_profiles/EXAMPLE.json"
    assert path.exists(), "data/format_profiles/EXAMPLE.json is missing"
    with open(path) as f:
        data = json.load(f)
    required_keys = [
        "set_code", "event_type", "computed_at", "confidence",
        "format_type", "format_speed", "fixing_priority", "curve_priority",
        "stay_open_until_pick", "splash_threshold", "top_color_pairs",
        "color_pair_wrs", "archetypes", "17lands_available",
    ]
    for key in required_keys:
        assert key in data, f"EXAMPLE.json missing required key: {key}"
