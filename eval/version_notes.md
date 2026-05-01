# Version Notes

Chronological record of significant changes to the project across the three
course phases. Versions are anchored to git commit dates rather than semver
because the project is solo and was developed in a continuous push toward
each phase deadline; the dates and commit hashes below are the auditable
references.

For per-bug context see `eval/failure_log.md`.
For per-experiment results see `eval/test_cases.md`.

---

## Phase 1 — Scoping and Justification (April 9–13, 2026)

| Date | Commit | Change | Notes |
|---|---|---|---|
| 2026-04-09 | `454727c` | Initial commit | Repository created. |
| 2026-04-13 | `1621ba7` | Phase 2 deliverables checkpoint (committed during Phase 1 transition) | Multi-Agent System Canvas, per-agent Agent Canvases, problem statement, agentic justification, initial architecture, scope boundaries. Phase 1 score: 97/100. |

Phase 1 work was conceptual: scoping document, system canvases, agentic
justification, scope boundaries. No runnable code committed.

## Phase 2 — Architecture, Prototype, and Evaluation Plan (April 13–23, 2026)

| Date | Commit | Change | Notes |
|---|---|---|---|
| 2026-04-13 | `1621ba7` | Phase 2 deliverables | Architecture diagram, role definitions, coordination logic, evaluation plan with 8 test scenarios, risk and governance plan. |
| 2026-04-13 | `afe7b87` | README | Initial README. |
| 2026-04-22 | `85631fd` | Map branch config updates | Map / Newberry Atlas exploration (later deferred to future work). |
| 2026-04-23 | `7abd3ea` | Final presentation file | Phase 2 final presentation. |

Phase 2 produced a working prototype of the core agent flow (Scout →
Synth → Hypothesizer ⇄ Critic), per-agent role definitions, the trap
case taxonomy, and the architecture diagram in Mermaid + PNG.

## Phase 3 — Final Product, Evidence, and Reflection (April 22 – May 1, 2026)

### Stream A: Architecture and pipeline expansion

| Date | Commit | Change | Notes |
|---|---|---|---|
| 2026-04-29 | `469da9e` | Add `isolation_mode` and `dna_analysis` to GenealogyState | State schema extended for the two cross-cutting Phase 3 concerns. |
| 2026-04-29 | `2f16e75` | Multi-source retrieval + gap mode | Scout integrated with FindAGrave, Wikidata, WikiTree; gap-detection entry path added. |
| 2026-04-29 | `7a19752` | Gap detection and subtree audit entry modes | `gap_search.py` and `audit.py` entry points; `tools/gap_scanner.py`, `tools/subtree_extractor.py`. |
| 2026-04-29 | `614b6de` | DNA Analyst integration into the Hypothesizer reasoning loop | Originally a parallel branch off Scout; serialized after F-01 surfaced. |
| 2026-04-29 | `d0439bc` | Three-trigger human escalation in Final Report Writer | Escalation logic moved out of agents into deterministic post-pipeline pass. |
| 2026-04-29 | `8771883` | Failure case analysis | First version of `docs/failure_cases.md`. |

### Stream B: Evaluation experiments

| Date | Commit | Change | Notes |
|---|---|---|---|
| 2026-04-29 | `0548044` | Evaluation and ablation experiments | `eval/single_agent_baseline.py`, cross-vendor scaffolding. |
| 2026-04-30 | `b00a4f8` | Eval summaries | `trap_suite_summary.md`, `ablation_summary.md`, `isolation_ab_summary.md`, `cross_vendor_summary.md`. |
| 2026-04-30 | `ab78aba` | Multi-Critic ensemble summary | `multi_critic_summary.md` covering the 3-vendor ensemble result (2/2 ambiguous cases escalated). |
| 2026-04-30 | `efaa4d7` | Eval smoke test after code updates | Re-ran trap suite (Tier 1 3/3) post-architecture-changes to confirm no regression. |

### Stream C: Reproducibility and replay

| Date | Commit | Change | Notes |
|---|---|---|---|
| 2026-04-29 | `523e83c` | Synthetic DNA datasets and testing and privacy features | `data/DNA_demo/` synthetic DNA for grader reproducibility; `tools/redact_trace.py`. |
| 2026-04-30 | `4da17e0` | Integrate replay mode into UI | Sidebar Live / Replay toggle. |
| 2026-04-30 | `a499a66` | Documentation update with replay-mode details | README + AI_USAGE updated. |
| 2026-04-30 | `8aca923` | Finish audit-mode replay | Audit tab gains saved-run loader. |
| 2026-04-30 | `3b49ce3` | Gap-mode replay traces for Kennedy, Habsburg, Queen | Public-data demo traces committed for grader reproducibility. |
| 2026-04-30 | `4a6b9de` | Category-aware replay dropdown + bare-surname scrub in redactor | UX + privacy hardening. |

### Stream D: UX and Streamlit polish

