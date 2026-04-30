"""FamilySearch API search — stub for multi-source corroboration.

This module provides the interface for searching FamilySearch.org records.
It requires a FAMILYSEARCH_API_KEY in the environment (via .env / dotenv).
Until the key is configured, the function returns an empty list with a
logged warning so the pipeline runs without it.

Activate by:
    1. Register at https://www.familysearch.org/developers/
    2. Obtain an API key
    3. Add FAMILYSEARCH_API_KEY=<your-key> to .env

The function signature and return format match the rest of the pipeline's
record-dict convention so the Scout can call it identically to
search_findagrave.

Usage:
    results = search_familysearch("John", "Kennedy", birth_year=1917)
"""

from __future__ import annotations

import os
from typing import Optional


def search_familysearch(
    first_name: str,
    last_name: str,
    birth_year: Optional[int] = None,
    death_year: Optional[int] = None,
    birth_place: Optional[str] = None,
) -> list[dict]:
    """Search FamilySearch for person records matching the given criteria.

    Returns up to 5 dicts, each with:
        {
            "record_id":    "familysearch:{person_id}",
            "source":       "familysearch",
            "source_type":  "familysearch",
            "record_type":  "person",
            "data": {
                "name":         str,
                "birth_date":   str | None,
                "birth_place":  str | None,
                "death_date":   str | None,
                "death_place":  str | None,
                "person_id":    str,
                "person_url":   str,
            },
        }

    Returns [] if the API key is not configured or on any failure.
    """
    api_key = os.environ.get("FAMILYSEARCH_API_KEY", "").strip()
    if not api_key:
        # Expected state until Kaitlin registers for the key.
        # Log once per import, don't spam on every call.
        if not _warned_once[0]:
            print(
                "[familysearch_search] FAMILYSEARCH_API_KEY not configured "
                "-- skipping FamilySearch search. Set the key in .env to "
                "enable."
            )
            _warned_once[0] = True
        return []

    # TODO: implement once API key is available.
    # Endpoint: https://api.familysearch.org/platform/tree/search
    # Headers: Authorization: Bearer {api_key}
    # Params: q.givenName, q.surname, q.birthLikeDate, q.deathLikeDate,
    #         q.birthLikePlace
    # Parse JSON response -> list of person dicts
    # Cap at 5 results
    # Return [] on any failure
    return []


# Module-level flag so the "not configured" warning prints only once.
_warned_once: list[bool] = [False]
