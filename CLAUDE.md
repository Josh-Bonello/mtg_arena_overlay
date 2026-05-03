# CLAUDE.md — MTG Limited Draft Agent

This file is the authoritative context for Claude Code working on this project.
Read it fully before touching any file. Every architectural decision is documented here.

---

## Project purpose

Build a suite of **live draft assistant agents** that make pick recommendations during
Magic: The Gathering booster draft and cube draft, trained on the voices and reasoning
styles of four expert limited hosts:

| Agent | Show | Style |
|---|---|---|
| Ben Werne | Lords of Limited | Data-driven, spreadsheet grader, archetype-focused, self-corrects on air |
| Ethan Saks | Lords of Limited | Pattern recognition, dynamic card updates, pick-order debates |
| Marshall Sutcliffe | Limited Resources | Foundational frameworks, teaching-first tone, methodical |
| Luis Scott-Vargas (LSV) | Limited Resources | Elite intuition, confident picks, power-level instincts |

Agents are called **live during a draft pick**. They must be fast and cheap.
All expensive data fetching happens at draft session start, not per-pick.

---

## Repository structure

```
/
├── CLAUDE.md                      ← you are here
├── pipeline/
│   ├── ingest/
│   │   ├── rss_scraper.py         # podcast RSS + episode metadata
│   │   ├── audio_downloader.py    # episode audio download
│   │   ├── transcriber.py         # Whisper large-v3 with MTG prompt seeding
│   │   ├── diarizer.py            # pyannote.audio speaker diarization
│   │   └── episode_classifier.py  # crash_course | rare_review | draft_log | etc.
│   ├── cards/
│   │   ├── scryfall_client.py     # Scryfall API + bulk data fetcher
│   │   ├── card_tagger.py         # Aho-Corasick tagger + fuzzy fallback
│   │   └── card_index.py          # per-card × per-host opinion index
│   ├── seventeen_lands/
│   │   ├── client.py              # rate-limited live endpoint fetcher
│   │   ├── bulk_downloader.py     # bulk file fetcher for archived sets
│   │   └── format_profiler.py     # format DNA builder (see Format Profiles below)
│   ├── video/
│   │   ├── yt_dlp_wrapper.py      # YouTube + Twitch VOD audio extraction
│   │   ├── frame_sampler.py       # 1fps frame sampling for OCR
│   │   └── ocr_card_detector.py   # Arena UI card name region OCR
│   └── corpus/
│       ├── formatter.py           # produces JSONL training corpus
│       └── divergence_tagger.py   # flags host vs 17lands opinion divergence
├── agent/
│   ├── session.py                 # DraftSession: initializes all data at draft start
│   ├── context_builder.py         # builds per-pick context JSON
│   ├── signal_tracker.py          # maintains signal_log across picks
│   ├── pool_analyzer.py           # computes pool_summary (colors, curve, removal)
│   ├── pick_modifier.py           # applies format profile weight adjustments
│   ├── personas/
│   │   ├── base_prompt.py         # shared system prompt structure
│   │   ├── ben.py                 # Ben Werne system prompt
│   │   ├── ethan.py               # Ethan Saks system prompt
│   │   ├── marshall.py            # Marshall Sutcliffe system prompt
│   │   └── lsv.py                 # LSV system prompt
│   └── cube/
│       ├── cube_classifier.py     # CubeCobra list ingestion + type detection
│       └── cube_profiles.py       # static profiles: powered | unpowered | pauper | themed
├── data/
│   ├── format_profiles/           # {set_code}.json — computed format DNA per set
│   ├── card_cache/                # Scryfall oracle data, keyed by card name
│   ├── seventeen_lands_cache/     # live endpoint responses, 24h TTL
│   └── corpus/                    # JSONL training files, one per host
├── tests/
└── requirements.txt
```

---

## Data pipeline overview

### Phase 1 — Podcast ingestion

1. Scrape RSS feeds for **Lords of Limited** and **Limited Resources**
2. Download audio, transcribe with **Whisper large-v3**
   - Always seed the Whisper prompt with card names from the episode's set
   - This dramatically reduces transcription errors on MTG proper nouns
