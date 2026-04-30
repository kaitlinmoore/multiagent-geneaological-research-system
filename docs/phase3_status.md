# Phase 3 Status Audit

_Generated 2026-04-29. Snapshot of what's done, what's outstanding, and where each
item lives. Source: CLAUDE.md checklist + repo inspection (eval/, traces/, docs/)._

---

## Code & Capabilities — DONE

| Capability | Files | Evidence |
|---|---|---|
| 5 agents + deterministic Final Report Writer | `agents/*.py` | 6 files |
| LangGraph orchestration with Critic loop (max 2 revisions) | `graph.py` | router conditional edge |
| Critic isolation as code guarantee | `agents/hypothesis_schema.py` | `filter_hypothesis_for_critic()` |
| `state["isolation_mode"]` A/B toggle | `state.py`, `agents/adversarial_critic.py` | filtered/unfiltered path |
| Multi-source retrieval | `tools/findagrave_search.py`, `wikidata_search.py`, `wikitree_search.py` | 3 sources |
| DNA Analyst integrated into reasoning loop (not just reporter) | `agents/dna_analyst.py`, `agents/relationship_hypothesizer.py` (DNA corroboration), `agents/adversarial_critic.py` (`dna_relevant`) | trace artifacts |
| Shared cM Project lookup with relationship-string aliases | `tools/shared_cm_lookup.py` | `_RELATIONSHIP_TABLE` + 30+ aliases |
| Gap detection mode | `gap_search.py`, `tools/gap_scanner.py` | CLI runs |
| Subtree audit mode (two-pass) | `audit.py`, `tools/subtree_extractor.py` | CLI runs |
| Streamlit app, 4 tabs | `app.py` | Pipeline / Family Tree / Audit / DNA Analysis |
| Family tree visualization with verdict-coloured nodes | `app.py` (graphviz) | Family Tree tab |
| Three-trigger human escalation | `agents/final_report_writer.py` (`check_escalation`) | report sections |
| Trace persistence (JSON + MD, dna_analysis preserved) | `tools/trace_writer.py` | `traces/demos/` |
| Synthetic DNA demos (no PII, reproducible) | `data/DNA_demo/{JFK, Maria_Theresia, Victoria_Hanover}_synthetic_DNA.csv` | 3 files, all verified to cross-reference |
| PII redactor for personal-tree traces | `tools/redact_trace.py` | `traces/redacted/moore_*.md` |
| `.gitignore` cleanup, demo/redacted allow-listed, PII paths gitignored | `.gitignore` | `git check-ignore` confirmed |

## Evaluation Artifacts — DONE

| Artifact | Path | Status |
|---|---|---|
| 8 trap cases (3 Tier 1, 3 Tier 2, 2 Tier 3) | `eval/trap_cases/*.ged` + `manifest.json` | Built |
| Trap eval results | `eval/results/eval_2026041*.json` | 4 runs |
| Critic isolation A/B (3 queries × 2 conditions) | `eval/results/isolation_*.json` + `isolation_ab_summary.md` | Aggregated |
| Cross-vendor Critic experiment (Anthropic vs OpenAI) | `eval/cross_vendor_critic_experiment.py` + `eval/results/cross_vendor_*.json` | 3 runs |
| Asymmetric pairing (weak OpenAI Hypothesizer + Opus 4.7 Critic) | `eval/cross_vendor_hypothesizer_experiment.py` + 3 result JSONs | Done |
| Multi-Critic ensemble (Anthropic + OpenAI + Gemini) | `eval/multi_critic_ensemble_experiment.py` + 4 result JSONs | Done |
| Critic model comparison (Sonnet 4.6 vs Opus 4.0 vs Opus 4.7) | trace files | Documented in CLAUDE.md |

## Documentation — IN PROGRESS

