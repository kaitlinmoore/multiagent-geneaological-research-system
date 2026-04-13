"""Critic-isolation A/B experiment.

Runs the full pipeline twice on the same input:
    Condition A (filtered):   state["isolation_mode"] = "filtered"
                              Critic reads hypotheses through
                              filter_hypothesis_for_critic() — the design
                              invariant from CLAUDE.md.
    Condition B (unfiltered): state["isolation_mode"] = "unfiltered"
                              Critic reads raw hypothesis dicts including
                              reasoning_narrative, alternatives_considered,
                              intermediate_steps, and llm_raw_response.

Both runs share the SAME seed hypothesis batch. Without this, each run
generates its own hypotheses (and the LLM is non-deterministic), so any
difference in critique verdicts is confounded with hypothesis drift.
The harness therefore:
    1. Runs the Record Scout → Profile Synthesizer → Hypothesizer chain once.
    2. Snapshots the resulting state.
    3. Invokes the Adversarial Critic node twice, once with each isolation_mode.
    4. Compares the two critique outputs on verdict, confidence, issues, and
       the justification/issue_found text (to detect whether Condition B
       parrots the Hypothesizer's reasoning narrative).

Metrics compared:
    - verdict distribution
    - confidence_in_critique per hypothesis
    - issues_found count
    - reasoning_leakage_score: crude signal — count unique phrases from the
      Hypothesizer's reasoning_narrative that appear verbatim (>=5 tokens)
      in the Critic's justification or issues_found text. If Condition B
      parrots reasoning, this score will be higher than Condition A.

Run:
    ./.venv/Scripts/python.exe eval/isolation_experiment.py

Output:
    eval/results/isolation_{timestamp}.json   machine-readable comparison
    traces/trace_..._isolation_a.{json,md}    full trace of Condition A
    traces/trace_..._isolation_b.{json,md}    full trace of Condition B
"""

from __future__ import annotations

import copy
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(override=True)

from agents.adversarial_critic import adversarial_critic_node
from agents.final_report_writer import final_report_writer_node
from agents.profile_synthesizer import profile_synthesizer_node
from agents.record_scout import record_scout_node
from agents.relationship_hypothesizer import relationship_hypothesizer_node
from tools.trace_writer import save_trace


_DEFAULT_GEDCOM = _REPO_ROOT / "data" / "The Kennedy Family.ged"
_DEFAULT_QUERY = "Who were the parents of John F. Kennedy?"
_DEFAULT_TARGET = {
    "name": "John F. Kennedy",
    "approx_birth": "1917",
    "location": "Brookline, MA",
}
_RESULTS_DIR = _REPO_ROOT / "eval" / "results"


# Named presets so multi-query A/B runs stay reproducible and command-line
# invocation is painless. Each preset fully specifies a single experiment
# run: GEDCOM path, research query, and target_person dict.
_PRESETS: dict[str, dict] = {
    "jfk": {
        "gedcom": _REPO_ROOT / "data" / "The Kennedy Family.ged",
        "query": "Who were the parents of John F. Kennedy?",
        "target_person": {
            "name": "John F. Kennedy",
            "approx_birth": "1917",
            "location": "Brookline, MA",
        },
    },
    "tier2_surname": {
        "gedcom": _REPO_ROOT / "eval" / "trap_cases" / "tier2_surname_mismatch.ged",
        "query": "Who are the parents of Lucia Rossi?",
        "target_person": {
            "name": "Lucia Rossi",
            "approx_birth": "1890",
            "location": "Florence, Italy",
        },
    },
    "tier3_joseph": {
        "gedcom": _REPO_ROOT / "eval" / "trap_cases" / "tier3_kennedy_ambiguous_joseph.ged",
        "query": "Who are the parents of Joseph Patrick Kennedy born around 1888 in Massachusetts?",
        "target_person": {
            "name": "Joseph Patrick Kennedy",
            "approx_birth": "1888",
            "location": "Massachusetts",
        },
    },
}


# ---------------------------------------------------------------------------
# Run both conditions against the same seed state
# ---------------------------------------------------------------------------