3. Diarize with **pyannote.audio** — two speakers per show
   - Manually verify 3–5 episodes per show to build speaker fingerprints
   - Tag every utterance with `speaker_id` before any further processing
4. Classify each episode by type: `crash_course | rare_review | draft_log | archetype_analysis | format_retrospective`
5. Segment out: sponsor reads, cross-talk, off-topic tangents

### Phase 2 — Card entity detection

This is the most critical pipeline step. Card names are proper nouns that look like
ordinary English words ("Consider", "Brainstorm", "Go for the Throat"). Without
grounding, they are invisible to training.

**Step 1 — Build the card name dictionary**
```python
# Fetch all Oracle card names from Scryfall catalog
GET https://api.scryfall.com/catalog/card-names
# ~30k+ names. Refresh weekly or on set release.
# Build Aho-Corasick automaton for O(n) multi-pattern matching.
```

**Step 2 — First pass: exact match**
Run Aho-Corasick over the full transcript. Tag all exact matches.

**Step 3 — Fuzzy pass**
Whisper mishears card names. Run RapidFuzz (Levenshtein ≤ 2) against the set-scoped
card list (derived from episode metadata) for any unresolved spans.

**Step 4 — Enrich matched cards**
For each detected card, attach from Scryfall bulk data (`oracle-cards` daily download):
- `mana_cost`, `type_line`, `oracle_text`, `rarity`, `set_code`, `color_identity`

**Step 5 — Annotate transcripts**
```
[CARD: Lightning Bolt | R | Instant | "Deal 3 damage to any target." | common | OTJ]
```

**Step 6 — Build card opinion index**
For each `card × host` pair, aggregate all mentions across episodes into a structured
opinion record: evaluation statements, grade changes, pick order claims, format context.

### Phase 3 — 17lands enrichment

**Data availability strategy — live first for current sets**

| Set age | Strategy |
|---|---|
| Active (0–6 weeks) | Live endpoint — this is the primary and most valuable source |
| Recent (6–12 weeks) | Live endpoint with weekly refresh |
| Archived (3+ months) | Check `/public/data` for bulk file; download if available |

New sets during embargo (~2 weeks post-release): live endpoint will return sparse data.
Fetch it anyway. Cards below 500-sample threshold get `gih_wr: null`. The agent falls
back to oracle text reasoning for null cards. Do NOT skip the fetch.

**Live endpoint**
```
GET https://www.17lands.com/card_ratings/data
  ?expansion=DSK
  &event_type=PremierDraft    # PremierDraft | TradDraft | QuickDraft | Sealed
  &start_date=YYYY-MM-DD      # optional
  &end_date=YYYY-MM-DD        # optional
```

**Rate limiting — strictly enforced**
```python
from requests_ratelimiter import LimiterSession

session = LimiterSession(per_second=0.4)   # ≤24 req/min hard ceiling
session.headers["User-Agent"] = "mtg-agent-trainer/1.0 (personal research project)"

# Always add jitter on top of the rate limiter
import random, time
time.sleep(random.uniform(0.5, 1.5))
```

Exponential backoff on 429/503: 5s → 15s → 45s → 120s. After 4 retries, skip + log.
Cache all responses to disk. TTL: 24h for active sets, permanent for archived sets.

**Key 17lands metrics and what they mean**

| Metric | What it measures | When to use |
|---|---|---|
| `gih_wr` | Win rate in games where card was drawn | Primary card quality signal |
| `alsa` | Average last seen at (pick position) | Measures how contested a card is |
| `iwd` | GIH WR − baseline deck WR | Actual card impact, filters deck quality bias |
| `oh_wr` | Opening hand win rate | Cards that are good early vs. late |
| `gns_wr` | Games not seen win rate | The baseline; tells you deck strength |

**IWD is more reliable than GIH WR alone.** High GIH WR can mean the card is strong,
or it can mean the card only goes in strong decks. IWD separates these cases.

### Phase 4 — Video enrichment