| Date | Commit | Change | Notes |
|---|---|---|---|
| 2026-04-29 | `d575115` | DNA file dropdown in Pipeline tab | |
| 2026-04-29 | `6e55e0d` | Data-availability banner + Audit-tab empty-state hint | |
| 2026-04-29 | `2ca2db9` | Explicit mode selector + gap-detection summary view | |
| 2026-04-30 | `fbbdab8` | Streamlit UX theme settings | |
| 2026-04-30 | `9d0fbda` | Disable non-relevant UI components in gap mode; fix single-gap runner; expand replay options | |
| 2026-04-30 | `efc420b` | Fix tree display for gap mode | |
| 2026-04-30 | `e9c0a63` | UI fixes — stale outputs and settings clear correctly | |
| 2026-04-30 | `63cb5ca`, `4775763`, `995805e` | Additional UI fixes | |
| 2026-04-30 | `69ec63d` | Fix Pass-2 button (replay-mode disable + tooltip) | |
| 2026-04-30 | `a1106c7` | Drop stale `pipeline_result` when trace validation fails | |
| 2026-04-30 | `9fcfd87` | Human-readable timestamps in display | |

### Stream E: Documentation and deliverables

| Date | Commit | Change | Notes |
|---|---|---|---|
| 2026-04-29 | `8d2c178` | Rewrite README for Phase 3 complete state | |
| 2026-04-29 | `e635857` | AI_USAGE Phase 3 entries | |
| 2026-04-30 | `db6d9a6` | Merge: README + AI_USAGE Phase 3 entries from docs-update | |
| 2026-04-30 | `a701671` | Updated documentation | |
| 2026-04-30 | `9893b47` | Fixed AI_USAGE numbering | |
| 2026-04-30 | `2fac5e6` | Documentation matched to updated replay selection | |
| 2026-04-30 | `2fc8b01` | Documentation expanded to cover specific failure mode | F-05 description corrected. |
| 2026-04-30 | `5153018` | Cleanup agent and tool docstrings | |
| 2026-04-30 | `8831fe3` | Updated architecture diagram | Orchestrator wrapper, memory subgraph, replay arrow added. |
| 2026-04-30 | `3f8c0a8` | Final Phase 3 report | `docs/phase3_report.md` complete. |
| 2026-05-01 | `9e52d40` | Final AI log | AI_USAGE finalized. |
| 2026-05-01 | `6a6ef1f` | Screenshots | Eight UI screenshots captured + screenshot index. |
| 2026-05-01 | `88a6bc8` | Final report with screenshot links | Inline figure references added to report .docx. |

---

## Bug fixes folded into the streams above

The following fixes are tracked in detail in `eval/failure_log.md`. They are
referenced here by ID for cross-linking.

| ID | Symptom | Stream | Resolution date |
|---|---|---|---|
| F-01 | Final Report Writer fired before Critic loop completed (LangGraph join semantics) | Stream A | 2026-04-29 (DNA Analyst sequentialized) |
| F-02 | Cross-surname false positive on Moore tree at scale | Stream A | 2026-04-29 (surname gate at 0.60 floor in `tools/fuzzy_match.py`) |
| F-03 | Silent verdict inversion from inter-agent vocabulary drift | Stream A | 2026-04-29 (alias table extended in `tools/shared_cm_lookup.py`); typed-enum boundary contract is open follow-up |
| F-04 | `python-gedcom-2` Latin-1 encoding crash on Habsburg | Stream A | 2026-04-29 (workaround in `tools/gedcom_parser.py`) |
| F-05 | Gap-mode produced zero hypotheses (state-key mismatch) | Stream A | 2026-04-29 (Scout writes to `retrieved_records` regardless of mode) |

---

## Out of scope decisions made during Phase 3

| Date | Decision | Rationale |
|---|---|---|
| 2026-04-29 | Migration map visualization (Folium + Newberry Atlas) deferred to future work | PoC code exists in `app/` directory but was not integrated with pipeline output. The agent system is the project's core thesis; the map was a stretch goal. Conceptual design preserved in report § 8. |
| 2026-04-29 | DNA clustering (DBSCAN / scikit-learn) deferred | Shared cM lookup table is sufficient for relationship prediction without clustering. Multi-match cluster detection is documented as future work. |
| 2026-04-29 | FamilySearch API integration not implemented | `tools/familysearch_search.py` stubbed but requires API-key registration. Wikidata + WikiTree provide equivalent independent sources without that cost. |
| 2026-04-30 | Persistent cross-session memory not implemented | Each pipeline run is stateless. Avoids the failure mode where an early misconception poisons later runs and keeps the system auditable. |

---

## Summary of versions

There is no formal versioning. The submission state is the `main` branch
HEAD as of the Canvas submission deadline. The commit hash at the time of
submission identifies the exact state.

**Phase 1 submission state:** commit `1621ba7` (2026-04-13)
**Phase 2 submission state:** commit `7abd3ea` (2026-04-23)
**Phase 3 submission state:** commit `88a6bc8` (2026-05-01) — most recent at the time of writing; will update if further commits land before the deadline.
