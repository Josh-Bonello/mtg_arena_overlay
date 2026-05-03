"""Download episode audio files from RSS-scraped URLs."""
import re
import time
from pathlib import Path

import requests
from tqdm import tqdm

AUDIO_DIR = Path("data/audio")
_BACKOFF = [2, 4, 8]


def _safe_filename(show: str, episode_number: int | None, title: str) -> str:
    if episode_number is not None:
        return f"{show}_{episode_number}.mp3"
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[\s-]+", "_", slug).strip("_")[:60]
    return f"{show}_{slug}.mp3"


def download_episode(
    episode_metadata: dict,
    output_dir: str | Path = AUDIO_DIR,
) -> Path:
    """Download episode audio. Skips if already present. Returns local path."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = _safe_filename(
        episode_metadata["show"],
        episode_metadata.get("episode_number"),
        episode_metadata.get("title", "unknown"),
    )
    dest = output_dir / filename

    if dest.exists():
        print(f"  skip (exists): {dest}")
        return dest

    url = episode_metadata["audio_url"]
    headers = {"User-Agent": "mtg-agent-trainer/1.0"}

    for attempt, backoff in enumerate([0] + _BACKOFF, start=1):
        if backoff:
            time.sleep(backoff)
        try:
            resp = requests.get(url, stream=True, timeout=60, headers=headers)
            resp.raise_for_status()

            total = int(resp.headers.get("content-length", 0))
            with open(dest, "wb") as f, tqdm(
                total=total,
                unit="B",
                unit_scale=True,
                desc=filename,
                leave=False,
            ) as bar:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
                    bar.update(len(chunk))

            print(f"  downloaded: {dest}  ({dest.stat().st_size / 1024 / 1024:.1f} MB)")
            return dest

        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt > len(_BACKOFF):
                raise
            print(f"  attempt {attempt} failed ({exc}), retrying in {_BACKOFF[attempt-1]}s...")

    raise RuntimeError(f"Failed to download {url} after {len(_BACKOFF)+1} attempts")
