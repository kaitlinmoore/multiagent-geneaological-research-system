"""Final Report Writer — deterministic, no-LLM node that composes state["final_report"].

This node runs AFTER the Adversarial Critic finalizes (status=="complete") and
before the graph ends. Its only job is to produce a human-readable markdown
summary of the run from the data already in state — it does not interpret,
it does not call the LLM, and it does not add any content not already present
in the profiles, hypotheses, or critiques.

Human escalation conditions (added for Phase 2 feedback):
    The report checks three triggers that flag a hypothesis for human review
    rather than silently publishing unresolved findings:
      1. Force-finalized after max revisions (Critic rejected, pipeline gave up)
      2. Low Critic confidence on accept (confidence_in_critique < 0.60)
      3. Conflicting verdicts for the same subject (family unit inconsistency)

    Flagged hypotheses are rendered in a separate "Findings Requiring Human
    Review" section with explicit escalation reasons. No evidence is suppressed
    — the user sees everything, with the quality signal made unmistakable.
"""

from __future__ import annotations

from typing import Optional

from state import GenealogyState


# Threshold below which an "accept" verdict is considered low-confidence.
_LOW_CONFIDENCE_ACCEPT_THRESHOLD = 0.60

# Minimum revision_count that signals force-finalization occurred.
_FORCE_FINALIZE_REVISION_FLOOR = 2


def final_report_writer_node(state: GenealogyState) -> dict:
    trace: list[str] = []
    trace.append("final_report_writer: enter")

    report = _compose_report(state)

    trace.append(
        f"final_report_writer: composed report "
        f"({len(report)} chars, {report.count(chr(10)) + 1} lines)"
    )
    trace.append("final_report_writer: exit")

    return {
        "final_report": report,
        "trace_log": trace,
    }


# ---------------------------------------------------------------------------
# Human escalation logic
# ---------------------------------------------------------------------------


def check_escalation(
    hypotheses: list[dict],
    critiques: list[dict],
    revision_count: int,
) -> list[dict]:
    """Evaluate each hypothesis for human-escalation triggers.

    Returns one entry per hypothesis:
        {
            "hypothesis_id": str,
            "escalation_flag": bool,
            "escalation_reasons": list[str],
        }

    Three triggers (any one flags the hypothesis):
      1. Force-finalized: matching critique verdict=="reject" AND
         revision_count >= _FORCE_FINALIZE_REVISION_FLOOR.
      2. Low-confidence accept: matching critique verdict=="accept" AND
         confidence_in_critique < _LOW_CONFIDENCE_ACCEPT_THRESHOLD.
      3. Conflicting verdicts for the same subject_id: one hypothesis
         accepted while another is rejected — flags ALL hypotheses in
         the conflicting group. A mix of accept + flag_uncertain is
         normal (the Critic is more confident about some relationships
         than others) and does NOT trigger escalation.
    """
    critique_by_id: dict[str, dict] = {
        c.get("hypothesis_id", ""): c for c in critiques
    }

    # First pass: per-hypothesis triggers 1 and 2.
    escalations: list[dict] = []
    for hyp in hypotheses:
        hyp_id = hyp.get("hypothesis_id", "")
        critique = critique_by_id.get(hyp_id)
        reasons: list[str] = []

        if critique:
            verdict = critique.get("verdict")
            conf = float(critique.get("confidence_in_critique") or 0.0)

            # Trigger 1: force-finalized after max revisions.
            if verdict == "reject" and revision_count >= _FORCE_FINALIZE_REVISION_FLOOR:
                reasons.append(
                    f"Rejected by Adversarial Critic after "
                    f"{revision_count} revision cycle(s) "
                    f"— pipeline force-finalized"
                )

            # Trigger 2: low-confidence accept.
            if verdict == "accept" and conf < _LOW_CONFIDENCE_ACCEPT_THRESHOLD:
                reasons.append(
                    f"Critic accepted with low confidence "
                    f"({conf:.2f}) — below {_LOW_CONFIDENCE_ACCEPT_THRESHOLD} "
                    f"threshold"
                )

        escalations.append({
            "hypothesis_id": hyp_id,
            "escalation_flag": bool(reasons),
            "escalation_reasons": reasons,
        })

    # Second pass: trigger 3 — conflicting verdicts for the same subject.
    by_subject: dict[str, list[int]] = {}
    for idx, hyp in enumerate(hypotheses):
        subject_id = hyp.get("subject_id", "")
        by_subject.setdefault(subject_id, []).append(idx)

    for subject_id, indices in by_subject.items():
        if len(indices) < 2:
            continue

        verdicts_in_group: set[str] = set()
        for idx in indices:
            hyp_id = hypotheses[idx].get("hypothesis_id", "")
            critique = critique_by_id.get(hyp_id)
            if critique:
                verdicts_in_group.add(critique.get("verdict", ""))

        has_accept = "accept" in verdicts_in_group
        has_reject = "reject" in verdicts_in_group

        if has_accept and has_reject:
            reason = (
                f"Conflicting verdicts for subject {subject_id}: "
                f"family unit has both accepted and "
                f"rejected hypotheses "
                f"({sorted(verdicts_in_group)})"
            )
            for idx in indices:
                esc = escalations[idx]
                if reason not in esc["escalation_reasons"]:
                    esc["escalation_reasons"].append(reason)
                    esc["escalation_flag"] = True

    return escalations


