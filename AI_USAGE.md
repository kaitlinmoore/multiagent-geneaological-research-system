# AI_USAGE.md

## Multi-Agent Genealogical Research System with Adversarial Critique and DNA Verification

**Author:** Kaitlin Moore  
**Track:** A (Technical Build) | Solo  
**Course:** 94815 Agentic Technologies  

---

## Overview

This document logs all uses of generative AI tools throughout the project. For each use, it records what tool was used, what it was used for, what was changed manually, and what was independently verified. Per course policy, AI assistance is acknowledged transparently, and the final submission reflects my own judgment and design decisions.

---

## Phase 1: Scoping and Justification

### Entry 1 — Project Ideation and Domain Selection

| Field | Details |
|-------|---------|
| **Tool** | Claude Opus 4.6 (Anthropic), via claude.ai |
| **Purpose** | Brainstorming project ideas, evaluating domains (GeoAI, space/planetary, biomedicine, genealogy, game-based), assessing feasibility, data accessibility, evaluation strategies, and agentic justification strength across candidates |
| **Prompt summary** | Extended multi-turn conversation exploring project ideas for the Agentic Systems Studio assignment. Began with open-ended brainstorming, then iteratively narrowed through structured questions about priorities (interview impact, evaluation clarity, personal interest, risk tolerance), domain expertise, data availability, and contamination resistance. Explored specific concerns including LLM training data contamination in evaluation, domain expertise requirements, and API access feasibility. |
| **What was changed manually** | Final domain selection (genealogy) was the my decision based on personal domain expertise, hobby involvement, and alignment with genetics background. Claude presented multiple options with tradeoffs; I evaluated and chose. |
| **What was verified independently** | FamilySearch API access requirements reviewed on familysearch.org/developers. GEDCOM export capability from Ancestry verified through my own Ancestry account. Availability of Shared cM Project data confirmed via DNA Painter website. |

---

### Entry 2 — Phase 1 Written Deliverables

| Field | Details |
|-------|---------|
| **Tool** | Claude Opus 4.6 (Anthropic), via claude.ai |
| **Purpose** | Drafting the Phase 1 written deliverables document (project summary, target user, problem statement, agentic justification, architecture, success criteria, scope, risks, team plan, Track A additions) |
| **Prompt summary** | "Sketch out Phase 1 for genealogy" followed by "Let's build the written deliverables" and format preferences. Claude generated a complete Word document based on architecture and design decisions made collaboratively in prior conversation turns. |
| **What was changed manually** | I changed the title, rewrote the project summary, heavily changed theformatting, and made minor edits to other sections of the report since it largely matched my instructions and input. |
| **What was verified independently** | Genealogical Proof Standard requirements verified against Board for Certification of Genealogists published standards. Agent architecture validated against my own understanding of genealogy research workflows. Success criteria percentages set based on my judgment of realistic performance. |

---

### Entry 3 — Canvas Documents

| Field | Details |
|-------|---------|
| **Tool** | Claude Opus 4.6 (Anthropic), via claude.ai |
| **Purpose** | Creating the System Specification Canvas, five individual Agent Canvases, and Architecture Canvas in HTML format, matching the style of course-provided examples |
| **Prompt summary** | I provided copies of example canvases and requested that Claude create similar canvases for each purpose based on the project specs I finalized. Claude generated HTML files following the exact format of the provided Canvas1_ComplianceMemo.html and ArchCanvas_ComplianceMemo.html examples, populated with genealogy project content and technical specifications from prior conversation. A follow-up correction was made when I identified that the assignment required one canvas per agent rather than a single architecture canvas. |
| **What was changed manually** | I updated the Users/Stakeholders section of Canvas1 to replace "Validation" row with "Reviewer" row (identified that the original framing described project testing rather than a system workflow role). I made adjustments to some of the architecture listings, edited the headers and titles, reviewed all content, and made other minor edits to each canvas. |
| **What was verified independently** | Assignment requirements re-read to confirm "one page Agent Canvas for each agent or component" meant individual per-agent canvases. Canvas content cross-checked against written deliverables for consistency. |

---

### Entry 4 — Orchestration Flow Diagram

