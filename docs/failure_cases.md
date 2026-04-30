# Failure Cases

Bugs encountered during Phase 3 development that produced wrong outputs in
ways that survived the unit-test layer and required deeper investigation. Each
case is described in the form _symptom → detection → root cause → fix →
architectural lesson._ The first three are documented in depth because the
lessons generalize to other agentic systems. The remaining two are summarized
in the appendix because their root causes are narrow.

---

## Case 1 — Final Report Writer fires before the Critic loop completes

### Symptom

In an early Phase 3 build where the DNA Analyst ran as a parallel branch off
the Record Scout, the same query would sometimes produce a complete report
including critiques and revisions, and sometimes produce a report with empty
`critiques`, `revision_count: 0`, and a `final_report` that looked like the
Hypothesizer's first-pass output dressed up as final. There was no
intermediate error and no clear pattern from query text alone.

### Detection

Caught by running the same JFK query three times back-to-back during a
sanity check before a presentation. Two runs produced 13 KB reports with
Critic verdicts; one produced an 8 KB report with no critiques. Diffing the
trace JSONs showed the difference was structural — the Critic node had not
been entered at all in the short run.

### Root cause

LangGraph cannot enforce deterministic join semantics when one of the
incoming edges to a join node is a conditional edge. The pipeline at that
time looked like:

```
Scout ──┬─→ Synth ──→ Hypo ⇄ Critic ─[reject? loop : finalize]→ Writer
        └─→ DNA ─────────────────────────────────────────────→ Writer
```

The Writer had two incoming edges: an unconditional one from DNA Analyst
and a conditional one from the Critic ("finalize" path). LangGraph fires a
node as soon as any active path leading to it is satisfied; it does not
know to wait for the conditional path to resolve before considering the
node ready. The DNA Analyst finished in roughly 200 ms (CSV parse + cM
table lookup, no LLM calls). The Hypothesizer + Critic loop took 30-90
seconds. Whenever DNA Analyst completed before the Critic loop reached the
finalize edge, the Writer fired immediately on the DNA path and consumed
state that did not yet contain critiques. The Critic path completed
afterward into a state object the report had already been composed from.

### Fix

Serialized the DNA Analyst between the Scout and the Profile Synthesizer:

```
Scout ──→ DNA ──→ Synth ──→ Hypo ⇄ Critic ─[reject? loop : finalize]→ Writer
```

The DNA Analyst's output (`state["dna_analysis"]`) is now read directly
by the Hypothesizer (which appends DNA evidence items to evidence chains)
and the Critic (which uses the `dna_relevant` field). The cost of
sequentialization is the DNA Analyst's ~200 ms, which is dwarfed by the
LLM calls in every adjacent node and is invisible in practice.

### Architectural lesson

Parallelism in agent orchestration only works cleanly when join semantics
are deterministic. A conditional edge anywhere upstream of a join forces
the rest of the graph downstream of the conditional to be sequential
relative to that conditional path, regardless of what other paths look
like. The design diagram showed two paths converging cleanly; the
framework's actual behavior depended on which path completed first. We
now design for the framework's failure mode (race-on-readiness) rather
than the diagram's intent (wait-for-all). This generalizes: in any
DAG-based agent framework with conditional edges, treat parallel branches
that converge at a join as sequential whenever any branch passes through
a conditional.

---

## Case 2 — Cross-surname false positive in fuzzy matching at scale

### Symptom

A subtree audit run against the Moore family tree (8,759 persons) flagged
a "Joan Knorr" as a candidate mother for an ancestor whose actual mother
was known and present in the tree. The flag carried high enough confidence
to appear in the report's body rather than the appendix.

### Detection

User flagged it during audit review. Joan Knorr is unrelated to the
subject; her surname does not appear elsewhere in the subject's lineage.
The match was visually obviously wrong to anyone who knew the family but
was not detectable by the audit's automatic checks alone.

### Root cause

