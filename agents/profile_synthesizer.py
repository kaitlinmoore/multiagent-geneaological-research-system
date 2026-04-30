"""Profile Synthesizer — consolidates retrieved records into cited person profiles.

Role: consolidate records into sourced person profiles. Every fact must
cite a source. Gaps are flagged explicitly.

Pipeline:
    1. Find all "subject" candidates in retrieved_records (Record Scout may
       surface multiple, per its retrieve-without-interpreting contract).
    2. DETERMINISTIC disambiguation: score each candidate against the query
       criteria (fuzzy name + birth-year match + location tokens). Record the
       decision for every candidate with explicit reasons.
    3. LLM synthesis: given the selected subject's records, produce a cited
       facts list and an explicit gaps list. LLM must cite source record_ids
       for every fact; citations are validated against actual retrieved_records.
    4. Build family references (name + record_id) for the Hypothesizer to use.

CRITICAL CRITIC-ISOLATION INVARIANT:
    The Synthesizer's disambiguation reasoning ("selected JFK because birth
    year 1917 matches query") IS part of the evidence chain and MUST be
    visible to the Critic. It is stored under profile["disambiguation"] and
    every excluded candidate's reason is recorded too.

    This is distinct from the Hypothesizer's inferential reasoning, which
    must NEVER be visible to the Critic. The Synthesizer does not generate
    hypotheses — it resolves identity and consolidates records.

Profile shape:
    {
        "profile_id":         "profile:@I0@",
        "subject_record_id":  "gedcom:@I0@",
        "subject_name":       "John Fitzgerald Kennedy",
        "disambiguation": {
            "query":               "<original question>",
            "query_criteria":      {...target_person dict...},
            "candidates_considered": [
                {"record_id", "name", "status": "SELECTED"|"excluded",
                 "score", "reasons": [...]}
            ]
        },
        "facts": [
            {"field": "birth_date", "value": "29 MAY 1917", "sources": ["gedcom:@I0@"]}
        ],
        "family": {
            "father":    {"name", "record_id"} | None,
            "mother":    {"name", "record_id"} | None,
            "spouses":   [{"name", "record_id"}, ...],
            "children":  [{"name", "record_id"}, ...]
        },
        "gaps": ["no cross-referenced sources beyond GEDCOM", ...]
    }
"""

from __future__ import annotations

import json
from typing import Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from state import GenealogyState
from tools.date_utils import get_year
from tools.fuzzy_match import name_match_score


llm = ChatAnthropic(model="claude-sonnet-4-6", max_tokens=2048)


# Scoring weights for deterministic disambiguation.
_NAME_WEIGHT = 1.0
_YEAR_EXACT_BONUS = 1.0
_YEAR_NEAR_BONUS = 0.5      # within 2 years
_YEAR_PENALTY = -0.5        # > 2 years off
_LOCATION_MATCH_BONUS = 0.5


_PROFILE_PROMPT = """You are a genealogy Profile Synthesizer. Your ONLY job is
to consolidate records into a cited facts list and identify gaps. You do NOT
interpret, speculate, or hypothesize.

Given a subject's records (the subject plus immediate family), return ONE JSON
object with:
  "facts": list of {"field": str, "value": str, "sources": list[str]}
  "gaps":  list of strings naming missing or problematic data

Rules for FACTS:
  - Every fact MUST cite at least one source record_id from the input records.
  - Use record_id strings exactly as given (e.g. "gedcom:@I0@").
  - Only include facts about the SUBJECT, not their relatives. Relatives appear
    elsewhere via family references — the facts list represents one person.
  - Include ONLY biographical facts: name, first_name, surname, sex, birth_date,
    birth_place, death_date, death_place, occupation, religion, burial, and
    similar person-level attributes.
  - DO NOT include GEDCOM structural pointers or identifiers (father_id,
    mother_id, spouse_id, spouse_ids, child_id, children_ids, famc, fams,
    family_as_child, family_as_spouse, id, etc.). These are record-linking
    metadata, not biographical facts.
  - Do not fill blanks. Do not paraphrase. Values come verbatim from records.

Rules for GAPS:
  - Flag gaps EXPLICITLY: missing birth date, missing parents, conflicting
    dates, ambiguous sources, missing corroboration, etc.
  - Do NOT propose relationships, hypotheses, or explanations for the gaps.

Return ONLY valid JSON. No prose, no markdown fences, no commentary.
"""

