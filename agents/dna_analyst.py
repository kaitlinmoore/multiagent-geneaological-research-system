"""DNA Analyst — parses DNA matches, predicts relationships, cross-references GEDCOM.

Role: parse DNA matches -> predict relationships from cM -> cross-reference
match names against the documentary tree.

This is the fifth agent. It runs in PARALLEL with the documentary pipeline
(Synthesizer -> Hypothesizer -> Critic) since it only needs gedcom_persons
from the Record Scout, not the hypothesis/critique results.

Pipeline:
    1. If no DNA data in state, return immediately with a trace note.
    2. Parse DNA CSV using tools.dna_parser.
    3. For each match, predict possible relationships via shared_cm_lookup.
    4. For MyHeritage matches (has_real_name=True), fuzzy-match against
       gedcom_persons to find tree candidates.
    5. Where a tree match is found, compare documentary vs DNA-predicted
       relationships.
    6. Aggregate: distribution by relationship tier, cross-reference hits,
       platform prediction consistency.

Output: state["dna_analysis"] dict consumed by the Final Report Writer.
"""

from __future__ import annotations

from typing import Optional

from state import GenealogyState
from tools.dna_parser import parse_dna_text
from tools.fuzzy_match import name_match_score
from tools.shared_cm_lookup import is_consistent, lookup_relationships


# Minimum fuzzy score to consider a DNA match name as matching a GEDCOM person.
_NAME_MATCH_THRESHOLD = 0.75

# Relationship tiers for distribution summary.
_TIERS = [
    ("Parent/Child",      3300, 99999),
    ("Sibling",           2200, 3300),
    ("Grandparent/Uncle", 1150, 2200),
    ("1st Cousin",         550, 1150),
    ("1C1R/Half-1C",       230,  550),
    ("2nd Cousin",          40,  230),
    ("Distant (<40 cM)",     0,   40),
]


def dna_analyst_node(state: GenealogyState) -> dict:
    trace: list[str] = []
    trace.append("dna_analyst: enter")

    dna_csv = state.get("dna_csv")
    if not dna_csv:
        trace.append("dna_analyst: no DNA data provided — skipping")
        trace.append("dna_analyst: exit")
        return {"dna_analysis": None, "trace_log": trace}

    # 1. Parse DNA file.
    parsed = parse_dna_text(dna_csv, filename_hint="uploaded_dna.csv")
    matches = parsed.get("matches") or []
    platform = parsed.get("platform", "unknown")
    trace.append(
        f"dna_analyst: parsed {len(matches)} matches from {platform}"
    )

    if not matches:
        trace.append("dna_analyst: no valid matches found — skipping")
        trace.append("dna_analyst: exit")
        return {
            "dna_analysis": {
                "platform": platform,
                "total_matches": 0,
                "relationship_distribution": {},
                "cross_references": [],
                "aggregate_consistency": "no data",
                "findings": ["No valid DNA matches found in the uploaded file."],
            },
            "trace_log": trace,
        }

    gedcom_persons = state.get("gedcom_persons") or []

    # 2. Identify the DNA test subject in the GEDCOM tree, if possible.
    # The DNA file's subject name (often guessed from the filename) is
    # fuzzy-matched against gedcom_persons. The matched ID lets the
    # Hypothesizer and Critic reason about DNA evidence with confidence
    # that the cM values describe shared DNA between THIS person and the
    # match list — not someone else.
    subject_gedcom_id, subject_match_score = _identify_dna_subject(
        parsed.get("subject_name"),
        state.get("target_person") or {},
        gedcom_persons,
    )
    if subject_gedcom_id:
        trace.append(
            f"dna_analyst: DNA test subject identified as "
            f"{subject_gedcom_id} (name match {subject_match_score:.2f})"
        )
    else:
        trace.append(
            "dna_analyst: DNA test subject could not be identified in GEDCOM "
            "(downstream agents will not apply DNA reasoning)"
        )

    # 3. Predict relationships + build distribution.
    distribution = _compute_distribution(matches)
    trace.append(
        f"dna_analyst: distribution — "
        + ", ".join(f"{k}: {v}" for k, v in distribution.items() if v > 0)
    )

    # 4. Cross-reference matches with real names against GEDCOM tree.
    cross_refs = _cross_reference(matches, gedcom_persons, trace)
    trace.append(f"dna_analyst: {len(cross_refs)} cross-references found")

    # 5. Check platform predictions against shared cM lookup.
    prediction_checks = _check_platform_predictions(matches)

    # 6. Aggregate findings.
    findings = _compile_findings(
        matches, distribution, cross_refs, prediction_checks, platform
    )
    consistency = _assess_consistency(cross_refs, prediction_checks)

    trace.append(f"dna_analyst: aggregate consistency = {consistency}")
    trace.append("dna_analyst: exit")

    return {
        "dna_analysis": {
            "platform": platform,
            "subject_name": parsed.get("subject_name"),
            "subject_gedcom_id": subject_gedcom_id,
            "subject_match_score": subject_match_score,
            "total_matches": len(matches),
            "relationship_distribution": distribution,
            "cross_references": cross_refs,
            "prediction_checks": prediction_checks,
            "aggregate_consistency": consistency,
            "findings": findings,
        },
        "trace_log": trace,
    }