`name_match_score()` weighted given-name and surname tokens equally and
combined them into a single composite score using a max-of-component
strategy across Jaro-Winkler, Levenshtein, Soundex, and Metaphone. In a
small tree, the only candidates above any reasonable threshold tend to be
genuinely related, because the population of "Joan with the right rough
birth year" is empty by chance. In a tree of 8,759 persons, that
population is non-empty by chance. A given-name token match plus a rough
date plausibility was sufficient to push a wholly unrelated candidate
above threshold; the surname mismatch was not a hard constraint, only a
component of the composite.

### Fix

Added a surname gate at a 0.60 floor: the surname token's independent
score must reach 0.60 before composite scoring is even attempted. If the
surname-score floor is not met, the candidate is dropped without further
evaluation.

This restored the correct behavior on the Moore tree and did not regress
on the Kennedy/Queen/Habsburg trees, which we re-ran after the change.
The threshold of 0.60 was chosen empirically: it is high enough to reject
unrelated surnames including ones that share a phoneme (Knorr vs. Moore
soundex share is below 0.60) but low enough to accept common spelling
variants and OCR-corrupted forms (Smyth↔Smith, Kennedy↔Kennedi).

### Architectural lesson

Fuzzy matching at scale is a precision problem, not a recall problem.
P(false positive | naive composite metric) grows with the candidate pool
roughly linearly, because the pool of candidates that match on a single
component grows linearly while the pool of candidates that match on
multiple correlated components stays small. The fix is to add gates that
exploit domain structure: in genealogy, surname inheritance is a strong
patrilineal signal that a naive composite blurs away. Surname spellings
do drift, but cross-surname false positives at scale are far more common
than the same person showing up under wholly different surnames. We
re-introduced that domain prior as a hard threshold.

The deeper takeaway is that "good enough on the small test set" is
insufficient validation for systems that will run against larger
production data. Phase 2 evaluation used trees of 70-4,683 persons; the
bug only manifested on 8,759. We would have caught it earlier by
deliberately running on the largest available tree as a routine pre-flight
check.

---

## Case 3 — Silent verdict inversion from inter-agent vocabulary drift

### Symptom

While inspecting the JFK + synthetic DNA demo trace during this session,
the Critic's structured output contained `verdict: accept`,
`confidence_in_critique: 0.95`, and `dna_relevant.cm_consistency_verdict:
"contradicts"` simultaneously. The Critic accepted the hypothesis while
its own DNA-aware reasoning said the DNA evidence contradicted it. The
Critic's free-text justification was internally consistent and reasonable;
only the structured field was wrong.

### Detection

Found by direct inspection of the trace JSON during the synthetic DNA
demo work. The Critic's accept verdict on JFK's parents looked correct
on the surface, but the `dna_relevant` field showed `"contradicts"` for
a hypothesis with 3487 cM shared with the proposed parent — a value that
sits exactly in the Parent/Child range of the Shared cM Project. The
contradiction was the trigger to look closer.

### Root cause

The Hypothesizer outputs `proposed_relationship` as natural-language
strings: `"father of"`, `"mother of"`. The Critic's DNA-aware logic calls
`tools.shared_cm_lookup.is_consistent(claimed_relationship, shared_cM)`,
which canonicalizes the relationship string against an alias table before
looking up the expected cM range. The alias table contained `"parent"`,
`"father"`, `"mother"`, `"child"`, `"son"`, `"daughter"`, but not the
prepositional forms `"father of"` or `"mother of"`. When called with
`"father of"`, `is_consistent()` returned a structure whose `consistent`
field was `False` with deviation text `"unknown relationship type:
'father of'"`. The calling code in the Critic interpreted `consistent ==
False` as "DNA contradicts the hypothesis" without checking the deviation
field for the unknown-type signal.

