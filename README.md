# Multi-Agent Genealogical Research System with Adversarial Critique

A multi-agent pipeline that investigates genealogical questions using GEDCOM family tree data, multi-source web retrieval, and DNA match data. The pipeline pairs a Hypothesizer with an isolated Adversarial Critic, runs deterministic checks before LLM reasoning, and produces cited research reports with calibrated confidence and explicit escalation triggers for human review. Built for **94-815 Agentic Technologies** (CMU Heinz College, Spring 2026).

**Author:** Kaitlin Moore (solo project) · **Track:** A — Technical Build

## For Graders | Evaluate without an API Key

The system supports a **replay mode** that loads previously-saved pipeline traces and renders them through the same UI a live run would produce. **No LLM calls are made; no API key is required.** Reproducibility without dependence on API access was a stated requirement from the project's outset.

### Streamlit Replay (recommended)

```bash
git clone https://github.com/kaitlinmoore/multiagent-geneaological-research-system.git
cd multiagent-geneaological-research-system
python -m venv .venv
source .venv/bin/activate          # Mac/Linux
# .venv\Scripts\activate           # Windows
pip install -r requirements.txt
streamlit run app.py
```

Once the app loads, in the sidebar select **Mode → Replay (no API key)**. The Pipeline tab will offer a **Trace category** toggle (Query mode / Gap detection mode) plus a trace dropdown filtered to the chosen category. Pick a trace and the Pipeline / Family Tree / DNA Analysis tabs render from the saved state.

#### Available replay traces — Query mode

| Demo | What to look for |
|---|---|
| `Demo: trace_*_jfk_parents_with_synthetic_dna` | Clean accept on JFK's parents; DNA cross-references render in the DNA Analysis tab |
| `Demo: trace_*_habsburg_maria_theresia_synthetic_dna` | **Escalation case.** Critic disagreed across hypotheses for the same subject; pipeline force-finalized after 2 revision cycles. Triggers human-review flags 1 and 3. |
| `Demo: trace_*_queen_victoria_synthetic_dna` | Clean accept on Queen Victoria's parents (English-language royal data) |
| `Redacted: moore_myheritage_dna_redacted` | Pseudonymized real-tree run; demonstrates the redactor + real-data behavior without exposing identity. |

#### Available replay traces — Gap detection mode

| Demo | What to look for |
|---|---|
| `Demo: trace_*_kennedy_gap_demo` | **Escalation case.** Robert Sargent Shriver missing both parents; Critic rejected on both revisions, pipeline force-finalized. |
| `Demo: trace_*_habsburg_gap_demo` | Albert I von Ungarn (b. 1016), missing mother. flag_uncertain at 0.75 — medieval source ambiguity. |
| `Demo: trace_*_queen_gap_demo` | Bodilan of Burgundy, missing mother. flag_uncertain at 0.72 — same pattern. |

The Family Tree and DNA Analysis tabs auto-render from whichever trace is selected. The Family Tree tab visualizes parental relationships in three distinct visual states: solid borders for relationships in the source GEDCOM, dashed-filled borders for gap-mode proposals (color-coded by Critic verdict), and dashed-hollow placeholders for parental slots that remain unfilled.

#### Audit replay (separate loader on the Audit tab)

Audit results have a different shape than pipeline traces, so audit replay uses a dedicated loader on the **Audit tab** rather than the Pipeline trace dropdown. In Replay mode the Audit tab opens with a "📂 Load a saved audit run" expander listing:

| Demo | Subtree | Pass 1 result | Pass 2 |
|---|---|---|---|
| `Demo: audit_*_habsburg_maria_theresia` | 18 persons / 166 relationships, 3 generations | 0 impossible, 5 flagged, 161 ok | 5/5 deep-audited; all accepted at 0.75–0.93 confidence |
| `Demo: audit_*_queen_edward_vii` | 19 / 23, 4 generations | 0 flagged (clean tree) | skipped (no problems) |
| `Demo: audit_*_kennedy_jfk` | 9 / 11, 4 generations | 1 flagged | 1/1 deep-audited and accepted at 0.85 |

Pass 1 (deterministic checks) also runs interactively without an API key in either mode — pick a GEDCOM and root person, click Run Audit. Pass 2 (LLM deep audit) requires Live mode.

### Live Mode Workflow (with API key)

For each entry mode, the Streamlit workflow is:

