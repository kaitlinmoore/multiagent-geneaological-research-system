"""Relationship Hypothesizer — proposes family connections with evidence + reasoning.

Role (CLAUDE.md): "Proposes family connections with evidence chains and
confidence levels. Tools: date arithmetic, haversine distance. Must state
weaknesses of own hypotheses."

Pipeline:
    1. Read profiles from state. Each profile already has disambiguated
       subject identity and family references.
    2. Select which relationships to hypothesize about based on the query
       (parents, spouses, children, etc.). Default to parental hypotheses
       when the query doesn't match a keyword pattern.
    3. Gather deterministic evidence for each proposed relationship using
       tools.date_utils (age plausibility) and tools.geo_utils
       (co-location signals). This is the "raw evidence" the Critic will see.
    4. Call the LLM to synthesize a full hypothesis per relationship,
       including: evidence_chain, confidence_score, stated_weaknesses, and
       the internal reasoning_narrative + alternatives_considered.
    5. Construct each hypothesis via make_hypothesis() so the public/internal
       field partition is explicit at the creation site.

CRITICAL CRITIC-ISOLATION INVARIANT:
    This module populates BOTH the public and internal fields of each
    hypothesis. It DOES NOT call filter_hypothesis_for_critic() — that is
    strictly the Critic's responsibility. The Hypothesizer's only obligation
    at the boundary is to use make_hypothesis() so both field sets are
    present and well-formed.

    The LLM is asked for `reasoning_narrative` explicitly. That field WILL
    contain the Hypothesizer's inferential chain-of-thought — that is the
    point. It exists so that (a) we can inspect it for debugging, and (b)
    the A/B experiment has real data to toggle between hiding and showing.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from agents.hypothesis_schema import make_hypothesis
from state import GenealogyState
from tools.date_utils import get_year, normalize_gedcom_date
from tools.fuzzy_match import name_match_score
from tools.geo_utils import place_distance_km


# Default Hypothesizer model. Production uses Anthropic Sonnet 4.6.
# A cross-vendor variant (e.g. weak OpenAI Hypothesizer + Anthropic Critic)
# is available for the asymmetric-capability experiment by setting:
#   HYPOTHESIZER_VENDOR=openai     HYPOTHESIZER_MODEL=gpt-4o-mini
#   HYPOTHESIZER_VENDOR=anthropic  HYPOTHESIZER_MODEL=claude-sonnet-4-6  (default)
_DEFAULT_VENDOR = "anthropic"
_DEFAULT_MODEL = "claude-sonnet-4-6"


def build_hypothesizer_llm(vendor: Optional[str] = None, model: Optional[str] = None):
    """Construct a Hypothesizer LLM. Defaults to Anthropic Sonnet 4.6.

    Override via env vars (HYPOTHESIZER_VENDOR, HYPOTHESIZER_MODEL) or arguments.
    """
    vendor = (vendor or os.environ.get("HYPOTHESIZER_VENDOR") or _DEFAULT_VENDOR).lower()
    model = model or os.environ.get("HYPOTHESIZER_MODEL") or _DEFAULT_MODEL

    if vendor == "anthropic":
        return ChatAnthropic(model=model, max_tokens=2048)
    if vendor == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, max_tokens=2048)
    if vendor == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model, max_output_tokens=2048)
    raise ValueError(f"unknown HYPOTHESIZER_VENDOR: {vendor!r}")


llm = build_hypothesizer_llm()


# Keyword → relationship-type routing.
_QUERY_KEYWORDS = {
    "parent": ["father", "mother"],
    "parents": ["father", "mother"],
    "father": ["father"],
    "mother": ["mother"],
    "dad": ["father"],
    "mom": ["mother"],
    "spouse": ["spouse"],
    "wife": ["spouse"],
    "husband": ["spouse"],
    "married": ["spouse"],
    "child": ["child"],
    "children": ["child"],
    "son": ["child"],
    "daughter": ["child"],
    "sibling": ["sibling"],
    "brother": ["sibling"],
    "sister": ["sibling"],
}


_HYPOTHESIZER_PROMPT = """You are a genealogy Relationship Hypothesizer.

