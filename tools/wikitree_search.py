"""WikiTree API search — retrieves person records with family relationships.

Uses WikiTree's public read API (no key required) to search for persons
and resolve their parent/spouse names. Returns records in the pipeline's
standard dict format with father, mother, and spouse name fields for
the Hypothesizer's corroboration step.

WikiTree stores women under maiden names (LastNameAtBirth), making it
complementary to Wikidata which often stores married names. This is
specifically valuable for resolving the maiden-name/married-name gap
that prevented Wikidata from corroborating maternal relationships.

Design contract:
    - Returns empty list on ANY failure.
    - Rate-limited to 1 request per second.
    - Capped at 5 search results.
    - Parent/spouse names are resolved via additional getPerson calls;
      a shared cache deduplicates across matches with shared parents.
    - Dates formatted to GEDCOM convention (DD MMM YYYY).

Usage:
    results = search_wikitree("John", "Kennedy", birth_year=1917)
"""

from __future__ import annotations

import re
import time
from typing import Optional

import requests


_API_URL = "https://api.wikitree.com/api.php"
_TIMEOUT_SECONDS = 15
_MAX_RESULTS = 5
_MIN_REQUEST_INTERVAL = 1.0

_last_request_time: float = 0.0

_MONTHS = [
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
]


def search_wikitree(
    first_name: str,
    last_name: str,
    birth_year: Optional[int] = None,
    death_year: Optional[int] = None,
) -> list[dict]:
    """Search WikiTree for persons matching the given criteria.

    Returns up to ``_MAX_RESULTS`` dicts, each with:
        {
            "record_id":    "wikitree:{WikiTree_ID}",
            "source":       "wikitree",
            "source_type":  "wikitree",
            "record_type":  "person",
            "data": {
                "name":         str,
                "birth_date":   str | None (GEDCOM format),
                "death_date":   str | None,
                "birth_place":  str | None,
                "death_place":  str | None,
                "father":       str | None (display name),
                "mother":       str | None (display name, MAIDEN name),
                "spouse":       str | None (display name),
                "wikitree_id":  str,
                "wikitree_url": str,
            },
        }

    Returns [] on any failure.
    """
    if not first_name or not last_name:
        return []

    try:
        matches = _search(first_name, last_name, birth_year, death_year)
    except Exception:
        return []

    if not matches:
        return []

    # Shared cache for parent/spouse name resolution.
    name_cache: dict = {}

    # Fetch spouses for the top match only (requires a separate getPerson).
    top_spouses: list[dict] = []
    top_id = matches[0].get("Name")
    if top_id:
        try:
            top_spouses = _fetch_spouses(top_id)
        except Exception:
            pass

    results: list[dict] = []
    for i, match in enumerate(matches[:_MAX_RESULTS]):
        wikitree_id = match.get("Name") or ""

        father_id = match.get("Father")
        mother_id = match.get("Mother")

        father_name = _resolve_person_name(father_id, name_cache)
        mother_name = _resolve_person_name(mother_id, name_cache)

        spouse_name = None
        if i == 0 and top_spouses:
            spouse_key = (
                top_spouses[0].get("Name")
                or top_spouses[0].get("Id")
            )
            if spouse_key:
                spouse_name = _resolve_person_name(spouse_key, name_cache)

        results.append({
            "record_id": f"wikitree:{wikitree_id}",
            "source": "wikitree",
            "source_type": "wikitree",
            "record_type": "person",
            "data": {
                "name": _make_display_name(match),
                "birth_date": _format_date(match.get("BirthDate")),
                "death_date": _format_date(match.get("DeathDate")),
                "birth_place": match.get("BirthLocation"),
                "death_place": match.get("DeathLocation"),
                "father": father_name,
                "mother": mother_name,
                "spouse": spouse_name,
                "wikitree_id": wikitree_id,
                "wikitree_url": f"https://www.wikitree.com/wiki/{wikitree_id}",
            },
        })

    return results


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------


