"""Final Report Writer — deterministic, no-LLM node that composes state["final_report"].

This node runs AFTER the Adversarial Critic finalizes (status=="complete") and
before the graph ends. Its only job is to produce a human-readable markdown
summary of the run from the data already in state — it does not interpret,
it does not call the LLM, and it does not add any content not already present
in the profiles, hypotheses, or critiques.

Keeping this as a deterministic node (instead of a post-processor in main.py)
has two advantages:
    1. state["final_report"] is always populated when the graph ends, so any
       caller that invokes the graph gets the complete artifact without extra
       glue code.
    2. The report composition logic is part of the graph and can be traced
       like any other agent step.
"""

from __future__ import annotations

from state import GenealogyState


def final_report_writer_node(state: GenealogyState) -> dict:
    trace = list(state.get("trace_log") or [])
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
# Composition helpers — pure string templating from state.
# ---------------------------------------------------------------------------


def _compose_report(state: GenealogyState) -> str:
    lines: list[str] = []

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
        f"(revision count {state.get('revision_count', 0)})"
    )
    lines.append("")

    _append_profiles_section(lines, state)
    _append_hypotheses_section(lines, state)
    _append_critiques_section(lines, state)

    return "\n".join(lines)


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

        # Disambiguation block: critical for the Critic to audit.
        disamb = profile.get("disambiguation") or {}
        candidates = disamb.get("candidates_considered") or []
        if candidates:
            lines.append("**Disambiguation:** selected from "
                         f"{len(candidates)} candidates")
            for cand in candidates:
                status = cand.get("status", "?")
                marker = "✓" if status == "SELECTED" else "✗"
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


def _append_hypotheses_section(lines: list[str], state: GenealogyState) -> None:
    hypotheses = state.get("hypotheses") or []
    lines.append("## Hypotheses")
    lines.append("")
    if not hypotheses:
        lines.append("_No hypotheses were generated._")
        lines.append("")
        return

    for hyp in hypotheses:
        lines.append(
            f"### {hyp.get('proposed_relationship')} — "
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
                lines.append(
                    f"- ({ev.get('source')}) {ev.get('claim')}"
                )
            lines.append("")

        weaknesses = hyp.get("stated_weaknesses") or []
        if weaknesses:
            lines.append("**Stated weaknesses (Hypothesizer's own):**")
            for weak in weaknesses:
                lines.append(f"- {weak}")
            lines.append("")


def _append_critiques_section(lines: list[str], state: GenealogyState) -> None:
    critiques = state.get("critiques") or []
    lines.append("## Adversarial Critique")
    lines.append("")
    if not critiques:
        lines.append("_No critiques were produced._")
        lines.append("")
        return

    for critique in critiques:
        verdict = critique.get("verdict", "?")
        verdict_marker = {
            "accept": "✓ ACCEPT",
            "reject": "✗ REJECT",
            "flag_uncertain": "? FLAG UNCERTAIN",
        }.get(verdict, verdict.upper())

        lines.append(
            f"### {verdict_marker} — "
            f"`{critique.get('hypothesis_id')}`"
        )
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

        # Deterministic Tier 1 results first (the reproducible audit trail).
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
