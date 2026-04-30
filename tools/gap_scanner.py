"""Gap scanner — discovers missing relationships in a parsed GEDCOM.

Two public functions:

    find_research_candidates(gedcom_persons, min_data_fields=3)
        Scans all persons and returns those missing a parent link who have
        enough data to make a research query viable.

    find_parent_candidates(gedcom_persons, child, missing_role)
        Searches the tree for plausible parents of a specific child, scored
        by surname similarity, age plausibility, and geographic proximity.

Design contract:
    - Pure functions over parser-output dicts. No I/O, no LLM calls, no
      network (geocoding is attempted but swallowed on failure).
    - Scoring components are returned visibly so the caller (or a human)
      can inspect why a candidate ranked where it did.
    - This module feeds the Record Scout's gap_mode, which populates
      retrieved_records in the same format as query mode so downstream
      agents (Synthesizer, Hypothesizer, Critic) work unchanged.
"""

from __future__ import annotations

from typing import Optional

from tools.date_utils import get_year, normalize_gedcom_date
from tools.fuzzy_match import name_match_score
from tools.geo_utils import geocode_place, haversine_km


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Fields that count toward "enough data to investigate".
_DATA_FIELDS = (
    "name",
    "birth_date",
    "birth_place",
    "death_date",
    "death_place",
    "spouse_ids",
    "children_ids",
)

# Parent-child age window (years). Outside this range, a candidate is
# penalized or excluded.
_MIN_PARENT_AGE_DIFF = 15
_MAX_PARENT_AGE_DIFF = 50

# Scoring weights for find_parent_candidates composite score.
_W_SURNAME = 0.35
_W_AGE = 0.30
_W_GEO = 0.20
_W_FAMILY = 0.15


# ---------------------------------------------------------------------------
# find_research_candidates
# ---------------------------------------------------------------------------


def find_research_candidates(
    gedcom_persons: list[dict],
    min_data_fields: int = 3,
) -> list[dict]:
    """Return persons missing a parent link who have enough data to research.

    Each result:
        {
            "person":        the person dict from the parser,
            "missing_role":  "father" | "mother" | "both",
            "data_fields":   int — count of populated fields from _DATA_FIELDS,
            "query":         auto-generated research question string,
        }

    Sorted by data_fields descending (richest records first — most likely
    to produce a useful pipeline run).
    """
    candidates: list[dict] = []
    for person in gedcom_persons:
        has_father = bool(person.get("father_id"))
        has_mother = bool(person.get("mother_id"))
        if has_father and has_mother:
            continue  # no gap

        filled = _count_data_fields(person)
        if filled < min_data_fields:
            continue  # not enough data to investigate

        if not has_father and not has_mother:
            missing_role = "both"
        elif not has_father:
            missing_role = "father"
        else:
            missing_role = "mother"

        query = _generate_query(person, missing_role)

        candidates.append({
            "person": person,
            "missing_role": missing_role,
            "data_fields": filled,
            "query": query,
        })

    candidates.sort(key=lambda c: c["data_fields"], reverse=True)
    return candidates


def _count_data_fields(person: dict) -> int:
    count = 0
    for field in _DATA_FIELDS:
        value = person.get(field)
        if value is None:
            continue
        if isinstance(value, list) and len(value) == 0:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        count += 1
    return count


def _generate_query(person: dict, missing_role: str) -> str:
    name = person.get("name") or "(unnamed)"
    birth = person.get("birth_date") or ""
    place = person.get("birth_place") or ""

    descriptor = f"{name}"
    if birth:
        descriptor += f", born {birth}"
    if place:
        descriptor += f" in {place}"

    if missing_role == "both":
        return f"Who are the parents of {descriptor}?"
    return f"Who is the {missing_role} of {descriptor}?"


# ---------------------------------------------------------------------------
# find_parent_candidates
# ---------------------------------------------------------------------------


