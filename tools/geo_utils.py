"""Geographic utilities — Haversine + geocoding for place-based reasoning.

Used by the Relationship Hypothesizer to check geographic plausibility
(e.g. two events in widely separated places can't involve the same person
in a short time window) and by the Adversarial Critic to flag impossible
co-location claims.

Layers:
  1. `haversine_km` — pure math, no network, no dependencies on geocoding.
  2. `geocode_place` — name → (lat, lon), cached in-process via functools.
  3. `place_distance_km` — name + name → km, combining the two.

Network policy:
  - Uses Nominatim via geopy, which requires a User-Agent and imposes a
    1 request / second rate limit. We wrap with RateLimiter to comply.
  - Every geocode call is memoized so repeated queries in the same session
    hit the cache, not the network.
  - All geocoding functions return None on any error rather than raising,
    so upstream agents can treat geography as best-effort evidence.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Optional

from geopy.exc import GeocoderServiceError, GeocoderTimedOut, GeocoderUnavailable
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim


# Per Nominatim usage policy: supply a descriptive User-Agent identifying the app.
_USER_AGENT = "multiagent-genealogical-research-system/0.1 (course project)"
_MIN_DELAY_SECONDS = 1.0


# Earth radius in kilometers — mean radius, good enough for genealogical scales.
_EARTH_RADIUS_KM = 6371.0088


# ---------------------------------------------------------------------------
# Pure math — no network.
# ---------------------------------------------------------------------------


def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Great-circle distance between two lat/lon points, in kilometers."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _EARTH_RADIUS_KM * c


# ---------------------------------------------------------------------------
# Geocoding — network, cached.
# ---------------------------------------------------------------------------


_geocoder = None
_rate_limited_geocode = None


def _get_geocoder():
    """Lazy-init a rate-limited Nominatim geocoder.

    We build this lazily so importing the module doesn't touch the network
    and tests can monkey-patch before the first call.
    """
    global _geocoder, _rate_limited_geocode
    if _rate_limited_geocode is None:
        _geocoder = Nominatim(user_agent=_USER_AGENT)
        _rate_limited_geocode = RateLimiter(
            _geocoder.geocode,
            min_delay_seconds=_MIN_DELAY_SECONDS,
            error_wait_seconds=5.0,
            max_retries=2,
            swallow_exceptions=False,
        )
    return _rate_limited_geocode


@lru_cache(maxsize=1024)
def geocode_place(place: Optional[str]) -> Optional[tuple[float, float]]:
    """Resolve a place name to (lat, lon), or None if unresolved.

    Results are memoized in-process. Returns None on any geocoder error so
    upstream agents can treat geography as best-effort.
    """
    if not place or not place.strip():
        return None

    try:
        geocode = _get_geocoder()
        location = geocode(place.strip())
    except (GeocoderTimedOut, GeocoderServiceError, GeocoderUnavailable):
        return None
    except Exception:
        # Conservative: never let geocoding crash the pipeline.
        return None

    if location is None:
        return None
    return (location.latitude, location.longitude)


def place_distance_km(place_a: Optional[str], place_b: Optional[str]) -> Optional[float]:
    """Distance in km between two place names, or None if either can't be resolved."""
    a = geocode_place(place_a)
    b = geocode_place(place_b)
    if a is None or b is None:
        return None
    return haversine_km(a[0], a[1], b[0], b[1])


# Graded distance tiers. These are SOFT signals — the geographic check NEVER
# auto-rejects. The Critic's LLM uses these alongside the subject's birth year
# to weigh plausibility contextually (a 2000km gap is normal for 19th-century
# trans-Atlantic migration but suspicious for 14th-century commoner lineages;
# European royal alliances span 1000-2500km in any era).
#
# Values chosen for European royal tree work:
#   <  500 km  co-regional (e.g. within a country)           → ok
#   < 1500 km  cross-border European (London↔Madrid ≈ 1260)  → ok
#   < 3000 km  edge of pre-modern range (Madrid↔Moscow≈3800) → flag_moderate
#   ≥ 3000 km  trans-continental, migration-era context only → flag_strong
_TIER_OK_CUTOFF_KM = 1500.0
_TIER_MODERATE_CUTOFF_KM = 3000.0


def check_geographic_plausibility(
    place_a: Optional[str],
    place_b: Optional[str],
) -> dict:
    """Best-effort geographic check with graded soft-flag verdicts.

    NEVER auto-rejects. All verdicts are soft signals the Critic's LLM is
    expected to interpret contextually using the subject's era. The raw
    ``distance_km`` is always included in the result so the LLM can reason
    numerically when the tier label is ambiguous for the era.

    Returns a check-result dict with the same shape as date_utils rule checks:

        {
            "check":       "geographic_plausibility",
            "verdict":     "ok" | "flag_moderate" | "flag_strong" | "insufficient_data",
            "reason":      human-readable explanation,
            "distance_km": int | None,
        }
    """
    distance = place_distance_km(place_a, place_b)
    if distance is None:
        return {
            "check": "geographic_plausibility",
            "verdict": "insufficient_data",
            "reason": "one or both places could not be geocoded",
            "distance_km": None,
        }

    distance_int = round(distance)
    if distance < _TIER_OK_CUTOFF_KM:
        verdict = "ok"
        reason = f"{distance_int}km apart (within intra-regional range)"
    elif distance < _TIER_MODERATE_CUTOFF_KM:
        verdict = "flag_moderate"
        reason = (
            f"{distance_int}km apart exceeds intra-regional range "
            f"({int(_TIER_OK_CUTOFF_KM)}km) — plausible in migration eras "
            f"or for cross-border alliances, suspicious in medieval/early-modern "
            f"non-royal lineages"
        )
    else:
        verdict = "flag_strong"
        reason = (
            f"{distance_int}km apart — trans-continental gap, requires "
            f"migration-era or colonial context to be plausible"
        )

    return {
        "check": "geographic_plausibility",
        "verdict": verdict,
        "reason": reason,
        "distance_km": distance_int,
    }
