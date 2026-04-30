"""Cross-vendor Critic experiment.

Addresses Phase 3 presentation feedback: same-vendor Hypothesizer and Critic
may share training-data assumptions and systematic failure modes, defeating
the adversarial-isolation guarantee. A Critic from a different company can't
quietly agree out of shared priors.

Design (mirrors the isolation A/B experiment):
    1. Build a SHARED SEED state by running Scout + Synthesizer + Hypothesizer
       once. This controls for hypothesis-generation drift between conditions.
    2. Snapshot the seed.
    3. Invoke the Adversarial Critic node twice on the same seed:
         Condition A: Anthropic Opus 4.7 (production default)
         Condition B: OpenAI GPT-5.5 (cross-vendor)
    4. Compare verdicts, confidence_in_critique, issues_found, justification
       reasoning quality, and Tier 1 / geo handling (these are deterministic
       and should be identical across vendors).

Run:
    ./.venv/Scripts/python.exe eval/cross_vendor_critic_experiment.py

Output:
    eval/results/cross_vendor_{timestamp}.json     full per-vendor critiques
    traces/trace_..._cross_vendor_anthropic.{json,md}
    traces/trace_..._cross_vendor_openai.{json,md}
"""

from __future__ import annotations

import copy
import json
import sys
import time
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(override=True)

from agents.adversarial_critic import build_critic_llm
import agents.adversarial_critic as critic_module
from agents.final_report_writer import final_report_writer_node
from agents.profile_synthesizer import profile_synthesizer_node
from agents.record_scout import record_scout_node
from agents.relationship_hypothesizer import relationship_hypothesizer_node
from agents.adversarial_critic import adversarial_critic_node
from tools.trace_writer import save_trace


_RESULTS_DIR = _REPO_ROOT / "eval" / "results"


# Conditions for the experiment.
_CONDITIONS = [
    {
        "name": "anthropic_opus_4_7",
        "vendor": "anthropic",
        "model": "claude-opus-4-7",
        "label": "Anthropic Opus 4.7",
    },
    {
        "name": "openai_gpt_5_5",
        "vendor": "openai",
        "model": "gpt-5.5",
        "label": "OpenAI GPT-5.5",
    },
]


# Default test query — JFK parents on the Kennedy GEDCOM.
_DEFAULT_GEDCOM = _REPO_ROOT / "data" / "The Kennedy Family.ged"
_DEFAULT_QUERY = "Who were the parents of John F. Kennedy?"
_DEFAULT_TARGET = {
    "name": "John F. Kennedy",
    "approx_birth": "1917",
    "location": "Brookline, MA",
}


