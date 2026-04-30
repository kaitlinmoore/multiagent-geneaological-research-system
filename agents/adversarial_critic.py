"""Adversarial Critic — independently attacks hypotheses.

Role (CLAUDE.md): "Independently attacks hypotheses. Uses deterministic
rule checks (date impossibilities, geographic implausibility) + LLM
reasoning for evidence sufficiency. Max 2 revision cycles."

CRITICAL CRITIC-ISOLATION INVARIANT:
    This node reads hypotheses EXCLUSIVELY through filter_hypothesis_for_critic
    from agents.hypothesis_schema. It NEVER reads raw state["hypotheses"] dicts.
    The filter call on line ~140 below is the single toggle point for the
    Critic-isolation A/B experiment:

        # Condition A (default, isolated)
        isolated = filter_hypotheses_for_critic(raw_hypotheses)

        # Condition B (relaxed, full context)
        isolated = raw_hypotheses

    Swap those two lines to run Condition B. Do not introduce any other read
    path to state["hypotheses"] anywhere in this file.

Pipeline:
    1. Filter hypotheses through filter_hypotheses_for_critic (isolation).
    2. For each filtered hypothesis, run DETERMINISTIC Tier 1 checks FIRST:
          - run_all_tier1_checks (date impossibilities, parent-age floors, etc.)
          - check_geographic_plausibility (soft flag)
       Any Tier 1 verdict == "impossible" → automatic reject with confidence
       0.98, NO LLM call. This is the fail-fast pattern from CLAUDE.md:
       "Deterministic checks in the Critic should run BEFORE LLM reasoning."
    3. If Tier 1 clean, call the LLM with (a) the isolated hypothesis,
       (b) the subject profile, (c) raw records for subject + related,
       (d) the Tier 1 check results, (e) the geographic result. The LLM
       independently evaluates evidence sufficiency.
    4. The LLM assigns confidence_in_critique (0..1) to its OWN output.
       Prompt explicitly instructs: high confidence ONLY when the issue is
       deterministic or clearly documented; low confidence when evidence is
       genuinely ambiguous. This is measurable for the Tier 3 eval axis —
       a Critic that scores 0.95 confidence on ambiguous cases is overconfident.
    5. Aggregate: any "reject" verdict → status=needs_revision and increment
       revision_count. Otherwise status=complete.

Critique dict shape (extends CLAUDE.md spec):
    {
        "hypothesis_id":          back-reference to the hypothesis
        "verdict":                "accept" | "reject" | "flag_uncertain"
        "issues_found":           list of strings (concrete concerns)
        "evidence_cited":         list of record_ids / Tier 1 check names
        "confidence_in_critique": float 0..1 — the Critic's self-assessed confidence
        "justification":          short human-readable explanation
        "tier1_results":          list of deterministic check results (for audit)
        "geo_result":             geographic plausibility result or None
        "isolation_mode":         "filtered" | "unfiltered" — which A/B condition ran
    }
"""

from __future__ import annotations

import json
import os
from typing import Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from agents.hypothesis_schema import (
    INTERNAL_HYPOTHESIS_FIELDS,
    filter_hypotheses_for_critic,
)
from state import GenealogyState
from tools.date_utils import run_all_tier1_checks
from tools.geo_utils import check_geographic_plausibility


# Default Critic model. The production system uses Anthropic Claude Opus 4.7.
# A cross-vendor variant (Anthropic Hypothesizer + non-Anthropic Critic) is
# available for the cross-vendor experiment by setting the env vars below
# OR by directly overriding `llm` from an experiment harness:
#
#   CRITIC_VENDOR=openai     CRITIC_MODEL=gpt-5.5
#   CRITIC_VENDOR=anthropic  CRITIC_MODEL=claude-opus-4-7   (default)
#
# The cross-vendor design rationale: an adversarial Critic from a different
# vendor cannot share training-data assumptions or systematic failure modes
# with the Hypothesizer. Same-vendor Critics may quietly agree because they
# share priors, defeating the adversarial-isolation guarantee.
_DEFAULT_VENDOR = "anthropic"
_DEFAULT_MODEL = "claude-opus-4-7"


