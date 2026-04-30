# Interaction Trace

- **Timestamp:** 20260429_223314
- **Label:** habsburg_maria_theresia_synthetic_dna
- **Query:** Who are the parents of Maria Theresia of Austria?
- **Status:** needs_revision
- **Revision count:** 2

---

## Agent Trace Log

```
record_scout: enter
record_scout: parsed 34020 persons from GEDCOM
record_scout: LLM criteria = {'primary_name': 'Maria Theresia von Österreich', 'surname': 'von Österreich', 'given_names': 'Maria Theresia', 'alt_names': ['Maria Theresa of Austria', "Marie Thérèse d'Autriche", 'Maria Theresia'], 'approx_birth_year': 1717, 'approx_location': 'Vienna, Austria'}
record_scout: query_mode — 155 candidates above threshold 0.7, keeping top 5
record_scout: top match = MARIA THERESIA von Österreich (score 1.0)
record_scout: built 39 GEDCOM record objects (including family context)
record_scout: FindAGrave returned 0 results
record_scout: Wikidata returned 1 results
record_scout: WikiTree returned 0 results
record_scout: total records after external corroboration: 40 (1 external)
record_scout: exit
dna_analyst: enter
dna_analyst: parsed 30 matches from myheritage
dna_analyst: DNA test subject identified as @I33@ (name match 1.00)
dna_analyst: distribution — Parent/Child: 11, Sibling: 3, Grandparent/Uncle: 1, 1st Cousin: 2, 1C1R/Half-1C: 1, 2nd Cousin: 6, Distant (<40 cM): 6
dna_analyst: 20 cross-references found
dna_analyst: aggregate consistency = consistent — no contradictions found
dna_analyst: exit
profile_synthesizer: enter
profile_synthesizer: disambiguated 5 candidates -> selected MARIA THERESIA von Österreich (score 2.0)
profile_synthesizer: excluded Maria Theresia von Herberstein (gedcom:@I1691@, score 0.892)
profile_synthesizer: excluded Maria Theresia von Österreich (gedcom:@I347@, score 0.5)
profile_synthesizer: excluded Maria Theresia Anna von Österreich (gedcom:@I374@, score 0.434)
profile_synthesizer: excluded Maria Theresia Cybo (gedcom:@I30496@, score 0.297)
profile_synthesizer: LLM synthesis produced 8 facts, 7 gaps
profile_synthesizer: built profile with 8 cited facts, 7 gaps
profile_synthesizer: exit
relationship_hypothesizer: enter
relationship_hypothesizer: 2 targets for MARIA THERESIA von Österreich: ['father', 'mother']
relationship_hypothesizer: built hypothesis hyp:@I33@:@I209@:father (confidence 0.88, 7 evidence items)
relationship_hypothesizer: built hypothesis hyp:@I33@:@I265@:mother (confidence 0.88, 5 evidence items)
relationship_hypothesizer: appended 1 external corroboration item(s) to evidence chains
relationship_hypothesizer: DNA SUPPORTS hyp:@I33@:@I209@:father (3489.0 cM consistent with father of)
relationship_hypothesizer: DNA SUPPORTS hyp:@I33@:@I265@:mother (3501.0 cM consistent with mother of)
relationship_hypothesizer: appended 2 DNA corroboration item(s) to evidence chains
relationship_hypothesizer: generated 2 hypotheses
relationship_hypothesizer: exit
adversarial_critic: enter
adversarial_critic: isolation_mode=filtered, filtered 2 hypotheses, stripped 4 internal field types
adversarial_critic: hyp:@I33@:@I209@:father tier1 (5 checks, 0 impossible)
adversarial_critic: hyp:@I33@:@I209@:father geo -> ok: 0km apart (within intra-regional range)
adversarial_critic: hyp:@I33@:@I209@:father DNA relevant — 1 cross-ref(s) for related person, deterministic check: supports
adversarial_critic: hyp:@I33@:@I209@:father LLM verdict=accept conf=0.92
adversarial_critic: hyp:@I33@:@I265@:mother tier1 (5 checks, 0 impossible)
adversarial_critic: hyp:@I33@:@I265@:mother DNA relevant — 1 cross-ref(s) for related person, deterministic check: supports
adversarial_critic: hyp:@I33@:@I265@:mother LLM verdict=reject conf=0.6
adversarial_critic: at least one reject; revision_count 0 -> 1, status=needs_revision
adversarial_critic: produced 2 critiques
adversarial_critic: exit
relationship_hypothesizer: enter
relationship_hypothesizer: 2 targets for MARIA THERESIA von Österreich: ['father', 'mother']
relationship_hypothesizer: built hypothesis hyp:@I33@:@I209@:father (confidence 0.93, 6 evidence items)
relationship_hypothesizer: built hypothesis hyp:@I33@:@I265@:mother (confidence 0.88, 6 evidence items)
relationship_hypothesizer: appended 1 external corroboration item(s) to evidence chains
relationship_hypothesizer: DNA SUPPORTS hyp:@I33@:@I209@:father (3489.0 cM consistent with father of)
relationship_hypothesizer: DNA SUPPORTS hyp:@I33@:@I265@:mother (3501.0 cM consistent with mother of)
relationship_hypothesizer: appended 2 DNA corroboration item(s) to evidence chains
relationship_hypothesizer: generated 2 hypotheses
relationship_hypothesizer: exit
adversarial_critic: enter
adversarial_critic: isolation_mode=filtered, filtered 2 hypotheses, stripped 4 internal field types
adversarial_critic: hyp:@I33@:@I209@:father tier1 (5 checks, 0 impossible)
adversarial_critic: hyp:@I33@:@I209@:father geo -> ok: 0km apart (within intra-regional range)
adversarial_critic: hyp:@I33@:@I209@:father DNA relevant — 1 cross-ref(s) for related person, deterministic check: supports
adversarial_critic: hyp:@I33@:@I209@:father LLM verdict=accept conf=0.92
adversarial_critic: hyp:@I33@:@I265@:mother tier1 (5 checks, 0 impossible)
adversarial_critic: hyp:@I33@:@I265@:mother DNA relevant — 1 cross-ref(s) for related person, deterministic check: supports
adversarial_critic: hyp:@I33@:@I265@:mother LLM verdict=reject conf=0.6
adversarial_critic: at least one reject; revision_count 1 -> 2, status=needs_revision
adversarial_critic: produced 2 critiques
adversarial_critic: exit
final_report_writer: enter
final_report_writer: composed report (17948 chars, 212 lines)
final_report_writer: exit
```

