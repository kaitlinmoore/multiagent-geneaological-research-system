# Test Cases

Structured table of evaluation cases following the rubric template
(Appendix: lightweight templates, page 16 of the assignment instructions).
Fields: `case_id`, `case_type`, `input_or_scenario`, `expected_behavior`,
`actual_behavior`, `outcome`, `evidence_or_citation`, `notes`.

The primary evaluation set is the eight-case adversarial trap suite spanning
three calibrated difficulty tiers. Three additional integration cases cover
the empirical real-data pipeline runs that ship as committed traces for
grader reproducibility. Five experiment-level cases cover the cross-cutting
evaluations (isolation A/B, single-agent ablation, multi-Critic ensemble,
cross-vendor Critic, asymmetric pairing). Total: 16 cases. The rubric's
minimum is five.

For deeper analysis see `docs/phase3_report.md` § 5 and the per-experiment
summaries in `eval/results/`.

---

## Adversarial trap suite (8 cases)

| case_id | case_type | input_or_scenario | expected_behavior | actual_behavior | outcome | evidence_or_citation | notes |
|---|---|---|---|---|---|---|---|
| **T1-01** | Tier 1 — deterministic impossibility | `tier1_parent_born_after_child.ged` — Alice Testcase b. 1850, parent born after child. Query: "Who are the parents of Alice Testcase?" | Critic rejects via Tier 1 fail-fast (`parent_younger_than_child`), no LLM invocation, confidence ≥ 0.90. | Reject at ~0.98 via Tier 1 rule. | **Pass** | `eval/results/eval_*.json` (latest); `eval/results/trap_suite_summary.md` | Deterministic check; confidence is fixed by implementation. |
| **T1-02** | Tier 1 — deterministic impossibility | `tier1_death_before_birth.ged` — Clara Impossible b. 1870, parent's death predates child's birth. | Reject via `death_before_birth` rule, confidence ≥ 0.90. | Reject at ~0.98. | **Pass** | same | |
| **T1-03** | Tier 1 — deterministic impossibility | `tier1_parent_too_young.ged` — Grace Tooyoung b. 1860, parent < 12 years old at birth. | Reject via `parent_too_young_at_birth` rule, confidence ≥ 0.90. | Reject at ~0.98. | **Pass** | same | |
| **T2-01** | Tier 2 — plausible-but-wrong | `tier2_geographically_impossible.ged` — Margaret Bianchi b. 1850 Dublin, with Sicilian-born parent in pre-mass-immigration era. | Tier 1 must NOT fire. Critic surfaces `geographic_flag_moderate_or_stronger` via geo plausibility tiers; verdict ∈ {reject, flag_uncertain}, confidence ≥ 0.50. | Reject / flag_uncertain with geographic implausibility cited. | **Pass** | `tools/geo_utils.py` haversine + era-aware tiers; `eval/results/trap_suite_summary.md` | Fix in F-02 for surname-gate is unrelated; this case tests geo signal. |
| **T2-02** | Tier 2 — plausible-but-wrong | `tier2_surname_mismatch.ged` — Lucia Rossi b. 1890 Florence, patronymic-culture father-child surname mismatch. | Tier 1 must NOT fire. Critic LLM reasoning cites the surname violation. | Reject / flag_uncertain with surname-pattern violation cited. | **Pass** | same | |
| **T2-03** | Tier 2 — plausible-but-wrong | `tier2_implausible_age_gap.ged` — Edward Longgap b. 1915 NYC, with 85-year father-child age gap (above plausibility but not deterministic-impossibility). | Tier 1 must NOT fire. Date-arithmetic plausibility flags the gap. | Reject / flag_uncertain with age-gap plausibility cited. | **Pass** | same | |
| **T3-01** | Tier 3 — genuinely ambiguous | `tier3_kennedy_duplicate_john.ged` — modified Kennedy GEDCOM with a second "John Kennedy b. 1917 Boston" injected to create matching ambiguity. Query targets that name + era. | `flag_uncertain` rather than confident accept/reject; confidence ≤ 0.85 on any non-flag verdict. | flag_uncertain at confidence below the 0.85 overconfidence ceiling. | **Pass** | `eval/results/trap_suite_summary.md`; trace JSONs in `eval/results/` | Success criterion is *appropriate uncertainty*, not "the right answer." A confident accept or reject would be a miss. |
| **T3-02** | Tier 3 — genuinely ambiguous | `tier3_kennedy_ambiguous_joseph.ged` — duplicate Joseph Patrick Kennedy ~1888 MA. | flag_uncertain, confidence ≤ 0.85 ceiling. | flag_uncertain below ceiling. | **Pass** | same | |

