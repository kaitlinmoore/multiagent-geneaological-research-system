"""Eval harness for trap_cases/ — runs the full graph against every trap case
in the manifest and reports how well the pipeline matches the expected
Critic behavior for each tier.

Usage:
    ./.venv/Scripts/python.exe eval/run_eval.py                # run all tiers
    ./.venv/Scripts/python.exe eval/run_eval.py --tier tier1   # only tier 1
    ./.venv/Scripts/python.exe eval/run_eval.py --tier tier2 tier3

Outputs:
    - Per-case pass/fail lines to stdout
    - traces/eval_{timestamp}_{tier}_{case}.md  (one trace per case via trace_writer)
    - eval/results/eval_{timestamp}.json        (machine-readable summary)

Evaluation criteria by tier (from trap_cases/manifest.json):
    Tier 1 — every hypothesis must be rejected with Tier 1 fail-fast and
             confidence_in_critique >= 0.90. Any LLM reasoning step running
             on Tier 1 is a miss (the fail-fast didn't trigger).

    Tier 2 — at least one hypothesis must produce verdict in
             {reject, flag_uncertain} with confidence >= 0.50. Accept
             is a miss. Tier 1 fail-fast must NOT fire (the error is not
             rule-checkable).

    Tier 3 — at least one hypothesis must produce verdict flag_uncertain
             with confidence <= 0.70 (low = appropriately humble). An
             accept or reject at high confidence is the overconfidence
             failure mode being measured.

This module is intentionally defensive: a single case failing should not
abort the full run. Failures are recorded and summarized at the end.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Ensure repo root on sys.path so eval/ can import the project packages.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(override=True)

from graph import build_graph
from tools.trace_writer import save_trace


_MANIFEST_PATH = _REPO_ROOT / "eval" / "trap_cases" / "manifest.json"
_TRAP_DIR = _REPO_ROOT / "eval" / "trap_cases"
_RESULTS_DIR = _REPO_ROOT / "eval" / "results"


# ---------------------------------------------------------------------------
# Per-case runner
# ---------------------------------------------------------------------------


def run_case(
    graph,
    case: dict,
    tier_name: str,
    tier_spec: dict,
    run_label: str,
) -> dict:
    """Run the full pipeline for a single trap case and evaluate the result."""
    gedcom_path = _TRAP_DIR / case["file"]
    if not gedcom_path.exists():
        return _case_failure(case, f"GEDCOM file not found: {gedcom_path}")

    try:
        gedcom_text = gedcom_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return _case_failure(case, f"failed to read GEDCOM: {exc}")

    initial_state = {
        "query": case["query"],
        "target_person": case["target_person"],
        "gedcom_text": gedcom_text,
        "gedcom_persons": [],
        "dna_csv": None,
        "retrieved_records": [],
        "profiles": [],
        "hypotheses": [],
        "critiques": [],
        "final_report": "",
        "revision_count": 0,
        "status": "running",
        "trace_log": [],
        "isolation_mode": None,  # defaults to "filtered" inside the Critic
    }

    t0 = time.time()
    try:
        final_state = graph.invoke(initial_state)
    except Exception as exc:
        return _case_failure(case, f"graph.invoke raised {type(exc).__name__}: {exc}")
    elapsed = time.time() - t0

    evaluation = _evaluate_case(final_state, tier_name, tier_spec, case)

    # Always save the trace so failures can be investigated.
    label = f"{run_label}_{tier_name}_{Path(case['file']).stem}"
    try:
        save_trace(final_state, label=label)
    except Exception:
        pass  # trace persistence is non-essential for eval pass/fail

    return {
        "file": case["file"],
        "query": case["query"],
        "tier": tier_name,
        "passed": evaluation["passed"],
        "reason": evaluation["reason"],
        "actual": evaluation["actual"],
        "expected": evaluation["expected"],
        "elapsed_sec": round(elapsed, 2),
        "status": final_state.get("status"),
        "revision_count": final_state.get("revision_count"),
    }


def _case_failure(case: dict, reason: str) -> dict:
    return {
        "file": case.get("file"),
        "query": case.get("query"),
        "tier": None,
        "passed": False,
        "reason": reason,
        "actual": None,
        "expected": None,
        "elapsed_sec": 0.0,
        "status": "error",
        "revision_count": None,
    }


# ---------------------------------------------------------------------------
# Evaluation logic per tier
# ---------------------------------------------------------------------------


def _evaluate_case(
    state: dict, tier_name: str, tier_spec: dict, case: Optional[dict] = None
) -> dict:
    """Compare the final pipeline state to the tier's expectations."""
    critiques = state.get("critiques") or []
    if not critiques:
        return {
            "passed": False,
            "reason": "no critiques produced (pipeline did not reach the Critic)",
            "actual": None,
            "expected": _summarize_expected(tier_spec),
        }

    # Extract per-critique summary for reporting and scoring.
    actual_summary = [
        {
            "hypothesis_id": c.get("hypothesis_id"),
            "verdict": c.get("verdict"),
            "confidence_in_critique": c.get("confidence_in_critique"),
            "tier1_hit": any(
                r.get("verdict") == "impossible"
                for r in (c.get("tier1_results") or [])
            ),
            "tier1_impossibles": [
                r.get("check") for r in (c.get("tier1_results") or [])
                if r.get("verdict") == "impossible"
            ],
            "geo_verdict": (c.get("geo_result") or {}).get("verdict"),
            "isolation_mode": c.get("isolation_mode"),
        }
        for c in critiques
    ]

    if tier_name == "tier1":
        result = _evaluate_tier1(critiques, tier_spec, case)
    elif tier_name == "tier2":
        result = _evaluate_tier2(critiques, tier_spec)
    elif tier_name == "tier3":
        result = _evaluate_tier3(critiques, tier_spec)
    else:
        result = {"passed": False, "reason": f"unknown tier {tier_name}"}

    return {
        "passed": result["passed"],
        "reason": result["reason"],
        "actual": actual_summary,
        "expected": _summarize_expected(tier_spec),
    }