# Fields the LLM should not emit as facts (defense-in-depth against the prompt).
_STRUCTURAL_FIELD_BLOCKLIST = {
    "id",
    "father_id",
    "mother_id",
    "spouse_id",
    "spouse_ids",
    "child_id",
    "children_id",
    "children_ids",
    "famc",
    "fams",
    "family_as_child",
    "family_as_spouse",
    "record_id",
}


def profile_synthesizer_node(state: GenealogyState) -> dict:
    trace: list[str] = []
    trace.append("profile_synthesizer: enter")

    records = state.get("retrieved_records") or []
    subject_candidates = [
        r for r in records if r.get("relation_to_target") == "subject"
    ]

    if not subject_candidates:
        trace.append("profile_synthesizer: no subject candidates in retrieved_records")
        trace.append("profile_synthesizer: exit")
        return {
            "profiles": [],
            "status": "running",
            "trace_log": trace,
        }

    # 1. Deterministic disambiguation with explicit reasons for every candidate.
    decisions = _disambiguate(subject_candidates, state["target_person"])
    selected_decision = decisions[0]
    selected_record = next(
        r for r in subject_candidates
        if r["record_id"] == selected_decision["record_id"]
    )
    trace.append(
        f"profile_synthesizer: disambiguated {len(subject_candidates)} candidates "
        f"-> selected {selected_record['data']['name']} "
        f"(score {selected_decision['score']})"
    )
    for d in decisions[1:]:
        trace.append(
            f"profile_synthesizer: excluded {d['name']} "
            f"({d['record_id']}, score {d['score']})"
        )

    # 2. LLM consolidates facts with citations; gather gaps.
    relevant_records = _gather_relevant_records(selected_record["data"], records)
    facts, gaps = _synthesize_facts(
        selected_record=selected_record,
        relevant_records=relevant_records,
        trace=trace,
    )

    # 3. Build family references from the person dict + record lookup.
    family = _build_family_references(selected_record["data"], records)

    profile = {
        "profile_id": f"profile:{selected_record['data']['id']}",
        "subject_record_id": selected_record["record_id"],
        "subject_name": selected_record["data"].get("name"),
        "disambiguation": {
            "query": state["query"],
            "query_criteria": state["target_person"],
            "candidates_considered": decisions,
        },
        "facts": facts,
        "family": family,
        "gaps": gaps,
    }

    trace.append(
        f"profile_synthesizer: built profile with {len(facts)} cited facts, "
        f"{len(gaps)} gaps"
    )
    trace.append("profile_synthesizer: exit")

    return {
        "profiles": [profile],
        "status": "running",
        "trace_log": trace,
    }


# ---------------------------------------------------------------------------
# Deterministic disambiguation
# ---------------------------------------------------------------------------


