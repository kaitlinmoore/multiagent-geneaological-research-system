# Phase 3 Submission Packet

**Course:** 94-815 Agentic Technologies — CMU Heinz College, Spring 2026

---

## 1. Project title

**Multi-Agent Genealogical Research System with Adversarial Critique and DNA Verification**

## 2. Team members

Kaitlin Moore

## 3. Selected track

**Track A — Technical Build**

## 4. One-paragraph project summary

This project is a multi-agent system that critiques genealogical claims before they propagate. Five autonomous agents (Record Scout, DNA Analyst, Profile Synthesizer, Relationship Hypothesizer, Adversarial Critic) plus a deterministic Final Report Writer are orchestrated through LangGraph: the Scout retrieves records from GEDCOM, FindAGrave, Wikidata, and WikiTree; the Synthesizer disambiguates candidates and produces sourced profiles; the Hypothesizer proposes relationships with cited evidence chains; and the Critic — structurally prevented from seeing the Hypothesizer's reasoning narrative via a code-enforced isolation filter — attacks each hypothesis with deterministic Tier-1 checks, geographic plausibility, DNA consistency lookups, and LLM reasoning. The system supports three entry modes (natural-language query, gap detection across orphaned tree branches, and subtree audit), runs against four public test trees plus the developer's personal Moore tree, and was evaluated across an 8-case adversarial trap suite (8/8 detected), a 4/8 single-agent baseline ablation, a Critic isolation A/B experiment (1/6 verdict change, 13:7 reasoning-leakage ratio), a 3-vendor multi-Critic ensemble (2/2 ambiguous cases correctly escalated), and a multi-version Critic-model comparison. The agentic claim is concrete and testable: adversarial critique with structurally enforced isolation catches errors that a single LLM call given the same context does not, and the gap concentrates exactly where the multi-agent design's specialized layers should help.

## 5. Repository

**GitHub:** <https://github.com/kaitlinmoore/multiagent-geneaological-research-system>

## 6. 5-minute project video

**YouTube:** <https://youtu.be/77XGY9_FW9s>

## 7. Final report

`docs/Multi-Agent Genealogy - Phase 3 - Kaitlin Moore.pdf`

Sections: Executive Summary · Problem Framing and Agentic Justification · System Architecture (pipeline / orchestration / memory organization / human escalation triggers) · Implementation Summary · Evaluation (trap suite, isolation A/B, cross-vendor, multi-Critic ensemble, single-agent ablation, empirical pipeline runs) · Failure Cases · Risk and Governance · Future Work · Reflection.

## 8. Architecture diagram

`docs/architecture_diagram.png` — six nodes wrapped in a LangGraph orchestrator layer, with the Critic isolation filter highlighted as the architectural lynchpin and a four-tier memory subgraph (working state · within-run trace · episodic / persisted · semantic / reference) showing the replay arrow.

Source: `docs/architecture_diagram.mermaid`.

## 9. Screenshot index

`docs/screenshots/screenshot_index.md` — eight UI screenshots covering the rubric's eight categories (home, main interaction, evidence/citation, saved state, artifact generation, evaluation/results, failure/boundary case, settings/controls), each with a one-line caption, a "why it matters" entry, and a section pointer into the final report.

Files (in `docs/screenshots/`):

- `Home Screen Live.png` — landing view, Live mode
- `Pipeline.png` — JFK trace replay, both findings accepted
- `Evidence.png` — evidence chain + Hypothesizer's stated weaknesses
- `history_or_state.png` — trace selector with four committed demo runs
- `FamilyTree.png` — verdict-colored family tree visualization
- `AuditResults.png` — Habsburg subtree audit (5 flagged, 161 ok of 166)
- `failure.png` — escalation trigger demonstration
- `Options.png` — mode selector + Live/Replay toggle

## 10. Evaluation summary

**Headline figure:** `docs/evaluation_summary.png` — four-panel infographic showing trap suite results, ablation comparison, isolation A/B numbers, and multi-Critic ensemble outcome.

**Underlying eval files** (in `eval/results/`):

