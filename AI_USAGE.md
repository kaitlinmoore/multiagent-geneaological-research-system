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

### Entry 4 — Phase 2 Design Decisions and Evaluation Planning

| Field | Details |
|-------|---------|
| **Tool** | Claude Opus 4.6 (Anthropic), via claude.ai |
| **Purpose** | Designing the adversarial trap taxonomy, Critic isolation A/B experiment, geographic plausibility redesign, and overall Phase 2 work sequencing. Responding to Phase 1 feedback (97/100) which requested explicit difficulty calibration for trap cases and empirical validation of the Critic isolation design. |
| **Prompt summary** | Extended multi-turn conversation reviewing Phase 1 feedback, then collaboratively designing: (1) three-tier adversarial trap taxonomy (deterministic / plausible-but-wrong / genuinely ambiguous) with tier-specific success criteria, (2) Critic isolation A/B experiment protocol (filtered vs. unfiltered conditions, shared seed state, leakage measurement), (3) geographic plausibility redesign from single binary threshold to multi-tier soft flags after identifying that European royal alliances would never trigger a 3000km cutoff. Also produced a CLAUDE.md project context file and structured handoff prompt for Claude Code. |
| **What was changed manually** | I described project feedback and ideas on responses to Claude. We collaborated on final design. I identified geographic plausiblity adjustment need and defined tiers. I selected appropriate A/B tests from suggestions Claude offered. |
| **What was verified independently** | Phase 1 feedback reviewed directly from graded submission. Geographic distances (London↔Paris, Madrid↔Vienna, etc.) verified via online distance calculators. Genealogical Proof Standard requirements cross-referenced with Board for Certification of Genealogists published standards. Decision to keep revision limit at 2 (not 3) validated against Phase 1 submitted canvas document. |

---

### Entry 5 — Implementation via Claude Code

| Field | Details |
|-------|---------|
| **Tool** | Claude Code (Anthropic), command-line agentic coding tool ||
| **Purpose** | Implementing the full four-agent pipeline: project scaffolding, state schema, GEDCOM parser, utility tools (date_utils, fuzzy_match, geo_utils), four agent nodes (Record Scout, Profile Synthesizer, Relationship Hypothesizer, Adversarial Critic), LangGraph graph assembly, final report writer, trace persistence, and entry point. Also built evaluation harness, trap case GEDCOM files, and A/B experiment runner. |
| **Prompt summary** | Structured seven-step handoff prompt (produced in claude.ai conversation) with explicit "stop after each step" instruction. Each step was reviewed before proceeding. Key prompts included: isolation boundary enforcement instruction (build filter_hypothesis_for_critic as a code guarantee, not convention), geographic threshold redesign instruction, date_utils instruction (accept raw GEDCOM strings, uncertainty envelopes for qualified dates), and Tier 1/2/3 trap case construction specifications. |
| **What was changed manually** | [TO BE FILLED IN — note any code you rewrote, debugging you did independently, design decisions you overrode, parameters you tuned. Key items to document: the Tier 3 evaluation criterion revision (changed from confidence < 0.70 to no overconfident accept/reject), the load_dotenv(override=True) fix, the Habsburg Latin-1 encoding workaround, any prompt tuning on individual agents] |
| **What was verified independently** | Parser output verified against GEDCOM files opened in text editor. JFK family relationships verified against public biographical sources. Moore family tree relationships verified against developer's personal family knowledge. Queen Victoria parentage verified against historical record. Habsburg Philip II parentage verified against historical record. Geographic distances spot-checked against online calculators. Tier 1 trap cases verified by manual date arithmetic. |

---

### Entry 6 — Pipeline Testing on Developer's Family Tree