- **Query mode** (default): pick a GEDCOM and optional DNA file, type a research question, click Run. Per-agent progress indicators advance; results render in the Pipeline tab; Family Tree and DNA Analysis tabs auto-update.
- **Gap detection**: pick a GEDCOM, click Run. The candidate scan produces a paginated table (50 per page) of persons missing parent links, ranked by data richness. To investigate one, pick it from the **Investigate a single gap** selectbox below the table and click **Run full pipeline on this gap** — that triggers the same multi-agent flow as query mode.
- **Subtree audit**: switch to the Audit tab. Pick a GEDCOM and a root person, set generations 1–5, click **Run Audit** (deterministic Pass 1; no API key needed). If problems are found, optionally click **Deep Audit Top N** to run the LLM pipeline on the top N flagged relationships (Pass 2; API key required).

### CLI Replay

```bash
python main.py --replay traces/demos/trace_20260429_201521_jfk_parents_with_synthetic_dna.json
python main.py --replay <any trace> --full-report     # dump entire saved report instead of head
```

Prints the agent trace log, the summary panel (status, hypothesis count, critique verdicts, DNA consistency), and the final report. Same output shape as a live run.

### Read-Only Artifacts (no install required)

For graders who want to review without setting up Python at all, every relevant artifact is committed and human-readable on GitHub:

- **Phase 3 final report:** [`docs/phase3_report.md`](docs/phase3_report.md)
- **Failure case analysis:** [`docs/failure_cases.md`](docs/failure_cases.md)
- **Architecture diagram:** [`docs/architecture_diagram.png`](docs/architecture_diagram.png)
- **Phase 2 deliverable PDF:** `docs/Multi-Agent Genealogy - Phase 2 - Kaitlin Moore.pdf`
- **AI tool disclosure:** [`AI_USAGE.md`](AI_USAGE.md)
- **Sample pipeline output:**
  - [`traces/demos/trace_*`](traces/demos/) — six pipeline traces: three query-mode + DNA (JFK, Maria Theresia, Queen Victoria) and three gap-mode (Kennedy/Habsburg/Queen)
  - [`traces/demos/audit_*`](traces/demos/) — three subtree-audit results (Habsburg/Queen/Kennedy) loadable from the Audit tab
  - [`traces/redacted/`](traces/redacted/) — pseudonymized real-tree run
- **Pre-rendered evaluation results:**
  - [`eval/results/ablation_summary.md`](eval/results/ablation_summary.md) — single-agent baseline vs full pipeline
  - [`eval/results/isolation_ab_summary.md`](eval/results/isolation_ab_summary.md) — Critic isolation A/B experiment
  - [`eval/results/`](eval/results/) — JSON results for the trap suite, cross-vendor experiments, and multi-Critic ensemble

## Key Architectural Feature: Critic Isolation as a Code Guarantee

The Adversarial Critic never sees the Hypothesizer's reasoning narrative, alternatives considered, or intermediate steps. This is the core agentic justification of the project. A Critic that can read the proposer's reasoning is no longer adversarial; it is a confirmation-bias amplifier.

The isolation is enforced as a code guarantee, not a naming convention. `agents/hypothesis_schema.py` declares two field sets: PUBLIC (visible to the Critic) and INTERNAL (stripped before the Critic sees a hypothesis). `filter_hypothesis_for_critic(hypothesis)` is the single read path the Critic uses. The Critic node never accesses raw `state["hypotheses"]` dicts directly. A `state["isolation_mode"]` toggle flips the filter on or off for the A/B experiment, but the production path is always filtered.

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

## Setup (Live Mode)

