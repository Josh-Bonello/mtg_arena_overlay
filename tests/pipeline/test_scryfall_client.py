"""Tests for pipeline/cards/scryfall_client.py"""
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import responses as resp_lib

import pipeline.cards.scryfall_client as sc

BASE = "https://api.scryfall.com"


def _fresh_cache_dir(tmp_path):
    cache_dir = tmp_path / "card_cache"
    sc.CACHE_DIR = cache_dir
    return cache_dir


# ---------------------------------------------------------------------------
# get_card_names
# ---------------------------------------------------------------------------

@resp_lib.activate
def test_get_card_names_fetches_and_caches(tmp_path):
    _fresh_cache_dir(tmp_path)
    resp_lib.add(resp_lib.GET, f"{BASE}/catalog/card-names",
                 json={"data": ["Lightning Bolt", "Counterspell"]})

    result = sc.get_card_names()
    assert result == ["Lightning Bolt", "Counterspell"]

    cache = sc.CACHE_DIR / "card_names.json"
    assert cache.exists()
    assert json.loads(cache.read_text()) == ["Lightning Bolt", "Counterspell"]
    assert len(resp_lib.calls) == 1


@resp_lib.activate
def test_get_card_names_uses_cache_when_fresh(tmp_path):
    cache_dir = _fresh_cache_dir(tmp_path)
    cache_dir.mkdir(parents=True)
    cache = cache_dir / "card_names.json"
    cache.write_text(json.dumps(["Cached Card"]))

    result = sc.get_card_names()
    assert result == ["Cached Card"]
    assert len(resp_lib.calls) == 0


@resp_lib.activate
def test_get_card_names_refetches_when_stale(tmp_path):
    cache_dir = _fresh_cache_dir(tmp_path)
    cache_dir.mkdir(parents=True)
    cache = cache_dir / "card_names.json"
    cache.write_text(json.dumps(["Old Card"]))

    stale_time = time.time() - (8 * 24 * 3600)
    import os
    os.utime(cache, (stale_time, stale_time))

    resp_lib.add(resp_lib.GET, f"{BASE}/catalog/card-names",
                 json={"data": ["New Card"]})

    result = sc.get_card_names()
    assert result == ["New Card"]
    assert len(resp_lib.calls) == 1


# ---------------------------------------------------------------------------
# get_set_card_names
# ---------------------------------------------------------------------------

@resp_lib.activate
def test_get_set_card_names_single_page(tmp_path):
    _fresh_cache_dir(tmp_path)
    resp_lib.add(resp_lib.GET, f"{BASE}/cards/search",
                 json={"data": [{"name": "Mosswood Drifter"}, {"name": "Pawpatch Formation"}],
                       "has_more": False})

    result = sc.get_set_card_names("BLB")
    assert "Mosswood Drifter" in result
    assert len(resp_lib.calls) == 1


@resp_lib.activate
def test_get_set_card_names_paginates(tmp_path):
    _fresh_cache_dir(tmp_path)
    resp_lib.add(resp_lib.GET, f"{BASE}/cards/search",
                 json={"data": [{"name": "Card A"}], "has_more": True})
    resp_lib.add(resp_lib.GET, f"{BASE}/cards/search",
                 json={"data": [{"name": "Card B"}], "has_more": False})

    result = sc.get_set_card_names("TST")
    assert result == ["Card A", "Card B"]
    assert len(resp_lib.calls) == 2


@resp_lib.activate
def test_get_set_card_names_uses_cache(tmp_path):
    cache_dir = _fresh_cache_dir(tmp_path)
    cache_dir.mkdir(parents=True)
    (cache_dir / "set_dsk.json").write_text(json.dumps(["Cackling Boneshard"]))

    result = sc.get_set_card_names("DSK")
    assert result == ["Cackling Boneshard"]
    assert len(resp_lib.calls) == 0


# ---------------------------------------------------------------------------
# get_oracle_bulk
# ---------------------------------------------------------------------------

@resp_lib.activate
def test_get_oracle_bulk_downloads_and_caches(tmp_path):
    _fresh_cache_dir(tmp_path)
    bulk_data = [{"id": "1", "name": "Lightning Bolt", "type_line": "Instant"}]

    resp_lib.add(resp_lib.GET, f"{BASE}/bulk-data",
                 json={"data": [{"type": "oracle_cards",
                                 "download_uri": "https://data.scryfall.io/oracle.json"}]})
    resp_lib.add(resp_lib.GET, "https://data.scryfall.io/oracle.json",
                 json=bulk_data)

    path = sc.get_oracle_bulk()
    assert path.exists()
    assert json.loads(path.read_text()) == bulk_data


@resp_lib.activate
def test_get_oracle_bulk_uses_cache_when_fresh(tmp_path):
    cache_dir = _fresh_cache_dir(tmp_path)
    cache_dir.mkdir(parents=True)
    cache = cache_dir / "oracle.json"
    cache.write_text(json.dumps([{"name": "Cached"}]))

    path = sc.get_oracle_bulk()
    assert path == cache
    assert len(resp_lib.calls) == 0


@resp_lib.activate
def test_get_oracle_bulk_raises_if_entry_missing(tmp_path):
    _fresh_cache_dir(tmp_path)
    resp_lib.add(resp_lib.GET, f"{BASE}/bulk-data",
                 json={"data": [{"type": "all_cards",
                                 "download_uri": "https://data.scryfall.io/all.json"}]})

    with pytest.raises(RuntimeError, match="oracle_cards"):
        sc.get_oracle_bulk()


# ---------------------------------------------------------------------------
# get_card
# ---------------------------------------------------------------------------

@resp_lib.activate
def test_get_card_fetches_and_caches(tmp_path):
    _fresh_cache_dir(tmp_path)
    card_data = {"name": "Lightning Bolt", "mana_cost": "{R}"}
    resp_lib.add(resp_lib.GET, f"{BASE}/cards/named",
                 json=card_data)

    result = sc.get_card("Lightning Bolt")
    assert result["name"] == "Lightning Bolt"

    slug_cache = sc.CACHE_DIR / "cards" / "lightning_bolt.json"
    assert slug_cache.exists()


@resp_lib.activate
def test_get_card_uses_cache(tmp_path):
    cache_dir = _fresh_cache_dir(tmp_path)
    (cache_dir / "cards").mkdir(parents=True)
    (cache_dir / "cards" / "lightning_bolt.json").write_text(
        json.dumps({"name": "Lightning Bolt", "mana_cost": "{R}"})
    )

    result = sc.get_card("Lightning Bolt")
    assert result["name"] == "Lightning Bolt"
    assert len(resp_lib.calls) == 0


@resp_lib.activate
def test_get_card_returns_none_on_404(tmp_path):
    _fresh_cache_dir(tmp_path)
    resp_lib.add(resp_lib.GET, f"{BASE}/cards/named",
                 json={"object": "error", "status": 404}, status=404)

    result = sc.get_card("NotARealCard XYZ")
    assert result is None