## Integration cases — empirical pipeline runs (3 cases)

| case_id | case_type | input_or_scenario | expected_behavior | actual_behavior | outcome | evidence_or_citation | notes |
|---|---|---|---|---|---|---|---|
| **E-01** | Real-data integration — query mode + DNA | "Who were the parents of John F. Kennedy?" against `data/The Kennedy Family.ged` + synthetic MyHeritage DNA. | Two parental hypotheses. Both should accept with high confidence; DNA evidence (3502 cM with proposed maternal match) should be `dna_relevant.cm_consistency_verdict: consistent`. | Father: accept @ 0.95. Mother: accept @ 0.92 with cm_consistency = consistent. No human-review escalation. | **Pass** | `traces/demos/trace_*_jfk_parents_with_synthetic_dna.json`; replay screenshot `docs/screenshots/Pipeline.png` | Headline demo trace for the video. |
| **E-02** | Real-data integration — query mode + escalation | Habsburg + synthetic DNA replay (Maria Theresia von Österreich). | Pipeline exercises escalation triggers. | Both findings flagged for human review: father accepted with conflicting-verdicts warning (Trigger 3); mother rejected and force-finalized after two revision cycles (Trigger 1). | **Pass** | `traces/demos/trace_*_habsburg_maria_theresia_synthetic_dna.json`; screenshot `docs/screenshots/failure.png` | Required failure / boundary-case demonstration; exercises two of three escalation triggers in one trace. |
| **E-03** | Real-data integration — subtree audit | Habsburg Maria Theresia, 3 generations, Pass 1 deterministic + Pass 2 LLM. | Pass 1 surfaces flagged + ok counts in seconds. Pass 2 runs the full pipeline on flagged subset only. | Pass 1: 28.38 s; 166 audited, 5 flagged, 161 ok, 0 impossible. Pass 2: 241.37 s; all 5 flagged relationships resolved with verdict + confidence in 0.75–0.93 range. | **Pass** | `traces/demos/audit_*_habsburg_maria_theresia.json`; screenshot `docs/screenshots/AuditResults.png` | Demonstrates the two-pass audit pattern; deterministic surface, LLM resolve. |

## Cross-cutting experiments (5 cases)