def build_critic_llm(vendor: Optional[str] = None, model: Optional[str] = None):
    """Construct a Critic LLM. Defaults to Anthropic Opus 4.7.

    Override via env vars (CRITIC_VENDOR, CRITIC_MODEL) or arguments.
    """
    vendor = (vendor or os.environ.get("CRITIC_VENDOR") or _DEFAULT_VENDOR).lower()
    model = model or os.environ.get("CRITIC_MODEL") or _DEFAULT_MODEL

    if vendor == "anthropic":
        return ChatAnthropic(model=model, max_tokens=2048)
    if vendor == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, max_tokens=2048)
    if vendor == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        # Gemini sometimes uses more output tokens for the same critique
        # length than Anthropic/OpenAI; 4096 prevents JSON truncation on
        # larger inputs (e.g. gap-mode hypotheses with rich record context).
        return ChatGoogleGenerativeAI(model=model, max_output_tokens=4096)
    raise ValueError(f"unknown CRITIC_VENDOR: {vendor!r} (use anthropic, openai, or google)")


llm = build_critic_llm()

# The geographic check itself now uses graded soft-flag tiers (see
# tools/geo_utils.check_geographic_plausibility). There is no Critic-level
# max_km knob anymore — the Critic passes the raw distance and tier verdict
# to the LLM, which is expected to weigh it contextually against the subject's
# birth year. This avoids the false-positive trade-off a single threshold
# imposes: European royal alliances routinely span 1000-2500km, while 1880s
# trans-Atlantic migration routinely spans 4000-5000km.

# Default A/B experiment condition. "filtered" uses filter_hypotheses_for_critic
# (Condition A, the isolation design). "unfiltered" reads raw hypotheses
# (Condition B, baseline for the experiment). Do NOT default this to
# "unfiltered" in production — it defeats the core agentic constraint.
_DEFAULT_ISOLATION_MODE = "filtered"


_CRITIC_PROMPT = """You are an Adversarial Critic. Your job is to independently
attack genealogical hypotheses and find flaws in their evidence. You were not
given the Hypothesizer's reasoning chain on purpose — reach your own conclusion
from the raw evidence.

You will receive:
  - An isolated hypothesis (subject_id, related_id, proposed_relationship,
    evidence_chain with cited sources, confidence_score, stated_weaknesses)
  - The subject profile (facts with citations, gaps, disambiguation candidates)
  - Raw records for the subject and related person
  - Deterministic Tier 1 rule-check results (already computed, trust them)
  - Geographic plausibility result (soft signal — NEVER auto-reject on it).
    The geo check returns graded verdicts: "ok", "flag_moderate", or
    "flag_strong", plus a raw distance_km. Interpret these RELATIVE to the
    subject's birth year, not as hard rules:
      * A 2000km gap is normal for 19th-century trans-Atlantic migration
        but suspicious for 14th-century non-royal lineages.
      * European alliances across 1000-2500km are routine in any era —
        a Madrid-to-Vienna or London-to-Paris gap is not implausible.
      * A trans-continental gap (>3000km) requires a migration-era or
        colonial context to be plausible; if the subject was born before
        the 1600s and the records show such a gap, that's a strong flag.
    Use the raw distance_km and the era to reach your own conclusion; do
    not mechanically downgrade your verdict on a flag_moderate.

You will NOT receive:
  - The Hypothesizer's reasoning narrative
  - Alternatives the Hypothesizer considered
  - Any explanation of how the Hypothesizer connected its evidence

Your task:
  1. Independently evaluate whether the evidence presented supports the
     proposed relationship. Do not trust the Hypothesizer's confidence score
     — reach your own conclusion.
  2. Identify concrete issues: missing corroboration, single-source evidence,
     suspicious coincidences, conflicting facts, unresolved ambiguity.
  3. Issue a verdict:
       "accept" — evidence is sufficient and the hypothesis is plausible
       "reject" — the hypothesis is demonstrably wrong OR the evidence is so
                  insufficient that the hypothesis cannot stand
       "flag_uncertain" — the hypothesis may be right but cannot be verified
                          with confidence given the available evidence
  4. Rate your OWN confidence in your critique (0..1). This is NOT the same
     as the Hypothesizer's confidence_score. Be honest:
       >0.9   ONLY when the issue is deterministic (Tier 1 impossible) or the
              evidence is clearly documented and unambiguous
       0.7-0.9  for LLM judgments on single-source cases with clear reasoning
       0.5-0.7  for circumstantial evidence where reasonable critics could disagree
       <0.5   when the evidence is genuinely ambiguous and equally supports
              multiple interpretations
     A critic who assigns 0.95 to a critique of an ambiguous Tier 3 case is
     OVERCONFIDENT. Match your confidence to the epistemic quality of your
     reasoning, not to the confidence of your tone.

Return ONE JSON object with exactly these keys:
  "verdict":                "accept" | "reject" | "flag_uncertain"
  "issues_found":           list of specific concerns (not boilerplate)
  "evidence_cited":         list of record_ids or check names referenced
  "confidence_in_critique": float 0..1
  "justification":          1-3 sentences explaining the verdict and confidence

Return ONLY valid JSON. No prose, no markdown fences.
"""