def find_parent_candidates(
    gedcom_persons: list[dict],
    child: dict,
    missing_role: str,
    max_results: int = 10,
    use_geocoding: bool = False,
) -> list[dict]:
    """Search the tree for plausible parents of ``child``.

    Args:
        gedcom_persons: full parsed person list.
        child: the person dict missing a parent.
        missing_role: "father" or "mother". Determines the expected sex
                      of the candidate and which surname heuristic to apply.
        max_results: cap on returned candidates.
        use_geocoding: if True, use live Nominatim geocoding for geographic
                       proximity scoring (accurate but slow — 1 req/sec rate
                       limit makes this impractical for trees >1000 persons).
                       If False (default), use fast token-overlap comparison
                       on birthplace strings instead.

    Each result:
        {
            "person":            candidate person dict,
            "composite_score":   float 0..1,
            "scoring": {
                "surname_score":  float 0..1,
                "age_score":      float 0..1,
                "geo_score":      float 0..1,
                "family_score":   float 0..1,
            },
            "age_diff":          int | None (candidate birth year - child birth year),
            "distance_km":       float | None,
        }

    Sorted by composite_score descending.
    """
    child_id = child.get("id")
    child_surname = (child.get("surname") or "").strip()
    child_birth_year = get_year(child.get("birth_date"))
    child_birth_place = (child.get("birth_place") or "").strip()
    other_parent_id = (
        child.get("mother_id") if missing_role == "father"
        else child.get("father_id")
    )
    expected_sex = "M" if missing_role == "father" else "F"

    # Pre-geocode child's birth place once (may be None). Only if geocoding enabled.
    child_coords = (
        _safe_geocode(child_birth_place)
        if use_geocoding and child_birth_place
        else None
    )

    scored: list[dict] = []
    for person in gedcom_persons:
        pid = person.get("id")
        # Exclude the child, the other parent, and persons already linked
        # as the child's parent in the opposite role.
        if pid == child_id or pid == other_parent_id:
            continue

        # Sex filter: if the candidate has a recorded sex, it must match.
        candidate_sex = person.get("sex")
        if candidate_sex and candidate_sex != expected_sex:
            continue

        result = _score_candidate(
            candidate=person,
            child_surname=child_surname,
            child_birth_year=child_birth_year,
            child_birth_place=child_birth_place,
            child_coords=child_coords,
            missing_role=missing_role,
            use_geocoding=use_geocoding,
        )
        if result["composite_score"] > 0.0:
            scored.append(result)

    scored.sort(key=lambda r: r["composite_score"], reverse=True)
    return scored[:max_results]


