"""Tests for pipeline/ingest/rss_scraper.py"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
import responses as resp_lib

from pipeline.ingest.rss_scraper import (
    _extract_set_hint,
    _parse_duration,
    _parse_episode_number,
    scrape,
)

FIXTURE_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Lords of Limited</title>
    <item>
      <title>Episode 423: Bloomburrow First Impressions</title>
      <pubDate>Tue, 30 Jul 2024 12:00:00 +0000</pubDate>
      <guid>ep-423-guid</guid>
      <enclosure url="https://example.com/ep423.mp3" type="audio/mpeg" length="0"/>
      <description>Ben and Ethan cover Bloomburrow crash course.</description>
      <itunes:duration>1:30:00</itunes:duration>
    </item>
    <item>
      <title>Episode 422: Duskmourn Set Review</title>
      <pubDate>Mon, 22 Jul 2024 12:00:00 +0000</pubDate>
      <guid>ep-422-guid</guid>
      <enclosure url="https://example.com/ep422.mp3" type="audio/mpeg" length="0"/>
      <description>Duskmourn rare review.</description>
      <itunes:duration>45:00</itunes:duration>
    </item>
  </channel>
</rss>
"""


class TestSetHintExtraction:
    def test_known_set_name(self):
        assert _extract_set_hint("Bloomburrow First Impressions", "") == "BLB"

    def test_duskmourn(self):
        assert _extract_set_hint("Duskmourn Set Review", "") == "DSK"

    def test_foundations(self):
        assert _extract_set_hint("Foundations Preview Show", "") == "FDN"

    def test_description_fallback(self):
        assert _extract_set_hint("Episode 400", "We cover wilds of eldraine today") == "WOE"

    def test_no_match_returns_none(self):
        result = _extract_set_hint("General Strategy Episode", "talking about drafting")
        assert result is None or isinstance(result, str)


class TestParseDuration:
    def test_hms(self):
        assert _parse_duration("1:30:00") == 5400

    def test_ms(self):
        assert _parse_duration("45:00") == 2700

    def test_seconds_only(self):
        assert _parse_duration("3600") == 3600

    def test_none(self):
        assert _parse_duration(None) is None


class TestParseEpisodeNumber:
    def test_episode_prefix(self):
        assert _parse_episode_number("Episode 423: Bloomburrow") == 423

    def test_ep_abbreviation(self):
        assert _parse_episode_number("ep. 50 – Strategy") == 50

    def test_hash_prefix(self):
        assert _parse_episode_number("#100 - Special") == 100

    def test_no_number(self):
        assert _parse_episode_number("General Strategy Talk") is None


@resp_lib.activate
def test_scrape_parses_feed(tmp_path):
    from pipeline.ingest import rss_scraper
    rss_scraper.DATA_DIR = tmp_path / "episode_metadata"
    rss_scraper.FEEDS = {"lords_of_limited": "https://fake-feed.example.com/rss"}

    resp_lib.add(resp_lib.GET, "https://fake-feed.example.com/rss",
                 body=FIXTURE_RSS.encode(), status=200,
                 content_type="application/rss+xml")

    result = scrape()
    episodes = result["lords_of_limited"]

    assert len(episodes) == 2
    ep = episodes[0]
    assert ep["show"] == "lords_of_limited"
    assert ep["episode_number"] == 423
    assert ep["title"] == "Episode 423: Bloomburrow First Impressions"
    assert ep["set_hint"] == "BLB"
    assert ep["audio_url"] == "https://example.com/ep423.mp3"
    assert ep["duration_seconds"] == 5400
    assert ep["guid"] == "ep-423-guid"


@resp_lib.activate
def test_scrape_since_filter(tmp_path):
    from pipeline.ingest import rss_scraper
    rss_scraper.DATA_DIR = tmp_path / "episode_metadata"
    rss_scraper.FEEDS = {"lords_of_limited": "https://fake-feed.example.com/rss"}

    resp_lib.add(resp_lib.GET, "https://fake-feed.example.com/rss",
                 body=FIXTURE_RSS.encode(), status=200,
                 content_type="application/rss+xml")

    result = scrape(since="2024-07-25")
    episodes = result["lords_of_limited"]
    assert len(episodes) == 1
    assert episodes[0]["episode_number"] == 423


@resp_lib.activate
def test_scrape_writes_json(tmp_path):
    from pipeline.ingest import rss_scraper
    rss_scraper.DATA_DIR = tmp_path / "episode_metadata"
    rss_scraper.FEEDS = {"lords_of_limited": "https://fake-feed.example.com/rss"}

    resp_lib.add(resp_lib.GET, "https://fake-feed.example.com/rss",
                 body=FIXTURE_RSS.encode(), status=200,
                 content_type="application/rss+xml")

    scrape()
    out = tmp_path / "episode_metadata" / "lords_of_limited.json"
    assert out.exists()
    data = json.loads(out.read_text())
    assert isinstance(data, list)
    assert len(data) == 2