The deeper reason this survived was that the trace recorded everything
correctly. The full alias-miss appeared in the trace; the
`cm_consistency_verdict: "contradicts"` value appeared in the trace; the
Critic's text justification, written from the alias-failed signal,
described the cM value as "consistent with parent-child relationship"
because the LLM looked at the raw cM number and reasoned correctly about
it. So the LLM's text and the structured field disagreed — but no part
of the pipeline checked them against each other.

### Fix

Two-part:
1. Added 30+ relationship-string aliases to
   `tools/shared_cm_lookup.py::_CANONICAL_ALIASES`, covering the
   prepositional forms (`"father of"`, `"mother of"`, `"son of"`,
   `"daughter of"`, `"parent of"`, `"child of"`), gendered grand- forms,
   `"aunt of"`/`"uncle of"`, and `"sibling of"`. After this change, the
   alias table covers every relationship label the Hypothesizer is
   prompted to emit.
2. Did not yet add a runtime contract assert at the boundary — flagged as
   future work.

### Architectural lesson

Inter-agent vocabulary is an undocumented coupling surface. Two agents
designed and tested independently will agree on roughly the same
relationship labels, but each individual agent's working set will drift
over time as prompts evolve. The drift is silent because no edge of the
graph type-checks the strings flowing across it. The Hypothesizer
gradually started saying `"father of"` instead of `"father"` to make its
output prose-readable; the lookup table never caught up.

Three structural responses are possible, in increasing order of cost:
- **Alias tables** — the cheapest fix, what we did. Works as long as
  someone remembers to update the table. Doesn't prevent the next drift.
- **Runtime contracts at boundaries** — assert the relationship string
  is in a known canonical set at the moment it crosses agent boundaries.
  Catches drift the next time it happens but requires the canonical set
  to be the source of truth.
- **Typed enum at the producer's output boundary** — the Hypothesizer
  emits a `RelationshipKind` enum, with a separate human-readable label
  generated downstream for prose. Eliminates the drift class entirely
  but requires schema discipline in every prompt.

We chose the alias-table fix to unblock the demo and have flagged the
typed-enum approach as future work. The real lesson generalizes beyond
this specific bug: any structured field that flows from one agent to
another's structured logic should be treated like a typed API, even when
it is naturally expressed as a string. Free-text inter-agent fields
should never feed structured downstream logic without canonicalization
at the boundary.

This is also a case where the trace artifact saved us. The bug had been
shipping for at least a week before it was noticed because the LLM-text
justifications looked plausible end-to-end. Routine inspection of the
structured fields against each other for internal consistency is now a
review-time check.

---

## Appendix — narrower failures, summarized

### `python-gedcom-2` Latin-1 GEDCOM crash

`python-gedcom-2`'s `Parser.parse_file()` hardcodes
`line.decode('utf-8-sig')` and provides no encoding override. The
Habsburg GEDCOM is Latin-1 (German umlauts: ö, ü, ß), so the very first
header line containing `Österreich` raised `UnicodeDecodeError` on byte
0xF6. Worked around by reading the file ourselves with
`encoding='latin-1', errors='replace'` and calling `parse_gedcom_text()`
on the resulting string. The library limitation is documented in
`tools/gedcom_parser.py`. No upstream fix attempted; this is a one-line
workaround at every call site.

### Gap-mode produces zero hypotheses

In an early gap-detection build, the Scout's gap-mode wrote candidate
parent records to `state["gap_candidates"]` while the Hypothesizer read
from `state["retrieved_records"]`. The pipeline ran cleanly with no
errors but produced zero hypotheses on every gap query. Detected by
running gap detection on the Moore tree and seeing 1,875 gaps reported
in the summary table but no Hypothesizer output downstream. Fixed by
normalizing the Scout's gap-mode output to write to the standard
`retrieved_records` state key (the same key it uses in query mode), so
the Hypothesizer reads from a single source of truth regardless of
mode. The narrow lesson: state-key contracts between agents need to be
tested with a passing end-to-end run, not just unit tests on each
agent in isolation.
