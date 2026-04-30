"""Interaction trace persistence.

Writes two artifacts per run into ``traces/``:

    trace_{timestamp}.json   full serialized state for reproducibility
    trace_{timestamp}.md     human-readable summary (final_report + trace_log)

Why both:
    - The JSON is the audit trail — every profile, hypothesis, critique,
      tier1 check, and trace_log entry is preserved. Use this for the Critic
      isolation A/B experiment comparison and for debugging.
    - The markdown is what you actually read. It's mostly the final_report
      (already composed by final_report_writer) plus the trace_log so you can
      see the sequence of agent actions in one scan.

Design choices:
    - gedcom_text is stripped from the JSON (too bulky for typical traces);
      a SHA-256 hash is stored instead so two runs over the same file can be
      cross-referenced without duplicating 30+ KB of GEDCOM per trace.
    - gedcom_persons IS kept — it's the structured parse downstream agents
      work from and is moderately sized (dozens of dicts, not megabytes).
    - save_trace() is defensive: it never raises. A failed trace write should
      not break the main pipeline; it logs to stdout and returns None.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


_TRACES_DIR_DEFAULT = Path(__file__).resolve().parent.parent / "traces"


def save_trace(
    state: dict,
    traces_dir: Optional[Path] = None,
    label: Optional[str] = None,
) -> Optional[dict]:
    """Persist a full interaction trace to disk.

    Args:
        state: the final GenealogyState dict returned by graph.invoke().
        traces_dir: override the default traces/ directory.
        label: optional short string appended to the filename (e.g. "jfk",
               "isolation_a"). Auto-sanitized to filesystem-safe characters.

    Returns:
        A dict with "json_path" and "md_path" pointing at the files written,
        or None if writing failed.
    """
    target_dir = Path(traces_dir) if traces_dir else _TRACES_DIR_DEFAULT
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        print(f"[trace_writer] could not create {target_dir}: {exc}")
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"trace_{timestamp}"
    if label:
        safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)
        base = f"{base}_{safe_label}"

    json_path = target_dir / f"{base}.json"
    md_path = target_dir / f"{base}.md"

    payload = _build_serializable_payload(state, timestamp=timestamp, label=label)

    try:
        json_path.write_text(
            json.dumps(payload, indent=2, default=str, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"[trace_writer] JSON write failed for {json_path}: {exc}")
        return None

    try:
        md_path.write_text(
            _build_markdown(state, timestamp=timestamp, label=label),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"[trace_writer] MD write failed for {md_path}: {exc}")
        return {"json_path": str(json_path), "md_path": None}

    return {"json_path": str(json_path), "md_path": str(md_path)}


# ---------------------------------------------------------------------------
# JSON payload construction
# ---------------------------------------------------------------------------


def _build_serializable_payload(
    state: dict, timestamp: str, label: Optional[str]
) -> dict:
    """Copy state and replace bulky/non-serializable fields for JSON output."""
    payload: dict[str, Any] = {
        "trace_metadata": {
            "timestamp": timestamp,
            "label": label,
            "saved_by": "tools.trace_writer.save_trace",
        },
        "query": state.get("query"),
        "target_person": state.get("target_person"),
        "status": state.get("status"),
        "revision_count": state.get("revision_count"),
    }

    # gedcom_text replaced with hash + length (too bulky for trace files).
    gedcom_text = state.get("gedcom_text") or ""
    if gedcom_text:
        payload["gedcom_source"] = {
            "sha256": hashlib.sha256(gedcom_text.encode("utf-8")).hexdigest(),
            "length_chars": len(gedcom_text),
        }
    else:
        payload["gedcom_source"] = None

    # Structured data is preserved verbatim.
    payload["gedcom_persons_count"] = len(state.get("gedcom_persons") or [])
    payload["retrieved_records"] = state.get("retrieved_records") or []
    payload["profiles"] = state.get("profiles") or []
    payload["hypotheses"] = state.get("hypotheses") or []
    payload["critiques"] = state.get("critiques") or []
    payload["dna_analysis"] = state.get("dna_analysis")
    payload["trace_log"] = state.get("trace_log") or []
    payload["final_report"] = state.get("final_report") or ""

    return payload


# ---------------------------------------------------------------------------
# Markdown rendering — intentionally thin. The final_report (composed by
# final_report_writer) is the meat; we just wrap it with metadata + trace_log.
# ---------------------------------------------------------------------------


def _build_markdown(state: dict, timestamp: str, label: Optional[str]) -> str:
    parts: list[str] = []
    parts.append("# Interaction Trace")
    parts.append("")
    parts.append(f"- **Timestamp:** {timestamp}")
    if label:
        parts.append(f"- **Label:** {label}")
    parts.append(f"- **Query:** {state.get('query', '(none)')}")
    parts.append(f"- **Status:** {state.get('status', 'unknown')}")
    parts.append(f"- **Revision count:** {state.get('revision_count', 0)}")
    parts.append("")
    parts.append("---")
    parts.append("")

    # Trace log — sequential view of agent actions.
    parts.append("## Agent Trace Log")
    parts.append("")
    parts.append("```")
    for entry in state.get("trace_log") or []:
        parts.append(str(entry))
    parts.append("```")
    parts.append("")
    parts.append("---")
    parts.append("")

    # Final report — produced deterministically by final_report_writer.
    final_report = state.get("final_report") or ""
    if final_report.strip():
        parts.append(final_report)
    else:
        parts.append("## Final Report")
        parts.append("")
        parts.append("_(final_report is empty — did the pipeline reach "
                     "final_report_writer?)_")
    parts.append("")

    return "\n".join(parts)