| case_id | case_type | input_or_scenario | expected_behavior | actual_behavior | outcome | evidence_or_citation | notes |
|---|---|---|---|---|---|---|---|
| **X-01** | Critic isolation A/B | 3 queries × 2 conditions (filtered vs. unfiltered hypotheses), shared-seed methodology. Tests whether filtering the Hypothesizer's reasoning out of the Critic's input changes verdicts. | Measurable change in verdict distribution and/or reasoning leakage when filter is removed. Magnitude is the experiment's output, not a hard target. | 1/6 hypotheses changed verdict under unfiltered condition. 5-gram leakage from Hypothesizer narrative into Critic justification: 13:7 unfiltered:filtered. | **Pass** (informative; effect size measurable and in expected direction) | `eval/isolation_experiment.py`; `eval/results/isolation_ab_summary.md` | Central agentic claim under direct experimental test. |
| **X-02** | Single-agent baseline ablation | Same 8 trap cases run through a single Anthropic LLM call given the same fuzzy-matched context the Critic sees, no multi-agent pipeline. | Multi-agent should outperform single-agent — gap concentrated where specialized layers help (Tier 2 / Tier 3). Tied or near-tied on Tier 1 (deterministic rules don't need agents). | Full pipeline 8/8; single-agent baseline 4/8. Tied on Tier 1 (3/3 vs 3/3). +2 on Tier 2 (3/3 vs 1/3). +2 on Tier 3 (2/2 vs 0/2). | **Pass** | `eval/single_agent_baseline.py`; `eval/results/ablation_summary.md` | The 4-case gap concentrates exactly where the multi-agent design's specialized layers should help. |
| **X-03** | Multi-Critic ensemble | 3 Critics from different vendors (Anthropic Opus 4.7, OpenAI GPT-5.5, Google Gemini 2.5 Pro) voting under conservative aggregation: any reject → reject; any flag_uncertain → flag_uncertain; unanimous accept required for accept. Run on Tier 3 ambiguous cases where Anthropic Opus alone accepted. | Ensemble should escalate to flag_uncertain on the cases where single-Critic Opus accepted, demonstrating vendor independence catches different blind spots. | 2/2 ambiguous Tier 3 cases correctly escalated to flag_uncertain. | **Pass** | `eval/multi_critic_ensemble_experiment.py`; `eval/results/multi_critic_summary.md` | Highest-impact result; addresses Phase 2 feedback that same-vendor models share training data. |
| **X-04** | Cross-vendor Critic comparison | Symmetric — Anthropic Opus 4.7 Critic vs OpenAI GPT-5.5 Critic on the same hypothesis set. | Disagreement on ambiguous cases is a useful signal; convergence on unambiguous cases strengthens findings. | On Tier 3 ambiguous: OpenAI flagged where Anthropic accepted — confirming independent failure modes. On unambiguous JFK: both vendors converged on accept. | **Pass** (informative) | `eval/cross_vendor_critic_experiment.py`; `eval/results/cross_vendor_summary.md` | Single-vendor evaluation would miss the ambiguity signal entirely. |
| **X-05** | Asymmetric pairing experiment | Weak OpenAI Hypothesizer (gpt-4o-mini) + strong Anthropic Opus 4.7 Critic. Tests whether a strong adversary catches a weak proposer's mistakes (the architectural claim made directly testable). | If the strong Critic catches mistakes the strong-strong baseline does not produce, the architecture earns its complexity. | Weak Hypothesizer produced **zero hypotheses** on the test cases (JFK, Moore gap, Tier 3 duplicate). No analyzable verdicts; experiment is re-runnable but inconclusive on these specific cases. | **Inconclusive** (null result honestly disclosed) | `eval/cross_vendor_hypothesizer_experiment.py`; `eval/results/cross_vendor_summary.md` § "Asymmetric pairing experiment" | The architectural claim is supported by X-03 (multi-Critic ensemble) instead. AI_USAGE Entry 21 should reflect this null finding (open follow-up). |

---

## Outcome legend

- **Pass** — actual matched expected behavior or expected-direction signal.
- **Inconclusive** — experiment ran but produced no analyzable evidence.
- **Fail** — actual diverged from expected. None in this set; failure modes encountered during development are tracked in `eval/failure_log.md`.

## How this file relates to other artifacts

- **`eval/run_eval.py`** + **`eval/trap_cases/manifest.json`** — runnable harness for T1-01 through T3-02.
- **`eval/results/*.md`** — per-experiment summary docs cross-referenced in the table.
- **`eval/results/*.json`** — raw run output; one JSON per recorded run.
- **`docs/phase3_report.md` § 5** — narrative interpretation of the same results.
- **`docs/failure_cases.md` + `eval/failure_log.md`** — bugs encountered during development that are deliberately *not* in this table because they did not reach the evaluation surface.
