"""Wikidata SPARQL search — retrieves structured person records for corroboration.

Queries the Wikidata SPARQL endpoint for humans matching a name and
approximate birth year. Returns structured records including family
relationship labels (father, mother, spouse) that downstream agents can
cross-reference against GEDCOM family pointers.

No API key required. Wikidata requires a descriptive User-Agent header
identifying the project.

Design contract:
    - Returns an empty list on ANY failure (network, SPARQL error, no results).
    - Rate-limited to 1 request per second.
    - Capped at 5 results per search.
    - Each result carries ``record_id: "wikidata:{Q_ID}"`` for citation.
    - Family relationship fields (father, mother, spouse) are included as
      string labels (not Wikidata IDs) so the Critic can compare them against
      GEDCOM names directly.

Usage:
    results = search_wikidata("John", "Kennedy", birth_year=1917)
"""

from __future__ import annotations

import re
import time
from typing import Optional

import requests


_USER_AGENT = (
    "MultiAgentGenealogyResearch/0.1 "
    "(CMU Heinz College course project; genealogical research system; "
    "Python/requests) Contact: 6ingeraffe@gmail.com"
)
_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
_TIMEOUT_SECONDS = 20
_MAX_RESULTS = 5
_BIRTH_YEAR_TOLERANCE = 5  # ±5 years for approximate matching
_MIN_REQUEST_INTERVAL = 1.0

_last_request_time: float = 0.0


def search_wikidata(
    first_name: str,
    last_name: str,
    birth_year: Optional[int] = None,
    death_year: Optional[int] = None,
    birth_place: Optional[str] = None,
) -> list[dict]:
    """Search Wikidata for person records matching the given criteria.

    Returns up to ``_MAX_RESULTS`` dicts, each with:
        {
            "record_id":    "wikidata:Q{id}",
            "source":       "wikidata",
            "source_type":  "wikidata",
            "record_type":  "person",
            "data": {
                "name":           str,
                "birth_date":     str | None,
                "death_date":     str | None,
                "birth_place":    str | None,
                "father":         str | None,   # label, not QID
                "mother":         str | None,
                "spouse":         str | None,
                "wikidata_id":    str,           # e.g. "Q9696"
                "wikidata_url":   str,
            },
        }

    Returns [] on any failure.
    """
    global _last_request_time

    full_name = f"{first_name} {last_name}".strip()
    if not full_name:
        return []

    sparql = _build_sparql_query(full_name, birth_year)

    # Rate limit.
    elapsed = time.time() - _last_request_time
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)

    try:
        response = requests.get(
            _SPARQL_ENDPOINT,
            params={"query": sparql},
            headers={
                "Accept": "application/sparql-results+json",
                "User-Agent": _USER_AGENT,
            },
            timeout=_TIMEOUT_SECONDS,
        )
        _last_request_time = time.time()
        response.raise_for_status()
    except Exception:
        return []

    try:
        return _parse_sparql_results(response.json())
    except Exception:
        return []


# ---------------------------------------------------------------------------
# SPARQL query construction
# ---------------------------------------------------------------------------


def _build_sparql_query(full_name: str, birth_year: Optional[int]) -> str:
    """Build a SPARQL query searching for humans by name and optional birth year.

    Uses the Wikidata ``wikibase:mwapi`` EntitySearch service for fuzzy
    name matching (handles aliases, alternate spellings, middle initials)
    then filters to instances of human (Q5) and optional birth year range.
    """
    safe_name = full_name.replace("\\", "\\\\").replace('"', '\\"')

    birth_filter = ""
    if birth_year:
        low = birth_year - _BIRTH_YEAR_TOLERANCE
        high = birth_year + _BIRTH_YEAR_TOLERANCE
        birth_filter = f"""
  FILTER(YEAR(?birthDate) >= {low} && YEAR(?birthDate) <= {high})"""

    return f"""
SELECT DISTINCT ?person ?personLabel ?birthDate ?deathDate
       ?birthPlaceLabel ?fatherLabel ?motherLabel ?spouseLabel
WHERE {{
  SERVICE wikibase:mwapi {{
    bd:serviceParam wikibase:endpoint "www.wikidata.org" ;
                    wikibase:api "EntitySearch" ;
                    mwapi:search "{safe_name}" ;
                    mwapi:language "en" .
    ?person wikibase:apiOutputItem mwapi:item .
  }}

  ?person wdt:P31 wd:Q5 .              # instance of human

  OPTIONAL {{ ?person wdt:P569 ?birthDate . }}
  OPTIONAL {{ ?person wdt:P570 ?deathDate . }}
  OPTIONAL {{ ?person wdt:P19 ?birthPlace . }}
  OPTIONAL {{ ?person wdt:P22 ?father . }}
  OPTIONAL {{ ?person wdt:P25 ?mother . }}
  OPTIONAL {{ ?person wdt:P26 ?spouse . }}
  {birth_filter}

  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
}}
LIMIT {_MAX_RESULTS}
"""


# ---------------------------------------------------------------------------
# Result parsing
# ---------------------------------------------------------------------------


def _parse_sparql_results(json_response: dict) -> list[dict]:
    """Parse Wikidata SPARQL JSON results into the standard record format."""
    bindings = json_response.get("results", {}).get("bindings", [])
    results: list[dict] = []
    seen_ids: set[str] = set()

    for row in bindings:
        person_uri = _get_value(row, "person")
        if not person_uri:
            continue
        qid = _extract_qid(person_uri)
        if not qid or qid in seen_ids:
            continue
        seen_ids.add(qid)

        results.append({
            "record_id": f"wikidata:{qid}",
            "source": "wikidata",
            "source_type": "wikidata",
            "record_type": "person",
            "data": {
                "name": _get_value(row, "personLabel"),
                "birth_date": _format_date(_get_value(row, "birthDate")),
                "death_date": _format_date(_get_value(row, "deathDate")),
                "birth_place": _get_value(row, "birthPlaceLabel"),
                "father": _get_value(row, "fatherLabel"),
                "mother": _get_value(row, "motherLabel"),
                "spouse": _get_value(row, "spouseLabel"),
                "wikidata_id": qid,
                "wikidata_url": f"https://www.wikidata.org/wiki/{qid}",
            },
        })

        if len(results) >= _MAX_RESULTS:
            break

    return results


def _get_value(row: dict, field: str) -> Optional[str]:
    """Extract a string value from a SPARQL binding row, or None."""
    binding = row.get(field)
    if not binding:
        return None
    value = binding.get("value", "").strip()
    return value if value else None


def _extract_qid(uri: str) -> Optional[str]:
    """Extract 'Q12345' from 'http://www.wikidata.org/entity/Q12345'."""
    match = re.search(r"(Q\d+)$", uri)
    return match.group(1) if match else None


def _format_date(iso_date: Optional[str]) -> Optional[str]:
    """Convert an ISO date like '1917-05-29T00:00:00Z' to '29 MAY 1917'
    for consistency with GEDCOM date format. Falls back to the raw string
    or None.
    """
    if not iso_date:
        return None

    _MONTHS = [
        "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
        "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
    ]

    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", iso_date)
    if match:
        year, month, day = match.groups()
        month_idx = int(month) - 1
        if 0 <= month_idx < 12:
            day_int = int(day)
            if day_int > 0:
                return f"{day_int} {_MONTHS[month_idx]} {year}"
            return f"{_MONTHS[month_idx]} {year}"
    return iso_date
