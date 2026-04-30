# Multi-Agent Genealogical Research System with Adversarial Critique

A multi-agent pipeline that investigates genealogical questions using GEDCOM family tree data, multi-source web retrieval, and DNA match data. The pipeline pairs a Hypothesizer with an isolated Adversarial Critic, runs deterministic checks before LLM reasoning, and produces cited research reports with calibrated confidence and explicit escalation triggers for human review. Built for **94815 Agentic Technologies** (CMU Heinz College, Prof. Anand S. Rao). Track A technical build, solo project.

## Key Architectural Feature: Critic Isolation as a Code Guarantee

The Adversarial Critic never sees the Hypothesizer's reasoning narrative, alternatives considered, or intermediate steps. This is the core agentic justification of the project — a Critic that can read the proposer's reasoning is no longer adversarial, it is a confirmation-bias amplifier.

The isolation is enforced as a code guarantee, not a naming convention. `agents/hypothesis_schema.py` declares two field sets — PUBLIC (visible to the Critic) and INTERNAL (stripped before the Critic sees a hypothesis). `filter_hypothesis_for_critic(hypothesis)` is the single read path the Critic uses; the Critic node never accesses raw `state["hypotheses"]` dicts directly. A `state["isolation_mode"]` toggle flips the filter on or off for the A/B experiment, but the production path is always filtered.

## Capabilities

- **Five autonomous agents** (Record Scout, Profile Synthesizer, Relationship Hypothesizer, Adversarial Critic, DNA Analyst) plus a deterministic Final Report Writer that composes the final markdown from state without invoking an LLM.
- **LangGraph orchestration** with a Hypothesizer ⇄ Critic revision loop capped at two cycles, then forced finalization with an explicit escalation flag.
- **Three entry modes**: query (default — investigate a specific person/relationship), gap detection (scan the GEDCOM for persons missing parent links and rank candidates from within the tree), subtree audit (walk every parent-child relationship in an N-generation subtree, two-pass deterministic + optional LLM).
- **Multi-source retrieval** in the Record Scout: GEDCOM, FindAGrave (HTML scrape), Wikidata (SPARQL), WikiTree (REST API). Each record tagged with `source_type` so downstream agents can weight independent corroboration.
- **DNA Analyst integrated into the reasoning loop**, not appended as a reporter. Cross-references match names against GEDCOM persons via fuzzy matching, predicts relationships against the Shared cM Project lookup table, and emits `dna_relevant` evidence items the Hypothesizer can cite and the Critic can challenge.
- **Streamlit four-tab application** (Pipeline, Family Tree, Audit, DNA Analysis) wrapping the same graph with file-picker affordances for the bundled GEDCOMs and synthetic DNA demos.

## Tested Against

| Dataset | Persons | Language / Encoding | In repo? | Result | Notable |
|---------|---------|---------------------|----------|--------|---------|
| Kennedy Family | 70 | English / UTF-8 | Yes (public) | Correct | Disambiguates 19th-century namesake from JFK; cross-vendor Critic reaches identical verdict |
| Queen Victoria | 4,683 | English / UTF-8 | Yes (public) | Correct | Initial name similarity 0.344, rescued by birth-year signal in disambiguation |
| Habsburg Dynasty | 34,020 | German / Latin-1 | Yes (public) | Correct | English query matched German records via LLM alt-name expansion; encoding workaround required |
| Moore Family Tree | 8,759 | English / UTF-8 | No (gitignored) | Correct | Trans-Atlantic Irish migration flagged; verified against developer's personal knowledge |
| Synthetic DNA demos | 10–50 matches each | n/a | Yes (`data/DNA_demo/`) | Reproducible | Hand-built ground truth for Kennedy, Maria Theresia, Victoria Hanover; lets graders exercise the DNA path without committing personal match data |

## Setup

### Prerequisites

- Python 3.12+ (3.14 works but LangChain emits a Pydantic compatibility warning)
- Anthropic API key (required); OpenAI or Google Gemini API keys (optional, for cross-vendor experiments)

### Installation

```bash
git clone https://github.com/kaitlinmoore/multiagent-geneaological-research-system.git
cd multiagent-geneaological-research-system

python -m venv .venv
source .venv/bin/activate        # Mac/Linux
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

Create a `.env` file in the project root containing your API key (the repo does not ship a `.env.example` — graders create their own):

```
ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...          # optional, for cross-vendor Critic experiment
# GOOGLE_API_KEY=...              # optional, for multi-Critic ensemble
```

## Running the Pipeline

The system supports three CLI entry modes plus a Streamlit GUI.

```bash
# Query mode — full pipeline against a specific research question.
# Defaults to JFK against the Kennedy GEDCOM with the synthetic DNA demo attached.
python main.py

# Subtree audit mode — walk every parent-child link in an N-generation subtree.
# Two-pass: deterministic Tier 1 + geographic checks, then optional LLM
# full-pipeline pass on the top-N most questionable relationships.
python audit.py

# Gap detection mode — scan a GEDCOM for persons missing parent links,
# score plausible parents from within the tree, and optionally run the
# pipeline on the top-N broken links.
python gap_search.py

# Streamlit GUI.
streamlit run app.py
```

Pipeline runs persist a JSON trace and a markdown summary to `traces/` (gitignored — the JSON contains structured copies of profiles, hypotheses, and critiques and may include personal tree content).

## Running Evaluations

```bash
# Manifest-driven trap suite (8 cases across 3 difficulty tiers).
python eval/run_eval.py