# ---------------------------------------------------------------------------
# Report composition
# ---------------------------------------------------------------------------


def _compose_report(state: GenealogyState) -> str:
    lines: list[str] = []
    hypotheses = state.get("hypotheses") or []
    critiques = state.get("critiques") or []
    revision_count = int(state.get("revision_count") or 0)

    escalations = check_escalation(hypotheses, critiques, revision_count)
    esc_by_id = {e["hypothesis_id"]: e for e in escalations}
    any_escalated = any(e["escalation_flag"] for e in escalations)

    # --- Header ---
    lines.append("# Genealogical Research Report")
    lines.append("")
    lines.append(f"**Query:** {state.get('query', '(no query)')}")

    target = state.get("target_person") or {}
    if isinstance(target, dict):
        target_desc = target.get("name") or str(target)
        if target.get("approx_birth"):
            target_desc += f" (approx. born {target['approx_birth']})"
        if target.get("location"):
            target_desc += f", {target['location']}"
    else:
        target_desc = str(target)
    lines.append(f"**Target:** {target_desc}")

    lines.append(
        f"**Pipeline status:** {state.get('status', 'unknown')}  "
        f"(revision count {revision_count})"
    )

    if any_escalated:
        escalated_count = sum(1 for e in escalations if e["escalation_flag"])
        lines.append(
            f"**Report status: Contains unresolved findings "
            f"— human review recommended** "
            f"({escalated_count} of {len(escalations)} hypotheses flagged)"
        )
    else:
        lines.append("**Report status: All findings accepted**")
    lines.append("")

    # --- Profiles (unchanged) ---
    _append_profiles_section(lines, state)

    # --- Split findings into accepted vs. escalated ---
    critique_by_id = {c.get("hypothesis_id", ""): c for c in critiques}

    accepted = [
        (hyp, critique_by_id.get(hyp.get("hypothesis_id", "")))
        for hyp in hypotheses
        if not esc_by_id.get(hyp.get("hypothesis_id", ""), {}).get(
            "escalation_flag"
        )
    ]
    escalated = [
        (
            hyp,
            critique_by_id.get(hyp.get("hypothesis_id", "")),
            esc_by_id.get(hyp.get("hypothesis_id", ""), {}),
        )
        for hyp in hypotheses
        if esc_by_id.get(hyp.get("hypothesis_id", ""), {}).get(
            "escalation_flag"
        )
    ]

    # --- Accepted findings ---
    lines.append("## Accepted Findings")
    lines.append("")
    if accepted:
        for hyp, critique in accepted:
            _render_finding(lines, hyp, critique)
    else:
        lines.append("_No findings passed without escalation flags._")
        lines.append("")

    # --- Findings requiring human review ---
    if escalated:
        lines.append("## Findings Requiring Human Review")
        lines.append("")
        for hyp, critique, esc in escalated:
            _render_escalated_finding(lines, hyp, critique, esc)

    # --- DNA Evidence (when available) ---
    _append_dna_section(lines, state)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Per-finding rendering (hypothesis + its critique together)
# ---------------------------------------------------------------------------


def _render_finding(
    lines: list[str],
    hyp: dict,
    critique: Optional[dict],
) -> None:
    """Render one accepted finding: hypothesis block + critique block."""
    _render_hypothesis_block(lines, hyp)
    if critique:
        _render_critique_block(lines, critique)


