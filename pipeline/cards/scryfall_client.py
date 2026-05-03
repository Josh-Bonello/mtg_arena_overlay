"""Scryfall API client with disk caching and rate limiting."""
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

_BASE = "https://api.scryfall.com"
_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = "mtg-agent-trainer/1.0"

CACHE_DIR = Path("data/card_cache")

_WEEKLY = 7 * 24 * 3600
_DAILY = 24 * 3600


def _is_stale(path: Path, ttl: int) -> bool:
    if not path.exists():
        return True
    age = datetime.now(timezone.utc).timestamp() - path.stat().st_mtime
    return age > ttl


def _get(url: str, **params) -> dict:
    time.sleep(random.uniform(0.05, 0.10))
    resp = _SESSION.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_card_names() -> list[str]:
    """Return all ~30k oracle card names. Cached weekly."""
    cache = CACHE_DIR / "card_names.json"
    if not _is_stale(cache, _WEEKLY):
        return json.loads(cache.read_text(encoding="utf-8"))

    data = _get(f"{_BASE}/catalog/card-names")
    names: list[str] = data["data"]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(names, ensure_ascii=False), encoding="utf-8")
    print(f"  [scryfall] card_names: {len(names)} names cached to {cache}")
    return names


def get_set_card_names(set_code: str) -> list[str]:
    """Return all card names for a given set (used for Whisper prompt seeding)."""
    cache = CACHE_DIR / f"set_{set_code.lower()}.json"
    if not _is_stale(cache, _WEEKLY):
        return json.loads(cache.read_text(encoding="utf-8"))

    names: list[str] = []
    url = f"{_BASE}/cards/search"
    params: dict = {"q": f"set:{set_code}", "page": 1}
    while True:
        data = _get(url, **params)
        names.extend(c["name"] for c in data.get("data", []))
        if not data.get("has_more"):
            break
        params["page"] += 1

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(names, ensure_ascii=False), encoding="utf-8")
    print(f"  [scryfall] {set_code}: {len(names)} cards cached to {cache}")
    return names


def get_oracle_bulk() -> Path:
    """Download the oracle-cards bulk JSON. Cached daily. Returns local path."""
    cache = CACHE_DIR / "oracle.json"
    if not _is_stale(cache, _DAILY):
        return cache

    bulk_index = _get(f"{_BASE}/bulk-data")
    download_url = None
    for entry in bulk_index.get("data", []):
        if entry.get("type") == "oracle_cards":
            download_url = entry["download_uri"]
            break
    if not download_url:
        raise RuntimeError("oracle_cards bulk-data entry not found")

    time.sleep(random.uniform(0.05, 0.10))
    resp = _SESSION.get(download_url, timeout=120, stream=True)
    resp.raise_for_status()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with cache.open("wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)

    size_mb = cache.stat().st_size / 1_048_576
    cards = json.loads(cache.read_text(encoding="utf-8"))
    print(
        f"  [scryfall] oracle bulk: {len(cards)} cards, "
        f"{size_mb:.1f} MB, saved to {cache}"
    )
    return cache


def get_card(name: str) -> dict | None:
    """Fuzzy-search a single card by name. Caches individual lookups."""
    slug = name.lower().replace(" ", "_").replace("/", "_")[:80]
    cache = CACHE_DIR / "cards" / f"{slug}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    try:
        data = _get(f"{_BASE}/cards/named", fuzzy=name)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return None
        raise

    (CACHE_DIR / "cards").mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data
