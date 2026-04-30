"""FindAGrave search — retrieves memorial records for multi-source corroboration.

Constructs a search against findagrave.com, parses the results page with
BeautifulSoup, and returns matching memorials in the same record-dict format
the pipeline uses for GEDCOM records. This gives the Synthesizer and Critic
an independent documentary source to cross-reference against GEDCOM data.

Design contract:
    - Returns an empty list on ANY failure (network, parsing, no results).
      Never crashes the pipeline.
    - Rate-limited to 1 request per second (same Nominatim pattern).
    - Capped at 5 results per search.
    - Each result carries ``record_id: "findagrave:{memorial_id}"`` so
      downstream agents can cite it distinctly from GEDCOM sources.

Usage:
    results = search_findagrave("John", "Kennedy", birth_year=1917)
"""

from __future__ import annotations

import re
import time
from typing import Optional
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup


_USER_AGENT = (
    "Mozilla/5.0 (compatible; MultiAgentGenealogyResearch/0.1; "
    "course project; +https://github.com)"
)
_TIMEOUT_SECONDS = 15
_MAX_RESULTS = 5
_MIN_REQUEST_INTERVAL = 1.0  # seconds between requests

_last_request_time: float = 0.0


def search_findagrave(
    first_name: str,
    last_name: str,
    birth_year: Optional[int] = None,
    death_year: Optional[int] = None,
    location: Optional[str] = None,
) -> list[dict]:
    """Search FindAGrave for memorials matching the given criteria.

    Returns up to ``_MAX_RESULTS`` dicts, each with:
        {
            "record_id":    "findagrave:{memorial_id}",
            "source":       "findagrave",
            "source_type":  "findagrave",
            "record_type":  "memorial",
            "data": {
                "name":           str,
                "birth_date":     str | None,
                "death_date":     str | None,
                "burial_location": str | None,
                "memorial_id":    str,
                "memorial_url":   str,
            },
        }

    Returns [] on any failure.
    """
    global _last_request_time

    url = _build_search_url(first_name, last_name, birth_year, death_year, location)
    if not url:
        return []

    # Rate limit.
    elapsed = time.time() - _last_request_time
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)

    try:
        response = requests.get(
            url,
            headers={"User-Agent": _USER_AGENT},
            timeout=_TIMEOUT_SECONDS,
        )
        _last_request_time = time.time()
        response.raise_for_status()
    except Exception:
        return []

    try:
        return _parse_results(response.text)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# URL construction
# ---------------------------------------------------------------------------


def _build_search_url(
    first_name: str,
    last_name: str,
    birth_year: Optional[int],
    death_year: Optional[int],
    location: Optional[str],
) -> Optional[str]:
    if not first_name or not last_name:
        return None

    params: list[str] = [
        f"firstname={quote_plus(first_name.strip())}",
        f"lastname={quote_plus(last_name.strip())}",
    ]
    if birth_year:
        params.append(f"birthyear={int(birth_year)}")
    if death_year:
        params.append(f"deathyear={int(death_year)}")
    if location:
        params.append(f"locationId=0")
        params.append(f"location={quote_plus(location.strip())}")

    return "https://www.findagrave.com/memorial/search?" + "&".join(params)


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------


def _parse_results(html: str) -> list[dict]:
    """Parse the FindAGrave search results page and extract memorial records."""
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []

    # FindAGrave renders results in memorial-item containers.
    # The structure varies but memorial links follow a pattern:
    #   <a href="/memorial/{id}/...">Name</a>
    # with birth/death info in nearby elements.
    memorial_links = soup.select('a[href*="/memorial/"]')

    seen_ids: set[str] = set()
    for link in memorial_links:
        href = link.get("href", "")
        memorial_id = _extract_memorial_id(href)
        if not memorial_id or memorial_id in seen_ids:
            continue
        seen_ids.add(memorial_id)

        raw_text = link.get_text(strip=True)
        if not raw_text or len(raw_text) < 3:
            continue

        # The link text often smashes the name, badges, and dates together:
        #   "John F. KennedyVVeteranFamous MemorialFlowers have been left.29 May 1917 – 22 Nov 1963"
        # Clean it up by extracting dates first, then stripping badge text.
        name, birth_date, death_date = _clean_memorial_text(raw_text)
        if not name:
            continue

        # Burial location from the surrounding context.
        burial = _extract_burial_location(link)

        results.append({
            "record_id": f"findagrave:{memorial_id}",
            "source": "findagrave",
            "source_type": "findagrave",
            "record_type": "memorial",
            "data": {
                "name": name,
                "birth_date": birth_date,
                "death_date": death_date,
                "burial_location": burial,
                "memorial_id": memorial_id,
                "memorial_url": f"https://www.findagrave.com/memorial/{memorial_id}",
            },
        })

        if len(results) >= _MAX_RESULTS:
            break

    return results


def _extract_memorial_id(href: str) -> Optional[str]:
    """Extract the numeric memorial ID from a FindAGrave URL path."""
    match = re.search(r"/memorial/(\d+)", href)
    return match.group(1) if match else None


# Known badge/decoration strings that FindAGrave concatenates into link text.
_BADGE_STRINGS = [
    "VVeteran",
    "Famous Memorial",
    "Flowers have been left.",
    "Flowers have been left",
    "Cenotaph",
    "No grave photo",
    "Original",
]

# Date range pattern: "29 May 1917 – 22 Nov 1963" or "1917 – 1963"
_DATE_RANGE_RE = re.compile(
    r"(\d{1,2}\s+\w{3,9}\s+\d{4}|\d{4})"
    r"\s*[\u2013\u2014\-]+\s*"  # en-dash, em-dash, or hyphen
    r"(\d{1,2}\s+\w{3,9}\s+\d{4}|\d{4})"
)


def _clean_memorial_text(
    raw: str,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract (name, birth_date, death_date) from a messy link-text blob."""
    text = raw

    # Extract date range before stripping — it's the most reliable anchor.
    birth_date: Optional[str] = None
    death_date: Optional[str] = None
    date_match = _DATE_RANGE_RE.search(text)
    if date_match:
        birth_date = date_match.group(1).strip()
        death_date = date_match.group(2).strip()
        text = text[: date_match.start()]

    # Strip badge strings.
    for badge in _BADGE_STRINGS:
        text = text.replace(badge, "")

    # Clean up stray bullet characters and whitespace.
    text = text.replace("\u2022", " ")  # bullet •
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")

    name = text if len(text) >= 3 else None
    return name, birth_date, death_date


def _extract_burial_location(link_tag) -> Optional[str]:
    """Walk up the DOM from a memorial link to find a burial location string."""
    container = link_tag
    for _ in range(5):
        parent = container.parent
        if parent is None:
            break
        container = parent
        if container.name in ("body", "html", "main", "section"):
            break

    text = container.get_text(separator=" ", strip=True)

    # Look for cemetery or location patterns.
    burial_match = re.search(
        r"(?:Burial:?\s*|Cemetery:?\s*|buried\s+(?:at|in)\s+)([^.;]+)",
        text,
        re.IGNORECASE,
    )
    if burial_match:
        loc = re.sub(r"\s+", " ", burial_match.group(1)).strip()
        return loc[:120] if loc else None

    # Fallback: if the container has location-ish text with a county/state
    # pattern, grab it.
    loc_match = re.search(
        r"(\w[\w\s]+County,\s*\w[\w\s]+)",
        text,
    )
    if loc_match:
        loc = re.sub(r"\s+", " ", loc_match.group(1)).strip()
        return loc[:120] if loc else None

    return None
