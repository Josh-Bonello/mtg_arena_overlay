# MTG Draft Agent — Makefile
# All targets are safe to re-run. Expensive steps (transcription, 17lands fetch)
# check for cached output before running and skip if already done.
#
# Usage:
#   make setup                        # first-time environment setup
#   make pipeline SET=DSK             # run full pipeline for a set
#   make draft SET=DSK PERSONA=ben    # start a live draft session
#   make help                         # list all targets

# ── Configuration ─────────────────────────────────────────────────────────────

SET        ?= DSK
EVENT_TYPE ?= PremierDraft
PERSONA    ?= ben
EPISODE    ?=
CUBE       ?=

PYTHON     := python -m
DATA       := data
LOG_LEVEL  := INFO

# ── Help ──────────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@echo ""
	@echo "MTG Draft Agent"
	@echo "──────────────────────────────────────────────────────────────"
	@echo ""
	@echo "  SETUP"
	@echo "  make setup                        First-time environment setup"
	@echo "  make install                      Install Python dependencies"
	@echo "  make dirs                         Create data/ directory structure"
	@echo ""
	@echo "  FULL PIPELINE"
	@echo "  make pipeline SET=DSK             Run full pipeline for a set"
	@echo "  make pipeline-resume SET=DSK      Resume pipeline, skip completed stages"
	@echo ""
	@echo "  PODCAST INGESTION"
	@echo "  make scrape                       Scrape both podcast RSS feeds"
	@echo "  make transcribe SET=DSK           Transcribe all episodes for a set"
	@echo "  make transcribe-one EPISODE=<url> Transcribe a single episode"
	@echo "  make diarize SET=DSK              Run speaker diarization for a set"
	@echo "  make diarize-verify SET=DSK       Print diarization samples for manual check"
	@echo "  make segment SET=DSK              Classify + strip non-useful segments"
	@echo ""
	@echo "  CARD ENTITY DETECTION"
	@echo "  make card-dict                    Build Scryfall card name dictionary"
	@echo "  make tag-cards SET=DSK            Run card tagger on transcripts for a set"
	@echo "  make tag-sample SET=DSK           Print 20 tagged card examples for review"
	@echo "  make opinion-index SET=DSK        Build card × host opinion index"
	@echo ""
	@echo "  17LANDS ENRICHMENT"
	@echo "  make fetch-17l SET=DSK            Fetch 17lands data for a set (live endpoint)"
	@echo "  make fetch-bulk SET=DSK           Download 17lands bulk file if available"
	@echo "  make format-profile SET=DSK       Build format profile from 17lands data"
	@echo "  make profile-diff SET=DSK         Diff current profile against previous"
	@echo "  make profile-show SET=DSK         Print format profile summary to console"
	@echo "  make refresh-all                  Refresh 17lands + profiles for all active sets"
	@echo ""
	@echo "  CORPUS"
	@echo "  make corpus SET=DSK               Build training corpus for a set"
	@echo "  make corpus-sample PERSONA=ben    Print 20 training examples for a persona"
	@echo "  make corpus-stats                 Print corpus size + divergence flag counts"
	@echo ""
	@echo "  VIDEO ENRICHMENT"
	@echo "  make video-fetch SET=DSK          Download YouTube/Twitch VODs for a set"
	@echo "  make video-ocr SET=DSK            Run frame sampler + OCR on draft videos"
	@echo ""
	@echo "  AGENT — LIVE DRAFT"
	@echo "  make draft SET=DSK PERSONA=ben    Start interactive draft session"
	@echo "  make draft-test SET=DSK           Run a mock draft with all 4 personas"
	@echo "  make pick SET=DSK PERSONA=ben     Make a single pick from stdin JSON"
	@echo ""
	@echo "  AGENT — CUBE"
	@echo "  make cube-classify CUBE=<path>    Classify a CubeCobra export JSON"
	@echo "  make draft-cube CUBE=powered PERSONA=lsv   Start powered cube draft"
	@echo ""
	@echo "  TESTING"
	@echo "  make test                         Run all tests"
	@echo "  make test-pipeline                Run pipeline unit tests only"
	@echo "  make test-agent                   Run agent unit tests only"
	@echo "  make test-format-classifier       Test format type classifier vs known sets"
	@echo "  make test-pick-modifier           Test pick weight modifier rules"
	@echo "  make test-17l                     Test 17lands fetcher (live, one request)"
	@echo ""
	@echo "  MAINTENANCE"
	@echo "  make clean-cache                  Delete 17lands + Scryfall caches"
	@echo "  make clean-transcripts SET=DSK    Delete transcripts for a set"
	@echo "  make clean-all                    Delete all generated data (careful!)"
	@echo "  make status                       Show pipeline completion status per set"
	@echo ""
	@echo "  Variables:"
	@echo "    SET        Set code, e.g. DSK BLB MH3 FDN   (default: DSK)"
	@echo "    EVENT_TYPE PremierDraft QuickDraft TradDraft  (default: PremierDraft)"
	@echo "    PERSONA    ben ethan marshall lsv             (default: ben)"
	@echo "    EPISODE    RSS episode URL for single transcription"
	@echo "    CUBE       Cube name or path to CubeCobra JSON"
	@echo ""

