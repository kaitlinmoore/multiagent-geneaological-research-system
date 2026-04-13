"""Compose eval/results/isolation_ab_summary.md from individual isolation_*.json
result files produced by eval/isolation_experiment.py.

Reads every isolation_*.json file in eval/results/, extracts the per-hypothesis
A/B comparison rows, and writes a single combined markdown table grouping by
preset. No analysis or interpretation — just the raw side-by-side numbers the
evaluation plan doc can cite.

Run after all A/B experiment presets have been executed:

    ./.venv/Scripts/python.exe eval/build_isolation_summary.py

Output:
    eval/results/isolation_ab_summary.md
"""

from __future__ import annotations

import json
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parent.parent
_RESULTS_DIR = _REPO_ROOT / "eval" / "results"
_OUTPUT_PATH = _RESULTS_DIR / "isolation_ab_summary.md"


# Preset display order in the summary. Unknown presets get appended alphabetically.
_PRESET_DISPLAY_ORDER = ["jfk", "tier2_surname", "tier3_joseph"]


def _load_isolation_files() -> list[dict]:
    """Return the contents of every isolation_*.json file, newest first per preset.

    When the same preset has been run more than once we take the most recent
    timestamp (alphabetically last), so rebuilding the summary doesn't require
    deleting stale result files.
    """
    files = sorted(_RESULTS_DIR.glob("isolation_*.json"))
    by_preset: dict[str, dict] = {}
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        preset = data.get("preset") or _infer_preset_from_filename(path.name)
        if preset is None:
            continue
        # Keep the newest per preset (later timestamps overwrite earlier ones).
        existing = by_preset.get(preset)
        if existing is None or path.name > existing["__source_file"]:
            data["__source_file"] = path.name
            data["__preset_name"] = preset
            by_preset[preset] = data
    return _order_presets(by_preset)


def _infer_preset_from_filename(filename: str) -> str | None:
    """Fallback for older isolation_*.json files without an embedded preset field.

    The JFK run from before the --preset flag was added is named
    `isolation_{timestamp}.json` with no preset suffix; infer it as 'jfk'.
    Newer files follow the `isolation_{timestamp}_{preset}.json` pattern.
    """
    stem = filename[:-len(".json")] if filename.endswith(".json") else filename
    parts = stem.split("_")
    # Expected: ["isolation", "YYYYMMDD", "HHMMSS"] or
    #           ["isolation", "YYYYMMDD", "HHMMSS", preset...]
    if len(parts) >= 4:
        return "_".join(parts[3:])
    if len(parts) == 3:
        return "jfk"  # legacy pre-preset JFK run
    return None


def _order_presets(by_preset: dict[str, dict]) -> list[dict]:
    ordered: list[dict] = []
    for name in _PRESET_DISPLAY_ORDER:
        if name in by_preset:
            ordered.append(by_preset.pop(name))
    for name in sorted(by_preset.keys()):
        ordered.append(by_preset[name])
    return ordered


def _format_table(per_hypothesis: list[dict]) -> list[str]:
    header = (
        "| Hypothesis | A verdict | A conf | A issues | A leakage "
        "| B verdict | B conf | B issues | B leakage "
        "| verdict changed | conf delta | leakage delta |"
    )
    sep = (
        "|---|---|---|---|---|---|---|---|---|---|---|---|"
    )
    lines = [header, sep]
    for row in per_hypothesis:
        a = row["a"]
        b = row["b"]
        lines.append(
            "| `{hid}` | {av} | {ac} | {ai} | {al} | {bv} | {bc} | {bi} | {bl} | {vc} | {cd:+} | {ld:+d} |".format(
                hid=row.get("hypothesis_id") or "(none)",
                av=a.get("verdict"),
                ac=_fmt_conf(a.get("confidence_in_critique")),
                ai=a.get("issues_count"),
                al=a.get("reasoning_leakage_score"),
                bv=b.get("verdict"),
                bc=_fmt_conf(b.get("confidence_in_critique")),
                bi=b.get("issues_count"),
                bl=b.get("reasoning_leakage_score"),
                vc="yes" if row.get("verdict_changed") else "no",
                cd=row.get("confidence_delta") or 0.0,
                ld=row.get("leakage_delta") or 0,
            )
        )
    return lines