| Field | Details |
|-------|---------|
| **Tool** | Claude Opus 4.6 (Anthropic), via claude.ai |
| **Purpose** | Creating an SVG orchestration flow diagram showing the agent pipeline, parallel execution paths, adversarial feedback loop, and final report synthesis |
| **Prompt summary** | I provided the orchestration description and requested a diagram. Initial version had an error (DNA Analyst path visually passed through the Adversarial Critic box, and appeared to show two independent lines feeding into the final report). I identified both issues; Claude produced a corrected version routing the genetic path around the right edge and clarifying that only the Hypothesizer's output feeds the report from the documentary path. |
| **What was changed manually** | No manual changes to the diagram itself. Corrections were made through conversation (I identified the visual errors, Claude regenerated). |
| **What was verified independently** | I verified the corrected diagram accurately represented the intended orchestration: parallel documentary/genetic paths, Hypothesizer ⇄ Critic revision loop, single documentary output to report, DNA path merging at synthesis. |

---

### Entry 5 — Literature and Landscape Research

| Field | Details |
|-------|---------|
| **Tool** | Claude Opus 4.6 (Anthropic), via claude.ai with web search |
| **Purpose** | Surveying the landscape of existing agentic systems for scientific research, genealogy AI tools, and multi-agent hypothesis generation systems to inform project positioning and identify gaps |
| **Prompt summary** | Multiple search queries across the conversation: existing multi-agent hypothesis generation systems, adversarial critique in scientific discovery, GeoAI agentic systems, space/planetary science agents, genealogy AI tools, game-based agent simulations. Claude conducted web searches and synthesized findings. |
| **What was changed manually** | I evaluated all landscape findings and made independent judgments about project differentiation and positioning. |
| **What was verified independently** | Key systems referenced (AstroAgents, SciAgents, BioDisco, AGATHA, VirSci, ChatDev, Generative Agents) verified via their published papers and GitHub repositories. Confirmed that no existing multi-agent agentic system exists for genealogical research. |

---

## Phase 2: Architecture, Prototype, and Evaluation Plan

### Entry 6 — Phase 2 Design Decisions and Evaluation Planning

| Field | Details |
|-------|---------|
| **Tool** | Claude Opus 4.6 (Anthropic), via claude.ai |
| **Purpose** | Designing the adversarial trap taxonomy, Critic isolation A/B experiment, geographic plausibility redesign, and overall Phase 2 work sequencing. Responding to Phase 1 feedback (97/100) which requested explicit difficulty calibration for trap cases and empirical validation of the Critic isolation design. |
| **Prompt summary** | Extended multi-turn conversation reviewing Phase 1 feedback, then collaboratively designing: (1) three-tier adversarial trap taxonomy (deterministic / plausible-but-wrong / genuinely ambiguous) with tier-specific success criteria, (2) Critic isolation A/B experiment protocol (filtered vs. unfiltered conditions, shared seed state, leakage measurement), (3) geographic plausibility redesign from single binary threshold to multi-tier soft flags after identifying that European royal alliances would never trigger a 3000km cutoff. Also produced a CLAUDE.md project context file and structured handoff prompt for Claude Code. |
| **What was changed manually** | I described project feedback and ideas on responses to Claude. We collaborated on final design. I identified geographic plausiblity adjustment need and defined tiers. I selected appropriate A/B tests from suggestions Claude offered. |
| **What was verified independently** | Phase 1 feedback reviewed directly from graded submission. Geographic distances (London↔Paris, Madrid↔Vienna, etc.) verified via online distance calculators. Genealogical Proof Standard requirements cross-referenced with Board for Certification of Genealogists published standards. Decision to keep revision limit at 2 (not 3) validated against Phase 1 submitted canvas document. |

---

### Entry 7 — Implementation via Claude Code