- `trap_suite_summary.md` — 8/8 across all three difficulty tiers
- `ablation_summary.md` — full pipeline 8/8 vs single-agent baseline 4/8; gap concentrated in Tier 2 / Tier 3
- `isolation_ab_summary.md` — 1/6 verdict change, 13:7 reasoning-leakage ratio
- `cross_vendor_summary.md` — Anthropic Opus 4.7 vs OpenAI GPT-5.5 vs Google Gemini 2.5 Pro
- `multi_critic_summary.md` — 3-vendor ensemble, 2/2 ambiguous cases correctly escalated under conservative aggregation
- Raw JSON results for every recorded run alongside each summary

**Failure analysis:** `eval/failure_log.md`, `docs/failure_cases.md` — three deeply documented cases (parallel-branch Writer race, surname-gate fuzzy-match false positive, alias-drift verdict inversion) plus two appendix items.

**Test cases:** `eval/test_cases.md` — 16 evaluation cases in the rubric's structured format (`case_id`, `case_type`, `input_or_scenario`, `expected_behavior`, `actual_behavior`, `outcome`, `evidence_or_citation`, `notes`). Covers the 8-case adversarial trap suite, 3 empirical pipeline runs, and 5 cross-cutting experiments. Rubric minimum is 5; this set delivers 16.

**Version notes:** `eval/version_notes.md` — chronological record of project changes across the three phases, anchored to git commit dates. Phase 3 changes are organized into five concurrent streams (architecture / evaluation / reproducibility / UX / documentation), with cross-references to the bug fixes in `failure_log.md` and the four "out of scope" decisions made during Phase 3.

## 11. List of submitted files and folders

```
multiagent-genealogical-research-system/
├── README.md
├── AI_USAGE.md
├── CLAUDE.md
├── requirements.txt
├── main.py                  # CLI entry — query mode + replay
├── audit.py                 # CLI entry — subtree audit
├── gap_search.py            # CLI entry — gap detection
├── app.py                   # Streamlit four-tab application
├── state.py                 # GenealogyState TypedDict + reducer
├── graph.py                 # LangGraph wiring
├── agents/
│   ├── record_scout.py
│   ├── profile_synthesizer.py
│   ├── relationship_hypothesizer.py
│   ├── adversarial_critic.py
│   ├── dna_analyst.py
│   ├── final_report_writer.py
│   └── hypothesis_schema.py        # isolation filter
├── tools/
│   ├── gedcom_parser.py
│   ├── fuzzy_match.py
│   ├── date_utils.py
│   ├── geo_utils.py
│   ├── findagrave_search.py
│   ├── wikidata_search.py
│   ├── wikitree_search.py
│   ├── shared_cm_lookup.py
│   ├── dna_parser.py
│   ├── gap_scanner.py
│   ├── subtree_extractor.py
│   ├── redact_trace.py
│   └── trace_writer.py
├── data/
│   ├── The Kennedy Family.ged
│   ├── Habsburg.ged
│   ├── Queen.ged
│   ├── Middle Earth.ged
│   ├── DNA/                        # GEDmatch + MyHeritage CSVs
│   ├── DNA_demo/                   # synthetic DNA for grader reproducibility
│   └── PII Trees/                  # gitignored — personal Moore family GEDCOMs
├── eval/
│   ├── test_cases.md               # 16 evaluation cases in rubric structure
│   ├── failure_log.md              # 5 failures in rubric structure
│   ├── version_notes.md            # phase-by-phase change log
│   ├── trap_cases/                 # 8 trap GEDCOMs across 3 tiers
│   ├── isolation_experiment.py
│   ├── single_agent_baseline.py
│   ├── cross_vendor_critic_experiment.py
│   ├── cross_vendor_hypothesizer_experiment.py
│   ├── multi_critic_ensemble_experiment.py
│   ├── run_eval.py
│   └── results/                    # JSON + summary markdown per experiment
├── traces/
│   ├── demos/                      # six trace + three audit demos for replay
│   └── redacted/                   # redacted Moore trace
└── docs/
    ├── phase3_report.md
    ├── Multi-Agent Genealogy - Phase 3 - Kaitlin Moore.pdf
    ├── Multi-Agent Genealogy - Phase 3 - Kaitlin Moore.docx
    ├── architecture_diagram.mermaid
    ├── architecture_diagram.png
    ├── arch_stage_1.png … arch_stage_5.png    # staged reveal for video
    ├── evaluation_summary.png
    ├── failure_cases.md
    ├── video_script.md
    ├── video_stills.pptx
    ├── submission_packet.md                    # this document
    └── screenshots/
        ├── screenshot_index.md
        └── 8 PNG files
```