def _fmt_conf(value) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def build_summary() -> Path:
    runs = _load_isolation_files()
    lines: list[str] = []
    lines.append("# Critic Isolation A/B Experiment — Summary")
    lines.append("")
    lines.append(
        "Side-by-side comparison of Condition A (filtered — the isolation "
        "design) vs. Condition B (unfiltered — raw hypothesis dicts including "
        "reasoning_narrative). Each row is one hypothesis from a single shared-seed "
        "run: the Scout → Synthesizer → Hypothesizer pipeline executes once, "
        "then the Critic is invoked twice against the same hypotheses with "
        "isolation_mode toggled."
    )
    lines.append("")
    lines.append(
        "Leakage score counts distinct 5-token phrases from each hypothesis's "
        "`reasoning_narrative` that appear verbatim in the Critic's "
        "`justification` + `issues_found` text. It's a crude verbatim-overlap "
        "signal, not a semantic one."
    )
    lines.append("")
    lines.append(
        "Raw source files in `eval/results/isolation_*.json`. This summary is "
        "regenerated by `eval/build_isolation_summary.py`."
    )
    lines.append("")

    if not runs:
        lines.append("_No isolation_*.json files found in eval/results/._")
        _OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return _OUTPUT_PATH

    # Per-preset sections + one combined table at the end.
    for run in runs:
        preset = run.get("__preset_name") or run.get("preset") or "(unknown)"
        lines.append(f"## `{preset}`")
        lines.append("")
        lines.append(f"- **Source file:** `eval/results/{run.get('__source_file')}`")
        lines.append(f"- **GEDCOM:** `{run.get('gedcom')}`")
        lines.append(f"- **Query:** {run.get('query')}")
        target = run.get("target_person") or {}
        lines.append(
            f"- **Target:** {target.get('name')} "
            f"(approx. born {target.get('approx_birth')}, {target.get('location')})"
        )
        seed = run.get("seed") or {}
        lines.append(
            f"- **Seed state:** {seed.get('hypothesis_count')} hypotheses, "
            f"{seed.get('profile_count')} profiles, "
            f"{seed.get('retrieved_record_count')} retrieved records"
        )
        comparison = run.get("comparison") or {}
        agg = comparison.get("aggregate") or {}
        lines.append(
            f"- **Aggregate:** "
            f"any_verdict_changed={agg.get('any_verdict_changed')}, "
            f"total leakage A={agg.get('total_reasoning_leakage_a')}, "
            f"total leakage B={agg.get('total_reasoning_leakage_b')}, "
            f"leakage ratio B:A={agg.get('leakage_ratio_b_to_a')}"
        )
        lines.append("")
        lines.extend(_format_table(comparison.get("per_hypothesis") or []))
        lines.append("")

    # Combined flat table — one row per hypothesis across all presets.
    lines.append("## Combined flat table (all presets)")
    lines.append("")
    combined_header = (
        "| Preset | Hypothesis | A verdict | A conf | A issues | A leakage "
        "| B verdict | B conf | B issues | B leakage "
        "| verdict changed | conf delta | leakage delta |"
    )
    combined_sep = (
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|"
    )
    lines.append(combined_header)
    lines.append(combined_sep)
    for run in runs:
        preset = run.get("__preset_name") or run.get("preset") or "(unknown)"
        comparison = run.get("comparison") or {}
        for row in comparison.get("per_hypothesis") or []:
            a = row["a"]
            b = row["b"]
            lines.append(
                "| `{p}` | `{hid}` | {av} | {ac} | {ai} | {al} | {bv} | {bc} | {bi} | {bl} | {vc} | {cd:+} | {ld:+d} |".format(
                    p=preset,
                    hid=row.get("hypothesis_id") or "(none)",
                    av=a.get("verdict"),
                    ac=_fmt_conf(a.get("confidence_in_critique")),
                    ai=a.get("issues_count"),
                    al=a.get("reasoning_leakage_score"),
                    bv=b.get("verdict"),
                    bc=_fmt_conf(b.get("confidence_in_critique")),
                    bi=b.get("issues_count"),
                    bl=b.get("reasoning_leakage_score"),
                    vc="yes" if row.get("verdict_changed") else "no",
                    cd=row.get("confidence_delta") or 0.0,
                    ld=row.get("leakage_delta") or 0,
                )
            )
    lines.append("")

    _OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return _OUTPUT_PATH


if __name__ == "__main__":
    out = build_summary()
    print(f"wrote {out}")