def _disambiguate(
    subject_candidates: list[dict],
    target_person: dict,
) -> list[dict]:
    """Score each candidate against query criteria; return decisions sorted
    best-first with exactly one marked SELECTED and the rest excluded.
    """
    target_name = target_person.get("name", "") if isinstance(target_person, dict) else ""
    target_birth_year = _parse_year(
        target_person.get("approx_birth") or target_person.get("birth_year")
    )
    target_location = (
        target_person.get("location") or ""
        if isinstance(target_person, dict)
        else ""
    ).lower()

    decisions: list[dict] = []
    for candidate in subject_candidates:
        person = candidate["data"]
        reasons: list[str] = []
        score = 0.0

        # Factor 1: fuzzy name similarity.
        name_score = name_match_score(target_name, person.get("name") or "")
        score += _NAME_WEIGHT * name_score
        reasons.append(f"name similarity {round(name_score, 3)}")

        # Factor 2: birth year match.
        candidate_year = get_year(person.get("birth_date"))
        if target_birth_year is not None and candidate_year is not None:
            diff = abs(target_birth_year - candidate_year)
            if diff == 0:
                score += _YEAR_EXACT_BONUS
                reasons.append(
                    f"exact birth year match ({candidate_year})"
                )
            elif diff <= 2:
                score += _YEAR_NEAR_BONUS
                reasons.append(
                    f"birth year within 2 years (target {target_birth_year}, "
                    f"candidate {candidate_year})"
                )
            else:
                score += _YEAR_PENALTY
                reasons.append(
                    f"birth year mismatch (target {target_birth_year}, "
                    f"candidate {candidate_year}, diff {diff}y)"
                )
        elif target_birth_year is not None:
            reasons.append(
                f"no birth year on candidate record; target is {target_birth_year}"
            )
        elif candidate_year is not None:
            reasons.append(
                f"candidate birth year is {candidate_year}; target has none"
            )

        # Factor 3: birth place token overlap.
        candidate_place = (person.get("birth_place") or "").lower()
        if target_location and candidate_place:
            target_tokens = _tokenize_place(target_location)
            candidate_tokens = _tokenize_place(candidate_place)
            shared = target_tokens & candidate_tokens
            if shared:
                score += _LOCATION_MATCH_BONUS
                reasons.append(
                    f"birth place tokens match: {sorted(shared)}"
                )
            else:
                reasons.append(
                    f"birth place mismatch (target '{target_location}', "
                    f"candidate '{candidate_place}')"
                )
        elif target_location:
            reasons.append(
                f"no birth place on candidate record; target is '{target_location}'"
            )

        decisions.append({
            "record_id": candidate["record_id"],
            "name": person.get("name"),
            "score": round(score, 3),
            "reasons": reasons,
        })

    decisions.sort(key=lambda d: d["score"], reverse=True)

    # Label exactly one as SELECTED; the rest as excluded.
    if decisions:
        decisions[0]["status"] = "SELECTED"
        for d in decisions[1:]:
            d["status"] = "excluded"

    return decisions


