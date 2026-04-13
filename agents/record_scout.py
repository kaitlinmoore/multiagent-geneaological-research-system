"""Record Scout — retrieves historical records for a target person.

Role (CLAUDE.md): "Searches for historical records. Retrieves but does NOT
interpret." The Scout's job is to find candidate records in the GEDCOM that
could be about the target person, and surface them as raw, cited records for
the Profile Synthesizer to consolidate.

Pipeline:
    1. Parse GEDCOM text into a list of person dicts (deterministic).
    2. Ask the LLM to extract structured search criteria from the natural-
       language query + target_person dict. This is a narrow retrieval task
       — NOT interpretation of records.
    3. Fuzzy-match every GEDCOM person against the criteria, surname-weighted.
    4. Expand the top matches into a flat list of cited record objects,
       including immediate family for context.

The LLM step is fallback-safe: if the API call fails or returns bad JSON,
the Scout falls back to direct matching on target_person["name"]. This keeps
the pipeline runnable even without network access.

Record shape (what the Profile Synthesizer will consume):
    {
        "record_id":          "gedcom:@I0@",          # for citation
        "source":             "gedcom",
        "record_type":        "individual",
        "relation_to_target": "subject" | "father" | "mother" | "spouse" | "child",
        "match_score":        0.95 | None,             # fuzzy-match score, subject only
        "data":               {...parser person dict...},
    }
"""

from __future__ import annotations

import json
from typing import Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from state import GenealogyState
from tools.fuzzy_match import name_match_score
from tools.gedcom_parser import parse_gedcom_text


llm = ChatAnthropic(model="claude-sonnet-4-6", max_tokens=1024)


# Fuzzy-match threshold — below this the candidate is discarded.
_MATCH_THRESHOLD = 0.70
# Cap on how many top candidates we expand into record bundles.
_MAX_CANDIDATES = 5


_SEARCH_CRITERIA_PROMPT = """You extract structured search criteria from genealogy queries.

Given a research question and a target person, return ONE JSON object with:
  "primary_name":        full name to match (string)
  "surname":             surname only (string, may be empty)
  "given_names":         given names only (string, may be empty)
  "alt_names":           list of alternate spellings, nicknames, or aliases (list of strings)
  "approx_birth_year":   integer year or null
  "approx_location":     city/region string or null

Return ONLY valid JSON. No prose, no markdown fences, no commentary.
"""