---

# Genealogical Research Report

**Query:** Who are the parents of Maria Theresia of Austria?
**Target:** MARIA THERESIA von Österreich (approx. born 1717), Vienna, Austria
**Pipeline status:** needs_revision  (revision count 2)
**Report status: Contains unresolved findings — human review recommended** (2 of 2 hypotheses flagged)

## Subject Profiles

### MARIA THERESIA von Österreich
`profile:@I33@` — source record `gedcom:@I33@`

**Disambiguation:** selected from 5 candidates
- ✓ `gedcom:@I33@` MARIA THERESIA von Österreich — score 2.0
    - name similarity 1.0
    - exact birth year match (1717)
    - birth place mismatch (target 'vienna, austria', candidate 'wien, österreich')
- ✗ `gedcom:@I1691@` Maria Theresia von Herberstein — score 0.892
    - name similarity 0.892
    - no birth year on candidate record; target is 1717
    - no birth place on candidate record; target is 'vienna, austria'
- ✗ `gedcom:@I347@` Maria Theresia von Österreich — score 0.5
    - name similarity 1.0
    - birth year mismatch (target 1717, candidate 1684, diff 33y)
    - birth place mismatch (target 'vienna, austria', candidate 'wien, österreich')
- ✗ `gedcom:@I374@` Maria Theresia Anna von Österreich — score 0.434
    - name similarity 0.934
    - birth year mismatch (target 1717, candidate 1845, diff 128y)
    - birth place mismatch (target 'vienna, austria', candidate 'wien, österreich')
- ✗ `gedcom:@I30496@` Maria Theresia Cybo — score 0.297
    - name similarity 0.797
    - birth year mismatch (target 1717, candidate 1725, diff 8y)
    - birth place mismatch (target 'vienna, austria', candidate 'novellara')

**Facts:**
- name: MARIA THERESIA von Österreich  _(gedcom:@I33@)_
- first_name: MARIA THERESIA von  _(gedcom:@I33@)_
- surname: Österreich  _(gedcom:@I33@)_
- sex: F  _(gedcom:@I33@)_
- birth_date: 13 MAY 1717  _(gedcom:@I33@)_
- birth_place: Wien, Österreich  _(gedcom:@I33@)_
- death_date: 29 NOV 1780  _(gedcom:@I33@)_
- death_place: Wien, Österreich  _(gedcom:@I33@)_