def _parse_year(value) -> Optional[int]:
    """Accept year as int, numeric string, or GEDCOM-style date; return int."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    # Try direct int parse first, else use get_year for GEDCOM forms.
    try:
        return int(text)
    except ValueError:
        return get_year(text)


def _tokenize_place(place: str) -> set[str]:
    """Split a place string into normalized tokens for overlap matching."""
    return {
        token.strip().lower()
        for token in place.replace(",", " ").replace(".", " ").split()
        if len(token.strip()) >= 2
    }


# ---------------------------------------------------------------------------
# LLM-driven fact synthesis
# ---------------------------------------------------------------------------


def _gather_relevant_records(
    selected_person: dict, all_records: list[dict]
) -> list[dict]:
    """Return the records that cover the selected subject and their immediate
    family, filtering out records for other candidate subjects.
    """
    relevant_ids: set[str] = {selected_person["id"]}
    if selected_person.get("father_id"):
        relevant_ids.add(selected_person["father_id"])
    if selected_person.get("mother_id"):
        relevant_ids.add(selected_person["mother_id"])
    relevant_ids.update(selected_person.get("spouse_ids") or [])
    relevant_ids.update(selected_person.get("children_ids") or [])

    return [
        r for r in all_records
        if r.get("data", {}).get("id") in relevant_ids
    ]


def _synthesize_facts(
    selected_record: dict,
    relevant_records: list[dict],
    trace: list[str],
) -> tuple[list[dict], list[str]]:
    """Ask the LLM to produce cited facts + gaps. Fallback on failure."""
    llm_payload = [
        {
            "record_id": r["record_id"],
            "relation_to_target": r.get("relation_to_target"),
            "data": r["data"],
        }
        for r in relevant_records
    ]
    prompt_body = (
        f"Subject record_id: {selected_record['record_id']}\n"
        f"Subject name: {selected_record['data'].get('name')}\n\n"
        f"Records:\n{json.dumps(llm_payload, default=str, indent=2)}\n\n"
        "Return the JSON object now:"
    )

    try:
        response = llm.invoke([
            SystemMessage(content=_PROFILE_PROMPT),
            HumanMessage(content=prompt_body),
        ])
        text = _strip_markdown_fences(response.content.strip())
        parsed = json.loads(text)
        raw_facts = parsed.get("facts") or []
        gaps = parsed.get("gaps") or []

        # Defense in depth: strip structural pointers even if the LLM emits them.
        facts: list[dict] = []
        dropped_structural = 0
        for fact in raw_facts:
            field = (fact.get("field") or "").strip().lower()
            if field in _STRUCTURAL_FIELD_BLOCKLIST:
                dropped_structural += 1
                continue
            facts.append(fact)
        if dropped_structural:
            trace.append(
                f"profile_synthesizer: dropped {dropped_structural} structural "
                f"pointer fact(s) from LLM output"
            )

        valid_source_ids = {r["record_id"] for r in relevant_records}
        for fact in facts:
            for src in fact.get("sources") or []:
                if src not in valid_source_ids:
                    trace.append(
                        f"profile_synthesizer: WARNING fact cites unknown "
                        f"source {src} (field={fact.get('field')})"
                    )
        trace.append(
            f"profile_synthesizer: LLM synthesis produced {len(facts)} facts, "
            f"{len(gaps)} gaps"
        )
        return facts, gaps
    except Exception as exc:
        trace.append(
            f"profile_synthesizer: LLM synthesis failed "
            f"({type(exc).__name__}: {exc}), using deterministic fallback"
        )
        return _deterministic_fact_fallback(selected_record)


def _deterministic_fact_fallback(selected_record: dict) -> tuple[list[dict], list[str]]:
    """Last-ditch: extract basic facts directly from the person dict."""
    person = selected_record["data"]
    source = selected_record["record_id"]

    field_map = [
        ("name", "name"),
        ("sex", "sex"),
        ("birth_date", "birth_date"),
        ("birth_place", "birth_place"),
        ("death_date", "death_date"),
        ("death_place", "death_place"),
    ]

    facts: list[dict] = []
    gaps: list[str] = []
    for field, key in field_map:
        value = person.get(key)
        if value:
            facts.append({"field": field, "value": str(value), "sources": [source]})
        else:
            gaps.append(f"missing {field}")
    return facts, gaps


def _strip_markdown_fences(text: str) -> str:
    if text.startswith("```"):
        body = text.strip("`")
        if body.lower().startswith("json"):
            body = body[4:]
        return body.strip()
    return text


# ---------------------------------------------------------------------------
# Family references
# ---------------------------------------------------------------------------


def _build_family_references(
    selected_person: dict, all_records: list[dict]
) -> dict:
    """Look up name + record_id for each known family member."""
    records_by_person_id = {
        r["data"]["id"]: r for r in all_records if r.get("data", {}).get("id")
    }

    def ref_for(person_id: Optional[str]) -> Optional[dict]:
        if not person_id:
            return None
        record = records_by_person_id.get(person_id)
        if not record:
            return None
        return {
            "name": record["data"].get("name"),
            "record_id": record["record_id"],
        }

    spouses = [
        ref_for(sid) for sid in selected_person.get("spouse_ids") or []
    ]
    children = [
        ref_for(cid) for cid in selected_person.get("children_ids") or []
    ]

    return {
        "father": ref_for(selected_person.get("father_id")),
        "mother": ref_for(selected_person.get("mother_id")),
        "spouses": [s for s in spouses if s],
        "children": [c for c in children if c],
    }