# Critic isolation A/B experiment (filtered vs unfiltered) on the JFK preset,
# plus an aggregate summary across multiple presets.
python eval/isolation_experiment.py --preset jfk
python eval/build_isolation_summary.py

# Cross-vendor Critic experiment (Anthropic Opus vs OpenAI GPT) on a shared
# hypothesis set.
python eval/cross_vendor_critic_experiment.py

# Multi-Critic ensemble (Anthropic + OpenAI + Google Gemini) with a
# conservative aggregation rule (any reject → reject).
python eval/multi_critic_ensemble_experiment.py

# Single-agent baseline ablation — one LLM call vs the full pipeline on
# the same 8 trap cases. The justification-of-complexity experiment.
python eval/single_agent_baseline.py

# Asymmetric pairing — weak OpenAI Hypothesizer + strong Anthropic Critic.
python eval/cross_vendor_hypothesizer_experiment.py
```

Results are written to `eval/results/`. Public-data result files (trap suite, isolation A/B, JFK and Tier 3 cross-vendor and multi-Critic, ablation) are committed; anything matching `*moore*` or other personal-tree patterns stays gitignored.

## Project Structure

```
multiagent-geneaological-research-system/
├── CLAUDE.md                       # Project context for Claude Code sessions
├── README.md                       # This file
├── AI_USAGE.md                     # AI-tool disclosure log
├── requirements.txt
├── main.py                         # CLI: query mode
├── audit.py                        # CLI: subtree audit mode
├── gap_search.py                   # CLI: gap detection mode
├── app.py                          # Streamlit four-tab GUI
├── state.py                        # GenealogyState TypedDict
├── graph.py                        # LangGraph wiring + Critic revision loop
├── agents/                         # Five autonomous agents + isolation schema
├── tools/                          # GEDCOM, fuzzy, date, geo, multi-source retrieval, DNA
├── data/                           # Public GEDCOMs + synthetic DNA demos
│   ├── DNA_demo/                   # Synthetic match files (in repo)
│   ├── DNA/                        # Personal match files (gitignored)
│   └── PII Trees/                  # Personal GEDCOMs (gitignored)
├── eval/                           # Trap cases, A/B harness, cross-vendor experiments
│   ├── trap_cases/
│   └── results/                    # Gitignored — may contain personal references
├── traces/                         # Pipeline output traces (gitignored)
└── docs/                           # Architecture diagram, phase deliverables
```

A more detailed tree, including per-file responsibilities, lives in `CLAUDE.md`.

## Evaluation Summary

- **Trap suite**: 8/8 cases passing (3 Tier 1 deterministic, 3 Tier 2 plausible-but-wrong, 2 Tier 3 genuinely ambiguous). Tier 3 success criterion is appropriate uncertainty (no overconfident accept or reject), not getting a "right" answer.
- **Critic isolation A/B**: 1 of 6 hypotheses flipped verdict under the unfiltered condition; reasoning-narrative leakage from Hypothesizer to Critic measurably higher in unfiltered runs (linguistic n-gram overlap roughly doubled).
- **Multi-Critic ensemble**: 2 of 2 ambiguous Tier 3 cases correctly escalated to flag_uncertain by the conservative aggregation rule, where a single Critic running Opus 4.7 alone would have accepted.
- **Single-agent baseline ablation**: full pipeline 8/8 vs single-LLM-call baseline 4/8 on the same trap suite. Tier 1 tied (3/3 vs 3/3 — fail-fast layer wins on operational cost, not detection uniqueness); multi-agent +2 on Tier 2 (geographic + naming plausibility) and +2 on Tier 3 (ambiguity calibration).

## Tech Stack

- **Orchestration:** LangGraph (with `langchain`, `langchain-anthropic`; cross-vendor experiments add `langchain-openai` and `langchain-google-genai`).
- **LLMs:** Claude Opus 4.7 for the Critic (sharper adversarial reasoning); Claude Sonnet 4.6 for all other agents.
- **GEDCOM parsing:** `python-gedcom-2` (maintained fork).
- **Fuzzy matching:** `jellyfish` (Soundex, Metaphone, Levenshtein, Jaro-Winkler).
- **Date handling:** `python-dateutil` plus custom GEDCOM-aware normalization.
- **Geocoding:** `geopy` with Nominatim, rate-limited at 1 req/sec.
- **External sources:** `requests` + `beautifulsoup4` for the FindAGrave HTML scrape; raw HTTPS for the Wikidata SPARQL endpoint; WikiTree public REST API.
- **DNA analysis:** Shared cM Project lookup table embedded in `tools/shared_cm_lookup.py` (no clustering library — DBSCAN/scikit-learn was originally scoped for Phase 3 but deprioritized).
- **GUI:** `streamlit` plus `graphviz` (family-tree visualization) and `pandas` (audit results table).

## Status

- **Phase 1** (Scoping and Justification): Complete. Score: 97/100.
- **Phase 2** (Architecture, Prototype, Evaluation Plan): Complete.
- **Phase 3** (Final Product, Evidence, Reflection): Deliverables in final review.

## AI Usage

This project used generative AI tools (Claude via claude.ai and Claude Code) extensively across all three phases for design, code generation, document drafting, and debugging. Every use is logged in `AI_USAGE.md` with the tool used, what was asked, what was changed manually, and what was independently verified. Domain selection, evaluation criteria, and final design decisions are the developer's; AI-generated outputs were reviewed and corrected before inclusion.