**Family references:** father=Karl VI des Heiligen Römischen Reiches; mother=Elisabeth von Braunschweig-Wolfenbüttel; spouse(s)=FRANZ I Stephan des Heiligen Römischen Reiches; children=Maria Elisabeth Amalie Antonia von Österreich, Maria Anna Josefa Antonia Johanna von Österreich, Maria Karoline Ernestine Antonia von Österreich, JOSEF II Benedikt des Heiligen Römischen Reiches, Maria Christine Johanna Josepha von Österreich, Maria Elisabeth Josefa Johanna von Österreich, Karl Joseph Emanuel Johann von Österreich, Maria Amalia Josepha Johanna von Österreich, Peter LEOPOLD II des Heiligen Römischen Reiches, Maria Carolina von Österreich, Maria Johanna Gabriele Josepha von Österreich, Maria Josepha Gabriele Johanna von Österreich, Marie Karoline Ludovika Josefa von Österreich, Ferdinand Karl Anton Josef Johann von Österreich-Modena, Maria Antonia Josepha Johanna von Österreich, Maximilian Franz Xaver Josef von Österreich

**Gaps and concerns (from Synthesizer):**
- No occupation recorded for subject
- No religion recorded for subject
- No burial place or burial date recorded for subject
- Birth date, death date, and birth place are sourced from a single record only (gedcom:@I33@); no corroborating external sources provided
- Death place is identical to birth place (Wien, Österreich) with no additional specificity, unlike the father's death place record which includes a district; possible lack of detail
- No marriage date or marriage place recorded for subject's union with spouse (gedcom:@I32@)
- No middle names or full regnal/formal name variants recorded beyond the single name field

## Accepted Findings

_No findings passed without escalation flags._

## Findings Requiring Human Review

### ⚠ UNRESOLVED — father of — `hyp:@I33@:@I209@:father`

**Escalation reasons:**
- Conflicting verdicts for subject @I33@: family unit has both accepted and rejected hypotheses (['accept', 'reject'])

**Subject:** `@I33@`  **Related:** `@I209@`  **Hypothesizer confidence:** 0.93

**Evidence chain:**
- (gedcom:@I33@) MARIA THERESIA von Österreich (born 13 MAY 1717, Wien, Österreich) has father_id explicitly recorded as @I209@, directly linking her to Karl VI des Heiligen Römischen Reiches.
- (gedcom:@I209@) Karl VI des Heiligen Römischen Reiches (born 01 OCT 1685, Wien, Österreich) has @I33@ listed among his children_ids, confirming a bidirectional parent-child link.
- (gedcom:@I33@) Both subject and candidate share the same birth place (Wien, Österreich), consistent with dynastic residence in the Habsburg imperial court.
- (gedcom:@I209@) Karl VI is recorded as member of family @F198@ (fams), and Maria Theresia is recorded as a child in the same family @F198@ (famc), placing them in the same family unit.
- (gedcom:@I33@) Karl VI's spouse @I265@ is recorded as the mother_id of Maria Theresia, corroborating the nuclear family structure.
- (gedcom:@I209@) The age gap between Karl VI (born 1685) and Maria Theresia (born 1717) is 32 years, which is biologically and historically plausible for a father-daughter relationship.
- (myheritage:unknown) DNA evidence supports father of: shared 3489.0 cM with Karl VI des Heiligen Roemischen Reiches (matched to Karl VI des Heiligen Römischen Reiches) is within expected range [3330, 3720] for Parent/Child