def adversarial_critic_node(state: GenealogyState) -> dict:
    trace: list[str] = []
    trace.append("adversarial_critic: enter")

    raw_hypotheses = state.get("hypotheses") or []
    if not raw_hypotheses:
        trace.append("adversarial_critic: no hypotheses to critique")
        trace.append("adversarial_critic: exit")
        return {
            "critiques": [],
            "status": "complete",
            "trace_log": trace,
        }

    # --- CRITIC ISOLATION BOUNDARY ------------------------------------------
    # THIS is the single read path into state["hypotheses"] from this module.
    # filter_hypotheses_for_critic strips reasoning_narrative, intermediate_steps,
    # alternatives_considered, and llm_raw_response. Nothing below this line
    # should access raw_hypotheses directly.
    #
    # isolation_mode can be overridden per-run via state["isolation_mode"],
    # which the A/B experiment harness flips between "filtered" (Condition A)
    # and "unfiltered" (Condition B). If state has no explicit value, we
    # fall back to the module default.
    isolation_mode = state.get("isolation_mode") or _DEFAULT_ISOLATION_MODE
    if isolation_mode == "filtered":
        isolated_hypotheses = filter_hypotheses_for_critic(raw_hypotheses)
    else:
        # Condition B of the A/B experiment: explicitly opt out of isolation.
        isolated_hypotheses = list(raw_hypotheses)
    trace.append(
        f"adversarial_critic: isolation_mode={isolation_mode}, "
        f"filtered {len(raw_hypotheses)} hypotheses, stripped "
        f"{len(INTERNAL_HYPOTHESIS_FIELDS)} internal field types"
    )
    # -----------------------------------------------------------------------

    profiles = state.get("profiles") or []
    retrieved_records = state.get("retrieved_records") or []
    gedcom_persons = state.get("gedcom_persons") or []
    dna_analysis = state.get("dna_analysis")
    person_by_id = {p["id"]: p for p in gedcom_persons if p.get("id")}

    critiques: list[dict] = []
    any_reject = False
    for isolated_hyp in isolated_hypotheses:
        critique = _critique_one(
            isolated_hyp=isolated_hyp,
            profiles=profiles,
            retrieved_records=retrieved_records,
            person_by_id=person_by_id,
            isolation_mode=isolation_mode,
            dna_analysis=dna_analysis,
            trace=trace,
        )
        critiques.append(critique)
        if critique["verdict"] == "reject":
            any_reject = True

    # Status + revision bookkeeping.
    revision_count = int(state.get("revision_count") or 0)
    if any_reject:
        new_revision_count = revision_count + 1
        status = "needs_revision"
        trace.append(
            f"adversarial_critic: at least one reject; "
            f"revision_count {revision_count} -> {new_revision_count}, "
            f"status=needs_revision"
        )
    else:
        new_revision_count = revision_count
        status = "complete"
        trace.append(
            "adversarial_critic: no rejects; status=complete"
        )

    trace.append(f"adversarial_critic: produced {len(critiques)} critiques")
    trace.append("adversarial_critic: exit")

    return {
        "critiques": critiques,
        "status": status,
        "revision_count": new_revision_count,
        "trace_log": trace,
    }