# ── Setup ─────────────────────────────────────────────────────────────────────

.PHONY: setup install dirs

setup: install dirs
	@echo "✓ Setup complete. Copy .env.example to .env and fill in credentials."

install:
	pip install -r requirements.txt
	@echo "✓ Dependencies installed"

dirs:
	mkdir -p $(DATA)/format_profiles
	mkdir -p $(DATA)/card_cache
	mkdir -p $(DATA)/seventeen_lands_cache
	mkdir -p $(DATA)/corpus
	mkdir -p $(DATA)/cube_profiles
	mkdir -p $(DATA)/transcripts
	mkdir -p $(DATA)/audio
	mkdir -p $(DATA)/video
	@echo "✓ data/ directory structure created"

# ── Full Pipeline ──────────────────────────────────────────────────────────────

.PHONY: pipeline pipeline-resume

pipeline: scrape transcribe diarize segment card-dict tag-cards opinion-index \
          fetch-17l format-profile corpus
	@echo ""
	@echo "✓ Full pipeline complete for $(SET)"
	@echo "  Run 'make corpus-sample PERSONA=ben' to spot-check training data"
	@echo "  Run 'make draft SET=$(SET) PERSONA=ben' to test the live agent"

pipeline-resume:
	@echo "Resuming pipeline for $(SET) — skipping completed stages..."
	$(PYTHON) pipeline.run --set $(SET) --event-type $(EVENT_TYPE) --resume

# ── Podcast Ingestion ──────────────────────────────────────────────────────────

.PHONY: scrape transcribe transcribe-one diarize diarize-verify segment

scrape:
	@echo "Scraping podcast RSS feeds..."
	$(PYTHON) pipeline.ingest.rss_scraper
	@echo "✓ Episode metadata stored. Run 'make status' to see what's available."

transcribe:
	@echo "Transcribing episodes for set $(SET) with MTG prompt seeding..."
	$(PYTHON) pipeline.ingest.transcriber --set $(SET)
	@echo "✓ Transcription complete for $(SET)"

transcribe-one:
	@test -n "$(EPISODE)" || (echo "ERROR: EPISODE= is required. Usage: make transcribe-one EPISODE=<url>" && exit 1)
	$(PYTHON) pipeline.ingest.transcriber --url $(EPISODE) --set $(SET)

diarize:
	@echo "Running speaker diarization for $(SET)..."
	$(PYTHON) pipeline.ingest.diarizer --set $(SET)
	@echo ""
	@echo "⚠  MANUAL CHECKPOINT REQUIRED"
	@echo "   Run 'make diarize-verify SET=$(SET)' and confirm speaker labels"
	@echo "   before running corpus generation."

diarize-verify:
	@echo "── Diarization samples for $(SET) ──────────────────────────────────────"
	@echo "Review these utterances and confirm speaker_id labels are correct."
	@echo "Ben/Ethan for LoL episodes, Marshall/LSV for LR episodes."
	@echo ""
	$(PYTHON) pipeline.ingest.diarizer --set $(SET) --verify --samples 30
	@echo ""
	@echo "If labels look wrong, run: make diarize SET=$(SET) to re-run with corrections."

segment:
	@echo "Classifying and filtering segments for $(SET)..."
	$(PYTHON) pipeline.ingest.episode_classifier --set $(SET)
	@echo "✓ Segments classified. Sponsor reads, cross-talk removed."

# ── Card Entity Detection ──────────────────────────────────────────────────────

.PHONY: card-dict tag-cards tag-sample opinion-index

card-dict:
	@echo "Fetching Scryfall card name catalog and building Aho-Corasick automaton..."
	$(PYTHON) pipeline.cards.card_tagger --build-dict
	@echo "✓ Card name dictionary built"

tag-cards:
	@echo "Running card entity tagger on transcripts for $(SET)..."
	$(PYTHON) pipeline.cards.card_tagger --set $(SET)
	@echo "✓ Card entities tagged"
	@echo "  Run 'make tag-sample SET=$(SET)' to review 20 examples"

tag-sample:
	@echo "── Card tagging samples for $(SET) ─────────────────────────────────────"
	$(PYTHON) pipeline.cards.card_tagger --set $(SET) --sample 20
	@echo ""
	@echo "Check: card names should be in [CARD: ...] format with oracle text attached."
	@echo "Check: fuzzy corrections logged above — review any that look wrong."