| Field | Details |
|-------|---------|
| **Tool** | Claude Code (Anthropic), command-line agentic coding tool ||
| **Purpose** | Implementing the full four-agent pipeline: project scaffolding, state schema, GEDCOM parser, utility tools (date_utils, fuzzy_match, geo_utils), four agent nodes (Record Scout, Profile Synthesizer, Relationship Hypothesizer, Adversarial Critic), LangGraph graph assembly, final report writer, trace persistence, and entry point. Also built evaluation harness, trap case GEDCOM files, and A/B experiment runner. |
| **Prompt summary** | Structured seven-step handoff prompt (produced in claude.ai conversation) with explicit "stop after each step" instruction. Each step was reviewed before proceeding. Key prompts included: isolation boundary enforcement instruction (build filter_hypothesis_for_critic as a code guarantee, not convention), geographic threshold redesign instruction, date_utils instruction (accept raw GEDCOM strings, uncertainty envelopes for qualified dates), and Tier 1/2/3 trap case construction specifications. |
| **What was changed manually** | [TO BE FILLED IN — note any code you rewrote, debugging you did independently, design decisions you overrode, parameters you tuned. Key items to document: the Tier 3 evaluation criterion revision (changed from confidence < 0.70 to no overconfident accept/reject), the load_dotenv(override=True) fix, the Habsburg Latin-1 encoding workaround, any prompt tuning on individual agents] |
| **What was verified independently** | Parser output verified against GEDCOM files opened in text editor. JFK family relationships verified against public biographical sources. Moore family tree relationships verified against developer's personal family knowledge. Queen Victoria parentage verified against historical record. Habsburg Philip II parentage verified against historical record. Geographic distances spot-checked against online calculators. Tier 1 trap cases verified by manual date arithmetic. |

---

### Entry 8 — Pipeline Testing on Developer's Family Tree

