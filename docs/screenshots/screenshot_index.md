# Screenshot Index

Eight UI screenshots covering the rubric categories in
*Agentic Systems Studio Assignment Instructions* (page 13). Each entry
maps a screenshot to what it demonstrates and where it is referenced in
the final report (`docs/phase3_report.md`).

---

| screenshot_file | caption | why_it_matters | where_it_is_discussed_in_the_report |
|---|---|---|---|
| `Home Screen Live.png` | Streamlit landing view in Live mode — four-tab layout, mode radio at Auto-detect, data-availability banner, and the input panel for GEDCOM, optional DNA file, and research query. | Establishes the landing view a grader sees and the entry-point UX. The four tabs preview the system's surface area; the data banner makes provenance and PII boundaries visible up front. | §4.2 Three entry modes; §7.5 Reproducibility without API access. |
| `Pipeline.png` | Pipeline tab in Replay mode with the JFK trace loaded — both parental hypotheses accepted, no human review required. | Demonstrates an end-to-end run a grader can reproduce without an API key. Shows the system's main output shape: structured findings with verdicts, not free text. The accepted-without-escalation status frames the failure-case screenshot below. | §5.6 Empirical pipeline runs (JFK); §3.4 Human escalation triggers; §7.5 Reproducibility. |
| `Evidence.png` | Expanded JFK *mother of* hypothesis card showing the full evidence chain (GEDCOM citations, 3502 cM MyHeritage DNA evidence) and the Hypothesizer's stated weaknesses against its own claim. | The single most direct evidence for the system's citation discipline and adversarial honesty. Every fact cites a record_id; the Hypothesizer is required to enumerate weaknesses against its own claim before the Critic ever sees it. This is what "agentic" looks like in practice for this domain. | §4.3 The Critic isolation guarantee in detail; §4.4 DNA Analyst integration into the reasoning loop. |
| `history_or_state.png` | Replay sidebar with trace-category radio and the dropdown expanded to show four committed demo traces (JFK, Habsburg, Queen Victoria, redacted Moore). | Concrete UI realization of the episodic / persisted memory tier in the architecture diagram — past runs are first-class addressable artifacts. Also documents the redacted-trace approach to surfacing real-data behavior without exposing PII. | §3.3 Orchestration and memory organization; §7.1 Privacy and PII; §7.5 Reproducibility. |
| `FamilyTree.png` | Family Tree tab on the JFK run — verdict-colored nodes, three-state border legend at top, accepted parents in green with confidence values 0.95 and 0.92. | The signature generated artifact of the system. Each connection is annotated with the Critic's verdict and confidence — the visualization itself is an evidence-bearing object, not just decoration. The legend at top captures the visual grammar that distinguishes in-GEDCOM relationships from system-proposed gap fills. | §5.6 Empirical pipeline runs (Family Tree visualization paragraph). |
| `AuditResults.png` | Habsburg Maria Theresia audit results — 166 relationships checked, 5 flagged for deep review, 161 ok, with the severity table and issue details visible. | This is the system's evaluation/results screen in the most concrete sense — every parent-child link in a 3-generation subtree audited deterministically, with the LLM tier reserved for the small number of cases that need it. The two-pass pattern (deterministic surface, then LLM resolve) is the project's most defensible engineering choice. | §4.2 Three entry modes (audit mode); §5.6 Empirical pipeline runs (Habsburg audit). |
| `failure.png` | Habsburg + synthetic DNA replay with both findings flagged for human review — father accepted but with a conflicting-verdicts warning, mother rejected and force-finalized after two revision cycles. | The required failure / boundary-case shot. Exercises two of the three escalation triggers simultaneously: force-finalize after max revisions (Trigger 1) and conflicting verdicts on the same subject (Trigger 3). Demonstrates that the system surfaces uncertainty rather than papering over it. | §3.4 Human escalation triggers; §5.6 Empirical pipeline runs (Habsburg + synthetic DNA demo). |
| `Options.png` | Pipeline-tab mode selector (Auto-detect / Query / Audit / Gap detection) with the Query-mode scope-expander affordance visible, alongside the sidebar Live / Replay toggle. | Documents the system's user-facing controls and the UX-affordance fix from late Phase 3 — Query mode's supported patterns are no longer hidden. The Live/Replay toggle adjacent makes the API-key-free reproducibility path visible as a setting, not a buried feature. | §4.2 Three entry modes; §7.5 Reproducibility without API access. |

---

## Notes for the grader

- All eight screenshots live in `docs/screenshots/`.
- Filenames are descriptive rather than numbered (the rubric's `01_home.png`
  pattern is recommended, not required); the table above orders them
  rubric-category-by-category so the eight rubric expectations are
  satisfied in sequence: home → main interaction → evidence/source →
  saved state → artifact → evaluation → failure → settings.
- Replay-mode screenshots (`Pipeline.png`, `history_or_state.png`,
  `FamilyTree.png`, `AuditResults.png`, `failure.png`) were captured
  against committed traces in `traces/demos/` and `traces/redacted/` —
  any grader can reproduce these views without an Anthropic API key.