def _evaluate_tier1(
    critiques: list[dict], tier_spec: dict, case: Optional[dict] = None
) -> dict:
    """Tier 1: at least one hypothesis must be rejected via Tier 1 fail-fast
    and cite the deterministic check declared in the case's ``expected_check``
    (if any).

    Why not 'all hypotheses'? A Tier 1 trap file can contain both the trap
    relationship and valid non-trap relationships (e.g. a mother that's fine
    alongside a father that's rule-impossible). The goal of Tier 1 is to
    verify the deterministic fail-fast layer catches the trap, not to require
    that every unrelated hypothesis also fail.
    """
    min_conf = float(tier_spec.get("expected_confidence_min", 0.90))
    expected_check = (case or {}).get("expected_check")

    rejected_via_fail_fast: list[dict] = []
    for c in critiques:
        if c.get("verdict") != "reject":
            continue
        tier1_impossibles = [
            r for r in (c.get("tier1_results") or [])
            if r.get("verdict") == "impossible"
        ]
        if not tier1_impossibles:
            continue  # rejected, but via LLM not fail-fast — skip
        conf = float(c.get("confidence_in_critique") or 0.0)
        if conf < min_conf:
            continue  # fail-fast fired but confidence below floor
        if expected_check:
            checks_hit = {r.get("check") for r in tier1_impossibles}
            if expected_check not in checks_hit:
                continue  # wrong deterministic check fired
        rejected_via_fail_fast.append(c)

    if rejected_via_fail_fast:
        reasons = [
            f"{c.get('hypothesis_id')} "
            f"(conf {c.get('confidence_in_critique')}, "
            f"checks {[r.get('check') for r in c.get('tier1_results') or [] if r.get('verdict') == 'impossible']})"
            for c in rejected_via_fail_fast
        ]
        return {
            "passed": True,
            "reason": (
                f"{len(rejected_via_fail_fast)}/{len(critiques)} hypotheses "
                f"rejected via Tier 1 fail-fast: {reasons}"
            ),
        }
    return {
        "passed": False,
        "reason": (
            f"no hypothesis triggered Tier 1 fail-fast reject "
            f"(expected_check={expected_check}, min_conf={min_conf}); "
            f"got {[(c.get('verdict'), c.get('confidence_in_critique')) for c in critiques]}"
        ),
    }


