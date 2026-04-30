"""Hypothesis dict schema and Critic-isolation filter.

This module is the single point of enforcement for the Critic isolation
constraint: the Critic receives the hypothesis and raw evidence ONLY —
never the Hypothesizer's reasoning chain. This prevents confirmation
bias and is the core agentic justification for the project; it must be
preserved in implementation.

A hypothesis dict has TWO explicitly-declared field sets:

1. PUBLIC fields — visible to the Critic via filter_hypothesis_for_critic():
       hypothesis_id          administrative key, stable for trace/A-B experiments
       subject_id             GEDCOM pointer of the subject person (e.g. "@I0@")
       related_id             GEDCOM pointer of the related person
       proposed_relationship  short label (e.g. "father of", "mother of")
       evidence_chain         list of cited facts [{claim, source}]
       confidence_score       float 0..1
       stated_weaknesses      list[str] the Hypothesizer acknowledges as limitations

2. INTERNAL fields — STRIPPED before the Critic sees them:
       reasoning_narrative     free-text explanation of how the Hypothesizer
                               connected the evidence
       intermediate_steps      list of structured thinking steps (optional)
       alternatives_considered list of alternative interpretations the Hypothesizer
                               weighed before committing

Enforcement rule:
    The Adversarial Critic node MUST call filter_hypothesis_for_critic() when
    reading state["hypotheses"]. It must NEVER access raw hypothesis dicts
    directly. This is the sole integrity boundary between the two agents.

A/B experiment hook:
    The planned Critic-isolation A/B experiment toggles between two conditions:
        Condition A (default): Critic uses filter_hypothesis_for_critic()
        Condition B (relaxed): Critic skips the filter and reads raw dicts
    Because the filter is an explicit one-line function call, switching between
    conditions is a single code change in the Critic node. Do not scatter
    hypothesis-reading logic elsewhere or the experiment becomes unreliable.
"""

from __future__ import annotations

from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# Field declarations — the authoritative partition of hypothesis keys.
# ---------------------------------------------------------------------------

PUBLIC_HYPOTHESIS_FIELDS: frozenset[str] = frozenset(
    {
        "hypothesis_id",
        "subject_id",
        "related_id",
        "proposed_relationship",
        "evidence_chain",
        "confidence_score",
        "stated_weaknesses",
    }
)

INTERNAL_HYPOTHESIS_FIELDS: frozenset[str] = frozenset(
    {
        "reasoning_narrative",
        "intermediate_steps",
        "alternatives_considered",
        "llm_raw_response",
    }
)


# ---------------------------------------------------------------------------
# The Critic-isolation filter — the ONE place this invariant is enforced.
# ---------------------------------------------------------------------------


def filter_hypothesis_for_critic(hypothesis: dict) -> dict:
    """Return a shallow copy of ``hypothesis`` containing only PUBLIC fields.

    The Adversarial Critic MUST use this function when reading any hypothesis.
    It strips every field not in ``PUBLIC_HYPOTHESIS_FIELDS``, including any
    unknown keys that might be added later. This fails SAFE: a new internal
    field added to the Hypothesizer without updating PUBLIC_HYPOTHESIS_FIELDS
    is automatically hidden from the Critic.

    This function is the toggle point for the Critic-isolation A/B experiment:

        # Condition A (default, isolated)
        for h in state["hypotheses"]:
            view = filter_hypothesis_for_critic(h)
            ...

        # Condition B (relaxed, full context)
        for h in state["hypotheses"]:
            view = h
            ...
    """
    return {
        key: value
        for key, value in hypothesis.items()
        if key in PUBLIC_HYPOTHESIS_FIELDS
    }


def filter_hypotheses_for_critic(hypotheses: Iterable[dict]) -> list[dict]:
    """Batch convenience: filter every hypothesis in a list."""
    return [filter_hypothesis_for_critic(h) for h in hypotheses]


# ---------------------------------------------------------------------------
# Constructor — forces callers to populate both public and internal fields.
# ---------------------------------------------------------------------------


def make_hypothesis(
    *,
    subject_id: str,
    related_id: str,
    proposed_relationship: str,
    evidence_chain: list[dict],
    confidence_score: float,
    stated_weaknesses: list[str],
    reasoning_narrative: str,
    intermediate_steps: Optional[list] = None,
    alternatives_considered: Optional[list] = None,
    hypothesis_id: Optional[str] = None,
    llm_raw_response: Optional[str] = None,
) -> dict:
    """Build a well-formed hypothesis dict with both public and internal fields.

    Using this constructor (rather than building dicts inline) makes the
    public/internal boundary visible at every hypothesis-creation site.
    All PUBLIC fields are keyword-only and required. INTERNAL fields may be
    omitted but default to empty containers, never None, so the shape is
    stable for downstream consumers that expect them to exist.

    Returns:
        dict with all keys from both PUBLIC_HYPOTHESIS_FIELDS and
        INTERNAL_HYPOTHESIS_FIELDS populated.
    """
    hypothesis = {
        # --- PUBLIC (visible to Critic via filter) ---
        "hypothesis_id": hypothesis_id or f"hyp:{subject_id}:{related_id}",
        "subject_id": subject_id,
        "related_id": related_id,
        "proposed_relationship": proposed_relationship,
        "evidence_chain": evidence_chain,
        "confidence_score": float(confidence_score),
        "stated_weaknesses": stated_weaknesses,
        # --- INTERNAL (stripped before Critic sees it) ---
        "reasoning_narrative": reasoning_narrative,
        "intermediate_steps": intermediate_steps or [],
        "alternatives_considered": alternatives_considered or [],
        "llm_raw_response": llm_raw_response or "",
    }
    return hypothesis


# ---------------------------------------------------------------------------
# Self-test — runnable as a script to verify the filter is sound.
# ---------------------------------------------------------------------------


def _self_test() -> None:
    """Run basic invariant checks on the filter. Raises AssertionError on failure."""
    # Filter must strip every internal field.
    sample = make_hypothesis(
        subject_id="@I0@",
        related_id="@I1@",
        proposed_relationship="father of",
        evidence_chain=[{"claim": "test", "source": "gedcom:@I0@"}],
        confidence_score=0.9,
        stated_weaknesses=["only one source"],
        reasoning_narrative="SECRET reasoning that must not leak to Critic",
        intermediate_steps=[{"step": 1, "thought": "more secrets"}],
        alternatives_considered=["uncle_pretending_to_be_father"],
    )

    filtered = filter_hypothesis_for_critic(sample)

    # Every public field present.
    assert set(filtered.keys()) == PUBLIC_HYPOTHESIS_FIELDS, (
        f"expected {PUBLIC_HYPOTHESIS_FIELDS}, got {set(filtered.keys())}"
    )

    # No internal field leaks.
    for forbidden in INTERNAL_HYPOTHESIS_FIELDS:
        assert forbidden not in filtered, (
            f"INTERNAL field '{forbidden}' leaked through filter"
        )

    # Specifically check that the reasoning narrative content is gone.
    for value in filtered.values():
        if isinstance(value, str):
            assert "SECRET" not in value
            assert "secrets" not in value

    # Public and internal sets must not overlap — if they do, filter is ambiguous.
    overlap = PUBLIC_HYPOTHESIS_FIELDS & INTERNAL_HYPOTHESIS_FIELDS
    assert not overlap, f"PUBLIC and INTERNAL fields overlap: {overlap}"

    print("hypothesis_schema self-test OK")


if __name__ == "__main__":
    _self_test()