The instructions in this section are for running the pipeline live (which makes LLM calls). For evaluation without an API key, see the [For Graders](#for-graders--evaluate-without-an-api-key) section above.

### Prerequisites

- Python 3.12+ (3.14 works but LangChain emits a Pydantic compatibility warning)
- Anthropic API key (required for live mode; replay mode does not need one)
- Optional: OpenAI or Google Gemini API keys for the cross-vendor experiments

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

The system supports three CLI entry modes plus a Streamlit GUI. `main.py` also supports a `--replay` flag for the no-API-key path documented above.

```bash
# Query mode — full pipeline against a specific research question.
# Defaults to JFK against the Kennedy GEDCOM with the synthetic DNA demo attached.
python main.py

# Replay mode — render a saved trace deterministically; no LLM calls.
python main.py --replay traces/demos/trace_20260429_201521_jfk_parents_with_synthetic_dna.json

# Subtree audit mode — walk every parent-child link in an N-generation subtree.
# Two-pass: deterministic Tier 1 + geographic checks, then optional LLM
# full-pipeline pass on the top-N most questionable relationships.
python audit.py

# Gap detection mode — scan a GEDCOM for persons missing parent links,
# score plausible parents from within the tree, and optionally run the
# pipeline on the top-N broken links.
python gap_search.py

# Streamlit GUI. Sidebar toggle picks Live (runs the pipeline; needs API key)
# or Replay (loads a saved trace; no API calls).
streamlit run app.py
```

Live pipeline runs persist a JSON trace and a markdown summary to `traces/` (top-level files are gitignored because traces from personal trees contain PII; `traces/demos/` and `traces/redacted/` are allow-listed for the committed reproducible artifacts).

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

## Outputs Included in the Repository

The repo ships a complete reproducibility set so a grader can inspect the system without running anything:

- **Pipeline traces** — `traces/demos/` (six committed: three query + DNA, three gap-mode) and `traces/redacted/` (one pseudonymized real-tree run)
- **Audit traces** — `traces/demos/audit_*` (three: Habsburg / Queen / Kennedy subtrees)
- **Synthetic DNA demos** — `data/DNA_demo/` (hand-built ground truth for Kennedy, Maria Theresia, Queen Victoria — exercises the DNA path without committing personal match data)
- **Evaluation results** — `eval/results/` with per-experiment summary docs (`trap_suite_summary.md`, `ablation_summary.md`, `isolation_ab_summary.md`, `cross_vendor_summary.md`, `multi_critic_summary.md`) plus raw JSON for every recorded run
- **Structured eval artifacts** — `eval/test_cases.md` (16 cases), `eval/failure_log.md` (5 failures), `eval/version_notes.md` (phase-by-phase change log)
- **Final report** — `docs/Multi-Agent Genealogy - Phase 3 - Kaitlin Moore.pdf` and the source `docs/phase3_report.md`
- **Architecture diagram** — `docs/architecture_diagram.png` plus the Mermaid source
- **UI screenshots** — eight captures in `docs/screenshots/` with `screenshot_index.md`
- **Failure case analysis** — `docs/failure_cases.md` (deep narrative form)
- **Video stills + script** — `docs/video_stills.pptx`, `docs/video_script.md`

## Known Limitations

- **Cross-session memory** — none, by design. Each pipeline run is stateless. This avoids the failure mode where an early misconception poisons later runs but means the system cannot learn between runs.
- **DNA clustering** — not implemented. The DNA Analyst uses the Shared cM Project lookup table for relationship prediction without DBSCAN/scikit-learn-style clustering. Multi-match cluster detection is documented as future work.
- **Migration map visualization** — originally scoped (Folium + Newberry Atlas centroids) but deferred. PoC code in `app/` is not wired into pipeline output. Conceptual design preserved in the final report's Future Work section.
- **FamilySearch API integration** — stubbed in `tools/familysearch_search.py` but not implemented. Wikidata + WikiTree provide equivalent independent sources without the API-key registration cost.
- **GEDCOM encoding** — `python-gedcom-2` hardcodes UTF-8; the Habsburg tree (Latin-1) requires a workaround at every call site (see `tools/gedcom_parser.py`). Documented in `eval/failure_log.md` as F-04.
- **Inter-agent vocabulary contracts** — relationship strings flowing from Hypothesizer to the shared-cM lookup are guarded by an alias table rather than a typed enum. The alias-table layer is sufficient for current behavior but a runtime-contract or typed-enum boundary is the proper architectural fix; tracked as F-03 follow-up in the failure log.
- **Geocoding** — uses Nominatim with a 1 req/sec rate limit. Period-correct geocoding (place names that have shifted political boundaries over centuries) is approximate; documented as future work.
- **Reproducibility caveat** — replay mode is fully deterministic, but live runs against external LLMs are not byte-stable across model versions. The committed traces preserve the exact state at the time of each recorded run.

## AI Usage

This project used generative AI tools (Claude via claude.ai and Claude Code) extensively across all three phases for brainstorming, research, code generation and debugging, document drafting and feedback, and auditing. Every use is logged in `AI_USAGE.md` with the tool used, what was asked, what was changed manually, and what was independently verified. Domain selection, evaluation criteria, and final design decisions are the developer's; AI-generated outputs were reviewed and corrected before inclusion.