def _score_candidate(
    candidate: dict,
    child_surname: str,
    child_birth_year: Optional[int],
    child_birth_place: str,
    child_coords: Optional[tuple[float, float]],
    missing_role: str,
    use_geocoding: bool = False,
) -> dict:
    """Score one candidate on four axes; return the result dict."""
    scoring: dict[str, float] = {}

    # --- Surname similarity ---
    cand_surname = (candidate.get("surname") or "").strip()
    if child_surname and cand_surname:
        if missing_role == "father":
            # Patrilineal: father's surname should match child's.
            scoring["surname_score"] = name_match_score(
                child_surname, cand_surname
            )
        else:
            # Mother: maiden name usually differs. Give a small base score
            # if any name similarity exists; full match is a bonus (could
            # indicate endogamy or married-name recording).
            raw = name_match_score(child_surname, cand_surname)
            scoring["surname_score"] = raw * 0.5  # dampen — mismatch is normal
    else:
        scoring["surname_score"] = 0.0

    # --- Age plausibility ---
    cand_birth_year = get_year(candidate.get("birth_date"))
    age_diff: Optional[int] = None
    if child_birth_year is not None and cand_birth_year is not None:
        age_diff = child_birth_year - cand_birth_year
        if _MIN_PARENT_AGE_DIFF <= age_diff <= _MAX_PARENT_AGE_DIFF:
            # Sweet spot: linearly scale within the window, peak at ~28y.
            peak = 28
            deviation = abs(age_diff - peak)
            max_deviation = max(peak - _MIN_PARENT_AGE_DIFF,
                                _MAX_PARENT_AGE_DIFF - peak)
            scoring["age_score"] = max(0.0, 1.0 - deviation / max_deviation)
        elif 0 < age_diff < _MIN_PARENT_AGE_DIFF:
            scoring["age_score"] = 0.1  # too young but not impossible
        elif age_diff > _MAX_PARENT_AGE_DIFF:
            scoring["age_score"] = 0.05  # implausibly old
        else:
            scoring["age_score"] = 0.0  # candidate younger than child
    else:
        scoring["age_score"] = 0.2  # unknown — small non-zero prior

    # --- Geographic proximity ---
    cand_birth_place = (candidate.get("birth_place") or "").strip()
    distance_km: Optional[float] = None
    if child_birth_place and cand_birth_place:
        if child_birth_place.lower() == cand_birth_place.lower():
            scoring["geo_score"] = 1.0
        elif use_geocoding:
            # Accurate but slow — live Nominatim geocoding + haversine.
            cand_coords = _safe_geocode(cand_birth_place)
            if child_coords and cand_coords:
                distance_km = haversine_km(
                    child_coords[0], child_coords[1],
                    cand_coords[0], cand_coords[1],
                )
                if distance_km < 50:
                    scoring["geo_score"] = 1.0
                elif distance_km < 200:
                    scoring["geo_score"] = 0.7
                elif distance_km < 500:
                    scoring["geo_score"] = 0.4
                elif distance_km < 1500:
                    scoring["geo_score"] = 0.2
                else:
                    scoring["geo_score"] = 0.05
            else:
                scoring["geo_score"] = 0.1
        else:
            # Fast fallback — token overlap on place strings.
            scoring["geo_score"] = _place_token_overlap(
                child_birth_place, cand_birth_place
            )
    else:
        scoring["geo_score"] = 0.1  # missing place data

    # --- Family unit bonus ---
    # If the candidate already has children in a compatible time range,
    # they're a known parent — stronger prior.
    children_ids = candidate.get("children_ids") or []
    fams = candidate.get("fams") or []
    if children_ids or fams:
        scoring["family_score"] = 0.6
        # Boost if the candidate has a spouse (complete family unit).
        if candidate.get("spouse_ids"):
            scoring["family_score"] = 0.8
    else:
        scoring["family_score"] = 0.2  # no known family

    composite = (
        _W_SURNAME * scoring["surname_score"]
        + _W_AGE * scoring["age_score"]
        + _W_GEO * scoring["geo_score"]
        + _W_FAMILY * scoring["family_score"]
    )

    return {
        "person": candidate,
        "composite_score": round(composite, 4),
        "scoring": {k: round(v, 3) for k, v in scoring.items()},
        "age_diff": age_diff,
        "distance_km": round(distance_km) if distance_km is not None else None,
    }


def _safe_geocode(place: str) -> Optional[tuple[float, float]]:
    """Geocode a place string, returning None on any failure."""
    if not place:
        return None
    try:
        return geocode_place(place)
    except Exception:
        return None


def _place_token_overlap(place_a: str, place_b: str) -> float:
    """Fast geo-similarity via normalized token overlap (Jaccard on place tokens).

    Examples:
        "Philadelphia, Pennsylvania, USA" vs "Philadelphia, PA" → shares
        "philadelphia" → overlap = 1/4 = 0.25 (low but non-zero signal).

        "Ireland" vs "Ireland" → exact match handled upstream (score 1.0).

        "Philadelphia, Pennsylvania, USA" vs "Pennsylvania, USA" → shares
        "pennsylvania", "usa" → overlap = 2/4 = 0.5.
    """
    tokens_a = _normalize_place_tokens(place_a)
    tokens_b = _normalize_place_tokens(place_b)
    if not tokens_a or not tokens_b:
        return 0.1  # can't compare
    shared = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(shared) / len(union) if union else 0.1


def _normalize_place_tokens(place: str) -> set[str]:
    """Split a place string into lowercase tokens, dropping short noise."""
    return {
        tok.lower()
        for tok in place.replace(",", " ").replace(".", " ").split()
        if len(tok.strip()) >= 2
    }