# ---------------------------------------------------------------------------
# Per-hypothesis critique
# ---------------------------------------------------------------------------


def _critique_one(
    isolated_hyp: dict,
    profiles: list[dict],
    retrieved_records: list[dict],
    person_by_id: dict[str, dict],
    isolation_mode: str,
    dna_analysis: Optional[dict],
    trace: list[str],
) -> dict:
    hypothesis_id = isolated_hyp.get("hypothesis_id", "<unknown>")

    # Step 1: deterministic Tier 1 checks FIRST (per CLAUDE.md fail-fast rule).
    tier1_results = _run_tier1(isolated_hyp, person_by_id)
    impossibles = [r for r in tier1_results if r.get("verdict") == "impossible"]
    trace.append(
        f"adversarial_critic: {hypothesis_id} tier1 "
        f"({len(tier1_results)} checks, {len(impossibles)} impossible)"
    )

    # Step 2: geographic plausibility as a soft signal.
    geo_result = _run_geo(isolated_hyp, person_by_id)
    if geo_result:
        trace.append(
            f"adversarial_critic: {hypothesis_id} geo -> "
            f"{geo_result['verdict']}: {geo_result['reason']}"
        )

    # Step 3: fail-fast on deterministic impossibles. NO LLM call.
    if impossibles:
        trace.append(
            f"adversarial_critic: {hypothesis_id} "
            f"AUTO-REJECT on {len(impossibles)} deterministic failures"
        )
        return {
            "hypothesis_id": hypothesis_id,
            "verdict": "reject",
            "issues_found": [
                f"[tier1:{r['check']}] {r['reason']}" for r in impossibles
            ],
            "evidence_cited": [r["check"] for r in impossibles],
            "confidence_in_critique": 0.98,
            "justification": (
                "Deterministic Tier 1 rule check(s) found impossible "
                "condition(s). No LLM reasoning was required; the critique "
                "is based on reproducible rule failures."
            ),
            "tier1_results": tier1_results,
            "geo_result": geo_result,
            "isolation_mode": isolation_mode,
        }

    # Step 4: LLM reasoning for evidence sufficiency.
    # DNA evidence relevant to THIS hypothesis (only if DNA test subject
    # matches the hypothesis subject — the cM data describes shared DNA
    # between this person and the match list).
    dna_relevant = _extract_relevant_dna_evidence(isolated_hyp, dna_analysis)
    if dna_relevant:
        trace.append(
            f"adversarial_critic: {hypothesis_id} DNA relevant — "
            f"{len(dna_relevant.get('cross_references_for_related') or [])} "
            f"cross-ref(s) for related person, "
            f"deterministic check: {dna_relevant.get('cm_consistency_verdict')}"
        )

    llm_verdict = _llm_critique(
        isolated_hyp=isolated_hyp,
        profiles=profiles,
        retrieved_records=retrieved_records,
        tier1_results=tier1_results,
        geo_result=geo_result,
        dna_relevant=dna_relevant,
        trace=trace,
    )

    return {
        "hypothesis_id": hypothesis_id,
        "verdict": llm_verdict["verdict"],
        "issues_found": llm_verdict["issues_found"],
        "evidence_cited": llm_verdict["evidence_cited"],
        "confidence_in_critique": llm_verdict["confidence_in_critique"],
        "justification": llm_verdict["justification"],
        "tier1_results": tier1_results,
        "geo_result": geo_result,
        "dna_relevant": dna_relevant,
        "isolation_mode": isolation_mode,
    }