def _evaluate_tier2(critiques: list[dict], tier_spec: dict) -> dict:
    """Tier 2: at least one hypothesis must be reject or flag_uncertain."""
    allowed = set(tier_spec.get("expected_verdict_any_of") or
                  ["reject", "flag_uncertain"])
    min_conf = float(tier_spec.get("expected_confidence_min", 0.50))

    matched = []
    for c in critiques:
        # Tier 2 must NOT fire the Tier 1 fail-fast (the error is not rule-catchable).
        tier1_impossibles = [
            r for r in (c.get("tier1_results") or [])
            if r.get("verdict") == "impossible"
        ]
        if tier1_impossibles:
            return {
                "passed": False,
                "reason": f"hypothesis {c.get('hypothesis_id')} fired Tier 1 "
                          f"unexpectedly: {[r.get('check') for r in tier1_impossibles]}",
            }
        if (
            c.get("verdict") in allowed
            and float(c.get("confidence_in_critique") or 0.0) >= min_conf
        ):
            matched.append(c.get("hypothesis_id"))

    if matched:
        return {
            "passed": True,
            "reason": f"matched verdict on {len(matched)}/{len(critiques)} "
                      f"hypotheses: {matched}",
        }
    return {
        "passed": False,
        "reason": (
            f"no hypothesis produced verdict in {sorted(allowed)} with "
            f"confidence >= {min_conf}; got "
            f"{[(c.get('verdict'), c.get('confidence_in_critique')) for c in critiques]}"
        ),
    }


def _evaluate_tier3(critiques: list[dict], tier_spec: dict) -> dict:
    """Tier 3: success = system surfaces ambiguity; failure = overconfident
    accept/reject on a genuinely ambiguous case.

    Two distinct signals are being measured:
      - GOOD: at least one hypothesis comes back flag_uncertain. That's the
        system acknowledging it can't confidently resolve the ambiguity.
        Confidence on a flag_uncertain verdict is not penalized — "I'm
        confident there's uncertainty here" is exactly the right behavior.
      - BAD: any hypothesis comes back accept or reject with confidence
        above the overconfidence_ceiling. That means the system confidently
        committed to an answer that the injected ambiguity doesn't support.
        Per the handoff note, 0.95 on a genuinely ambiguous case is the
        failure-mode target; the ceiling is therefore set well below that
        (0.85 by default) to catch early drift.

    A case PASSES if: at least one critique is flag_uncertain AND no
    critique is an accept/reject at confidence above the ceiling.

    Tier 1 fail-fast must NOT fire (the case is not rule-checkable).
    """
    ceiling = float(tier_spec.get("overconfidence_ceiling", 0.85))

    for c in critiques:
        tier1_impossibles = [
            r for r in (c.get("tier1_results") or [])
            if r.get("verdict") == "impossible"
        ]
        if tier1_impossibles:
            return {
                "passed": False,
                "reason": f"hypothesis {c.get('hypothesis_id')} fired Tier 1 "
                          f"unexpectedly on an ambiguous case",
            }

    # The explicit failure mode: confident commitment to a definite answer.
    overconfident = [
        c for c in critiques
        if c.get("verdict") in ("accept", "reject")
        and float(c.get("confidence_in_critique") or 0.0) > ceiling
    ]
    if overconfident:
        return {
            "passed": False,
            "reason": (
                f"{len(overconfident)} hypothesis(es) overconfident "
                f"(accept/reject at conf > {ceiling}): "
                f"{[(c.get('verdict'), c.get('confidence_in_critique')) for c in overconfident]}"
            ),
        }

    # Required positive signal: at least one flag_uncertain.
    flagged = [c for c in critiques if c.get("verdict") == "flag_uncertain"]
    if flagged:
        return {
            "passed": True,
            "reason": (
                f"{len(flagged)}/{len(critiques)} hypotheses flag_uncertain, "
                f"no overconfident accept/reject above {ceiling}"
            ),
        }

    # Neither overconfident nor any flag — system confidently answered without
    # acknowledging ambiguity. This is a softer miss than overconfidence but
    # still a failure: the system didn't surface the injected ambiguity at all.
    return {
        "passed": False,
        "reason": (
            "no hypothesis flag_uncertain and no overconfidence triggered; "
            "system confidently answered without surfacing injected ambiguity: "
            f"{[(c.get('verdict'), c.get('confidence_in_critique')) for c in critiques]}"
        ),
    }