def _identify_dna_subject(
    dna_subject_name,
    target_person,
    gedcom_persons,
):
    """Identify the GEDCOM person whose DNA was tested.

    Combines two signals: the parsed-from-filename DNA subject name and
    the pipeline's target_person. If either fuzzy-matches a GEDCOM person
    above 0.70, return that person's ID.
    """
    candidates_to_try: list[str] = []
    if dna_subject_name:
        candidates_to_try.append(dna_subject_name)
    if isinstance(target_person, dict) and target_person.get("name"):
        candidates_to_try.append(target_person["name"])

    best_id = None
    best_score = 0.0
    for cand_name in candidates_to_try:
        for p in gedcom_persons:
            pname = p.get("name") or ""
            if not pname:
                continue
            score = name_match_score(cand_name, pname)
            if score > best_score:
                best_score = score
                best_id = p.get("id")
    if best_id and best_score >= 0.70:
        return best_id, round(best_score, 3)
    return None, round(best_score, 3) if best_score else 0.0


# ---------------------------------------------------------------------------
# Distribution
# ---------------------------------------------------------------------------


def _compute_distribution(matches: list[dict]) -> dict[str, int]:
    dist: dict[str, int] = {}
    for label, lo, hi in _TIERS:
        count = sum(1 for m in matches if lo <= m["shared_cM"] < hi)
        dist[label] = count
    return dist


# ---------------------------------------------------------------------------
# Cross-referencing: DNA match names vs. GEDCOM persons
# ---------------------------------------------------------------------------


def _cross_reference(
    matches: list[dict],
    gedcom_persons: list[dict],
    trace: list[str],
) -> list[dict]:
    """For matches with real names, fuzzy-match against GEDCOM and compare
    documentary vs DNA-predicted relationships."""
    if not gedcom_persons:
        return []

    real_name_matches = [m for m in matches if m.get("has_real_name")]
    if not real_name_matches:
        trace.append("dna_analyst: no real-name matches (platform may use aliases)")
        return []

    cross_refs: list[dict] = []
    for dna_match in real_name_matches:
        dna_name = dna_match["name"]
        best_gedcom = None
        best_score = 0.0

        for person in gedcom_persons:
            gedcom_name = person.get("name") or ""
            if not gedcom_name:
                continue
            score = name_match_score(dna_name, gedcom_name)
            if score > best_score:
                best_score = score
                best_gedcom = person

        if best_score >= _NAME_MATCH_THRESHOLD and best_gedcom:
            # Predict relationship from DNA.
            predictions = lookup_relationships(dna_match["shared_cM"])
            top_prediction = predictions[0]["relationship"] if predictions else "unknown"

            # Check platform prediction consistency.
            platform_pred = dna_match.get("platform_prediction")
            platform_check = None
            if platform_pred:
                platform_check = is_consistent(
                    dna_match["shared_cM"], platform_pred
                )

            cross_refs.append({
                "dna_name": dna_name,
                "gedcom_name": best_gedcom.get("name"),
                "gedcom_id": best_gedcom.get("id"),
                "name_match_score": round(best_score, 3),
                "shared_cM": dna_match["shared_cM"],
                "dna_predicted_relationship": top_prediction,
                "platform_prediction": platform_pred,
                "platform_consistent": (
                    platform_check["consistent"] if platform_check else None
                ),
                "all_possible_relationships": [
                    r["relationship"] for r in predictions[:5]
                ],
            })

    return cross_refs