**Stated weaknesses (Hypothesizer's own):**
- All genealogical data derives from a single GEDCOM file; no independent external documentary sources (e.g., baptismal registers, Habsburg court records, academic historical genealogies) are cited in the supplied records.
- Birth date, death date, and birth place for the subject are sourced from a single record (gedcom:@I33@) only, with no corroborating archival citation.
- The subject's death place lacks district-level specificity compared to the candidate's death place record, suggesting possible inconsistency in data quality across records.
- No DNA evidence is available to corroborate the biological father-daughter relationship.
- The formal/regnal name variants for Maria Theresia are not fully recorded, introducing a minor risk of conflation with another individual of the same name, though this is low given the historical prominence of the persons involved.

#### Critique: ✓ ACCEPT
**Critic self-confidence:** 0.92  **Isolation mode:** `filtered`

**Justification:** Bidirectional GEDCOM linkage (father_id and children_ids), shared family @F198@, all Tier 1 checks pass, geographic plausibility is perfect, and DNA shared cM of 3489 falls squarely within the Parent/Child expected range. This is also a well-documented historical relationship (Maria Theresa was the daughter of Emperor Charles VI), making the hypothesis robust despite single-source GEDCOM provenance.

**Tier 1 deterministic checks:**
- [ok] death_before_birth: death is not before birth
- [ok] implausible_lifespan: lifespan within 120 years
- [ok] [father] parent_younger_than_child: parent is not younger than child
- [ok] [father] parent_too_young_at_birth: parent age plausible (>= 12)
- [ok] [father] parent_died_before_conception: father alive ~9mo before birth holds

**Geographic check:** [ok] 0km apart (within intra-regional range)

**Issues found by the Critic:**
- All genealogical data derives from a single GEDCOM file with no independent archival corroboration
- DNA match identification relies on fuzzy name matching (score 0.958), though the historical context makes misidentification unlikely

### ⚠ UNRESOLVED — mother of — `hyp:@I33@:@I265@:mother`

**Escalation reasons:**
- Rejected by Adversarial Critic after 2 revision cycle(s) — pipeline force-finalized
- Conflicting verdicts for subject @I33@: family unit has both accepted and rejected hypotheses (['accept', 'reject'])

**Subject:** `@I33@`  **Related:** `@I265@`  **Hypothesizer confidence:** 0.88

**Evidence chain:**
- (gedcom:@I33@) MARIA THERESIA von Österreich (born 13 MAY 1717) explicitly records her mother_id as @I265@, directly linking her to Elisabeth von Braunschweig-Wolfenbüttel.
- (gedcom:@I265@) Elisabeth von Braunschweig-Wolfenbüttel's children_ids list includes @I33@ (MARIA THERESIA von Österreich), confirming the parent-child link from the candidate's side.
- (gedcom:@I33@) Both MARIA THERESIA and Elisabeth are linked to the same family unit @F198@: MARIA THERESIA via famc and Elisabeth via fams, placing them in the same nuclear family record.
- (gedcom:@I265@) Elisabeth von Braunschweig-Wolfenbüttel is recorded as spouse of @I209@, who is also recorded as the father_id of MARIA THERESIA, corroborating the parental couple.
- (gedcom:@I265@) Elisabeth's birth year of 1691 and MARIA THERESIA's birth year of 1717 yield an age gap of 26 years, which is biologically plausible for a mother-daughter relationship.
- (gedcom:@I265@) Elisabeth von Braunschweig-Wolfenbüttel died 21 DEC 1750, after MARIA THERESIA's birth on 13 MAY 1717, meaning the candidate was alive at the time of the subject's birth.
- (wikidata:Q131706) Independent source (Wikidata, Maria Theresa of Austria) confirms mother of: 'Elisabeth Christine of Brunswick-Wolfenbüttel' matches GEDCOM name 'Elisabeth von Braunschweig-Wolfenbüttel' (similarity 0.83)
- (myheritage:unknown) DNA evidence supports mother of: shared 3501.0 cM with Elisabeth von Braunschweig-Wolfenbuettel (matched to Elisabeth von Braunschweig-Wolfenbüttel) is within expected range [3330, 3720] for Parent/Child

**Stated weaknesses (Hypothesizer's own):**
- All evidence derives from a single GEDCOM file; no independent external documentary sources (e.g., Habsburg court birth registers, contemporaneous baptismal records) are cited to corroborate the mother_id link.
- Elisabeth von Braunschweig-Wolfenbüttel's birth place is null, preventing geographic plausibility analysis to support co-location at the time of MARIA THERESIA's birth in Wien.
- The GEDCOM data itself may have been compiled from secondary historical sources of varying quality; transcription errors in the family linkages cannot be ruled out without cross-referencing primary records.
- Only four children are listed under Elisabeth (@I7396@, @I33@, @I353@, @I7397@), which is a relatively small number for a royal consort of the period; possible incomplete recording of children or a different Elisabeth may have been conflated.

#### Critique: ✗ REJECT
**Critic self-confidence:** 0.6  **Isolation mode:** `filtered`

**Justification:** The biographical facts (1691-1750 lifespan, marriage to Karl VI/@I209@, daughter Maria Theresia born 1717) align correctly with the historical Elisabeth Christine of Brunswick-Wolfenbüttel, so the proposed relationship is almost certainly factually correct. However, I am rejecting because the evidence chain is materially flawed: the DNA evidence is impossible (both subjects died in the 18th century) and constitutes fabricated or mis-attributed data, and the remaining evidence is single-source GEDCOM self-reference plus a name-similarity Wikidata hit. The hypothesis happens to be historically true, but the evidence as presented does not properly establish it and includes a spurious DNA claim that should be disqualified.

**Tier 1 deterministic checks:**
- [ok] death_before_birth: death is not before birth
- [ok] implausible_lifespan: lifespan within 120 years
- [ok] [mother] parent_younger_than_child: parent is not younger than child
- [ok] [mother] parent_too_young_at_birth: parent age plausible (>= 12)
- [ok] [mother] parent_died_before_conception: mother alive at birth holds

**Issues found by the Critic:**
- Maria Theresa of Austria's actual mother was Elisabeth Christine of Brunswick-Wolfenbüttel (born 28 Aug 1691, died 21 Dec 1750) — these dates match @I265@. However, the GEDCOM records her name as 'Elisabeth' without 'Christine'; this is a minor naming variant, not a substantive issue.
- DNA evidence is anachronistic and impossible: Maria Theresa died in 1780 and Elisabeth Christine died in 1750. No autosomal DNA test (MyHeritage, etc.) could have been performed on either individual. The 3501 cM 'match' is fabricated or refers to different living persons mis-identified by fuzzy name matching, and should not be treated as corroborating evidence.
- All genealogical evidence derives from a single GEDCOM file with no independent primary-source citation; the Wikidata 'confirmation' is just a name-similarity match, not an independent record lookup.
- Stated weakness about 'only four children' is itself a red flag — Elisabeth Christine actually had only four children who survived infancy plus stillbirths, so this is consistent, but the GEDCOM may be conflating or under-recording.

## DNA Evidence

**Platform:** myheritage  **Total matches:** 30  **Consistency:** consistent — no contradictions found

**Match distribution by relationship tier:**
- Parent/Child: 11
- Sibling: 3
- Grandparent/Uncle: 1
- 1st Cousin: 2
- 1C1R/Half-1C: 1
- 2nd Cousin: 6
- Distant (<40 cM): 6

**GEDCOM cross-references (20 name matches):**
- DNA: **Karl VI des Heiligen Roemischen Reiches** (3489.0 cM) matched GEDCOM: **Karl VI des Heiligen Römischen Reiches** (`@I209@`)
  - DNA-predicted: Parent/Child | Platform said: Parent | Consistent: True
- DNA: **Elisabeth von Braunschweig-Wolfenbuettel** (3501.0 cM) matched GEDCOM: **Elisabeth von Braunschweig-Wolfenbüttel** (`@I265@`)
  - DNA-predicted: Parent/Child | Platform said: Parent | Consistent: True
- DNA: **Leopold Johann von Oesterreich** (2604.0 cM) matched GEDCOM: **Leopold Johann von Österreich** (`@I7396@`)
  - DNA-predicted: Full Sibling | Platform said: Sibling | Consistent: True
- DNA: **Maria Anna von Oesterreich** (2587.0 cM) matched GEDCOM: **Maria Anna von Österreich** (`@I353@`)
  - DNA-predicted: Full Sibling | Platform said: Sibling | Consistent: True
- DNA: **Maria Amalia von Oesterreich** (2622.0 cM) matched GEDCOM: **Maria Amalia von Österreich** (`@I7397@`)
  - DNA-predicted: Full Sibling | Platform said: Sibling | Consistent: True
- DNA: **FRANZ I Stephan des Heiligen Roemischen Reiches** (18.0 cM) matched GEDCOM: **FRANZ I Stephan des Heiligen Römischen Reiches** (`@I32@`)
  - DNA-predicted: 4th Cousin 1x Removed | Platform said: Distant Cousin | Consistent: False
- DNA: **JOSEF II Benedikt des Heiligen Roemischen Reiches** (3460.0 cM) matched GEDCOM: **JOSEF II Benedikt des Heiligen Römischen Reiches** (`@I34@`)
  - DNA-predicted: Parent/Child | Platform said: Child | Consistent: True
- DNA: **Peter LEOPOLD II des Heiligen Roemischen Reiches** (3478.0 cM) matched GEDCOM: **Peter LEOPOLD II des Heiligen Römischen Reiches** (`@I31@`)
  - DNA-predicted: Parent/Child | Platform said: Child | Consistent: True
- DNA: **Maria Antonia Josepha Johanna von Oesterreich** (3445.0 cM) matched GEDCOM: **Maria Antonia Josepha Johanna von Österreich** (`@I36@`)
  - DNA-predicted: Parent/Child | Platform said: Child | Consistent: True
- DNA: **Maria Karoline Ernestine Antonia von Oesterreich** (3502.0 cM) matched GEDCOM: **Maria Karoline Ernestine Antonia von Österreich** (`@I271@`)
  - DNA-predicted: Parent/Child | Platform said: Child | Consistent: True
- DNA: **Maria Christine Johanna Josepha von Oesterreich** (3471.0 cM) matched GEDCOM: **Maria Christine Johanna Josepha von Österreich** (`@I35@`)
  - DNA-predicted: Parent/Child | Platform said: Child | Consistent: True
- DNA: **Ferdinand Karl Anton Josef Johann von Oesterreich-Modena** (3458.0 cM) matched GEDCOM: **Ferdinand Karl Anton Josef Johann von Österreich-Modena** (`@I279@`)
  - DNA-predicted: Parent/Child | Platform said: Child | Consistent: True
- DNA: **Maximilian Franz Xaver Josef von Oesterreich** (3489.0 cM) matched GEDCOM: **Maximilian Franz Xaver Josef von Österreich** (`@I207@`)
  - DNA-predicted: Parent/Child | Platform said: Child | Consistent: True
- DNA: **Maria Carolina von Oesterreich** (3469.0 cM) matched GEDCOM: **Maria Carolina von Österreich** (`@I276@`)
  - DNA-predicted: Parent/Child | Platform said: Child | Consistent: True
- DNA: **Maria Elisabeth Amalie Antonia von Oesterreich** (3491.0 cM) matched GEDCOM: **Maria Elisabeth Amalie Antonia von Österreich** (`@I269@`)
  - DNA-predicted: Parent/Child | Platform said: Child | Consistent: True
- DNA: **Hildegard Frauenlob** (857.0 cM) matched GEDCOM: **Hildegard Felder** (`@I12368@`)
  - DNA-predicted: Great-Grandparent | Platform said: 1st Cousin | Consistent: True
- DNA: **Wilhelm von Trauttmansdorff** (872.0 cM) matched GEDCOM: **Wilhelm von Paulsdorf** (`@I6933@`)
  - DNA-predicted: Great-Grandparent | Platform said: 1st Cousin | Consistent: True
- DNA: **Theodore Marlowe** (228.0 cM) matched GEDCOM: **Theodor Ankarcrona** (`@I13345@`)
  - DNA-predicted: 2nd Cousin | Platform said: 2nd Cousin | Consistent: True
- DNA: **Eleanor Ashbrook** (124.0 cM) matched GEDCOM: **Eleanor von Bohun** (`@I8058@`)
  - DNA-predicted: 2nd Cousin 1x Removed | Platform said: 2C1R | Consistent: True
- DNA: **Rosalind T.** (42.0 cM) matched GEDCOM: **Rosalin Cubitts** (`@I11855@`)
  - DNA-predicted: 3rd Cousin 1x Removed | Platform said: 3C1R | Consistent: False

**Platform prediction consistency:** 25/30 consistent with Shared cM Project ranges

**Findings:**
- DNA data from myheritage: 30 total matches analyzed.
- 15 close relative(s) detected in Parent/Child, Sibling, or Grandparent/Uncle range.
- 3 match(es) in 1st cousin or closer cousin range.
- 6 distant matches (<40 cM) — expected for large match lists.
- 20 DNA match name(s) matched to GEDCOM tree persons (fuzzy score >= 0.75).
-   - 'Karl VI des Heiligen Roemischen Reiches' matched 'Karl VI des Heiligen Römischen Reiches' (@I209@) at 3489.0 cM (predicted: Parent/Child)
-   - 'Elisabeth von Braunschweig-Wolfenbuettel' matched 'Elisabeth von Braunschweig-Wolfenbüttel' (@I265@) at 3501.0 cM (predicted: Parent/Child)
-   - 'Leopold Johann von Oesterreich' matched 'Leopold Johann von Österreich' (@I7396@) at 2604.0 cM (predicted: Full Sibling)
- Platform relationship predictions: 25/30 (83%) consistent with Shared cM Project ranges.