Sources: YouTube (Lords of Limited, Limited Resources channels) + Twitch VODs

1. Extract audio via **yt-dlp** → same Whisper pipeline as podcasts
2. Frame sample at 1fps during draft segments → OCR Arena card name UI regions
3. Cross-reference detected card names against Scryfall
4. Detect pick events (card highlight flash + audio cue) → build pack-contents context
5. Tag "first impression on reveal" utterances — high-value training signal distinct
   from considered post-draft opinions

---

## Format profiles

Every set gets a `format_profiles/{set_code}.json` file that describes how that format
should be drafted. The agent loads this at session start and uses it to re-weight card
evaluations before making pick recommendations.

**Format types**

| Type | Key signal | Agent behavior |
|---|---|---|
| `aggressive` | on_play_wr > 0.530 | Penalize 5+ CMC, bonus for 2-drops, commit colors by pick 4 |
| `tempo` | on_play_wr ~0.52, evasion high IWD | Upweight evasion, track creature count, removal highly valued |
| `synergy` | color_pair_wr_spread > 0.070 | Apply archetype bonus when 3+ pieces assembled, weight signal cards higher |
| `goodstuff` | color_pair_wr_spread < 0.050 | Raw IWD dominates, raise fixing priority, splash threshold lower |
| `bomb_driven` | rare GIH WR >> common GIH WR | Anchor color commitment to best rare in pool, pick bombs over synergy |

**Profile lifecycle**

- **Week 0 (embargo):** Bootstrapped from crash course podcast episode analysis.
  `confidence: low`. Host verdicts are the primary signal.
- **Week 1–2:** Live 17lands data, partial. `confidence: medium`.
- **Week 3–6:** Full 17lands data. `confidence: high`. Profile re-runs weekly.
- **Archived:** Final snapshot frozen. Becomes permanent training data.

**Format profile schema** — see `data/format_profiles/EXAMPLE.json` for full spec.
Key fields: `format_type`, `on_play_wr`, `color_pair_wr_spread`, `fixing_priority`,
`curve_priority`, `stay_open_until_pick`, `splash_threshold`, `archetype_synergy_bonus`,
`open_signal_weight`, `top_color_pairs`, `color_pair_wrs`, `archetypes`.

---

## Live draft agent

### Architecture

The agent is called **once per pick**. The call must be fast. All data is pre-fetched.

```
DraftSession.start(set_code, event_type, persona)
  → fetch 17lands card ratings → in-memory dict
  → load format profile
  → load Scryfall oracle data for set
  → initialize SignalTracker, PoolAnalyzer

Per pick:
  ContextBuilder.build(pack, pool, pick_num, pack_num)
    → PoolAnalyzer.summarize(pool)           # color counts, curve, removal, evasion
    → PickModifier.apply(pack, format_profile) # re-weight cards per format type
    → SignalTracker.get_log()                # interpreted signal summary
  → Agent(persona).recommend(context)        # 2–4 sentence pick recommendation
```

### Context object structure

```python
{
  "format": "PremierDraft",       # or QuickDraft | TradDraft | Cube
  "set_code": "DSK",
  "pack_num": 1,                  # 1 | 2 | 3
  "pick_num": 7,                  # 1–15
  "overall_pick": 7,              # 1–45
  "picks_remaining": 38,

  "pool": [                       # cards already drafted
    { "name": "Fear of Missing Out", "colors": ["R"], "type": "Enchantment",
      "gih_wr": 0.621, "alsa": 2.1, "iwd": 0.068, "adj_gih_wr": 0.621 }
  ],
  "pool_summary": {               # pre-computed by PoolAnalyzer, never re-derived by agent
    "color_counts": {"R": 5, "B": 3},
    "curve": {"1": 1, "2": 3, "3": 2, "4": 1, "5+": 0},
    "removal_count": 2,
    "evasion_count": 3,
    "has_finisher": false,
    "fixing_count": 0
  },

  "current_pack": [               # cards available to pick, after PickModifier
    { "name": "Abhorrent Oculus", "colors": ["U"], "rarity": "mythic",
      "gih_wr": 0.654, "adj_gih_wr": 0.654, "alsa": 1.4, "iwd": 0.101,
      "oracle_text": "Flash. When ~ enters, draw a card..." }
  ],

  "signal_log": [                 # built by SignalTracker, pre-interpreted
    { "pick": 4, "card": "Sheltered by Ghosts", "color": "W",
      "position": 7, "note": "strong W card late — W may be open" }
  ],

  "meta": {
    "top_color_pairs": ["RB", "UB", "RG"],
    "color_pair_wr": {"RB": 0.571, "UB": 0.563},
    "format_type": "tempo",
    "format_speed": "medium_fast",
    "format_notes": "evasion matters, 2-drops important, rooms archetype in UB"
  },

  "17lands_snapshot": {
    "fetched_at": "2025-11-01T14:22Z",
    "source": "live_api",          # live_api | bulk_file
    "embargo_active": false,
    "sample_cutoff": 500
  }
}
```

