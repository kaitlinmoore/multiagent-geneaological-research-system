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
from typing import Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from agents.hypothesis_schema import make_hypothesis
from state import GenealogyState
from tools.date_utils import get_year, normalize_gedcom_date
from tools.geo_utils import place_distance_km


llm = ChatAnthropic(model="claude-sonnet-4-6", max_tokens=2048)


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
    trace = list(state.get("trace_log") or [])
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