def record_scout_node(state: GenealogyState) -> dict:
    trace = list(state.get("trace_log") or [])
    trace.append("record_scout: enter")

    # 1. Parse GEDCOM (deterministic).
    gedcom_persons = parse_gedcom_text(state["gedcom_text"])
    trace.append(f"record_scout: parsed {len(gedcom_persons)} persons from GEDCOM")

    # 2. LLM extracts structured search criteria.
    criteria = _extract_search_criteria(
        state["query"], state["target_person"], trace
    )

    # 3. Fuzzy match against all persons.
    scored_candidates = _score_candidates(gedcom_persons, criteria)
    top_candidates = scored_candidates[:_MAX_CANDIDATES]
    trace.append(
        f"record_scout: {len(scored_candidates)} candidates above "
        f"threshold {_MATCH_THRESHOLD}, keeping top {len(top_candidates)}"
    )
    if top_candidates:
        trace.append(
            "record_scout: top match = "
            f"{top_candidates[0]['person']['name']} "
            f"(score {top_candidates[0]['score']})"
        )

    # 4. Expand to flat record list with citations and family context.
    person_by_id = {p["id"]: p for p in gedcom_persons}
    retrieved_records = _build_records(top_candidates, person_by_id)
    trace.append(
        f"record_scout: built {len(retrieved_records)} record objects "
        f"(including family context)"
    )
    trace.append("record_scout: exit")

    return {
        "gedcom_persons": gedcom_persons,
        "retrieved_records": retrieved_records,
        "status": "running",
        "trace_log": trace,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_search_criteria(
    query: str, target: dict, trace: list[str]
) -> dict:
    """Ask the LLM for structured search criteria. Falls back on failure."""
    fallback = {
        "primary_name": target.get("name", "") if isinstance(target, dict) else str(target),
        "surname": "",
        "given_names": "",
        "alt_names": [],
        "approx_birth_year": None,
        "approx_location": target.get("location") if isinstance(target, dict) else None,
    }

    try:
        messages = [
            SystemMessage(content=_SEARCH_CRITERIA_PROMPT),
            HumanMessage(
                content=(
                    f"Query: {query}\n"
                    f"Target: {json.dumps(target)}\n\n"
                    "Return the JSON object now:"
                )
            ),
        ]
        response = llm.invoke(messages)
        text = _strip_markdown_fences(response.content.strip())
        criteria = json.loads(text)
        trace.append(f"record_scout: LLM criteria = {criteria}")
        return criteria
    except Exception as exc:
        trace.append(
            f"record_scout: LLM criteria extraction failed "
            f"({type(exc).__name__}: {exc}), using fallback"
        )
        return fallback


def _strip_markdown_fences(text: str) -> str:
    """Handle LLM responses that wrap JSON in ```json fences despite instructions."""
    if text.startswith("```"):
        body = text.strip("`")
        if body.lower().startswith("json"):
            body = body[4:]
        return body.strip()
    return text


def _score_candidates(persons: list[dict], criteria: dict) -> list[dict]:
    """Fuzzy-score every person against criteria; return above-threshold sorted."""
    surname = (criteria.get("surname") or "").strip()
    given = (criteria.get("given_names") or "").strip()
    primary = (criteria.get("primary_name") or "").strip()
    alt_names = criteria.get("alt_names") or []

    scored: list[dict] = []
    for person in persons:
        score = _score_person(person, surname, given, primary, alt_names)
        if score >= _MATCH_THRESHOLD:
            scored.append({"person": person, "score": round(score, 3)})

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored


def _score_person(
    person: dict,
    surname: str,
    given: str,
    primary: str,
    alt_names: list[str],
) -> float:
    """Composite match score combining surname/given-name split and alt names."""
    scores: list[float] = []

    if surname and person.get("surname"):
        surname_score = name_match_score(surname, person["surname"])
        if given and person.get("first_name"):
            given_score = name_match_score(given, person["first_name"])
            scores.append(0.6 * surname_score + 0.4 * given_score)
        else:
            scores.append(surname_score)

    if primary and person.get("name"):
        scores.append(name_match_score(primary, person["name"]))

    for alt in alt_names:
        if alt and person.get("name"):
            scores.append(name_match_score(alt, person["name"]))

    return max(scores) if scores else 0.0


def _build_records(
    candidates: list[dict], person_by_id: dict[str, dict]
) -> list[dict]:
    """Flatten candidates + their immediate family into a cited record list."""
    records: list[dict] = []
    for candidate in candidates:
        person = candidate["person"]
        records.append(_make_record(person, "subject", candidate["score"]))

        for role, parent_id in (
            ("father", person.get("father_id")),
            ("mother", person.get("mother_id")),
        ):
            if parent_id and parent_id in person_by_id:
                records.append(_make_record(person_by_id[parent_id], role, None))

        for spouse_id in person.get("spouse_ids") or []:
            if spouse_id in person_by_id:
                records.append(_make_record(person_by_id[spouse_id], "spouse", None))

        for child_id in person.get("children_ids") or []:
            if child_id in person_by_id:
                records.append(_make_record(person_by_id[child_id], "child", None))

    # Deduplicate by record_id, preferring the first (richest) occurrence.
    seen: dict[str, dict] = {}
    for record in records:
        seen.setdefault(record["record_id"], record)
    return list(seen.values())


def _make_record(
    person: dict, relation: str, match_score: Optional[float]
) -> dict:
    return {
        "record_id": f"gedcom:{person['id']}",
        "source": "gedcom",
        "record_type": "individual",
        "relation_to_target": relation,
        "match_score": match_score,
        "data": person,
    }
