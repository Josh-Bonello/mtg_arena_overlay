"""RSS scraper for Lords of Limited and Limited Resources podcast feeds."""
import argparse
import json
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree

import requests

FEEDS = {
    "lords_of_limited": "https://feeds.transistor.fm/lords-of-limited",
    "limited_resources": "https://feeds.libsyn.com/51742/rss",
}

SET_NAME_MAP = {
    "bloomburrow": "BLB",
    "duskmourn": "DSK",
    "foundations": "FDN",
    "murders at karlov manor": "MKM",
    "outlaws of thunder junction": "OTJ",
    "modern horizons 3": "MH3",
    "modern horizons 2": "MH2",
    "innistrad: midnight hunt": "MID",
    "innistrad: crimson vow": "VOW",
    "kamigawa: neon dynasty": "NEO",
    "streets of new capenna": "SNC",
    "dominaria united": "DMU",
    "the brothers' war": "BRO",
    "phyrexia: all will be one": "ONE",
    "march of the machine": "MOM",
    "wilds of eldraine": "WOE",
    "the lost caverns of ixalan": "LCI",
    "murders": "MKM",
    "thunder junction": "OTJ",
    "caverns of ixalan": "LCI",
    "strixhaven": "STX",
    "secrets of strixhaven": "STX",
    "tarkir": "TDM",
    "aetherdrift": "AED",
    "final fantasy": "FIN",
    "edge of eternities": "EOE",
    "amonkhet remastered": "AKR",
    "zendikar rising": "ZNR",
    "kaldheim": "KHM",
    "innistrad midnight hunt": "MID",
    "innistrad crimson vow": "VOW",
    "new capenna": "SNC",
}

DATA_DIR = Path("data/episode_metadata")


def _extract_set_hint(title: str, description: str) -> str | None:
    text = f"{title} {description}".lower()
    for name, code in SET_NAME_MAP.items():
        if name in text:
            return code
    set_code_match = re.search(r"\b([A-Z]{3,4})\b", title)
    if set_code_match:
        candidate = set_code_match.group(1)
        if candidate not in {"THE", "AND", "FOR", "NOT", "BUT", "RSS"}:
            return candidate
    return None


def _parse_duration(duration_str: str | None) -> int | None:
    if not duration_str:
        return None
    parts = duration_str.strip().split(":")
    try:
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            return h * 3600 + m * 60 + s
        if len(parts) == 2:
            m, s = int(parts[0]), int(parts[1])
            return m * 60 + s
        return int(parts[0])
    except ValueError:
        return None


def _parse_episode_number(title: str) -> int | None:
    # "Episode 423", "ep. 50", "#100"
    match = re.search(r"\b(?:ep(?:isode)?\.?\s*)(\d+)\b|#\s*(\d+)\b", title, re.IGNORECASE)
    if match:
        return int(match.group(1) or match.group(2))
    # "Limited Resources 851 - ..." / "Lords of Limited 423 - ..."
    match = re.search(r"(?:limited resources|lords of limited)\s+(\d+)", title, re.IGNORECASE)
    if match:
        return int(match.group(1))
    # Title starts with a number: "100: Strategy"
    match = re.search(r"^(\d+)[:\-\s]", title)
    if match:
        return int(match.group(1))
    return None


def _fetch_feed(show: str, url: str) -> list[dict]:
    resp = requests.get(url, timeout=30, headers={"User-Agent": "mtg-agent-trainer/1.0"})
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.content)
    ns = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}
    episodes = []
    for item in root.iter("item"):
        title_el = item.find("title")
        title = title_el.text.strip() if title_el is not None and title_el.text else ""
        pub_date_el = item.find("pubDate")
        published_at = None
        if pub_date_el is not None and pub_date_el.text:
            try:
                published_at = parsedate_to_datetime(pub_date_el.text).isoformat()
            except Exception:
                published_at = None
        enclosure = item.find("enclosure")
        audio_url = enclosure.get("url") if enclosure is not None else None
        guid_el = item.find("guid")
        guid = guid_el.text.strip() if guid_el is not None and guid_el.text else None
        desc_el = item.find("description")
        description = desc_el.text or "" if desc_el is not None else ""
        duration_el = item.find("itunes:duration", ns)
        duration_seconds = _parse_duration(
            duration_el.text if duration_el is not None else None
        )
        episode = {
            "show": show,
            "episode_number": _parse_episode_number(title),
            "title": title,
            "published_at": published_at,
            "audio_url": audio_url,
            "duration_seconds": duration_seconds,
            "description": description[:500],
            "guid": guid,
            "set_hint": _extract_set_hint(title, description),
        }
        episodes.append(episode)
    return episodes


def scrape(since: str | None = None) -> dict[str, list[dict]]:
    """Scrape both RSS feeds. Returns {show: [episode, ...]}."""
    since_dt = None
    if since:
        since_dt = datetime.fromisoformat(since).replace(tzinfo=timezone.utc)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    results = {}

    for show, url in FEEDS.items():
        print(f"\nScraping {show}...")
        episodes = _fetch_feed(show, url)

        if since_dt:
            filtered = []
            for ep in episodes:
                if ep["published_at"]:
                    ep_dt = datetime.fromisoformat(ep["published_at"])
                    if ep_dt.tzinfo is None:
                        ep_dt = ep_dt.replace(tzinfo=timezone.utc)
                    if ep_dt >= since_dt:
                        filtered.append(ep)
            episodes = filtered

        out_path = DATA_DIR / f"{show}.json"
        with open(out_path, "w") as f:
            json.dump(episodes, f, indent=2)

        results[show] = episodes
        dates = [ep["published_at"] for ep in episodes if ep["published_at"]]
        date_range = f"{min(dates)[:10]} to {max(dates)[:10]}" if dates else "n/a"
        print(f"  {len(episodes)} episodes  |  {date_range}  |  saved to {out_path}")

        # Console sample — first 3 episodes
        print("  Sample:")
        for ep in episodes[:3]:
            print(f"    [{ep['published_at'][:10] if ep['published_at'] else '?'}] "
                  f"#{ep['episode_number']} {ep['title'][:60]}  set={ep['set_hint']}")

        time.sleep(0.5)

    return results


def main():
    parser = argparse.ArgumentParser(description="Scrape podcast RSS feeds")
    parser.add_argument("--since", help="Only fetch episodes after this ISO date")
    args = parser.parse_args()
    scrape(since=args.since)


if __name__ == "__main__":
    main()