### Pick modifier rules

Cards in `current_pack` get an `adj_gih_wr` computed by `PickModifier` before the
agent sees them. Rules applied in order:

1. **Fast format:** cards with CMC ≥ 5 get −0.020 unless they have haste/flash/ETB
2. **Fast format:** cards with CMC ≤ 2 and gih_wr ≥ format average get +0.010
3. **Synergy format:** card completes archetype (3+ pieces in pool) → +0.020
4. **Goodstuff format:** fixing cards get +0.015 if pool has 0 fixing
5. **Bomb-driven format:** card is rare/mythic and colors match best rare in pool → +0.015
6. **Any format:** gih_wr is null (< 500 samples) → flag as `data: sparse`, no adj

### Signal logic

**Pack 1 (passes left):** signals come from players to your right.
**Pack 2 (passes right):** signals come from players to your left — different neighbor.
**Pack 3 (passes left):** signals from right again.

Signal strength = card power (GIH WR vs format average) × recency weight.
A pick-8 rare sending a signal outweighs a pick-8 common.

Positive signal: strong card in a color arrives later than its ALSA average.
Negative signal: a color's commons stop appearing early; high-ALSA cards gone fast.

The `SignalTracker` builds the `signal_log`. The agent interprets it; it does not
recompute it.

### Agent output format

The agent returns 2–4 sentences in the persona's voice. No bullet lists. No rankings.
One clear pick recommendation with the key reasoning.

Examples by persona:

**Ben:** "Abhorrent Oculus is the pick — it's sitting at 65% GIH WR for a reason.
Blue is flowing late from your left and you're already in black, so UB is very much
on the table. This is a first pick I'd be comfortable writing in the spreadsheet."

**LSV:** "Mythic flash threat that draws a card — this is a clear first pick and I
wouldn't think twice. The fact that blue is open makes it even cleaner."

**Marshall:** "Here's the fundamental question: are you willing to commit toward blue?
If the signals hold, Abhorrent Oculus is the kind of rare that defines your deck.
I'd take it and stay open to confirming blue over the next few picks."

**Ethan:** "This is one of those cards that's even better than its stats show once you
factor in the evasion and the flash timing. Blue looks open, the Oculus is the pick."

---

## Cube mode

When `format == "Cube"`, the following changes apply:

- **No 17lands data.** The `17lands_snapshot` block is omitted from context entirely.
- **No PickModifier adjustments** based on format statistics.
- **Cube profile loaded instead** from `agent/cube/cube_profiles.py`.
- If `cube_list` is provided (CubeCobra export), run `CubeClassifier` to detect type
  and supported archetypes.

**Cube types and their agent behavior:**

| Type | `format_type` | `stay_open_until` | `fixing_priority` | Key note |
|---|---|---|---|---|
| `powered` | bomb_driven + fast | pick 3 | high | Power 9 / artifact mana always P1; combo archetypes viable |
| `unpowered` | goodstuff + synergy | pick 5–6 | high | Blue always threatening to be best; track blue flow |
| `pauper` | synergy + tempo | pick 6–7 | medium | Synergy is how commons compete; role-players valued |
| `themed` | inferred | inferred | inferred | Requires cube_list to classify |