def _render_escalated_finding(
    lines: list[str],
    hyp: dict,
    critique: Optional[dict],
    esc: dict,
) -> None:
    """Render one escalated finding with visual marker and reasons."""
    hyp_id = hyp.get("hypothesis_id", "")
    relationship = hyp.get("proposed_relationship", "")

    lines.append(
        f"### \u26a0 UNRESOLVED — {relationship} — `{hyp_id}`"
    )
    lines.append("")

    reasons = esc.get("escalation_reasons") or []
    if reasons:
        lines.append("**Escalation reasons:**")
        for reason in reasons:
            lines.append(f"- {reason}")
        lines.append("")

    _render_hypothesis_block(lines, hyp, heading_level=4)
    if critique:
        _render_critique_block(lines, critique, heading_level=4)


def _render_hypothesis_block(
    lines: list[str],
    hyp: dict,
    heading_level: int = 3,
) -> None:
    """Render a hypothesis block (evidence chain + weaknesses)."""
    prefix = "#" * heading_level

    # Only emit the heading when rendering inside Accepted Findings
    # (escalated findings already have their own heading).
    if heading_level == 3:
        lines.append(
            f"{prefix} {hyp.get('proposed_relationship')} — "
            f"`{hyp.get('hypothesis_id')}`"
        )

    lines.append(
        f"**Subject:** `{hyp.get('subject_id')}`  "
        f"**Related:** `{hyp.get('related_id')}`  "
        f"**Hypothesizer confidence:** {hyp.get('confidence_score')}"
    )
    lines.append("")

    evidence_chain = hyp.get("evidence_chain") or []
    if evidence_chain:
        lines.append("**Evidence chain:**")
        for ev in evidence_chain:
            lines.append(f"- ({ev.get('source')}) {ev.get('claim')}")
        lines.append("")

    weaknesses = hyp.get("stated_weaknesses") or []
    if weaknesses:
        lines.append("**Stated weaknesses (Hypothesizer's own):**")
        for weak in weaknesses:
            lines.append(f"- {weak}")
        lines.append("")


def _render_critique_block(
    lines: list[str],
    critique: dict,
    heading_level: int = 3,
) -> None:
    """Render a critique block (verdict, tier1, geo, issues)."""
    prefix = "#" * heading_level
    verdict = critique.get("verdict", "?")
    verdict_marker = {
        "accept": "\u2713 ACCEPT",
        "reject": "\u2717 REJECT",
        "flag_uncertain": "? FLAG UNCERTAIN",
    }.get(verdict, verdict.upper())

    lines.append(f"{prefix} Critique: {verdict_marker}")
    lines.append(
        f"**Critic self-confidence:** "
        f"{critique.get('confidence_in_critique')}  "
        f"**Isolation mode:** `{critique.get('isolation_mode', '?')}`"
    )
    lines.append("")

    justification = critique.get("justification")
    if justification:
        lines.append(f"**Justification:** {justification}")
        lines.append("")

    tier1 = critique.get("tier1_results") or []
    if tier1:
        lines.append("**Tier 1 deterministic checks:**")
        for result in tier1:
            role = f" [{result.get('role')}]" if result.get("role") else ""
            lines.append(
                f"- [{result.get('verdict')}]{role} "
                f"{result.get('check')}: {result.get('reason')}"
            )
        lines.append("")

    geo = critique.get("geo_result")
    if geo:
        lines.append(
            f"**Geographic check:** [{geo.get('verdict')}] "
            f"{geo.get('reason')}"
        )
        lines.append("")

    issues = critique.get("issues_found") or []
    if issues:
        lines.append("**Issues found by the Critic:**")
        for issue in issues:
            lines.append(f"- {issue}")
        lines.append("")


# ---------------------------------------------------------------------------
# Profiles section (unchanged from original)
# ---------------------------------------------------------------------------


