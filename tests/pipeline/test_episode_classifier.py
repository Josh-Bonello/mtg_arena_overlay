"""Tests for pipeline/ingest/episode_classifier.py"""
import pytest
from pipeline.ingest.episode_classifier import classify_episode

EMPTY_TRANSCRIPT = {"full_text": ""}


def meta(title, description=""):
    return {"title": title, "description": description}


class TestCrashCourse:
    def test_first_impressions_in_title(self):
        assert classify_episode(meta("Bloomburrow First Impressions"), EMPTY_TRANSCRIPT) == "crash_course"

    def test_crash_course_in_title(self):
        assert classify_episode(meta("DSK Crash Course"), EMPTY_TRANSCRIPT) == "crash_course"

    def test_preview_show_in_title(self):
        assert classify_episode(meta("OTJ Preview Show"), EMPTY_TRANSCRIPT) == "crash_course"

    def test_set_preview_in_description(self):
        assert classify_episode(meta("Episode 423", "Early look at the new set"), EMPTY_TRANSCRIPT) == "crash_course"


class TestRareReview:
    def test_rare_review_in_title(self):
        assert classify_episode(meta("Bloomburrow Rare Review"), EMPTY_TRANSCRIPT) == "rare_review"

    def test_set_review_in_title(self):
        assert classify_episode(meta("OTJ Set Review Part 1"), EMPTY_TRANSCRIPT) == "rare_review"

    def test_card_ratings_in_title(self):
        assert classify_episode(meta("Card Ratings: Duskmourn"), EMPTY_TRANSCRIPT) == "rare_review"


class TestFormatRetrospective:
    def test_retrospective_in_title(self):
        assert classify_episode(meta("BLB Format Retrospective"), EMPTY_TRANSCRIPT) == "format_retrospective"

    def test_looking_back_in_title(self):
        assert classify_episode(meta("Looking Back at DSK"), EMPTY_TRANSCRIPT) == "format_retrospective"

    def test_format_wrap_in_title(self):
        assert classify_episode(meta("Format Wrap: MKM"), EMPTY_TRANSCRIPT) == "format_retrospective"


class TestArchetypeAnalysis:
    def test_archetype_in_title(self):
        assert classify_episode(meta("The Best Archetypes in DSK"), EMPTY_TRANSCRIPT) == "archetype_analysis"

    def test_color_pair_in_title(self):
        assert classify_episode(meta("Ranking Every Color Pair in BLB"), EMPTY_TRANSCRIPT) == "archetype_analysis"


class TestDraftLog:
    def test_pack_pick_pattern_in_transcript(self):
        transcript = {"full_text": "OK so pack 1 pick 3, we have this pack in front of us."}
        assert classify_episode(meta("Episode 400"), transcript) == "draft_log"

    def test_p1p1_shorthand(self):
        transcript = {"full_text": "P1P1 I'm taking the bomb rare here."}
        assert classify_episode(meta("Episode 401"), transcript) == "draft_log"


class TestUnknown:
    def test_no_match_returns_unknown(self):
        result = classify_episode(meta("General Strategy Talk"), {"full_text": "just chatting"})
        assert result == "unknown"

    def test_unknown_does_not_raise(self):
        result = classify_episode({}, {})
        assert result == "unknown"

    def test_none_values_dont_raise(self):
        result = classify_episode({"title": None, "description": None}, {"full_text": None})
        assert result == "unknown"


class TestTitlePriority:
    def test_title_beats_transcript(self):
        # Title says crash_course, transcript has draft_log patterns
        transcript = {"full_text": "pack 1 pick 1, let's go"}
        result = classify_episode(meta("Bloomburrow First Impressions"), transcript)
        assert result == "crash_course"