**Powered Cube card tier system (baked into system prompt):**
- **Tier S:** Power 9, Time Vault, Library of Alexandria — always first pick
- **Tier A:** Jace TMS, Tinker, Recurring Nightmare, Show and Tell — first pick in color
- **Tier B:** Counterspell, Swords to Plowshares, Lightning Bolt, Thoughtseize
- **Below B:** Evaluate by role within the specific archetype being drafted

**Singleton signal logic:** Each card exists once. Read archetype signals from
"key role players missing" rather than volume of a color. Track combo pieces seen and
passed to infer what other players are building.

---

## Training corpus structure

Training files live in `data/corpus/`. One JSONL file per host.

Each line is a training example:
```json
{
  "messages": [
    {
      "role": "system",
      "content": "You are Ben Werne from Lords of Limited. [persona details] [set context] [known card pool]"
    },
    {
      "role": "user",
      "content": "[pick context JSON or card evaluation question]"
    },
    {
      "role": "assistant",
      "content": "[Ben's actual words from the episode, cleaned and diarized]"
    }
  ],
  "metadata": {
    "episode": "ep-423",
    "set_code": "BLB",
    "episode_type": "crash_course",
    "card_entities": ["Mabel, Heir to Cragflame", "Jolted Awake"],
    "gih_wr_at_time": { "Mabel, Heir to Cragflame": 0.641 },
    "divergence_flag": false,
    "host": "ben"
  }
}
```

**Divergence flag:** set to `true` when the host's evaluation directionally contradicts
17lands data for a card. These are high-value training examples — they teach the agent
the host's distinctive perspective vs. crowd consensus.

**Episode type weighting:**
- `crash_course` — highest weight (format-defining verdicts)
- `rare_review` — high weight (systematic card evaluation)
- `draft_log` — high weight (in-context pick reasoning)
- `archetype_analysis` — medium weight
- `format_retrospective` — medium weight (post-format wisdom)

---

## Key commands

```bash
# Run full pipeline for a set
python -m pipeline.run --set DSK --event_type PremierDraft

# Build format profile from 17lands data
python -m pipeline.seventeen_lands.format_profiler --set DSK

# Transcribe a single episode
python -m pipeline.ingest.transcriber --url <rss_episode_url> --set DSK

# Start a draft session (dev/test)
python -m agent.session --set DSK --persona ben --event_type PremierDraft

# Classify a cube from CubeCobra export
python -m agent.cube.cube_classifier --input cube_export.json
```

---

## Important constraints

- **Never call 17lands live during a pick.** All data is pre-fetched at `DraftSession.start()`.
- **17lands rate limit: ≤24 req/min with jitter.** This is a community site. Be respectful.
- **New set + no 17lands data ≠ skip enrichment.** Fetch anyway; handle nulls gracefully.
- **Card names are case-insensitive in Scryfall fuzzy matching.**
- **Whisper will mishear MTG names.** Always seed with set card names. Always run fuzzy pass.
- **The agent returns 2–4 sentences.** Never a ranked list. Never bullet points. Fast to read.
- **Pool summary is pre-computed.** The agent never counts cards or calculates curve itself.
- **Format profile re-runs weekly** while a set is actively drafted.
- **Embargo period:** sparse 17lands data is expected and handled. `confidence: low` profile
  uses crash course episode verdicts as primary signal until data matures.

## Autonomous run protocol

When running autonomously through all issues:

1. Work epic by epic in the order listed in this file
2. One branch per issue, one PR per issue
3. Tests must pass before a PR is opened
4. At MANUAL CHECKPOINT markers in the Makefile, stop and output:
   - The checkpoint name
   - The exact output to review
   - What "looks good" means for that checkpoint
   - The exact command to run to proceed: `touch .continue`
5. Poll for `.continue` every 30 seconds before resuming
6. Delete `.continue` after consuming it

To resume after a review: `touch .continue`