| Field | Details |
|-------|---------|
| **Tool** | Claude Code (Anthropic), command-line agentic coding tool |
| **Purpose** | Running the full pipeline on my Moore Family Tree GEDCOM (8,759 persons, exported from my father's Ancestry account) to validate the system on real personal data with no LLM training data contamination risk. |
| **Prompt summary** | "Run the full pipeline on the Moore Family Tree with a query about a real ancestor you can verify." Query: "Who are the parents of James Joseph Moore?" (b. 1883, Pennsylvania). |
| **What was changed manually** | Claude suggested potential queries, from which I chose. I verified pipeline output. |
| **What was verified independently** | Correct parents (Philip Henry Moore, Margaret M. McCusker) verified against developer's personal knowledge of family tree. Three-way "James Moore" disambiguation result verified against GEDCOM file contents. Trans-Atlantic geographic flag on Margaret McCusker verified against family knowledge of Irish ancestry. |

---

### Entry 7 — Stress Testing on European Royal Trees

| Field | Details |
|-------|---------|
| **Tool** | Claude Code (Anthropic), command-line agentic coding tool |
| **Purpose** | Running the pipeline on Habsburg.ged (34,020 persons, German language, Latin-1 encoding) and Queen.ged (4,683 persons, English) to test system behavior on large-scale, non-English, and historically complex datasets outside the primary US-English design scope. |
| **Prompt summary** | "Run the pipeline on Habsburg.ged with an English query against German data" and "Run on Queen.ged." Queries: "Who are the parents of Philip II of Spain?" and "Who are the parents of Queen Victoria?" |
| **What was changed manually** | I selected the Habsburg file, uncertain about how the language barrier would impact the results. When it was clear that a workaround was feasible, I prompted Claude in natural language for the code fix. |
| **What was verified independently** | Philip II parentage (Karl V, Isabella von Portugal) and Queen Victoria parentage (Edward Augustus Hanover, Victoria Mary Louisa) verified against historical sources. Encoding issue root cause (Latin-1 byte 0xF6 = ö) verified by examining raw file bytes. Place-as-surname pattern (/Spanien/) verified by reading GEDCOM file directly. |

---

### Entry 8 — Phase 2 Written Deliverables

| Field | Details |
|-------|---------|
| **Tool** | Claude Opus 4.6 (Anthropic), via claude.ai |
| **Purpose** | Producing the Phase 2 written deliverables: architecture document (architecture diagram, role definitions, coordination logic, tools/memory/data design, prototype evidence), evaluation plan (trap taxonomy, reconstruction test results, A/B experiment results, success criteria tracking), and risk and governance plan (failure modes, privacy considerations, trust/reliability, misuse risks, governance controls). Each produced as both markdown (for repository) and Word document (for submission editing). |
| **Prompt summary** | "Ready to start on the written deliverables. We will work in sections. Let's start with Architecture." followed by sequential requests for each document section. Claude generated complete drafts referencing actual pipeline results, trace data, and experiment outcomes from the implementation phase. Architecture diagram was produced separately by Claude Code as a Mermaid flowchart, refined after initial render showed text clipping. |
| **What was changed manually** | I reviewed and edited all drafted text extensively. I aggregated all output into one document and formatted.  I also manually edited the Mermaid flowchart produced by Claude to produce a more visually appealing result. I cut text that was unnecessary, incorrect, or unclear. |
| **What was verified independently** | All pipeline results referenced in documents verified against actual trace files in traces/ directory. A/B experiment numbers verified against eval/results/isolation_ab_summary.md. Trap case results verified against eval/results/ JSON files. Rubric coverage verified against assignment instructions. |

---

## Phase 3: Final Product, Evidence, and Reflection

*[Entries will be added as Phase 3 work proceeds]*

---

## Summary of AI Tool Usage

| Tool | Version | Phases Used | Primary Purpose |
|------|---------|-------------|-----------------|
| Claude | Opus 4.6 (Anthropic) | 1, 2, 3 | Project design, code generation, document drafting, debugging, evaluation design |

---

## Disclosure Statement

Generative AI (Claude Opus 4.6) was used extensively as a collaborative tool throughout this project. I maintained responsibility for all design decisions, domain judgment, evaluation criteria, and final content. AI-generated outputs were reviewed, revised where necessary, and independently verified before inclusion. My domain expertise in genealogy (active hobbyist) and genetics (M.S. in Cellular and Molecular Biology) informed the evaluation of AI-generated content throughout.