def _extract_relevant_dna_evidence(
    isolated_hyp: dict, dna_analysis: Optional[dict]
) -> Optional[dict]:
    """Extract the DNA evidence specifically relevant to one hypothesis.

    Returns None if DNA data is absent, the test subject isn't identified,
    or the DNA test subject isn't this hypothesis's subject. Otherwise
    returns:
        {
            "dna_subject_gedcom_id": str,
            "test_subject_matches_hypothesis_subject": bool,
            "cross_references_for_related": list[dict],
            "cm_consistency_verdict": str,  # "supports" | "contradicts" | "no match in DNA list"
            "platform": str,
            "total_matches": int,
        }
    """
    if not dna_analysis:
        return None
    dna_subject_id = dna_analysis.get("subject_gedcom_id")
    if not dna_subject_id:
        return None

    subject_id = isolated_hyp.get("subject_id")
    related_id = isolated_hyp.get("related_id")
    if subject_id != dna_subject_id:
        # cM data is between dna_subject_id and the matches; doesn't apply
        # to a hypothesis where the subject is someone else.
        return None

    cross_refs = dna_analysis.get("cross_references") or []
    refs_for_related = [
        xr for xr in cross_refs if xr.get("gedcom_id") == related_id
    ]

    # Compute deterministic consistency verdict if we have a cross-ref.
    from tools.shared_cm_lookup import is_consistent
    relationship = isolated_hyp.get("proposed_relationship", "")
    cm_verdict = "no match in DNA list"
    cm_check = None
    if refs_for_related:
        xr = refs_for_related[0]
        cm = xr.get("shared_cM")
        if cm is not None:
            cm_check = is_consistent(cm, relationship)
            cm_verdict = "supports" if cm_check.get("consistent") else "contradicts"

    return {
        "dna_subject_gedcom_id": dna_subject_id,
        "test_subject_matches_hypothesis_subject": True,
        "cross_references_for_related": refs_for_related,
        "cm_consistency_verdict": cm_verdict,
        "cm_consistency_detail": cm_check,
        "platform": dna_analysis.get("platform"),
        "total_matches": dna_analysis.get("total_matches"),
    }


# ---------------------------------------------------------------------------
# Deterministic check helpers
# ---------------------------------------------------------------------------


def _run_tier1(
    isolated_hyp: dict, person_by_id: dict[str, dict]
) -> list[dict]:
    """Run date_utils Tier 1 checks relevant to this hypothesis."""
    subject_id = isolated_hyp.get("subject_id")
    related_id = isolated_hyp.get("related_id")
    relationship = (isolated_hyp.get("proposed_relationship") or "").lower()

    subject = person_by_id.get(subject_id)
    if subject is None:
        return [
            {
                "check": "subject_lookup",
                "verdict": "insufficient_data",
                "reason": f"subject {subject_id} not in gedcom_persons",
            }
        ]

    related = person_by_id.get(related_id)
    father = related if "father" in relationship else None
    mother = related if "mother" in relationship else None

    return run_all_tier1_checks(subject, father=father, mother=mother)


def _run_geo(
    isolated_hyp: dict, person_by_id: dict[str, dict]
) -> Optional[dict]:
    """Run geographic plausibility check between subject and related birthplaces."""
    subject = person_by_id.get(isolated_hyp.get("subject_id"))
    related = person_by_id.get(isolated_hyp.get("related_id"))
    if not subject or not related:
        return None

    subject_place = subject.get("birth_place")
    related_place = related.get("birth_place")
    if not subject_place or not related_place:
        return None

    try:
        return check_geographic_plausibility(subject_place, related_place)
    except Exception:
        # geo_utils is already defensive, but catch anything stray so the
        # critic never crashes on a network hiccup.
        return None


# ---------------------------------------------------------------------------
# LLM reasoning step
# ---------------------------------------------------------------------------