| Field | Details |
|-------|---------|
| **Tool** | Claude Code (Anthropic), command-line agentic coding tool |
| **Purpose** | Running the full pipeline on my Moore Family Tree GEDCOM (8,759 persons, exported from my father's Ancestry account) to validate the system on real personal data with no LLM training data contamination risk. |
| **Prompt summary** | "Run the full pipeline on the Moore Family Tree with a query about a real ancestor you can verify." Query: "Who are the parents of James Joseph Moore?" (b. 1883, Pennsylvania). |
| **What was changed manually** | Claude suggested potential queries, from which I chose. I verified pipeline output. |
| **What was verified independently** | Correct parents (Philip Henry Moore, Margaret M. McCusker) verified against developer's personal knowledge of family tree. Three-way "James Moore" disambiguation result verified against GEDCOM file contents. Trans-Atlantic geographic flag on Margaret McCusker verified against family knowledge of Irish ancestry. |

---

### Entry 9 — Stress Testing on European Royal Trees

| Field | Details |
|-------|---------|
| **Tool** | Claude Code (Anthropic), command-line agentic coding tool |
| **Purpose** | Running the pipeline on Habsburg.ged (34,020 persons, German language, Latin-1 encoding) and Queen.ged (4,683 persons, English) to test system behavior on large-scale, non-English, and historically complex datasets outside the primary US-English design scope. |
| **Prompt summary** | "Run the pipeline on Habsburg.ged with an English query against German data" and "Run on Queen.ged." Queries: "Who are the parents of Philip II of Spain?" and "Who are the parents of Queen Victoria?" |
| **What was changed manually** | I selected the Habsburg file, uncertain about how the language barrier would impact the results. When it was clear that a workaround was feasible, I prompted Claude in natural language for the code fix. |
| **What was verified independently** | Philip II parentage (Karl V, Isabella von Portugal) and Queen Victoria parentage (Edward Augustus Hanover, Victoria Mary Louisa) verified against historical sources. Encoding issue root cause (Latin-1 byte 0xF6 = ö) verified by examining raw file bytes. Place-as-surname pattern (/Spanien/) verified by reading GEDCOM file directly. |

---

### Entry 10 — Phase 2 Written Deliverables

| Field | Details |
|-------|---------|
| **Tool** | Claude Opus 4.6 (Anthropic), via claude.ai |
| **Purpose** | Producing the Phase 2 written deliverables: architecture document (architecture diagram, role definitions, coordination logic, tools/memory/data design, prototype evidence), evaluation plan (trap taxonomy, reconstruction test results, A/B experiment results, success criteria tracking), and risk and governance plan (failure modes, privacy considerations, trust/reliability, misuse risks, governance controls). Each produced as both markdown (for repository) and Word document (for submission editing). |
| **Prompt summary** | "Ready to start on the written deliverables. We will work in sections. Let's start with Architecture." followed by sequential requests for each document section. Claude generated complete drafts referencing actual pipeline results, trace data, and experiment outcomes from the implementation phase. Architecture diagram was produced separately by Claude Code as a Mermaid flowchart, refined after initial render showed text clipping. |
| **What was changed manually** | I reviewed and edited all drafted text extensively. I aggregated all output into one document and formatted.  I also manually edited the Mermaid flowchart produced by Claude to produce a more visually appealing result. I cut text that was unnecessary, incorrect, or unclear. |
| **What was verified independently** | All pipeline results referenced in documents verified against actual trace files in traces/ directory. A/B experiment numbers verified against eval/results/isolation_ab_summary.md. Trap case results verified against eval/results/ JSON files. Rubric coverage verified against assignment instructions. |

---

## Phase 3: Final Product, Evidence, and Reflection

### Entry 11 — Streamlit four-tab application

| Field | Details |
|-------|---------|
| **Tool** | Claude Code (Anthropic), command-line agentic coding tool |
| **Purpose** | Building a Streamlit GUI wrapping the existing pipeline so the system is exercisable without CLI familiarity. Four tabs: Pipeline (file inputs, query routing, per-agent progress display, results rendering with escalation styling), Family Tree (graphviz visualization of immediate family with verdict-coloured nodes), Audit (subtree audit two-pass workflow), DNA Analysis (DNA match summary). |
| **Prompt summary** | [USER: please paste exact prompts here — the Streamlit build spanned multiple sessions, including the original four-tab scaffolding, file-picker dropdowns scanning `data/`, the Audit tab with two-pass deterministic plus LLM workflow, and a later UX session adding the DNA file dropdown, data-availability banner, and explicit mode selector]. The build proceeded incrementally with stop-for-review checkpoints between each tab. |
| **What was changed manually** | [USER: please describe what you changed]. Likely items: layout adjustments, copy edits, the colour palette for the verdict nodes, placement of progress indicators, the wording of the data-availability banner, and CSS tuning. |
| **What was verified independently** | Ran `streamlit run app.py` after each change to confirm no crashes and that the page rendered. Walked through the Pipeline tab end-to-end against the Kennedy GEDCOM and the synthetic DNA demo. Confirmed the Family Tree tab's colour coding matched the Critic verdicts in the report. Confirmed the Audit tab's Pass-1 results matched what `python audit.py` produced from the CLI on the same root and depth. |

---

### Entry 12 — DNA Analyst agent (initial reporter mode)

| Field | Details |
|-------|---------|
| **Tool** | Claude Code (Anthropic) |
| **Purpose** | Building the DNA Analyst as a separate agent that parses GEDmatch and MyHeritage match-list CSVs, normalizes match names, cross-references against GEDCOM persons via fuzzy matching, predicts relationships using the Shared cM Project lookup table, and reports match distribution, prediction consistency, and any GEDCOM cross-references found. The initial design was reporter-only — output appended to the report but not consulted by the Hypothesizer or Critic. |
| **Prompt summary** | [USER: please paste exact prompt]. Likely framed as a request to build a DNA Analyst node that parses the two CSV formats, looks up each match's name in the GEDCOM, and produces a summary section. |
| **What was changed manually** | [USER: please describe what you changed]. Likely items: column-mapping logic between GEDmatch and MyHeritage formats, fuzzy-match thresholds for cross-referencing match names against GEDCOM persons, decisions about which match-list fields to surface in the report. |
| **What was verified independently** | Cross-reference output verified against the synthetic DNA demo files where the ground-truth matches were hand-built. Spot-checked GEDmatch and MyHeritage column parsing against the personal `data/DNA/` files. Shared cM lookup verified against the published Shared cM Project distribution. |

---

### Entry 13 — DNA Analyst integration into the reasoning loop

| Field | Details |
|-------|---------|
| **Tool** | Claude Code (Anthropic) |
| **Purpose** | Promoting the DNA Analyst's output from a passive report section into evidence the Hypothesizer can cite and the Critic can challenge. Hypothesizer now adds DNA evidence items to the `evidence_chain` of relationship hypotheses; the Critic receives a `dna_relevant` field carrying the cM consistency verdict for each hypothesis. |
| **Prompt summary** | After reviewing the reporter-only output, the DNA path was felt to be under-used: DNA evidence appeared in the report but never influenced any verdict. Requested "option B" full integration. [USER: please paste exact prompt — the option A vs option B framing matters for the disclosure]. |
| **What was changed manually** | [USER: please describe what you changed]. Likely items: how DNA findings are phrased in the evidence chain, the cM-consistency verdict thresholds (consistent / inconsistent / inconclusive), the decision about whether DNA evidence should weaken or support a hypothesis by default. |
| **What was verified independently** | Walked through a JFK pipeline run with the synthetic DNA demo attached and confirmed DNA evidence appeared in the hypothesis evidence chain and that the Critic's justification referenced it. Compared evidence chains on the same hypothesis with vs. without `dna_csv` to confirm the DNA path actually changed downstream behavior. |

---

### Entry 14 — Multi-source retrieval (FindAGrave, Wikidata, WikiTree)

| Field | Details |
|-------|---------|
| **Tool** | Claude Code (Anthropic) |
| **Purpose** | Extending the Record Scout beyond GEDCOM-only retrieval. Added FindAGrave (HTML scrape via BeautifulSoup), Wikidata (SPARQL endpoint), and WikiTree (public REST API). Each retrieved record is tagged with `source_type` so downstream agents — and the Critic in particular — can weight independent corroboration appropriately rather than treating one user-uploaded GEDCOM as the only source of truth. |
| **Prompt summary** | [USER: please paste exact prompt — the source selection and the priority order matter]. FamilySearch was scoped originally but deprioritized after API-key registration friction; equivalent independent coverage came from Wikidata and WikiTree. |
| **What was changed manually** | [USER: please describe what you changed]. Likely items: search-result filtering thresholds, decisions about including or excluding unverified Wikidata claims, rate-limit handling, defensive handling of HTML structure changes on FindAGrave. |
| **What was verified independently** | Each source verified to return non-empty results for at least one query (JFK on FindAGrave, Queen Victoria on Wikidata, Philip II on WikiTree). Confirmed `relation_to_target` and `source_type` tagging propagates correctly into the Hypothesizer's evidence chain. |

---

### Entry 15 — Gap detection mode

| Field | Details |
|-------|---------|
| **Tool** | Claude Code (Anthropic) |
| **Purpose** | Adding a third entry mode (`gap_search.py` plus `tools/gap_scanner.py`) that scans a GEDCOM for persons missing one or both parent links, scores plausible parents from within the same tree using fuzzy name match, era plausibility, and place overlap, and optionally runs the full pipeline on the top-N candidates with a `gap_mode: True` flag so the Record Scout swaps to `find_parent_candidates` instead of fuzzy-matching a target person. |
| **Prompt summary** | [USER: please paste exact prompt — gap mode was a non-trivial design choice and may have started from a question like "what would the system do for an unconnected person in the tree"]. |
| **What was changed manually** | [USER: please describe what you changed]. Likely items: the data-richness threshold (`min_data_fields`) for which gaps are worth investigating, the scoring weights for parent candidates, the auto-generated query template for each gap. |
| **What was verified independently** | Ran `gap_search.py` against the Kennedy GEDCOM and confirmed the candidate list matched manual inspection of persons whose `father_id` or `mother_id` is missing in the GEDCOM. Confirmed that selecting a top-N gap and running the pipeline produces a coherent hypothesis with parent candidates from inside the tree, not invented externally. |

---

### Entry 16 — Subtree audit mode

| Field | Details |
|-------|---------|
| **Tool** | Claude Code (Anthropic) |
| **Purpose** | Adding a subtree audit entry mode (`audit.py` plus `tools/subtree_extractor.py`) that walks every parent-child relationship in an N-generation subtree rooted at a target person and audits each. Two passes: Pass 1 runs the deterministic Tier 1 date checks plus the multi-tier geographic plausibility flag in milliseconds; Pass 2 optionally invokes the full LLM pipeline on the top-N most questionable relationships from Pass 1. |
| **Prompt summary** | [USER: please paste exact prompt — the two-pass design is a key architectural choice and the prompt motivation matters]. |
| **What was changed manually** | [USER: please describe what you changed]. Likely items: the Pass-1 severity thresholds (impossible / flagged / ok), the heuristic for "questionable" that determines which relationships go to Pass 2, the report format for downloaded audit reports. |
| **What was verified independently** | Ran `audit.py` on the Kennedy tree with depth 3 and confirmed every parent-child relationship in the subtree was audited (count matched the parent-child links visible in the GEDCOM). Pass-1 verdicts on the Tier 1 trap-case GEDCOMs matched the expected verdicts in `eval/trap_cases/manifest.json`. |

---

### Entry 17 — Three-trigger human escalation

| Field | Details |
|-------|---------|
| **Tool** | Claude Code (Anthropic) |
| **Purpose** | Defining and implementing explicit escalation logic in `agents/final_report_writer.py` (`check_escalation`) so the system surfaces unresolved findings rather than silently publishing low-confidence conclusions. Three triggers; any one flags a hypothesis: (1) force-finalized after max revisions (Critic rejected on both cycles), (2) low-confidence accept (Critic accept with `confidence_in_critique < 0.60`), (3) conflicting verdicts for the same subject (one accept and one reject in the same family unit). |
| **Prompt summary** | Phase 2 feedback noted that the Critic's accept/reject was binary and obscured low-confidence acceptances. Asked Claude Code to formalize the escalation conditions and integrate them into the Final Report Writer. [USER: please paste exact prompt for the trigger thresholds]. |
| **What was changed manually** | Trigger 3 was narrowed during review to fire only when the same subject has both `accept` and `reject` — a mix of `accept` and `flag_uncertain` is normal (the Critic is more confident about some relationships than others) and was producing false escalations in early traces. [USER: confirm or correct]. |
| **What was verified independently** | Walked through trace files where the Critic rejected once then accepted to confirm the escalation flag did not fire (single rejection during revision is not "force-finalized"). Walked through a trace where the Critic accepted with `confidence_in_critique = 0.55` to confirm the low-confidence-accept trigger fired. Manually constructed a multi-hypothesis state with a mixed verdict set and confirmed only `accept` plus `reject` triggers Trigger 3, not `accept` plus `flag_uncertain`. |

---

### Entry 18 — Critic isolation enforcement as a code guarantee

| Field | Details |
|-------|---------|
| **Tool** | Claude Code (Anthropic) |
| **Purpose** | Replacing the Phase 2 naming-convention isolation (the Critic was simply asked not to read certain fields) with a load-bearing code boundary. `agents/hypothesis_schema.py` declares PUBLIC and INTERNAL field sets; `filter_hypothesis_for_critic(hypothesis)` is the single read path the Critic node uses. The Critic node never accesses `state["hypotheses"]` dicts directly. A `state["isolation_mode"]` toggle flips the filter on or off for the A/B experiment, with the production path always filtered. |
| **Prompt summary** | [USER: please paste exact prompt — this is the project's core agentic justification, and the prompt and review trail matter]. |
| **What was changed manually** | [USER: please describe what you changed]. Likely items: the exact partition of fields between PUBLIC and INTERNAL (in particular whether the Hypothesizer's stated weaknesses count as PUBLIC — they should, since they are part of the Hypothesizer's openly declared limitations and a useful signal to the Critic). |
| **What was verified independently** | Inspected the Critic node code to confirm there is no path that reads `state["hypotheses"]` outside `filter_hypothesis_for_critic`. Re-ran the A/B isolation experiment after the rewrite to confirm filtered runs produced the same verdicts as before the rewrite (no regression) and that toggling `isolation_mode = "unfiltered"` actually exposed the INTERNAL fields downstream. |

---

### Entry 19 — Critic model upgrade: Sonnet 4.6 → Opus 4.0 → Opus 4.7

| Field | Details |
|-------|---------|
| **Tool** | Claude Code (Anthropic) — model swap in `agents/adversarial_critic.py` |
| **Purpose** | Tuning Critic model selection independently from the rest of the pipeline. Initial production used Claude Sonnet 4.6 across all five agents; comparison runs against Claude Opus 4.0 produced more conservative confidence ratings; the final production setting is Claude Opus 4.7 for the Critic only, keeping Sonnet 4.6 for Record Scout, Profile Synthesizer, Hypothesizer, and DNA Analyst. |
| **Prompt summary** | [USER: please paste exact prompt — the comparison reasoning and the JFK accept/0.82 → 0.75 → 0.90+ progression should be captured]. |
| **What was changed manually** | The final decision to keep the Critic on Opus 4.7 and the others on Sonnet 4.6 was a cost/quality tradeoff judgment. [USER: confirm]. |
| **What was verified independently** | Ran the JFK pipeline against each of the three Critic models and recorded `critique.confidence_in_critique` and the `justification` text. Opus 4.7 produced the sharpest justifications and consolidated multiple issues into single coherent paragraphs where Sonnet 4.6 had bulleted them. No model regressed below baseline accept verdict on the JFK case. |

---

### Entry 20 — Cross-vendor Critic experiment

| Field | Details |
|-------|---------|
| **Tool** | Claude Code (Anthropic) |
| **Purpose** | Addressing Phase 3 presentation feedback that same-vendor models (all Anthropic) may share training data and failure modes. Built `eval/cross_vendor_critic_experiment.py` to run the same Hypothesizer output through an Anthropic Opus 4.7 Critic and an OpenAI GPT-5.5 Critic in parallel, then compare verdicts, confidence, and justification structure. |
| **Prompt summary** | [USER: please paste exact prompt]. |
| **What was changed manually** | [USER: please describe what you changed]. Likely items: the prompt template adjustment for the OpenAI variant (Anthropic system-prompt conventions don't translate one-to-one), parsing differences in JSON-mode outputs, scoring of disagreements. |
| **What was verified independently** | Confirmed the two vendors agreed on at least one trap case and disagreed on at least one (cross-vendor diversity actually exists in the resulting verdicts, not just in superficial wording). Verified the OpenAI Critic call did not leak Anthropic-specific tokens into its prompt and vice versa. |

---

### Entry 21 — Asymmetric pairing experiment (weak Hypothesizer + strong Critic)

| Field | Details |
|-------|---------|
| **Tool** | Claude Code (Anthropic) |
| **Purpose** | Testing the central agentic claim of the project — that adversarial critique adds value beyond what the proposer can self-check — by running a deliberately weak OpenAI Hypothesizer paired with a strong Anthropic Opus 4.7 Critic. If the strong Critic catches mistakes that a strong-Hypothesizer-plus-strong-Critic baseline does not produce, the architecture is doing the work the project claims it does. |
| **Prompt summary** | [USER: please paste exact prompt]. |
| **What was changed manually** | [USER: please describe what you changed]. Likely items: the choice of "weak" model (a GPT-3.5-class or 4o-mini-class model rather than GPT-5.5), the framing of the comparison relative to the strong-strong baseline. |
| **What was verified independently** | Recorded baseline strong-Hypothesizer plus strong-Critic results, then ran the asymmetric variant on the same hypothesis IDs. Hypotheses where the asymmetric run produced a reject or escalation that the symmetric run accepted are the evidence the Critic actually catches the weak Hypothesizer's mistakes; recorded a list of such cases from the run output. |

---

### Entry 22 — Multi-Critic ensemble

| Field | Details |
|-------|---------|
| **Tool** | Claude Code (Anthropic) |
| **Purpose** | Extending the cross-vendor Critic experiment from pairwise comparison to a three-vendor ensemble (Anthropic Opus 4.7 + OpenAI + Google Gemini 2.5 Pro) with a conservative aggregation rule: any `reject` from any vendor produces an ensemble `reject`; any `flag_uncertain` from any vendor produces an ensemble `flag_uncertain`. Tests whether ensemble-level escalation catches genuinely ambiguous cases that a single Critic running in isolation would have accepted. |
| **Prompt summary** | [USER: please paste exact prompt — the conservative aggregation rule was a design choice and may have started from a different default like majority vote]. |
| **What was changed manually** | [USER: please describe what you changed]. Likely items: the aggregation rule (started simpler? majority vote considered then rejected?), the choice of Google Gemini 2.5 Pro specifically, prompt parity tuning across the three vendors. |
| **What was verified independently** | Ran the ensemble against the two Tier 3 ambiguous trap cases. Both were correctly escalated (at least one vendor produced `flag_uncertain` or `reject`) where a single Opus 4.7 Critic accepted both with high confidence. The 2/2 escalation result is reproducible from the persisted ensemble run output. |

---

### Entry 23 — Bug fixes (surname gate, Habsburg encoding, shared_cm aliases)

| Field | Details |
|-------|---------|
| **Tool** | Claude Code (Anthropic) |
| **Purpose** | Three independent bugs surfaced during pipeline runs and were fixed in close succession. (a) The Profile Synthesizer's disambiguation was matching "Joan Knorr" to "James Moore" because Soundex and Metaphone collapsed both surnames the same way — added a 0.60 fuzzy-match floor on the surname field as a gate before composite scoring. (b) `Habsburg.ged` is Latin-1, not UTF-8; python-gedcom-2 does not surface an encoding parameter, so the workaround reads the file as bytes, decodes as Latin-1, and passes the resulting string to the parser (acknowledged in Phase 2 Entry 7; implementation detail recorded here). (c) `shared_cm_lookup` keys on relationship strings like "father" and "mother" but the Hypothesizer was emitting "father of" and "mother of"; silent consistency-verdict inversion was caught only during trace inspection. |
| **Prompt summary** | Each fix was a follow-up after observing the failure. [USER: please paste the prompts you used for each fix where you have them; the trace-inspection moment for the third bug is worth quoting verbatim if you have it]. |
| **What was changed manually** | I identified all three bugs in trace inspection or output review, flagged them, and reviewed each fix before merging. [USER: confirm; describe any tuning of the surname-gate threshold or any other parameter]. |
| **What was verified independently** | Re-ran the Moore-tree pipeline against the Joan Knorr case after the surname gate landed and confirmed the false positive no longer occurred. Re-ran the Habsburg pipeline after the encoding fix and confirmed German diacritics rendered correctly in the parsed person dicts. Re-ran a JFK-with-DNA trace after the alias fix and confirmed the DNA consistency verdict matched expectation rather than inverted. |

---

### Entry 24 — Synthetic DNA demos and PII redactor

| Field | Details |
|-------|---------|
| **Tool** | Claude Code (Anthropic) |
| **Purpose** | Making the DNA path reproducible for graders without committing personal match data. Created `data/DNA_demo/*_synthetic_DNA.csv` for Kennedy, Maria Theresia, and Victoria Hanover, hand-built so each file's matches map to verifiable persons in the corresponding public GEDCOM. Built `tools/redact_trace.py` to pseudonymize traces produced from personal trees, replacing real names with consistent stand-ins so trace files can be inspected and shared without PII exposure. |
| **Prompt summary** | [USER: please paste exact prompt — the synthetic-data design constraints (realistic shared-cM distribution, mapping to real GEDCOM persons, no leakage of personal names) are probably worth quoting]. |
| **What was changed manually** | Hand-built the synthetic match lists to map onto the public GEDCOM persons, using realistic shared-cM values consistent with the Shared cM Project distribution. [USER: confirm; describe the construction process and whether any of the file content was generated programmatically vs by hand]. |
| **What was verified independently** | Walked the synthetic Kennedy file through the DNA Analyst manually, confirming each row resolves to a real person in the Kennedy GEDCOM at the predicted relationship tier. Confirmed `redact_trace.py` is deterministic (same input produces same pseudonyms) and that no original names from the personal tree survive in the redacted output. |

---

### Entry 25 — Architecture diagram regeneration

| Field | Details |
|-------|---------|
| **Tool** | Claude Code (Anthropic) for the Mermaid edits, plus claude.ai for design discussion |
| **Purpose** | Updating `docs/architecture_diagram.mermaid` and the rendered PNG to reflect the actual Phase 3 orchestration: DNA Analyst placed sequentially after Record Scout (originally drafted as a parallel branch but serialized because LangGraph cannot enforce join semantics when one incoming edge is conditional — the Critic's "finalize" path), and the isolation filter shown as a load-bearing boundary between Hypothesizer and Critic rather than an implicit attribute. |
| **Prompt summary** | [USER: please paste exact prompt — the parallelism rationale is worth recording]. |
| **What was changed manually** | Manually edited the Mermaid for visual layout (node positions, edge routing), as for the Phase 2 diagram. [USER: confirm]. |
| **What was verified independently** | Rendered the diagram and walked it side-by-side with the actual graph wiring in `graph.py` to confirm every edge in the diagram exists in code and vice versa. Confirmed the isolation filter is depicted at the boundary it actually enforces in `agents/hypothesis_schema.py`. |

---

## Summary of AI Tool Usage

| Tool | Version | Phases Used | Primary Purpose |
|------|---------|-------------|-----------------|
| Claude | Opus 4.6 (Anthropic) | 1, 2, 3 | Project design, code generation, document drafting, debugging, evaluation design |

---

## Disclosure Statement

Generative AI (Claude Opus 4.6) was used extensively as a collaborative tool throughout this project. I maintained responsibility for all design decisions, domain judgment, evaluation criteria, and final content. AI-generated outputs were reviewed, revised where necessary, and independently verified before inclusion. My domain expertise in genealogy (active hobbyist) and genetics (M.S. in Cellular and Molecular Biology) informed the evaluation of AI-generated content throughout.