You will be given a SUBJECT person, a CANDIDATE related person, a proposed
RELATIONSHIP TYPE, and deterministic prior evidence (ages, co-location,
rule checks). Your job is to synthesize a well-formed hypothesis.

Return ONE JSON object with exactly these keys:

  "proposed_relationship":  short human-readable label, e.g. "father of",
                            "mother of", "spouse of"
  "evidence_chain":         list of {"claim": str, "source": str} items.
                            Each claim MUST cite a source record_id drawn
                            from the supplied records (e.g. "gedcom:@I0@").
  "confidence_score":       float in [0, 1]. Be conservative:
                              >0.9  only with multiple independent sources
                              0.7-0.9  single well-supported source
                              0.5-0.7  circumstantial
                              <0.5   weak or conflicting evidence
  "stated_weaknesses":      list of concrete concerns (not boilerplate).
                            Examples: "only one source", "no DNA corroboration",
                            "shared name with Jr — possible mistaken identity"
  "reasoning_narrative":    3-8 sentences explaining HOW the evidence supports
                            this relationship. This is the Hypothesizer's
                            inferential chain — be explicit about each step.
  "alternatives_considered": list of alternative interpretations the evidence
                            could support (e.g. "could be uncle", "could be
                            another person of same name"), or [] if none.

Rules:
  - Every claim in evidence_chain MUST use a source record_id from the input.
  - Do not invent facts. Values come verbatim from records.
  - stated_weaknesses MUST list real concerns even when confidence is high.

Return ONLY valid JSON. No prose, no markdown fences.
"""


def relationship_hypothesizer_node(state: GenealogyState) -> dict:
    trace: list[str] = []
    trace.append("relationship_hypothesizer: enter")

    profiles = state.get("profiles") or []
    if not profiles:
        trace.append("relationship_hypothesizer: no profiles in state, skipping")
        trace.append("relationship_hypothesizer: exit")
        return {
            "hypotheses": [],
            "status": "running",
            "trace_log": trace,
        }

    gedcom_persons = state.get("gedcom_persons") or []
    retrieved_records = state.get("retrieved_records") or []
    person_by_id = {p["id"]: p for p in gedcom_persons}
    record_by_person_id = {
        r["data"]["id"]: r for r in retrieved_records if r.get("data", {}).get("id")
    }

    hypotheses: list[dict] = []
    for profile in profiles:
        profile_hypotheses = _hypothesize_for_profile(
            profile=profile,
            query=state["query"],
            person_by_id=person_by_id,
            record_by_person_id=record_by_person_id,
            trace=trace,
        )
        hypotheses.extend(profile_hypotheses)

    # Corroboration step: scan external records for evidence that supports
    # each hypothesis, and append matching citations to the evidence chain.
    _append_external_corroboration(
        hypotheses, retrieved_records, person_by_id, trace
    )

    # DNA corroboration: if DNA Analyst output is available AND the
    # hypothesis subject IS the DNA test subject, look for the hypothesis's
    # related person in the DNA cross-references. Add a DNA evidence item
    # — supporting if the cM is consistent with the proposed relationship,
    # contradicting if not.
    _append_dna_corroboration(hypotheses, state.get("dna_analysis"), trace)

    trace.append(
        f"relationship_hypothesizer: generated {len(hypotheses)} hypotheses"
    )
    trace.append("relationship_hypothesizer: exit")

    return {
        "hypotheses": hypotheses,
        "status": "running",
        "trace_log": trace,
    }


# ---------------------------------------------------------------------------
# Per-profile hypothesis generation
# ---------------------------------------------------------------------------


def _hypothesize_for_profile(
    profile: dict,
    query: str,
    person_by_id: dict[str, dict],
    record_by_person_id: dict[str, dict],
    trace: list[str],
) -> list[dict]:
    subject_id = _strip_record_id_prefix(profile["subject_record_id"])
    subject_person = person_by_id.get(subject_id)
    if not subject_person:
        trace.append(
            f"relationship_hypothesizer: subject {subject_id} not in gedcom_persons"
        )
        return []

    targets = _select_relationship_targets(query, profile["family"])
    if not targets:
        trace.append(
            "relationship_hypothesizer: no relationship targets derived from query + family"
        )
        return []

    trace.append(
        f"relationship_hypothesizer: {len(targets)} targets for "
        f"{profile['subject_name']}: "
        f"{[t['relationship_type'] for t in targets]}"
    )

    hypotheses: list[dict] = []
    for target in targets:
        related_id = _strip_record_id_prefix(target["record_id"])
        related_person = person_by_id.get(related_id)
        if not related_person:
            trace.append(
                f"relationship_hypothesizer: skipping {related_id} "
                f"(not in gedcom_persons)"
            )
            continue

        # Build deterministic prior evidence the LLM will work from.
        prior = _compute_prior_evidence(
            subject_person=subject_person,
            related_person=related_person,
            relationship_type=target["relationship_type"],
        )

        hypothesis = _synthesize_one_hypothesis(
            subject_person=subject_person,
            related_person=related_person,
            subject_record_id=profile["subject_record_id"],
            related_record_id=target["record_id"],
            relationship_type=target["relationship_type"],
            subject_profile=profile,
            prior_evidence=prior,
            trace=trace,
        )
        if hypothesis is not None:
            hypotheses.append(hypothesis)

    return hypotheses


def _select_relationship_targets(query: str, family: dict) -> list[dict]:
    """Decide which family relationships to hypothesize about from the query text."""
    query_lower = query.lower()
    selected_types: set[str] = set()
    for keyword, types in _QUERY_KEYWORDS.items():
        if keyword in query_lower:
            selected_types.update(types)

    # If the query doesn't hit a keyword, default to parents — the most common
    # genealogy research question. CLAUDE.md's trap taxonomy assumes parental
    # hypotheses as the primary unit of work.
    if not selected_types:
        selected_types = {"father", "mother"}

    targets: list[dict] = []
    if "father" in selected_types and family.get("father"):
        targets.append(
            {"relationship_type": "father", "record_id": family["father"]["record_id"]}
        )
    if "mother" in selected_types and family.get("mother"):
        targets.append(
            {"relationship_type": "mother", "record_id": family["mother"]["record_id"]}
        )
    if "spouse" in selected_types:
        for spouse in family.get("spouses") or []:
            targets.append(
                {"relationship_type": "spouse", "record_id": spouse["record_id"]}
            )
    if "child" in selected_types:
        for child in family.get("children") or []:
            targets.append(
                {"relationship_type": "child", "record_id": child["record_id"]}
            )
    return targets


# ---------------------------------------------------------------------------
# Deterministic prior evidence (for the LLM to cite + for Critic preview)
# ---------------------------------------------------------------------------


def _compute_prior_evidence(
    subject_person: dict,
    related_person: dict,
    relationship_type: str,
) -> dict:
    """Compute numerical priors the LLM can reference in its evidence chain."""
    subject_birth_year = get_year(subject_person.get("birth_date"))
    related_birth_year = get_year(related_person.get("birth_date"))
    age_delta = None
    if subject_birth_year and related_birth_year:
        age_delta = subject_birth_year - related_birth_year

    birthplace_distance_km = None
    subject_place = subject_person.get("birth_place")
    related_place = related_person.get("birth_place")
    if subject_place and related_place:
        # Live geocoding; returns None on any error. lru_cache memoizes.
        try:
            birthplace_distance_km = place_distance_km(subject_place, related_place)
        except Exception:
            birthplace_distance_km = None

    # Plausibility flags based on relationship type.
    plausibility_flags: list[str] = []
    if relationship_type in ("father", "mother"):
        if age_delta is not None:
            if age_delta < 12:
                plausibility_flags.append(
                    f"parent-child age gap {age_delta}y below biological minimum 12y"
                )
            elif age_delta > 60:
                plausibility_flags.append(
                    f"parent-child age gap {age_delta}y unusually large"
                )
            else:
                plausibility_flags.append(
                    f"parent-child age gap {age_delta}y is biologically plausible"
                )

    return {
        "subject_birth_year": subject_birth_year,
        "related_birth_year": related_birth_year,
        "age_delta": age_delta,
        "subject_birth_place": subject_place,
        "related_birth_place": related_place,
        "birthplace_distance_km": (
            round(birthplace_distance_km) if birthplace_distance_km else None
        ),
        "plausibility_flags": plausibility_flags,
    }


# ---------------------------------------------------------------------------
# LLM synthesis — one call per hypothesis for clear traceability
# ---------------------------------------------------------------------------


def _synthesize_one_hypothesis(
    subject_person: dict,
    related_person: dict,
    subject_record_id: str,
    related_record_id: str,
    relationship_type: str,
    subject_profile: dict,
    prior_evidence: dict,
    trace: list[str],
) -> Optional[dict]:
    prompt_body = _build_prompt_body(
        subject_person=subject_person,
        related_person=related_person,
        subject_record_id=subject_record_id,
        related_record_id=related_record_id,
        relationship_type=relationship_type,
        subject_profile=subject_profile,
        prior_evidence=prior_evidence,
    )

    try:
        response = llm.invoke(
            [
                SystemMessage(content=_HYPOTHESIZER_PROMPT),
                HumanMessage(content=prompt_body),
            ]
        )
        raw_text = response.content.strip() if isinstance(response.content, str) else str(response.content)
        parsed = json.loads(_strip_markdown_fences(raw_text))
    except Exception as exc:
        trace.append(
            f"relationship_hypothesizer: LLM call failed for {relationship_type} "
            f"({type(exc).__name__}: {exc}), using deterministic fallback"
        )
        return _deterministic_fallback_hypothesis(
            subject_person=subject_person,
            related_person=related_person,
            subject_record_id=subject_record_id,
            related_record_id=related_record_id,
            relationship_type=relationship_type,
            prior_evidence=prior_evidence,
        )

    # Validate citations against available record_ids.
    valid_source_ids = {subject_record_id, related_record_id}
    evidence_chain = parsed.get("evidence_chain") or []
    for item in evidence_chain:
        src = (item or {}).get("source")
        if src and src not in valid_source_ids:
            trace.append(
                f"relationship_hypothesizer: WARNING evidence cites unknown "
                f"source {src}"
            )

    subject_id = subject_person["id"]
    related_id = related_person["id"]

    hypothesis = make_hypothesis(
        subject_id=subject_id,
        related_id=related_id,
        proposed_relationship=parsed.get(
            "proposed_relationship", f"{relationship_type} of"
        ),
        evidence_chain=evidence_chain,
        confidence_score=float(parsed.get("confidence_score", 0.5)),
        stated_weaknesses=parsed.get("stated_weaknesses") or [],
        reasoning_narrative=parsed.get("reasoning_narrative", ""),
        alternatives_considered=parsed.get("alternatives_considered") or [],
        llm_raw_response=raw_text,
        hypothesis_id=f"hyp:{subject_id}:{related_id}:{relationship_type}",
    )
    trace.append(
        f"relationship_hypothesizer: built hypothesis "
        f"{hypothesis['hypothesis_id']} "
        f"(confidence {hypothesis['confidence_score']:.2f}, "
        f"{len(hypothesis['evidence_chain'])} evidence items)"
    )
    return hypothesis


def _build_prompt_body(
    subject_person: dict,
    related_person: dict,
    subject_record_id: str,
    related_record_id: str,
    relationship_type: str,
    subject_profile: dict,
    prior_evidence: dict,
) -> str:
    available_sources = (
        f"  - {subject_record_id}  (subject: {subject_person.get('name')})\n"
        f"  - {related_record_id}  (candidate: {related_person.get('name')})"
    )
    return (
        f"Relationship type to hypothesize: {relationship_type}\n\n"
        f"Subject:\n{json.dumps(subject_person, default=str, indent=2)}\n\n"
        f"Candidate related person:\n"
        f"{json.dumps(related_person, default=str, indent=2)}\n\n"
        f"Subject profile facts (already consolidated with citations):\n"
        f"{json.dumps(subject_profile.get('facts', []), default=str, indent=2)}\n\n"
        f"Subject profile gaps:\n"
        f"{json.dumps(subject_profile.get('gaps', []), indent=2)}\n\n"
        f"Deterministic prior evidence (from date_utils + geo_utils):\n"
        f"{json.dumps(prior_evidence, indent=2)}\n\n"
        f"Available record_id sources (use these exact strings in citations):\n"
        f"{available_sources}\n\n"
        f"Return the JSON hypothesis now:"
    )


def _deterministic_fallback_hypothesis(
    subject_person: dict,
    related_person: dict,
    subject_record_id: str,
    related_record_id: str,
    relationship_type: str,
    prior_evidence: dict,
) -> dict:
    """Build a minimally-populated hypothesis without the LLM.

    Confidence is capped at 0.5 because we couldn't run the synthesis step.
    Weaknesses explicitly note the fallback so the Critic knows provenance.
    """
    subject_id = subject_person["id"]
    related_id = related_person["id"]

    evidence_chain = [
        {
            "claim": f"subject {subject_person.get('name')} born {subject_person.get('birth_date') or 'unknown'}",
            "source": subject_record_id,
        },
        {
            "claim": f"candidate {related_person.get('name')} born {related_person.get('birth_date') or 'unknown'}",
            "source": related_record_id,
        },
    ]
    if prior_evidence.get("age_delta") is not None:
        evidence_chain.append(
            {
                "claim": f"age delta subject - candidate = {prior_evidence['age_delta']} years",
                "source": subject_record_id,
            }
        )

    return make_hypothesis(
        subject_id=subject_id,
        related_id=related_id,
        proposed_relationship=f"{relationship_type} of",
        evidence_chain=evidence_chain,
        confidence_score=0.5,
        stated_weaknesses=[
            "LLM synthesis unavailable — deterministic fallback only",
            "no evidence beyond GEDCOM records",
            "no corroborating sources",
        ],
        reasoning_narrative=(
            "Fallback hypothesis generated without LLM. The relationship is "
            "drawn directly from the GEDCOM family pointers; no inferential "
            "reasoning was performed."
        ),
        alternatives_considered=[],
        hypothesis_id=f"hyp:{subject_id}:{related_id}:{relationship_type}",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_record_id_prefix(record_id: Optional[str]) -> Optional[str]:
    """Turn 'gedcom:@I0@' into '@I0@'; leave '@I0@' alone; return None for None."""
    if record_id is None:
        return None
    if ":" in record_id:
        return record_id.split(":", 1)[1]
    return record_id


def _strip_markdown_fences(text: str) -> str:
    if text.startswith("```"):
        body = text.strip("`")
        if body.lower().startswith("json"):
            body = body[4:]
        return body.strip()
    return text


# ---------------------------------------------------------------------------
# External source corroboration — appends to existing evidence chains
# ---------------------------------------------------------------------------

# Minimum fuzzy-match score to consider an external record corroborating.
_CORROBORATION_NAME_THRESHOLD = 0.70


def _append_external_corroboration(
    hypotheses: list[dict],
    retrieved_records: list[dict],
    person_by_id: dict[str, dict],
    trace: list[str],
) -> None:
    """Scan external records for evidence supporting each hypothesis.

    For each hypothesis, checks Wikidata and FindAGrave records in
    retrieved_records. If an external record names the same related person
    (by fuzzy name match), a corroboration entry is appended to the
    hypothesis's evidence_chain with the external record_id.

    Modifies hypotheses in place. Additive only — never removes or replaces
    existing GEDCOM evidence items.
    """
    external_records = [
        r for r in retrieved_records
        if r.get("source_type") in ("wikidata", "findagrave", "wikitree")
    ]
    if not external_records:
        return

    total_added = 0
    for hyp in hypotheses:
        related_id = hyp.get("related_id")
        related_person = person_by_id.get(related_id)
        if not related_person:
            continue

        related_name = related_person.get("name") or ""
        relationship = (hyp.get("proposed_relationship") or "").lower()
        evidence_chain = hyp.get("evidence_chain") or []

        # Determine which relationship field to check on external records.
        # Wikidata records have father/mother/spouse fields as labels.
        role_field = _relationship_to_wikidata_field(relationship)

        for ext in external_records:
            source_type = ext.get("source_type")
            ext_data = ext.get("data") or {}
            record_id = ext.get("record_id")

            corroboration = _check_corroboration(
                ext_data=ext_data,
                source_type=source_type,
                related_name=related_name,
                role_field=role_field,
                relationship=relationship,
            )
            if corroboration:
                evidence_chain.append({
                    "claim": corroboration,
                    "source": record_id,
                })
                total_added += 1

    if total_added:
        trace.append(
            f"relationship_hypothesizer: appended {total_added} external "
            f"corroboration item(s) to evidence chains"
        )


def _append_dna_corroboration(
    hypotheses: list[dict],
    dna_analysis: Optional[dict],
    trace: list[str],
) -> None:
    """Append DNA-derived evidence items to hypotheses where applicable.

    Conditions for adding a DNA evidence item to hypothesis (subject -> related):
      1. DNA Analyst identified a GEDCOM ID for the DNA test subject
      2. That ID matches the hypothesis's subject_id (the cM values describe
         shared DNA between this subject and the matches)
      3. The hypothesis's related person appears in cross_references
      4. The cM value can be checked against the proposed relationship via
         the Shared cM Project lookup table

    The evidence item explicitly notes whether DNA SUPPORTS or CONTRADICTS
    the proposed relationship. The Critic can then evaluate that claim.
    """
    if not dna_analysis or not dna_analysis.get("cross_references"):
        return

    dna_subject_id = dna_analysis.get("subject_gedcom_id")
    if not dna_subject_id:
        trace.append(
            "relationship_hypothesizer: DNA data present but test subject "
            "not identified — DNA reasoning skipped"
        )
        return

    from tools.shared_cm_lookup import is_consistent

    cross_refs = dna_analysis["cross_references"]
    cross_ref_by_id = {xr.get("gedcom_id"): xr for xr in cross_refs if xr.get("gedcom_id")}

    total_added = 0
    for hyp in hypotheses:
        subject_id = hyp.get("subject_id")
        if subject_id != dna_subject_id:
            continue  # cM data isn't between this subject and the match list

        related_id = hyp.get("related_id")
        xr = cross_ref_by_id.get(related_id)
        if not xr:
            continue  # related person not in DNA matches

        relationship = hyp.get("proposed_relationship", "")
        cm_value = xr.get("shared_cM")
        if cm_value is None:
            continue

        check = is_consistent(cm_value, relationship)
        evidence_chain = hyp.get("evidence_chain") or []
        match_id = xr.get("match_id") or "unknown"
        platform = dna_analysis.get("platform", "dna")
        record_id = f"{platform}:{match_id}"

        if check.get("consistent"):
            evidence_chain.append({
                "claim": (
                    f"DNA evidence supports {relationship}: shared "
                    f"{cm_value} cM with {xr.get('dna_name')} (matched to "
                    f"{xr.get('gedcom_name')}) is within expected range "
                    f"{check.get('expected_range')} for {check.get('claimed', relationship)}"
                ),
                "source": record_id,
            })
            trace.append(
                f"relationship_hypothesizer: DNA SUPPORTS {hyp.get('hypothesis_id')} "
                f"({cm_value} cM consistent with {relationship})"
            )
        else:
            evidence_chain.append({
                "claim": (
                    f"DNA evidence inconsistent with {relationship}: "
                    f"{cm_value} cM with {xr.get('dna_name')} is "
                    f"{check.get('deviation', 'outside expected range')}"
                ),
                "source": record_id,
            })
            trace.append(
                f"relationship_hypothesizer: DNA CONTRADICTS {hyp.get('hypothesis_id')} "
                f"({cm_value} cM inconsistent with {relationship})"
            )
        total_added += 1

    if total_added:
        trace.append(
            f"relationship_hypothesizer: appended {total_added} DNA "
            f"corroboration item(s) to evidence chains"
        )


def _relationship_to_wikidata_field(relationship: str) -> Optional[str]:
    """Map a hypothesis relationship label to the Wikidata data field."""
    rel = relationship.lower().strip()
    if "father" in rel:
        return "father"
    if "mother" in rel:
        return "mother"
    if "spouse" in rel or "wife" in rel or "husband" in rel:
        return "spouse"
    return None


def _check_corroboration(
    ext_data: dict,
    source_type: str,
    related_name: str,
    role_field: Optional[str],
    relationship: str,
) -> Optional[str]:
    """Check if an external record corroborates the proposed relationship.

    Returns a claim string if corroborating, None otherwise.
    """
    if source_type in ("wikidata", "wikitree") and role_field:
        return _check_structured_source_corroboration(
            ext_data, related_name, role_field, relationship, source_type
        )
    if source_type == "findagrave":
        return _check_findagrave_corroboration(
            ext_data, related_name, relationship
        )
    return None


def _check_structured_source_corroboration(
    ext_data: dict,
    related_name: str,
    role_field: str,
    relationship: str,
    source_type: str,
) -> Optional[str]:
    """Check a structured external record's family fields against the related
    person's name. Works for any source with father/mother/spouse label fields
    (Wikidata, WikiTree).
    """
    source_value = ext_data.get(role_field)
    if not source_value or not related_name:
        return None

    score = name_match_score(related_name, source_value)
    if score >= _CORROBORATION_NAME_THRESHOLD:
        source_label = source_type.capitalize()
        source_name = ext_data.get("name") or source_label
        return (
            f"Independent source ({source_label}, {source_name}) confirms "
            f"{relationship}: '{source_value}' matches GEDCOM name "
            f"'{related_name}' (similarity {score:.2f})"
        )
    return None


def _check_findagrave_corroboration(
    ext_data: dict,
    related_name: str,
    relationship: str,
) -> Optional[str]:
    """Check FindAGrave memorial name + dates against the related person.

    FindAGrave records don't carry family relationship fields, so we can
    only corroborate that the related person EXISTS as an independent
    memorial record (name + date match). This is weaker than Wikidata's
    explicit family links but still constitutes independent documentary
    evidence of the person's existence.
    """
    fg_name = ext_data.get("name")
    if not fg_name or not related_name:
        return None

    score = name_match_score(related_name, fg_name)
    if score >= _CORROBORATION_NAME_THRESHOLD:
        fg_birth = ext_data.get("birth_date") or "unknown"
        fg_death = ext_data.get("death_date") or "unknown"
        return (
            f"Independent memorial record (FindAGrave) confirms existence of "
            f"'{fg_name}' (b.{fg_birth}, d.{fg_death}), matching "
            f"'{related_name}' (similarity {score:.2f})"
        )
    return None