def _llm_critique(
    isolated_hyp: dict,
    profiles: list[dict],
    retrieved_records: list[dict],
    tier1_results: list[dict],
    geo_result: Optional[dict],
    dna_relevant: Optional[dict],
    trace: list[str],
) -> dict:
    subject_id = isolated_hyp.get("subject_id")
    related_id = isolated_hyp.get("related_id")

    # Only pass the profile that matches our subject, not all profiles.
    relevant_profile = _find_profile_for_subject(profiles, subject_id)
    # Only pass records relevant to this hypothesis (subject + related).
    relevant_records = [
        r for r in retrieved_records
        if r.get("data", {}).get("id") in {subject_id, related_id}
    ]

    prompt_body = _build_prompt_body(
        isolated_hyp=isolated_hyp,
        relevant_profile=relevant_profile,
        relevant_records=relevant_records,
        tier1_results=tier1_results,
        geo_result=geo_result,
        dna_relevant=dna_relevant,
    )

    try:
        response = llm.invoke(
            [
                SystemMessage(content=_CRITIC_PROMPT),
                HumanMessage(content=prompt_body),
            ]
        )
        raw = (
            response.content.strip()
            if isinstance(response.content, str)
            else str(response.content)
        )
        parsed = json.loads(_strip_markdown_fences(raw))
        trace.append(
            f"adversarial_critic: {isolated_hyp.get('hypothesis_id')} LLM "
            f"verdict={parsed.get('verdict')} conf={parsed.get('confidence_in_critique')}"
        )
        return {
            "verdict": parsed.get("verdict") or "flag_uncertain",
            "issues_found": parsed.get("issues_found") or [],
            "evidence_cited": parsed.get("evidence_cited") or [],
            "confidence_in_critique": float(
                parsed.get("confidence_in_critique", 0.5)
            ),
            "justification": parsed.get("justification") or "",
        }
    except Exception as exc:
        trace.append(
            f"adversarial_critic: LLM call failed "
            f"({type(exc).__name__}: {exc}), falling back to flag_uncertain"
        )
        return {
            "verdict": "flag_uncertain",
            "issues_found": [
                "LLM reasoning step unavailable; only deterministic Tier 1 "
                "checks were evaluated"
            ],
            "evidence_cited": [],
            "confidence_in_critique": 0.30,
            "justification": (
                "The LLM critique step failed. Tier 1 deterministic checks "
                "passed, but evidence sufficiency could not be independently "
                "evaluated. Low confidence flags the unknown."
            ),
        }


def _find_profile_for_subject(
    profiles: list[dict], subject_id: Optional[str]
) -> Optional[dict]:
    """Match subject_id like '@I0@' against profile subject_record_id like 'gedcom:@I0@'."""
    if not subject_id:
        return None
    for profile in profiles:
        record_id = profile.get("subject_record_id") or ""
        # record_id format is "source:pointer", strip prefix for comparison
        pointer = record_id.split(":", 1)[-1] if ":" in record_id else record_id
        if pointer == subject_id:
            return profile
    return None


def _build_prompt_body(
    isolated_hyp: dict,
    relevant_profile: Optional[dict],
    relevant_records: list[dict],
    tier1_results: list[dict],
    geo_result: Optional[dict],
    dna_relevant: Optional[dict],
) -> str:
    dna_section = ""
    if dna_relevant:
        dna_section = (
            "\nDNA evidence (relevant to this hypothesis only):\n"
            f"{json.dumps(dna_relevant, default=str, indent=2)}\n\n"
            "Interpret the DNA evidence as follows:\n"
            "  - cm_consistency_verdict='supports' means the cM falls within the "
            "expected range for the proposed relationship (positive evidence).\n"
            "  - cm_consistency_verdict='contradicts' means the cM is outside that "
            "range (negative evidence — actively undermines the hypothesis).\n"
            "  - cm_consistency_verdict='no match in DNA list' means the related "
            "person was NOT found in the DNA match list. Treat this as a soft "
            "absence-of-evidence signal: for close relationships (parent, sibling, "
            "1st cousin) it's surprising and arguably negative; for distant "
            "relationships (4th+ cousin) it's unsurprising and not informative.\n"
            "  - DNA cross-references are based on FUZZY name matching against "
            "GEDCOM persons; a match is a candidate, not a confirmed identity.\n"
        )
    return (
        "Isolated hypothesis (reasoning narrative intentionally absent):\n"
        f"{json.dumps(isolated_hyp, default=str, indent=2)}\n\n"
        "Subject profile (facts, gaps, disambiguation):\n"
        f"{json.dumps(relevant_profile, default=str, indent=2)}\n\n"
        "Raw records for subject and related person:\n"
        f"{json.dumps(relevant_records, default=str, indent=2)}\n\n"
        "Tier 1 deterministic check results:\n"
        f"{json.dumps(tier1_results, default=str, indent=2)}\n\n"
        "Geographic plausibility (soft signal):\n"
        f"{json.dumps(geo_result, default=str, indent=2)}\n"
        f"{dna_section}\n"
        "Return your critique JSON now:"
    )


def _strip_markdown_fences(text: str) -> str:
    if text.startswith("```"):
        body = text.strip("`")
        if body.lower().startswith("json"):
            body = body[4:]
        return body.strip()
    return text