def _rate_limit() -> None:
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()


def _search(
    first_name: str,
    last_name: str,
    birth_year: Optional[int],
    death_year: Optional[int],
) -> list[dict]:
    """Call WikiTree searchPerson and return the matches list."""
    params: dict = {
        "action": "searchPerson",
        "FirstName": first_name.strip(),
        "LastName": last_name.strip(),
        "fields": (
            "Name,FirstName,MiddleName,LastNameAtBirth,LastNameCurrent,"
            "RealName,BirthDate,DeathDate,BirthLocation,DeathLocation,"
            "Father,Mother"
        ),
        "limit": str(_MAX_RESULTS),
    }
    if birth_year:
        params["BirthDate"] = str(int(birth_year))
    if death_year:
        params["DeathDate"] = str(int(death_year))

    _rate_limit()
    resp = requests.post(
        _API_URL,
        data=params,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    data = resp.json()

    # Response is either [{"status": 0, "matches": [...]}] or similar.
    if isinstance(data, list) and data:
        return data[0].get("matches") or []
    if isinstance(data, dict):
        return data.get("matches") or []
    return []


def _fetch_spouses(wikitree_id: str) -> list[dict]:
    """Fetch the Spouses list for a WikiTree profile."""
    _rate_limit()
    resp = requests.post(
        _API_URL,
        data={
            "action": "getPerson",
            "key": wikitree_id,
            "fields": "Spouses",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list) and data:
        person = data[0].get("person") or {}
    elif isinstance(data, dict):
        person = data.get("person") or {}
    else:
        return []
    return person.get("Spouses") or []


def _resolve_person_name(
    person_key, cache: dict
) -> Optional[str]:
    """Resolve a numeric ID or WikiTree ID to a display name via getPerson.

    Uses a shared ``cache`` to avoid duplicate API calls for parents shared
    across siblings.
    """
    if not person_key or person_key == 0:
        return None

    cache_key = str(person_key)
    if cache_key in cache:
        return cache[cache_key]

    try:
        _rate_limit()
        resp = requests.post(
            _API_URL,
            data={
                "action": "getPerson",
                "key": cache_key,
                "fields": "FirstName,MiddleName,LastNameAtBirth,LastNameCurrent",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()

        if isinstance(data, list) and data:
            person = data[0].get("person") or {}
        elif isinstance(data, dict):
            person = data.get("person") or {}
        else:
            cache[cache_key] = None
            return None

        name = _make_display_name(person)
        cache[cache_key] = name
        return name
    except Exception:
        cache[cache_key] = None
        return None


# ---------------------------------------------------------------------------
# Name and date formatting
# ---------------------------------------------------------------------------


def _make_display_name(person: dict) -> Optional[str]:
    """Construct 'FirstName MiddleName LastNameAtBirth' from WikiTree fields."""
    parts: list[str] = []
    for field in ("FirstName", "RealName"):
        val = (person.get(field) or "").strip()
        if val:
            parts.append(val)
            break
    middle = (person.get("MiddleName") or "").strip()
    if middle:
        parts.append(middle)
    last = (person.get("LastNameAtBirth") or person.get("LastNameCurrent") or "").strip()
    if last:
        parts.append(last)
    return " ".join(parts) if parts else None


def _format_date(iso_date: Optional[str]) -> Optional[str]:
    """Convert ISO date 'YYYY-MM-DD' to GEDCOM format 'DD MMM YYYY'."""
    if not iso_date:
        return None
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(iso_date))
    if not match:
        return None
    year, month, day = match.groups()
    month_idx = int(month) - 1
    if not (0 <= month_idx < 12):
        return None
    day_int = int(day)
    if day_int > 0:
        return f"{day_int} {_MONTHS[month_idx]} {year}"
    return f"{_MONTHS[month_idx]} {year}"