def run_experiment(
    gedcom_path: Path = _DEFAULT_GEDCOM,
    query: str = _DEFAULT_QUERY,
    target_person: dict = _DEFAULT_TARGET,
) -> dict:
    print("=== Cross-vendor Critic experiment ===")
    print(f"GEDCOM:  {gedcom_path.name}")
    print(f"Query:   {query}")
    print(f"Target:  {target_person}")
    print(f"Critics: " + " vs ".join(c["label"] for c in _CONDITIONS))
    print()

    gedcom_text = gedcom_path.read_text(encoding="utf-8", errors="replace")
    base_state = _initial_state(query, target_person, gedcom_text)

    # --- Build shared seed state ---
    print("Building shared seed (Scout -> Synthesizer -> Hypothesizer)...")
    t0 = time.time()
    seed = record_scout_node(base_state)
    seed_state = _merge(base_state, seed)
    seed = profile_synthesizer_node(seed_state)
    seed_state = _merge(seed_state, seed)
    seed = relationship_hypothesizer_node(seed_state)
    seed_state = _merge(seed_state, seed)
    t_seed = time.time() - t0
    print(
        f"  seed: {len(seed_state.get('hypotheses') or [])} hypotheses "
        f"in {t_seed:.1f}s"
    )
    print()

    if not seed_state.get("hypotheses"):
        raise RuntimeError("Seed state has no hypotheses; cannot run experiment")

    # --- Run Critic per condition ---
    run_label = datetime.now().strftime("%Y%m%d_%H%M%S")
    condition_outputs: list[dict] = []

    original_llm = critic_module.llm

    try:
        for cond in _CONDITIONS:
            print(f"Running Condition: {cond['label']}...")
            # Swap the module-level LLM for this condition.
            critic_module.llm = build_critic_llm(
                vendor=cond["vendor"], model=cond["model"]
            )

            state = copy.deepcopy(seed_state)
            t0 = time.time()
            critic_out = adversarial_critic_node(state)
            elapsed = time.time() - t0
            state = _merge(state, critic_out)
            state = _merge(state, final_report_writer_node(state))

            print(
                f"  {cond['label']}: {len(state['critiques'])} critiques "
                f"in {elapsed:.1f}s"
            )

            # Save full trace per condition.
            save_trace(state, label=f"{run_label}_cross_vendor_{cond['name']}")

            condition_outputs.append({
                "condition": cond,
                "critiques": state["critiques"],
                "elapsed_sec": round(elapsed, 2),
                "trace_log": state.get("trace_log") or [],
            })
    finally:
        # Restore the production LLM.
        critic_module.llm = original_llm

    print()

    # --- Compare ---
    comparison = _compare(seed_state["hypotheses"], condition_outputs)

    print("=== Comparison ===")
    for entry in comparison["per_hypothesis"]:
        print(f"  {entry['hypothesis_id']}")
        for cn, stats in entry["per_condition"].items():
            print(
                f"    {cn:30s} verdict={stats['verdict']:<14} "
                f"conf={stats['confidence_in_critique']}  "
                f"issues={stats['issues_count']}"
            )

    print()
    print("=== Aggregate ===")
    agg = comparison["aggregate"]
    print(f"  any verdict differs across conditions: {agg['any_verdict_differs']}")
    print(f"  max confidence delta:                  {agg['max_confidence_delta']:+.3f}")
    print(f"  identical Tier 1 results:              {agg['tier1_identical']}")
    print(f"  identical geo results:                 {agg['geo_identical']}")

    # --- Persist ---
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path = _RESULTS_DIR / f"cross_vendor_{run_label}.json"
    result_path.write_text(
        json.dumps(
            {
                "run_label": run_label,
                "timestamp": datetime.now().isoformat(),
                "gedcom": str(gedcom_path.name),
                "query": query,
                "target_person": target_person,
                "seed": {
                    "hypothesis_count": len(seed_state["hypotheses"]),
                    "elapsed_sec": round(t_seed, 2),
                },
                "conditions": [
                    {
                        "name": c["condition"]["name"],
                        "vendor": c["condition"]["vendor"],
                        "model": c["condition"]["model"],
                        "label": c["condition"]["label"],
                        "elapsed_sec": c["elapsed_sec"],
                        "critiques": c["critiques"],
                    }
                    for c in condition_outputs
                ],
                "comparison": comparison,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print()
    print(f"wrote {result_path}")
    return {"result_path": str(result_path), "comparison": comparison}


def _compare(seed_hypotheses, condition_outputs) -> dict:
    """Per-hypothesis side-by-side comparison."""
    per_hypothesis: list[dict] = []
    for hyp in seed_hypotheses:
        hid = hyp.get("hypothesis_id")
        per_condition: dict[str, dict] = {}
        for cond_out in condition_outputs:
            label = cond_out["condition"]["label"]
            critique = next(
                (c for c in cond_out["critiques"] if c.get("hypothesis_id") == hid),
                {},
            )
            per_condition[label] = {
                "verdict": critique.get("verdict"),
                "confidence_in_critique": critique.get("confidence_in_critique"),
                "issues_count": len(critique.get("issues_found") or []),
                "justification": critique.get("justification", "")[:300],
                "tier1_impossibles": [
                    r.get("check") for r in (critique.get("tier1_results") or [])
                    if r.get("verdict") == "impossible"
                ],
                "geo_verdict": (critique.get("geo_result") or {}).get("verdict"),
            }
        per_hypothesis.append({
            "hypothesis_id": hid,
            "per_condition": per_condition,
        })

    # Aggregate metrics.
    any_verdict_differs = False
    max_conf_delta = 0.0
    tier1_identical = True
    geo_identical = True

    for entry in per_hypothesis:
        verdicts = {
            stats["verdict"] for stats in entry["per_condition"].values()
        }
        if len(verdicts) > 1:
            any_verdict_differs = True

        confs = [
            stats["confidence_in_critique"]
            for stats in entry["per_condition"].values()
            if stats["confidence_in_critique"] is not None
        ]
        if len(confs) >= 2:
            delta = max(confs) - min(confs)
            if delta > max_conf_delta:
                max_conf_delta = delta

        tier1_sets = [
            tuple(sorted(stats["tier1_impossibles"]))
            for stats in entry["per_condition"].values()
        ]
        if len(set(tier1_sets)) > 1:
            tier1_identical = False

        geo_set = {
            stats["geo_verdict"]
            for stats in entry["per_condition"].values()
        }
        if len(geo_set) > 1:
            geo_identical = False

    return {
        "per_hypothesis": per_hypothesis,
        "aggregate": {
            "any_verdict_differs": any_verdict_differs,
            "max_confidence_delta": round(max_conf_delta, 3),
            "tier1_identical": tier1_identical,
            "geo_identical": geo_identical,
        },
    }


def _initial_state(query, target, gedcom_text) -> dict:
    return {
        "query": query,
        "target_person": target,
        "gedcom_text": gedcom_text,
        "gedcom_persons": [],
        "dna_csv": None,
        "retrieved_records": [],
        "profiles": [],
        "hypotheses": [],
        "critiques": [],
        "dna_analysis": None,
        "final_report": "",
        "revision_count": 0,
        "status": "running",
        "trace_log": [],
        "isolation_mode": None,
    }


def _merge(state: dict, delta: dict) -> dict:
    """Merge a node's return into running state, handling the trace_log
    reducer (additive list) vs other fields (overwrite)."""
    out = dict(state)
    for k, v in delta.items():
        if k == "trace_log" and isinstance(v, list):
            out["trace_log"] = list(out.get("trace_log") or []) + v
        else:
            out[k] = v
    return out


if __name__ == "__main__":
    run_experiment()