opinion-index:
	@echo "Building card × host opinion index for $(SET)..."
	$(PYTHON) pipeline.cards.card_index --set $(SET)
	@echo "✓ Opinion index built"

# ── 17lands Enrichment ────────────────────────────────────────────────────────

.PHONY: fetch-17l fetch-bulk format-profile profile-diff profile-show refresh-all

fetch-17l:
	@echo "Fetching 17lands card ratings for $(SET) ($(EVENT_TYPE))..."
	@echo "Rate limit: ≤24 req/min with jitter. This may take a moment."
	$(PYTHON) pipeline.seventeen_lands.client --set $(SET) --event-type $(EVENT_TYPE)
	@echo "✓ 17lands data cached for $(SET)"

fetch-bulk:
	@echo "Checking 17lands public data page for bulk file for $(SET)..."
	$(PYTHON) pipeline.seventeen_lands.bulk_downloader --set $(SET)

format-profile:
	@echo "Building format profile for $(SET)..."
	$(PYTHON) pipeline.seventeen_lands.format_profiler --set $(SET) \
		--event-type $(EVENT_TYPE)
	@$(MAKE) profile-show SET=$(SET)

profile-diff:
	@echo "── Format profile diff for $(SET) ──────────────────────────────────────"
	$(PYTHON) pipeline.seventeen_lands.format_profiler --set $(SET) --diff
	@echo ""
	@echo "If format_type changed, review agent behavior for this set."

profile-show:
	@echo "── Format profile: $(SET) ───────────────────────────────────────────────"
	$(PYTHON) pipeline.seventeen_lands.format_profiler --set $(SET) --show
	@echo ""
	@echo "⚠  MANUAL CHECKPOINT"
	@echo "   Does the format_type and top color pairs match your intuition?"
	@echo "   If not, check 17lands sample counts — may still be in embargo."

refresh-all:
	@echo "Refreshing 17lands data + format profiles for all active sets..."
	$(PYTHON) pipeline.seventeen_lands.client --refresh-active
	@echo "✓ All active sets refreshed"

# ── Training Corpus ────────────────────────────────────────────────────────────

.PHONY: corpus corpus-sample corpus-stats divergence-report

corpus:
	@echo ""
	@echo "⚠  PRE-FLIGHT CHECK"
	@echo "   Have you verified diarization labels? (make diarize-verify SET=$(SET))"
	@echo "   Have you reviewed card tagging? (make tag-sample SET=$(SET))"
	@echo "   Have you confirmed the format profile? (make profile-show SET=$(SET))"
	@echo ""
	@read -p "Proceed with corpus generation for $(SET)? [y/N] " confirm && \
		[ "$$confirm" = "y" ] || exit 0
	$(PYTHON) pipeline.corpus.formatter --set $(SET)
	@echo "✓ Training corpus generated for $(SET)"
	@$(MAKE) corpus-stats

corpus-sample:
	@echo "── Training corpus samples: $(PERSONA) ─────────────────────────────────"
	$(PYTHON) pipeline.corpus.formatter --persona $(PERSONA) --sample 20
	@echo ""
	@echo "⚠  MANUAL CHECKPOINT"
	@echo "   Does the assistant voice sound like $(PERSONA)?"
	@echo "   Are card entity tags present and correct?"
	@echo "   Are 17lands values attached to card mentions?"

corpus-stats:
	@echo "── Corpus statistics ───────────────────────────────────────────────────"
	$(PYTHON) pipeline.corpus.formatter --stats
	@echo ""

divergence-report:
	@echo "── Host vs 17lands divergence flags ────────────────────────────────────"
	$(PYTHON) pipeline.corpus.divergence_tagger --report --set $(SET)

# ── Video Enrichment ──────────────────────────────────────────────────────────

.PHONY: video-fetch video-ocr

video-fetch:
	@echo "Downloading YouTube/Twitch VODs for $(SET)..."
	$(PYTHON) pipeline.video.yt_dlp_wrapper --set $(SET)

video-ocr:
	@echo "Running frame sampler + Arena OCR for $(SET)..."
	$(PYTHON) pipeline.video.frame_sampler --set $(SET)
	$(PYTHON) pipeline.video.ocr_card_detector --set $(SET)
	@echo "✓ Video card detection complete for $(SET)"

# ── Agent — Live Draft ────────────────────────────────────────────────────────

.PHONY: draft draft-test pick

draft:
	@echo "Starting draft session: SET=$(SET) PERSONA=$(PERSONA) EVENT=$(EVENT_TYPE)"
	@echo "Fetching 17lands data and loading format profile at session start..."
	$(PYTHON) agent.session \
		--set $(SET) \
		--persona $(PERSONA) \
		--event-type $(EVENT_TYPE)