# ---------------------------------------------------------------------------
# Platform prediction consistency
# ---------------------------------------------------------------------------


def _check_platform_predictions(matches: list[dict]) -> dict:
    """Check how often the platform's own prediction is consistent with
    the shared cM lookup table."""
    total_with_prediction = 0
    consistent_count = 0
    inconsistent: list[dict] = []

    for m in matches:
        pred = m.get("platform_prediction")
        if not pred:
            continue
        total_with_prediction += 1
        check = is_consistent(m["shared_cM"], pred)
        if check["consistent"]:
            consistent_count += 1
        else:
            if check.get("expected_range"):  # only flag if we recognized the relationship
                inconsistent.append({
                    "name": m["name"],
                    "shared_cM": m["shared_cM"],
                    "platform_said": pred,
                    "deviation": check["deviation"],
                })

    return {
        "total_with_prediction": total_with_prediction,
        "consistent": consistent_count,
        "inconsistent_count": len(inconsistent),
        "inconsistent_examples": inconsistent[:5],
    }


# ---------------------------------------------------------------------------
# Findings and consistency assessment
# ---------------------------------------------------------------------------


def _compile_findings(
    matches: list[dict],
    distribution: dict[str, int],
    cross_refs: list[dict],
    prediction_checks: dict,
    platform: str,
) -> list[str]:
    findings: list[str] = []

    findings.append(
        f"DNA data from {platform}: {len(matches)} total matches analyzed."
    )

    # Distribution summary.
    close = sum(
        distribution.get(t, 0) for t in ("Parent/Child", "Sibling", "Grandparent/Uncle")
    )
    if close:
        findings.append(
            f"{close} close relative(s) detected in Parent/Child, Sibling, "
            f"or Grandparent/Uncle range."
        )

    cousins = distribution.get("1st Cousin", 0) + distribution.get("1C1R/Half-1C", 0)
    if cousins:
        findings.append(f"{cousins} match(es) in 1st cousin or closer cousin range.")

    distant = distribution.get("Distant (<40 cM)", 0)
    if distant:
        findings.append(
            f"{distant} distant matches (<40 cM) — expected for large match lists."
        )

    # Cross-reference findings.
    if cross_refs:
        findings.append(
            f"{len(cross_refs)} DNA match name(s) matched to GEDCOM tree persons "
            f"(fuzzy score >= {_NAME_MATCH_THRESHOLD})."
        )
        for xr in cross_refs[:3]:
            findings.append(
                f"  - '{xr['dna_name']}' matched '{xr['gedcom_name']}' "
                f"({xr['gedcom_id']}) at {xr['shared_cM']} cM "
                f"(predicted: {xr['dna_predicted_relationship']})"
            )
    elif any(m.get("has_real_name") for m in matches):
        findings.append(
            "DNA matches have real names but none matched GEDCOM tree persons "
            f"above the {_NAME_MATCH_THRESHOLD} threshold."
        )
    else:
        findings.append(
            "DNA platform uses aliases — name-based cross-referencing not possible."
        )

    # Platform prediction consistency.
    pc = prediction_checks
    if pc["total_with_prediction"]:
        rate = pc["consistent"] / pc["total_with_prediction"] * 100
        findings.append(
            f"Platform relationship predictions: {pc['consistent']}/"
            f"{pc['total_with_prediction']} ({rate:.0f}%) consistent with "
            f"Shared cM Project ranges."
        )

    return findings


def _assess_consistency(
    cross_refs: list[dict],
    prediction_checks: dict,
) -> str:
    """Produce a one-line aggregate consistency assessment."""
    if not cross_refs and not prediction_checks.get("total_with_prediction"):
        return "insufficient data for consistency assessment"

    issues: list[str] = []
    if prediction_checks.get("inconsistent_count", 0) > 0:
        issues.append(
            f"{prediction_checks['inconsistent_count']} inconsistent "
            f"platform predictions"
        )

    if not issues:
        return "consistent — no contradictions found"
    return "partially consistent — " + "; ".join(issues)