| Item | Path | Status |
|---|---|---|
| CLAUDE.md (Phase 3 reflective state) | `CLAUDE.md` | Up-to-date as of this audit |
| README.md | `README.md` | **STALE** — references "Phase 3 in progress, remaining: DNA Analyst, Streamlit, full eval" — all done. Needs Phase 3-complete rewrite. |
| Architecture diagram | `docs/architecture_diagram.{mermaid,png}` | **JUST UPDATED** to reflect sequential DNA placement and isolation filter as boundary |
| Phase 1 written deliverables | (submitted, not in repo) | Done (97/100) |
| Phase 2 written deliverables | `docs/Multi-Agent Genealogy - Phase 2 - Kaitlin Moore.pdf` | Done |
| Phase 3 final report | _(not started)_ | OUTSTANDING |
| AI_USAGE.md Phase 3 entries | `AI_USAGE.md` | Phases 1+2 only; **Phase 3 missing entirely** |

## Submission Deliverables — OUTSTANDING

| Deliverable | Owner | Blocker |
|---|---|---|
| Phase 3 final report (12-18 pages) | mostly Claude Code, prose from claude.ai outline | needs failure-case docs decided |
| 5-minute video | user | needs storyboard + script (in flight via Stream C) |
| AI_USAGE.md Phase 3 entries | Claude Code (drafting) + user (reviewing) | needs prompt history compiled |
| Failure case analysis (≥2 documented) | Claude Code | candidates in CLAUDE.md notes; **need to choose 2** |
| Submission packet PDF | user (Word/PDF compile) | needs final report |
| Architecture diagram PDF | trivial | will do alongside report compile |
| Repo cleanup pass (final) | Claude Code | end of project |
| CLAUDE.md final-state update | Claude Code | end of project |

## Open Decisions (need your input)

1. **Failure cases — pick 2 of these to document in the report:**
   - **Gap-mode 0-hypotheses bug** — when Scout's gap_mode returned candidates but Hypothesizer found nothing because of a state-key mismatch
   - **Parallel-branch report writer firing prematurely** — DNA Analyst as parallel branch crashed the Critic-revision join semantics; root cause for the eventual sequential placement
   - **Joan Knorr name-only fuzzy match false positive** — surname-gate added (0.60 floor) after this
   - **Habsburg encoding crash** — `python-gedcom-2.parse_file()` hardcodes utf-8-sig; root cause for the read-then-parse-text workaround
   - **Hypothesizer relationship-string drift** — "father of"/"mother of" weren't in `shared_cm_lookup` aliases until 2026-04-29; consistency check silently inverted
   
   I'd recommend the parallel-branch one (deepest design lesson) + the Joan Knorr one (cleanest pre/post comparison). Both have clear root causes and clean fixes. Tell me if you'd swap.

2. **Streamlit grader-facing UX** — Stream B's session is going to look at this; do you want me to wait until Stream B reports back before drafting the report's "Implementation" section, or should I write it now from the existing app.py state and update later?

3. **Ablation comparison** — CLAUDE.md flags this as "to be evaluated for inclusion." Recommendation: drop it. It wasn't required by the assignment (we confirmed earlier this session), and the cross-vendor + multi-Critic + isolation A/B already demonstrate empirical evaluation depth. Including it adds work without rubric coverage.

## Outstanding Phase 2 Carry-overs

CLAUDE.md lists two Phase 2 items as "outstanding":
- Risk and governance plan — will live in Phase 3 final report's governance section instead. Not separate.
- AI_USAGE.md Phase 2 entries — actually present (entries 4-8 in the file). CLAUDE.md is wrong; will fix when CLAUDE.md gets its final-state update.

---

## Suggested next moves (in dependency order)

1. **Stream A (this session, immediate):** Pick the 2 failure cases. Draft them as standalone subsections so they're ready to drop into the report.
2. **Stream A:** Run the synthetic-DNA pipeline on Habsburg + Queen, produce demo traces under `traces/demos/`.
3. **Stream A:** Write the Phase 3 report from claude.ai's outline + this audit + failure-case drafts + eval results.
4. **Stream A:** AI_USAGE.md Phase 3 entries.
5. **Stream A:** README rewrite + final CLAUDE.md update.
6. **You:** Screenshots after Stream B reports back.
7. **You:** Record video using Stream C's script.