draft-test:
	@echo "Running mock draft with all 4 personas for $(SET)..."
	@echo ""
	@echo "── Ben ──────────────────────────────────────────────────────────────────"
	$(PYTHON) agent.session --set $(SET) --persona ben --mock
	@echo ""
	@echo "── Ethan ────────────────────────────────────────────────────────────────"
	$(PYTHON) agent.session --set $(SET) --persona ethan --mock
	@echo ""
	@echo "── Marshall ─────────────────────────────────────────────────────────────"
	$(PYTHON) agent.session --set $(SET) --persona marshall --mock
	@echo ""
	@echo "── LSV ──────────────────────────────────────────────────────────────────"
	$(PYTHON) agent.session --set $(SET) --persona lsv --mock
	@echo ""
	@echo "⚠  MANUAL CHECKPOINT"
	@echo "   Does each persona's voice feel distinct and correct?"
	@echo "   Are recommendations referencing 17lands data appropriately?"
	@echo "   Are recommendations 2-4 sentences, no bullet points?"

pick:
	@echo "Making a single pick recommendation from stdin..."
	@echo "Pipe a context JSON: cat context.json | make pick SET=$(SET) PERSONA=$(PERSONA)"
	$(PYTHON) agent.session --set $(SET) --persona $(PERSONA) --single-pick

# ── Agent — Cube ──────────────────────────────────────────────────────────────

.PHONY: cube-classify draft-cube

cube-classify:
	@test -n "$(CUBE)" || (echo "ERROR: CUBE= is required. Usage: make cube-classify CUBE=<path-to-json>" && exit 1)
	@echo "Classifying cube from $(CUBE)..."
	$(PYTHON) agent.cube.cube_classifier --input $(CUBE)
	@echo "✓ Cube profile written to data/cube_profiles/"

draft-cube:
	@test -n "$(CUBE)" || (echo "ERROR: CUBE= is required. Usage: make draft-cube CUBE=powered PERSONA=lsv" && exit 1)
	@echo "Starting cube draft: CUBE=$(CUBE) PERSONA=$(PERSONA)"
	$(PYTHON) agent.session \
		--format cube \
		--cube $(CUBE) \
		--persona $(PERSONA)

# ── Testing ───────────────────────────────────────────────────────────────────

.PHONY: test test-pipeline test-agent test-format-classifier test-pick-modifier test-17l

test:
	pytest tests/ -v --tb=short
	@echo "✓ All tests passed"

test-pipeline:
	pytest tests/pipeline/ -v --tb=short

test-agent:
	pytest tests/agent/ -v --tb=short

test-format-classifier:
	@echo "Testing format type classifier against known sets..."
	@echo "Expected: BLB=aggressive, MH2=synergy, FDN=goodstuff, DSK=tempo"
	pytest tests/pipeline/test_format_classifier.py -v --tb=short -s

test-pick-modifier:
	@echo "Testing pick weight modifier rules..."
	pytest tests/agent/test_pick_modifier.py -v --tb=short -s

test-17l:
	@echo "Testing 17lands fetcher — making ONE live request to DSK..."
	@echo "Watch for rate limiting behavior and correct response parsing."
	$(PYTHON) pipeline.seventeen_lands.client --set DSK --test-one
	@echo "✓ 17lands fetcher test complete"

# ── Maintenance ───────────────────────────────────────────────────────────────

.PHONY: clean-cache clean-transcripts clean-all status

clean-cache:
	@read -p "Delete all 17lands + Scryfall caches? [y/N] " confirm && \
		[ "$$confirm" = "y" ] || exit 0
	rm -rf $(DATA)/seventeen_lands_cache/*
	rm -rf $(DATA)/card_cache/*
	@echo "✓ Caches cleared"

clean-transcripts:
	@test -n "$(SET)" || (echo "ERROR: SET= is required" && exit 1)
	@read -p "Delete all transcripts for $(SET)? [y/N] " confirm && \
		[ "$$confirm" = "y" ] || exit 0
	rm -rf $(DATA)/transcripts/$(SET)
	@echo "✓ Transcripts deleted for $(SET)"

clean-all:
	@echo "WARNING: This will delete ALL generated data including training corpus."
	@read -p "Are you sure? Type 'yes' to confirm: " confirm && \
		[ "$$confirm" = "yes" ] || exit 0
	rm -rf $(DATA)/transcripts/*
	rm -rf $(DATA)/audio/*
	rm -rf $(DATA)/video/*
	rm -rf $(DATA)/seventeen_lands_cache/*
	rm -rf $(DATA)/card_cache/*
	rm -rf $(DATA)/corpus/*
	rm -rf $(DATA)/format_profiles/*
	rm -rf $(DATA)/cube_profiles/*
	@echo "✓ All generated data deleted"

status:
	@echo "── Pipeline status ─────────────────────────────────────────────────────"
	$(PYTHON) pipeline.run --status
	@echo ""