def _append_profiles_section(lines: list[str], state: GenealogyState) -> None:
    profiles = state.get("profiles") or []
    lines.append("## Subject Profiles")
    lines.append("")
    if not profiles:
        lines.append("_No profiles were synthesized._")
        lines.append("")
        return

    for profile in profiles:
        lines.append(f"### {profile.get('subject_name') or '(unnamed)'}")
        lines.append(
            f"`{profile.get('profile_id')}` — source record "
            f"`{profile.get('subject_record_id')}`"
        )
        lines.append("")

        disamb = profile.get("disambiguation") or {}
        candidates = disamb.get("candidates_considered") or []
        if candidates:
            lines.append(
                "**Disambiguation:** selected from "
                f"{len(candidates)} candidates"
            )
            for cand in candidates:
                status = cand.get("status", "?")
                marker = "\u2713" if status == "SELECTED" else "\u2717"
                lines.append(
                    f"- {marker} `{cand.get('record_id')}` "
                    f"{cand.get('name')} — score {cand.get('score')}"
                )
                for reason in cand.get("reasons") or []:
                    lines.append(f"    - {reason}")
            lines.append("")

        facts = profile.get("facts") or []
        if facts:
            lines.append("**Facts:**")
            for fact in facts:
                sources = ", ".join(fact.get("sources") or [])
                lines.append(
                    f"- {fact.get('field')}: {fact.get('value')}  "
                    f"_({sources})_"
                )
            lines.append("")

        family = profile.get("family") or {}
        family_bits: list[str] = []
        if family.get("father"):
            family_bits.append(f"father={family['father']['name']}")
        if family.get("mother"):
            family_bits.append(f"mother={family['mother']['name']}")
        if family.get("spouses"):
            spouses = ", ".join(s["name"] for s in family["spouses"])
            family_bits.append(f"spouse(s)={spouses}")
        if family.get("children"):
            children = ", ".join(c["name"] for c in family["children"])
            family_bits.append(f"children={children}")
        if family_bits:
            lines.append("**Family references:** " + "; ".join(family_bits))
            lines.append("")

        gaps = profile.get("gaps") or []
        if gaps:
            lines.append("**Gaps and concerns (from Synthesizer):**")
            for gap in gaps:
                lines.append(f"- {gap}")
            lines.append("")


# ---------------------------------------------------------------------------
# DNA Evidence section
# ---------------------------------------------------------------------------


def _append_dna_section(lines: list[str], state: GenealogyState) -> None:
    dna = state.get("dna_analysis")
    if not dna:
        return  # no DNA data — skip section entirely

    lines.append("## DNA Evidence")
    lines.append("")
    lines.append(
        f"**Platform:** {dna.get('platform', 'unknown')}  "
        f"**Total matches:** {dna.get('total_matches', 0)}  "
        f"**Consistency:** {dna.get('aggregate_consistency', 'unknown')}"
    )
    lines.append("")

    # Match distribution.
    dist = dna.get("relationship_distribution") or {}
    if dist:
        lines.append("**Match distribution by relationship tier:**")
        for tier, count in dist.items():
            if count:
                lines.append(f"- {tier}: {count}")
        lines.append("")

    # Cross-references.
    cross_refs = dna.get("cross_references") or []
    if cross_refs:
        lines.append(
            f"**GEDCOM cross-references ({len(cross_refs)} name matches):**"
        )
        for xr in cross_refs:
            lines.append(
                f"- DNA: **{xr.get('dna_name')}** ({xr.get('shared_cM')} cM) "
                f"matched GEDCOM: **{xr.get('gedcom_name')}** "
                f"(`{xr.get('gedcom_id')}`)"
            )
            lines.append(
                f"  - DNA-predicted: {xr.get('dna_predicted_relationship')} "
                f"| Platform said: {xr.get('platform_prediction')} "
                f"| Consistent: {xr.get('platform_consistent')}"
            )
        lines.append("")

    # Platform prediction checks.
    pc = dna.get("prediction_checks") or {}
    if pc.get("total_with_prediction"):
        lines.append(
            f"**Platform prediction consistency:** "
            f"{pc.get('consistent', 0)}/{pc.get('total_with_prediction', 0)} "
            f"consistent with Shared cM Project ranges"
        )
        incon = pc.get("inconsistent_examples") or []
        if incon:
            lines.append("Inconsistent examples:")
            for ex in incon[:3]:
                lines.append(
                    f"- {ex.get('name')}: {ex.get('shared_cM')} cM, "
                    f"platform said '{ex.get('platform_said')}' — "
                    f"{ex.get('deviation')}"
                )
        lines.append("")

    # Findings.
    findings = dna.get("findings") or []
    if findings:
        lines.append("**Findings:**")
        for f in findings:
            lines.append(f"- {f}")
        lines.append("")