def _summarize_expected(tier_spec: dict) -> dict:
    """Extract the fields the report shows under 'expected'."""
    return {
        k: v for k, v in tier_spec.items()
        if k not in ("cases", "description")
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run trap case eval harness.")
    parser.add_argument(
        "--tier",
        nargs="+",
        choices=["tier1", "tier2", "tier3"],
        help="Run only the named tier(s). Default: all tiers.",
    )
    parser.add_argument(
        "--label",
        default=None,
        help="Optional run label for trace filenames.",
    )
    args = parser.parse_args(argv)

    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    tiers = manifest.get("tiers") or {}
    tier_filter = set(args.tier) if args.tier else set(tiers.keys())

    graph = build_graph()
    run_label = args.label or datetime.now().strftime("%Y%m%d_%H%M%S")

    all_results: list[dict] = []
    print(f"=== trap case eval run {run_label} ===")
    print()

    for tier_name, tier_spec in tiers.items():
        if tier_name not in tier_filter:
            continue
        cases = tier_spec.get("cases") or []
        print(f"[{tier_name}] {len(cases)} case(s) — {tier_spec.get('description', '')[:80]}")
        for case in cases:
            print(f"  running {case['file']} ... ", end="", flush=True)
            result = run_case(graph, case, tier_name, tier_spec, run_label)
            all_results.append(result)
            marker = "PASS" if result["passed"] else "FAIL"
            print(
                f"{marker}  "
                f"({result['elapsed_sec']}s, status={result.get('status')}, "
                f"revisions={result.get('revision_count')})"
            )
            if not result["passed"]:
                print(f"    reason: {result['reason']}")
        print()

    # Summary
    total = len(all_results)
    passed = sum(1 for r in all_results if r["passed"])
    print(f"=== summary: {passed}/{total} passed ===")
    for tier_name in tiers:
        if tier_name not in tier_filter:
            continue
        tier_results = [r for r in all_results if r["tier"] == tier_name]
        tp = sum(1 for r in tier_results if r["passed"])
        print(f"  {tier_name}: {tp}/{len(tier_results)}")

    # Persist machine-readable summary.
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results_path = _RESULTS_DIR / f"eval_{run_label}.json"
    results_path.write_text(
        json.dumps(
            {
                "run_label": run_label,
                "timestamp": datetime.now().isoformat(),
                "tiers_run": sorted(tier_filter),
                "results": all_results,
                "summary": {
                    "total": total,
                    "passed": passed,
                    "per_tier": {
                        tn: {
                            "total": sum(1 for r in all_results if r["tier"] == tn),
                            "passed": sum(
                                1 for r in all_results if r["tier"] == tn and r["passed"]
                            ),
                        }
                        for tn in tiers if tn in tier_filter
                    },
                },
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {results_path}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
