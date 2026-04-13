# Multi-Agent Genealogical Research System with Adversarial Critique

A multi-agent pipeline that investigates genealogical questions using GEDCOM family tree data, evaluates its own hypotheses through an adversarial critique loop, and produces cited research reports with calibrated confidence assessments.

Built for **94815 Agentic Technologies** (CMU Heinz College, Prof. Anand S. Rao). Track A technical build, solo project.

## What It Does

Given a GEDCOM file and a natural language query (e.g., *"Who are the parents of James Joseph Moore?"*), the system:

1. **Record Scout** — Parses the GEDCOM, extracts search criteria via LLM (including alternate name forms), and surfaces candidate matches using fuzzy name matching.
2. **Profile Synthesizer** — Disambiguates candidates using deterministic scoring (name similarity + birth year + location), then consolidates the selected person's records into a cited profile.
3. **Relationship Hypothesizer** — Proposes family connections with evidence chains, confidence scores, and stated weaknesses. Populates both public and internal reasoning fields.
4. **Adversarial Critic** — Independently evaluates hypotheses *without access to the Hypothesizer's reasoning* (enforced by a whitelist isolation filter). Runs deterministic date/geographic checks before LLM reasoning. Can reject hypotheses and trigger revision (up to 2 cycles).
5. **Final Report Writer** — Composes a structured markdown report from the pipeline's output. Deterministic, no LLM.

## Key Architectural Feature: Critic Isolation

The Critic never sees the Hypothesizer's reasoning narrative, alternatives considered, or intermediate steps. This is enforced by `filter_hypothesis_for_critic()` — a whitelist filter in `agents/hypothesis_schema.py`, not a naming convention. The isolation prevents confirmation bias and was validated empirically via an A/B experiment comparing filtered vs. unfiltered Critic behavior across three query types.

## Tested Against

| Dataset | Persons | Language | Correct? | Notable |
|---------|---------|----------|----------|---------|
| Kennedy Family | 70 | English | Yes | 19th-century namesake correctly disambiguated |
| Moore Family Tree (developer's own) | 8,759 | English | Yes | Trans-Atlantic Irish migration detected |
| Queen Victoria | 4,683 | English | Yes | Name similarity 0.344, rescued by birth year |
| Habsburg Dynasty | 34,020 | German | Yes | English query matched German records via LLM alt-names |

## Setup

### Prerequisites

- Python 3.12+ (3.14 works but LangChain emits a Pydantic compatibility warning)
- Anthropic API key

### Installation

```bash
git clone https://github.com/kaitlinmoore/multiagent-geneaological-research-system.git
cd multiagent-geneaological-research-system

python -m venv .venv
source .venv/bin/activate        # Mac/Linux
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt

cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### Running the Pipeline

```bash
python main.py
```

By default, runs against `data/The Kennedy Family.ged` with a query about JFK's parents. 
To run a different query, edit `GEDCOM_PATH`, `TRACE_LABEL`, and `initial_state` in `main.py`.

Traces are saved to `traces/` as both JSON (machine-readable) and markdown (human-readable).


### Running the Evaluation Suite

```bash
python eval/run_eval.py
```

Runs all 8 adversarial trap cases (3 Tier 1, 3 Tier 2, 2 Tier 3) and reports pass/fail per tier.

### Running the A/B Isolation Experiment

```bash
python eval/isolation_experiment.py --preset jfk
python eval/isolation_experiment.py --preset tier2_surname
python eval/isolation_experiment.py --preset tier3_joseph
python eval/build_isolation_summary.py
```

Results saved to `eval/results/`.

## Project Structure

```
├── CLAUDE.md                    # Project context for Claude Code
├── main.py                      # Entry point
├── state.py                     # GenealogyState TypedDict
├── graph.py                     # LangGraph graph definition
├── agents/
│   ├── record_scout.py
│   ├── profile_synthesizer.py
│   ├── relationship_hypothesizer.py
│   ├── adversarial_critic.py
│   ├── final_report_writer.py
│   └── hypothesis_schema.py     # Isolation filter + hypothesis constructor
├── tools/
│   ├── gedcom_parser.py         # GEDCOM → structured person dicts
│   ├── fuzzy_match.py           # Jellyfish-based name similarity
│   ├── date_utils.py            # Date normalization + Tier 1 checks
│   ├── geo_utils.py             # Haversine + geocoding + multi-tier flags
│   └── trace_writer.py          # JSON + markdown trace persistence
├── eval/
│   ├── trap_cases/              # Synthetic GEDCOM files for adversarial testing
│   ├── run_eval.py              # Evaluation harness
│   ├── isolation_experiment.py  # A/B experiment runner
│   └── results/                 # Evaluation output
├── data/                        # GEDCOM files (sample files only in repo)
├── traces/                      # Pipeline output traces
├── docs/
│   ├── architecture_diagram.mermaid
│   └── architecture_diagram.png
└── AI_USAGE.md                  # AI assistance disclosure
```

## Evaluation

**Adversarial trap cases:** 8/8 passing across three difficulty tiers — deterministic impossibilities (100% detection, LLM not invoked), plausible-but-wrong errors (100% detection via LLM reasoning), and genuinely ambiguous cases (appropriate uncertainty expressed, no overconfident verdicts).

**A/B isolation experiment:** Across 3 queries and 6 hypotheses, isolation did not degrade Critic performance (5/6 identical verdicts). Reasoning visibility nearly doubled linguistic leakage from the Hypothesizer's narrative into the Critic's output (13 vs. 7 five-gram overlaps).

## Tech Stack

- **Orchestration:** LangGraph
- **LLM:** Claude Sonnet (Anthropic API)
- **GEDCOM parsing:** python-gedcom-2
- **Name matching:** Jellyfish (Soundex, Metaphone, Jaro-Winkler, Levenshtein)
- **Geocoding:** GeoPy (Nominatim)
- **Date handling:** python-dateutil

## Status

- **Phase 1** (Scoping): Complete. Score: 97/100.
- **Phase 2** (Architecture, Prototype, Evaluation Plan): Complete.
- **Phase 3** (Final Product, Evidence, Reflection): In progress. Remaining: DNA Analyst agent, Streamlit interface with tree visualization, full evaluation suite, ablation comparison, failure analysis, final report, 5-minute video.

## AI Usage

This project uses AI assistance throughout, documented transparently in `AI_USAGE.md`. Design decisions, domain selection, and evaluation criteria reflect the developer's judgment. All generated outputs were reviewed, and errors were identified and corrected by the developer.