def run_experiment(
    gedcom_path: Path = _DEFAULT_GEDCOM,
    query: str = _DEFAULT_QUERY,
    target_person: dict = _DEFAULT_TARGET,
    preset_name: str = "custom",
) -> dict:
    print(f"=== Critic isolation A/B experiment ===")
    print(f"Preset:     {preset_name}")
    print(f"GEDCOM:     {gedcom_path.name}")
    print(f"Query:      {query}")
    print(f"Target:     {target_person}")
    print()

    gedcom_text = gedcom_path.read_text(encoding="utf-8", errors="replace")
    base_state = _initial_state(query, target_person, gedcom_text)

    # Run the pre-Critic chain once. The resulting state is the seed both
    # conditions will critique — this controls for hypothesis-generation drift.
    print("Building shared seed state (Scout -> Synthesizer -> Hypothesizer)...")
    t0 = time.time()
    seed = record_scout_node(base_state)
    seed_state = {**base_state, **seed}
    seed = profile_synthesizer_node(seed_state)
    seed_state = {**seed_state, **seed}
    seed = relationship_hypothesizer_node(seed_state)
    seed_state = {**seed_state, **seed}
    t_seed = time.time() - t0
    print(
        f"  seed: {len(seed_state.get('hypotheses') or [])} hypotheses "
        f"generated in {t_seed:.1f}s"
    )
    print()

    if not seed_state.get("hypotheses"):
        raise RuntimeError("Seed state has no hypotheses; cannot run experiment")

    # Condition A: filtered (default Critic isolation mode)
    print("Running Condition A (isolation_mode=filtered)...")
    state_a = copy.deepcopy(seed_state)
    state_a["isolation_mode"] = "filtered"
    t0 = time.time()
    critic_a = adversarial_critic_node(state_a)
    state_a = {**state_a, **critic_a}
    t_a = time.time() - t0
    state_a = {**state_a, **final_report_writer_node(state_a)}
    print(
        f"  condition A: {len(state_a['critiques'])} critiques in {t_a:.1f}s"
    )

    # Condition B: unfiltered (raw hypothesis dicts visible to Critic)
    print("Running Condition B (isolation_mode=unfiltered)...")
    state_b = copy.deepcopy(seed_state)
    state_b["isolation_mode"] = "unfiltered"
    t0 = time.time()
    critic_b = adversarial_critic_node(state_b)
    state_b = {**state_b, **critic_b}
    t_b = time.time() - t0
    state_b = {**state_b, **final_report_writer_node(state_b)}
    print(
        f"  condition B: {len(state_b['critiques'])} critiques in {t_b:.1f}s"
    )
    print()

    # Persist both full traces.
    run_label = datetime.now().strftime("%Y%m%d_%H%M%S")
    trace_prefix = f"{run_label}_isolation_{preset_name}"
    save_trace(state_a, label=f"{trace_prefix}_a")
    save_trace(state_b, label=f"{trace_prefix}_b")

    comparison = compare_critiques(
        seed_hypotheses=seed_state["hypotheses"],
        critiques_a=state_a["critiques"],
        critiques_b=state_b["critiques"],
    )

    print("=== comparison ===")
    for entry in comparison["per_hypothesis"]:
        print(
            f"  {entry['hypothesis_id']}"
        )
        print(
            f"    A: verdict={entry['a']['verdict']:<14} "
            f"conf={entry['a']['confidence_in_critique']}  "
            f"issues={entry['a']['issues_count']}  "
            f"leakage={entry['a']['reasoning_leakage_score']}"
        )
        print(
            f"    B: verdict={entry['b']['verdict']:<14} "
            f"conf={entry['b']['confidence_in_critique']}  "
            f"issues={entry['b']['issues_count']}  "
            f"leakage={entry['b']['reasoning_leakage_score']}"
        )
        print(
            f"    delta: verdict_changed={entry['verdict_changed']}  "
            f"conf_delta={entry['confidence_delta']:+.2f}  "
            f"leakage_delta={entry['leakage_delta']:+d}"
        )

    # Persist machine-readable comparison.
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path = _RESULTS_DIR / f"isolation_{run_label}_{preset_name}.json"
    result_path.write_text(
        json.dumps(
            {
                "run_label": run_label,
                "preset": preset_name,
                "timestamp": datetime.now().isoformat(),
                "gedcom": str(gedcom_path.name),
                "query": query,
                "target_person": target_person,
                "seed": {
                    "hypothesis_count": len(seed_state["hypotheses"]),
                    "profile_count": len(seed_state.get("profiles") or []),
                    "retrieved_record_count": len(
                        seed_state.get("retrieved_records") or []
                    ),
                    "elapsed_sec": round(t_seed, 2),
                },
                "condition_a": {
                    "isolation_mode": "filtered",
                    "elapsed_sec": round(t_a, 2),
                    "critiques": state_a["critiques"],
                },
                "condition_b": {
                    "isolation_mode": "unfiltered",
                    "elapsed_sec": round(t_b, 2),
                    "critiques": state_b["critiques"],
                },
                "comparison": comparison,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print()
    print(f"wrote {result_path}")
    return {
        "result_path": str(result_path),
        "comparison": comparison,
    }


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------


def compare_critiques(
    seed_hypotheses: list[dict],
    critiques_a: list[dict],
    critiques_b: list[dict],
) -> dict:
    """Produce a per-hypothesis comparison dict of A vs B critique outputs."""
    a_by_id = {c.get("hypothesis_id"): c for c in critiques_a}
    b_by_id = {c.get("hypothesis_id"): c for c in critiques_b}

    per_hypothesis: list[dict] = []
    for hyp in seed_hypotheses:
        hyp_id = hyp.get("hypothesis_id")
        reasoning = hyp.get("reasoning_narrative") or ""
        ca = a_by_id.get(hyp_id) or {}
        cb = b_by_id.get(hyp_id) or {}

        a_stats = _critique_stats(ca, reasoning)
        b_stats = _critique_stats(cb, reasoning)

        per_hypothesis.append(
            {
                "hypothesis_id": hyp_id,
                "a": a_stats,
                "b": b_stats,
                "verdict_changed": a_stats["verdict"] != b_stats["verdict"],
                "confidence_delta": round(
                    (b_stats["confidence_in_critique"] or 0.0)
                    - (a_stats["confidence_in_critique"] or 0.0),
                    3,
                ),
                "leakage_delta": (
                    b_stats["reasoning_leakage_score"]
                    - a_stats["reasoning_leakage_score"]
                ),
            }
        )

    total_leakage_a = sum(
        entry["a"]["reasoning_leakage_score"] for entry in per_hypothesis
    )
    total_leakage_b = sum(
        entry["b"]["reasoning_leakage_score"] for entry in per_hypothesis
    )
    any_verdict_changed = any(e["verdict_changed"] for e in per_hypothesis)

    return {
        "per_hypothesis": per_hypothesis,
        "aggregate": {
            "total_reasoning_leakage_a": total_leakage_a,
            "total_reasoning_leakage_b": total_leakage_b,
            "any_verdict_changed": any_verdict_changed,
            "leakage_ratio_b_to_a": (
                round(total_leakage_b / total_leakage_a, 2)
                if total_leakage_a > 0 else None
            ),
        },
    }


def _critique_stats(critique: dict, reasoning_narrative: str) -> dict:
    """Summarize one critique for comparison."""
    issues = critique.get("issues_found") or []
    justification = critique.get("justification") or ""
    critique_text = " ".join([justification] + issues).lower()
    leakage = _reasoning_leakage_score(reasoning_narrative, critique_text)
    return {
        "verdict": critique.get("verdict"),
        "confidence_in_critique": critique.get("confidence_in_critique"),
        "issues_count": len(issues),
        "isolation_mode": critique.get("isolation_mode"),
        "reasoning_leakage_score": leakage,
    }


def _reasoning_leakage_score(
    reasoning_narrative: str, critique_text: str
) -> int:
    """Count unique >=5-token phrases from ``reasoning_narrative`` that appear
    verbatim in ``critique_text``.

    This is a crude leakage detector: it catches cases where Condition B
    parrots sentences or clauses from the Hypothesizer's reasoning. Short
    or single-word overlaps are ignored to avoid false positives on common
    genealogy vocabulary (birth, death, father, etc.).
    """
    if not reasoning_narrative or not critique_text:
        return 0

    tokens = re.findall(r"\w+", reasoning_narrative.lower())
    if len(tokens) < 5:
        return 0

    hits: set[str] = set()
    window = 5
    for i in range(len(tokens) - window + 1):
        phrase = " ".join(tokens[i : i + window])
        if phrase in critique_text:
            hits.add(phrase)
    return len(hits)


def _initial_state(query: str, target_person: dict, gedcom_text: str) -> dict:
    return {
        "query": query,
        "target_person": target_person,
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
        "isolation_mode": None,
    }


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Critic isolation A/B experiment (filtered vs unfiltered)."
    )
    parser.add_argument(
        "--preset",
        choices=sorted(_PRESETS.keys()),
        default="jfk",
        help="Named experiment preset. See _PRESETS in source for definitions.",
    )
    args = parser.parse_args()

    preset = _PRESETS[args.preset]
    run_experiment(
        gedcom_path=preset["gedcom"],
        query=preset["query"],
        target_person=preset["target_person"],
        preset_name=args.preset,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
