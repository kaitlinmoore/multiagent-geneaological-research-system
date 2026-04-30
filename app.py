"""Streamlit interface for the multi-agent genealogy pipeline.

Reconciled from two divergent editing sessions into four tabs:
  1. Pipeline  — GEDCOM/DNA input, query routing, progress indicators, results
  2. Family Tree — graphviz visualization color-coded by Critic verdict
  3. Audit     — dedicated subtree audit with deterministic + LLM passes
  4. DNA Analysis — DNA match summary when DNA data was provided

Run with: streamlit run app.py
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Optional

# =====================================================================
# API KEY FIX: load .env with explicit path BEFORE any project imports.
# ChatAnthropic constructors cache the key at module import time.
# =====================================================================
_REPO_ROOT = Path(__file__).resolve().parent
_ENV_PATH = _REPO_ROOT / ".env"

from dotenv import load_dotenv
load_dotenv(_ENV_PATH, override=True)

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import graphviz
import streamlit as st

from agents.final_report_writer import check_escalation
from graph import build_graph
from tools.trace_writer import save_trace


# =====================================================================
# Constants
# =====================================================================

AGENT_ORDER: list[tuple[str, str]] = [
    ("record_scout", "Record Scout"),
    ("dna_analyst", "DNA Analyst"),
    ("profile_synthesizer", "Profile Synthesizer"),
    ("relationship_hypothesizer", "Relationship Hypothesizer"),
    ("adversarial_critic", "Adversarial Critic"),
    ("final_report_writer", "Final Report Writer"),
]
AGENT_LABELS = dict(AGENT_ORDER)

DATA_DIR = _REPO_ROOT / "data"
DNA_DEMO_DIR = DATA_DIR / "DNA_demo"
DNA_PERSONAL_DIR = DATA_DIR / "DNA"
TRACES_DIR = _REPO_ROOT / "traces"
TRACES_DEMOS_DIR = TRACES_DIR / "demos"
TRACES_REDACTED_DIR = TRACES_DIR / "redacted"
UPLOAD_SENTINEL = "-- upload instead --"
DNA_NONE_SENTINEL = "-- no DNA file --"
TRACE_NONE_SENTINEL = "-- pick a trace --"


# =====================================================================
# GEDCOM file handling
# =====================================================================

@st.cache_data(show_spinner=False)
def discover_gedcom_files() -> list[str]:
    if not DATA_DIR.is_dir():
        return []
    paths = sorted(
        p for p in DATA_DIR.rglob("*.ged")
        if p.is_file() and "trap_cases" not in str(p)
    )
    return [str(p.relative_to(DATA_DIR)).replace("\\", "/") for p in paths]


def load_gedcom_from_disk(relative_path: str) -> str:
    full_path = (DATA_DIR / relative_path).resolve()
    if DATA_DIR.resolve() not in full_path.parents and full_path != DATA_DIR.resolve():
        raise ValueError(f"Path {relative_path!r} resolves outside data/.")
    try:
        return full_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return full_path.read_text(encoding="latin-1")


# =====================================================================
# DNA file handling
# =====================================================================

@st.cache_data(show_spinner=False)
def discover_dna_files() -> list[tuple[str, str]]:
    """Scan DNA_demo/ and DNA/ for .csv files.

    Returns a list of (display_label, absolute_path) pairs. Demo files come
    first, personal files only appear if data/DNA/ exists AND is non-empty
    (it's gitignored, so a fresh clone won't have any).
    """
    pairs: list[tuple[str, str]] = []
    if DNA_DEMO_DIR.is_dir():
        for p in sorted(DNA_DEMO_DIR.glob("*.csv")):
            if p.is_file():
                pairs.append((f"Demo: {p.stem}", str(p)))
    if DNA_PERSONAL_DIR.is_dir():
        personal = sorted(p for p in DNA_PERSONAL_DIR.glob("*.csv") if p.is_file())
        if personal:
            for p in personal:
                pairs.append((f"Personal: {p.stem}", str(p)))
    return pairs


def load_dna_from_disk(absolute_path: str) -> str:
    """Read a DNA CSV from disk. Strips BOM (utf-8-sig) like the upload path."""
    full = Path(absolute_path).resolve()
    # Guard: must live under one of the recognized DNA dirs.
    allowed_roots = {DNA_DEMO_DIR.resolve(), DNA_PERSONAL_DIR.resolve()}
    if not any(root in full.parents for root in allowed_roots):
        raise ValueError(f"Path {absolute_path!r} is outside the DNA directories.")
    return full.read_text(encoding="utf-8-sig", errors="replace")


# =====================================================================
# Trace replay handling — loading saved pipeline runs without API calls
# =====================================================================

@st.cache_data(show_spinner=False)
def discover_traces() -> list[tuple[str, str, str]]:
    """Scan traces/demos/ and traces/redacted/ for replayable JSON traces.

    Returns a list of (display_label, absolute_path, category) triples.
    Demo traces come first; redacted traces (pseudonymized real-tree
    runs) appear after.

    Category is one of:
        "query" — query-mode pipeline trace (parent investigation).
        "gap"   — gap-detection trace (fill missing parental link).

    Audit JSONs (audit_*.json) are EXCLUDED here — they have a different
    schema and are loaded separately by the Audit tab's saved-audit
    loader. The .map.json re-identification files are also excluded.
    """
    pairs: list[tuple[str, str, str]] = []
    for label_prefix, src in (
        ("Demo", TRACES_DEMOS_DIR),
        ("Redacted", TRACES_REDACTED_DIR),
    ):
        if not src.is_dir():
            continue
        for p in sorted(src.glob("*.json")):
            if not p.is_file():
                continue
            if p.name.endswith(".map.json"):
                continue
            if p.name.startswith("audit_"):
                continue  # belongs to the Audit-tab loader
            # Peek at the trace's target_person to determine its category.
            # Cheap on small files; cached at the function level so it
            # runs once per session per file.
            try:
                tjson = json.loads(p.read_text(encoding="utf-8"))
                tp = tjson.get("target_person") or {}
                category = "gap" if tp.get("gap_mode") else "query"
            except Exception:
                category = "query"  # benign fallback — unknown traces show under Query
            pairs.append((f"{label_prefix}: {p.stem}", str(p), category))
    return pairs


def load_trace_from_disk(absolute_path: str) -> dict:
    """Read a saved trace JSON. Guarded to live under traces/."""
    import json
    full = Path(absolute_path).resolve()
    allowed_root = TRACES_DIR.resolve()
    if allowed_root not in full.parents:
        raise ValueError(f"Path {absolute_path!r} is outside traces/.")
    return json.loads(full.read_text(encoding="utf-8"))


def extract_gedcom_text(uploaded_file) -> str:
    raw = uploaded_file.getvalue()
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            ged_names = [n for n in zf.namelist() if n.lower().endswith(".ged")]
            if not ged_names:
                raise ValueError("Zip contains no .ged file.")
            with zf.open(ged_names[0]) as inner:
                return inner.read().decode("utf-8", errors="replace")
    return raw.decode("utf-8", errors="replace")


# =====================================================================
# Query routing — detect audit-pattern queries
# =====================================================================

_AUDIT_PATTERNS = [
    r"\baudit\b", r"\bcheck\b.*\btree\b", r"\bquestionable\b",
    r"\bweak\b.*\bevidence\b", r"\bgoing\s+back\s+\d+\s+generation",
    r"\b\d+\s+generation", r"\banything\s+wrong\b", r"\bverify\b.*\btree\b",
    r"\bvalidate\b", r"\bsuspicious\b", r"\bflag\b.*\bissue",
]


def _format_trace_timestamp(ts: str) -> str:
    """Reformat a YYYYMMDD_HHMMSS trace timestamp as YYYY-MM-DD HH:MM:SS
    for human-readable UI display. Returns the original string unchanged
    if it doesn't match the expected pattern (handles '?', 'unknown',
    missing, or any future format change gracefully)."""
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})", ts or "")
    if not m:
        return ts
    return f"{m[1]}-{m[2]}-{m[3]} {m[4]}:{m[5]}:{m[6]}"


def is_audit_query(query: str) -> bool:
    q = query.lower().strip()
    return any(re.search(pat, q) for pat in _AUDIT_PATTERNS)


def extract_generations_from_query(query: str) -> int:
    match = re.search(r"(\d+)\s*generation", query.lower())
    if match:
        return max(1, min(int(match.group(1)), 5))
    return 3


# =====================================================================
# Pipeline progress tracker
# =====================================================================

def render_agent_row(placeholder, label: str, state: str, detail: str = "") -> None:
    icons = {"waiting": "---", "running": "...", "done": "OK", "revised": "REV"}
    icon = icons.get(state, " ")
    detail_html = f' <span class="agent-detail">({detail})</span>' if detail else ""
    html = (
        f'<div class="agent-row state-{state}">'
        f'  <span class="agent-icon">{icon}</span>'
        f'  <span class="agent-label">{label}</span>'
        f'  <span class="agent-state">  {state}</span>'
        f'  {detail_html}'
        f'</div>'
    )
    placeholder.markdown(html, unsafe_allow_html=True)


def run_pipeline(initial_state: dict, status_placeholders: dict) -> dict:
    for key, label in AGENT_ORDER:
        render_agent_row(status_placeholders[key], label, "waiting")

    graph = build_graph()
    running: dict[str, Any] = dict(initial_state)
    run_counts: dict[str, int] = {k: 0 for k, _ in AGENT_ORDER}

    for event in graph.stream(initial_state, stream_mode="updates"):
        for node_name, delta in event.items():
            if delta:
                # trace_log uses an Annotated reducer (operator.add), so
                # deltas contain only NEW entries. Accumulate manually.
                if "trace_log" in delta:
                    running.setdefault("trace_log", []).extend(delta["trace_log"])
                    rest = {k: v for k, v in delta.items() if k != "trace_log"}
                    running.update(rest)
                else:
                    running.update(delta)
            if node_name in status_placeholders:
                run_counts[node_name] += 1
                label = AGENT_LABELS[node_name]
                detail = ""
                if run_counts[node_name] > 1:
                    detail = f"revision {run_counts[node_name] - 1}"
                render_agent_row(
                    status_placeholders[node_name], label,
                    "done" if run_counts[node_name] == 1 else "revised",
                    detail,
                )

    return running


# =====================================================================
# Family-tree visualization (graphviz)
# =====================================================================

_COLOR_GREEN = {"fillcolor": "#D5F5E3", "color": "#0F6E56", "fontcolor": "#0B4F3D"}
_COLOR_AMBER = {"fillcolor": "#FCF3CF", "color": "#BA7517", "fontcolor": "#7C4A03"}
_COLOR_RED = {"fillcolor": "#FADBD8", "color": "#A32D2D", "fontcolor": "#7F1D1D"}
_COLOR_GRAY = {"fillcolor": "#EEEEEE", "color": "#9E9E9E", "fontcolor": "#424242"}
_COLOR_SUBJECT = {"fillcolor": "#E3F2FD", "color": "#1565C0", "fontcolor": "#0D47A1"}


def _strip_record_prefix(record_id: str) -> str:
    if record_id and ":" in record_id:
        return record_id.split(":", 1)[1]
    return record_id or ""


def _escape_html(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _node_label(name: str, birth: str, death: str, footer: str) -> str:
    parts = [f"<B>{_escape_html(name) or '(unknown)'}</B>"]
    if birth or death:
        parts.append(_escape_html(f"b. {birth or '?'}  d. {death or '?'}"))
    if footer:
        parts.append(f'<FONT POINT-SIZE="9">{_escape_html(footer)}</FONT>')
    return "<" + "<BR/>".join(parts) + ">"


def _color_for(hyp, critique, esc) -> dict:
    if esc and esc.get("escalation_flag"):
        return _COLOR_RED
    if not critique:
        return _COLOR_GRAY
    verdict = critique.get("verdict", "")
    if verdict == "reject":
        return _COLOR_RED
    if verdict == "flag_uncertain":
        return _COLOR_AMBER
    if verdict == "accept":
        if float((hyp or {}).get("confidence_score") or 0.0) >= 0.75:
            return _COLOR_GREEN
        return _COLOR_AMBER
    return _COLOR_GRAY


def _verdict_footer(critique, esc) -> str:
    if esc and esc.get("escalation_flag"):
        base = "escalated"
    elif critique:
        base = critique.get("verdict", "?")
    else:
        base = "no verdict"
    conf = (critique or {}).get("confidence_in_critique")
    if conf is not None:
        try:
            return f"{base} ({float(conf):.2f})"
        except (TypeError, ValueError):
            pass
    return base


def build_family_tree(result: dict) -> Optional[graphviz.Digraph]:
    profiles = result.get("profiles") or []
    if not profiles:
        return None
    profile = profiles[0]

    subject_record_id = profile.get("subject_record_id", "")
    subject_id = _strip_record_prefix(subject_record_id)
    subject_name = profile.get("subject_name") or "(unknown subject)"
    family = profile.get("family") or {}
    hypotheses = result.get("hypotheses") or []
    critiques = result.get("critiques") or []
    revision_count = int(result.get("revision_count") or 0)
    records = result.get("retrieved_records") or []

    escalations = check_escalation(hypotheses, critiques, revision_count)
    esc_by_hyp_id = {e["hypothesis_id"]: e for e in escalations}
    critique_by_hyp_id = {c.get("hypothesis_id", ""): c for c in critiques}
    records_by_record_id = {r.get("record_id"): r for r in records}

    def lookup_dates(record_id):
        record = records_by_record_id.get(record_id)
        if not record:
            return "", ""
        data = record.get("data") or {}
        return data.get("birth_date") or "", data.get("death_date") or ""

    def lookup_critique(member_record_id):
        member_id = _strip_record_prefix(member_record_id)
        for hyp in hypotheses:
            pair = {hyp.get("subject_id", ""), hyp.get("related_id", "")}
            if pair == {subject_id, member_id}:
                hyp_id = hyp.get("hypothesis_id", "")
                return hyp, critique_by_hyp_id.get(hyp_id), esc_by_hyp_id.get(hyp_id, {})
        return None, None, {}

    dot = graphviz.Digraph("family", engine="dot")
    dot.attr(rankdir="TB", nodesep="0.45", ranksep="0.7", bgcolor="transparent", pad="0.2")
    dot.attr("node", shape="box", style="rounded,filled", fontname="Helvetica", fontsize="11", margin="0.15,0.10")
    dot.attr("edge", fontname="Helvetica", fontsize="9", color="#7E7E7E")

    subject_birth, subject_death = lookup_dates(subject_record_id)
    dot.node("subject", _node_label(subject_name, subject_birth, subject_death, "SUBJECT"), **_COLOR_SUBJECT)

    # Build the parent_specs list. Three sources, in priority order:
    # 1. In-GEDCOM parents from profile.family (existing relationships)
    # 2. Gap-mode proposed parents from hypotheses (relationship absent in
    #    the GEDCOM but the Hypothesizer proposed a candidate). Marked
    #    proposed=True so rendering can visually distinguish.
    # 3. Still-missing roles from target_person.gap_mode metadata that
    #    didn't get a hypothesis (placeholder to show the gap exists).
    parent_specs: list[dict] = []
    if family.get("father"):
        parent_specs.append({"role": "father", "ref": family["father"], "proposed": False, "missing": False})
    if family.get("mother"):
        parent_specs.append({"role": "mother", "ref": family["mother"], "proposed": False, "missing": False})

    existing_roles = {p["role"] for p in parent_specs}

    # Supplement with gap-mode hypotheses for parental roles not already
    # populated from the GEDCOM. A gap-mode trace's hypotheses propose
    # a candidate parent; we surface that here.
    for hyp in hypotheses:
        if hyp.get("subject_id") != subject_id:
            continue
        rel = (hyp.get("proposed_relationship") or "").lower()
        role: Optional[str] = None
        if "father" in rel and "father" not in existing_roles:
            role = "father"
        elif "mother" in rel and "mother" not in existing_roles:
            role = "mother"
        else:
            continue
        related_id = hyp.get("related_id") or ""
        related_record_id = f"gedcom:{related_id}" if related_id else ""
        related_record = records_by_record_id.get(related_record_id) or {}
        related_data = related_record.get("data") or {}
        parent_specs.append({
            "role": role,
            "ref": {
                "name": related_data.get("name") or "(proposed candidate)",
                "record_id": related_record_id,
            },
            "proposed": True,
            "missing": False,
        })
        existing_roles.add(role)

    # Add MISSING placeholders for any parental role still without an
    # entry. In gap mode we show BOTH parents regardless of which role
    # the run investigated, so the user sees the full picture: what's
    # in the GEDCOM, what was proposed, and what's still a gap.
    target = result.get("target_person") or {}
    if target.get("gap_mode"):
        for role in ("father", "mother"):
            if role not in existing_roles:
                parent_specs.append({
                    "role": role,
                    "ref": {"name": "(no proposal)", "record_id": ""},
                    "proposed": False,
                    "missing": True,
                })
                existing_roles.add(role)

    with dot.subgraph() as s:
        s.attr(rank="same")
        for idx, spec in enumerate(parent_specs):
            role = spec["role"]
            ref = spec["ref"] or {}
            proposed = spec.get("proposed", False)
            missing = spec.get("missing", False)
            nid = f"parent_{idx}"
            rid = ref.get("record_id") or ""
            hyp, crit, esc = lookup_critique(rid)
            b, d = lookup_dates(rid)

            # Footer text and color depend on which kind of parent this is.
            if missing:
                footer = f"{role.upper()} GAP — no proposal"
                node_kwargs = dict(_COLOR_GRAY)
                # Hollow / dashed to read as "still missing"
                node_kwargs["style"] = "rounded,dashed"
            elif proposed:
                footer = f"PROPOSED {role.upper()} {_verdict_footer(crit, esc)}"
                node_kwargs = dict(_color_for(hyp, crit, esc))
                # Dashed border distinguishes "not yet in the GEDCOM" from
                # in-GEDCOM relationships even when verdict colors agree.
                node_kwargs["style"] = "rounded,filled,dashed"
            else:
                footer = f"{role.upper()} {_verdict_footer(crit, esc)}"
                node_kwargs = _color_for(hyp, crit, esc)

            s.node(
                nid,
                _node_label(ref.get("name") or "?", b, d, footer),
                **node_kwargs,
            )

            edge_label = (
                f"proposed {role}" if proposed
                else (f"missing {role}" if missing else role)
            )
            edge_kwargs: dict[str, str] = {}
            if proposed or missing:
                edge_kwargs["style"] = "dashed"
            dot.edge(nid, "subject", label=edge_label, **edge_kwargs)

    spouses = family.get("spouses") or []
    with dot.subgraph() as s:
        s.attr(rank="same")
        s.node("subject")
        for idx, ref in enumerate(spouses):
            ref = ref or {}
            nid = f"spouse_{idx}"
            rid = ref.get("record_id") or ""
            hyp, crit, esc = lookup_critique(rid)
            b, d = lookup_dates(rid)
            s.node(nid, _node_label(ref.get("name") or "?", b, d, f"SPOUSE {_verdict_footer(crit, esc)}"), **_color_for(hyp, crit, esc))
            dot.edge("subject", nid, label="spouse", dir="none", style="dashed")

    children = family.get("children") or []
    with dot.subgraph() as s:
        s.attr(rank="same")
        for idx, ref in enumerate(children):
            ref = ref or {}
            nid = f"child_{idx}"
            rid = ref.get("record_id") or ""
            hyp, crit, esc = lookup_critique(rid)
            b, d = lookup_dates(rid)
            s.node(nid, _node_label(ref.get("name") or "?", b, d, f"CHILD {_verdict_footer(crit, esc)}"), **_color_for(hyp, crit, esc))
            dot.edge("subject", nid, label="child")

    return dot


# =====================================================================
# Results rendering
# =====================================================================

def render_results(result: dict) -> None:
    hypotheses = result.get("hypotheses") or []
    critiques = result.get("critiques") or []
    revision_count = int(result.get("revision_count") or 0)
    final_report = result.get("final_report") or ""

    escalations = check_escalation(hypotheses, critiques, revision_count)
    n_total = len(escalations)
    n_escalated = sum(1 for e in escalations if e["escalation_flag"])

    if n_total == 0:
        st.warning("Pipeline produced no hypotheses to evaluate.")
    elif n_escalated == 0:
        st.success(f"All {n_total} findings accepted — no human review required.")
    else:
        st.error(f"{n_escalated} of {n_total} findings flagged for human review.")

    critique_by_id = {c.get("hypothesis_id", ""): c for c in critiques}
    esc_by_id = {e["hypothesis_id"]: e for e in escalations}

    if hypotheses:
        st.markdown("#### Findings")
        for hyp in hypotheses:
            hyp_id = hyp.get("hypothesis_id", "")
            relationship = hyp.get("proposed_relationship", "(unnamed)")
            critique = critique_by_id.get(hyp_id) or {}
            esc = esc_by_id.get(hyp_id) or {}
            verdict = critique.get("verdict", "?")
            flagged = bool(esc.get("escalation_flag"))
            header = f"**{relationship}** — `{hyp_id}` — verdict: `{verdict}`"
            if flagged:
                with st.container(border=True):
                    st.error(header)
                    for reason in esc.get("escalation_reasons") or []:
                        st.markdown(f"- {reason}")
            elif verdict == "flag_uncertain":
                with st.container(border=True):
                    st.warning(header)
            else:
                with st.container(border=True):
                    st.success(header)

    with st.expander("Full report", expanded=False):
        if final_report.strip():
            st.markdown(final_report)
        else:
            st.info("No final report was produced.")

    with st.expander("Pipeline trace log", expanded=False):
        trace_log = result.get("trace_log") or []
        if trace_log:
            st.code("\n".join(str(t) for t in trace_log), language="text")
        else:
            st.write("_(empty)_")

    with st.expander("Download artifacts", expanded=False):
        trace_paths = st.session_state.get("trace_paths")
        if trace_paths:
            st.write(f"**JSON trace:** `{trace_paths.get('json_path')}`")
            st.write(f"**Markdown trace:** `{trace_paths.get('md_path')}`")
        st.download_button(
            "Download report (markdown)",
            data=final_report or "",
            file_name="genealogy_report.md",
            mime="text/markdown",
            disabled=not final_report.strip(),
        )


# =====================================================================
# Audit helpers
# =====================================================================

def _find_person(persons, name_query, birth_year=None, location=None):
    """Find the best-matching person using surname gate + name + birth year + location.

    Two-stage matching:
      1. Surname gate: extract the last word of the query as the presumed
         surname. Only consider candidates whose surname field fuzzy-matches
         it above 0.60. This prevents phonetic false positives like
         "Joan Knorr" matching "James Moore" (same Soundex, different surname).
      2. Composite score: name similarity + birth year bonus + location bonus.
         Same logic as the Profile Synthesizer's disambiguation.
    """
    from tools.fuzzy_match import name_match_score
    from tools.date_utils import get_year

    # Extract presumed surname from query (last word).
    query_parts = name_query.strip().split()
    query_surname = query_parts[-1] if query_parts else ""

    target_year = None
    if birth_year:
        try:
            target_year = int(str(birth_year).strip())
        except (ValueError, TypeError):
            pass
    target_loc_tokens = set()
    if location:
        target_loc_tokens = {
            t.lower() for t in location.replace(",", " ").split() if len(t) >= 2
        }

    best, best_score = None, 0.0
    for p in persons:
        pname = p.get("name") or ""
        if not pname:
            continue

        # Stage 1: surname gate.
        p_surname = p.get("surname") or ""
        if query_surname and p_surname:
            surname_score = name_match_score(query_surname, p_surname)
            if surname_score < 0.60:
                continue
        elif query_surname and not p_surname:
            # No surname on record — check if query surname appears in full name.
            if query_surname.lower() not in pname.lower():
                continue

        # Stage 2: composite score.
        score = name_match_score(name_query, pname)

        if target_year:
            p_year = get_year(p.get("birth_date"))
            if p_year:
                diff = abs(target_year - p_year)
                if diff == 0:
                    score += 1.0
                elif diff <= 2:
                    score += 0.5
                else:
                    score -= 0.5

        if target_loc_tokens:
            p_place = (p.get("birth_place") or "").lower()
            p_tokens = {t for t in p_place.replace(",", " ").split() if len(t) >= 2}
            shared = target_loc_tokens & p_tokens
            if shared:
                score += 0.5

        if score > best_score:
            best_score = score
            best = p

    if best and best_score >= 0.60:
        return best, best_score
    return None, best_score


def render_audit_results(results, pass2=None):
    import pandas as pd

    impossible = sum(1 for r in results if r["severity"] == "impossible")
    flagged = sum(1 for r in results if r["severity"] == "flagged")
    ok = sum(1 for r in results if r["severity"] == "ok")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Checked", len(results))
    c2.metric("Impossible", impossible)
    c3.metric("Flagged", flagged)
    c4.metric("OK", ok)

    rows = []
    for r in results:
        rows.append({
            "Severity": r["severity"].upper(),
            "Child": r["child_name"],
            "Role": r["role"],
            "Parent": r["parent_name"],
            "Age": f"{r['age_gap']}y" if r["age_gap"] is not None else "-",
            "Geo": r["geo_verdict"] or "-",
        })
    df = pd.DataFrame(rows)

    def _color(val):
        return {"IMPOSSIBLE": "background-color: #f8d7da; color: #721c24",
                "FLAGGED": "background-color: #fff3cd; color: #856404",
                "OK": "background-color: #d4edda; color: #155724"}.get(val, "")
    st.dataframe(df.style.map(_color, subset=["Severity"]),
                 use_container_width=True, hide_index=True)

    # Show issues as full-width text below the table.
    flagged = [r for r in results if r["issues"]]
    if flagged:
        with st.expander(f"Issue details ({len(flagged)} relationships)", expanded=True):
            for r in flagged:
                st.markdown(f"**{r['child_name']} <- {r['role']} -> {r['parent_name']}**")
                for issue in r["issues"]:
                    st.markdown(f"- {issue}")

    if pass2:
        st.subheader("Deep Audit Results (LLM)")
        for dr in pass2:
            verdicts = dr.get("deep_verdicts") or [dr.get("deep_verdict", "?")]
            confs = dr.get("deep_confs") or []
            st.markdown(
                f"**{dr['child_name']}** <- {dr['role']} -> **{dr['parent_name']}**: "
                f"verdicts={verdicts}, confidence={confs}, time={dr.get('deep_elapsed', '?')}s"
            )
            for issue in (dr.get("deep_issues") or []):
                st.markdown(f"- {issue}")


# =====================================================================
# DNA rendering
# =====================================================================

def render_dna_analysis(dna: dict) -> None:
    st.metric("Total Matches", dna.get("total_matches", 0))
    st.write(f"**Platform:** {dna.get('platform', '?')}  |  **Consistency:** {dna.get('aggregate_consistency', '?')}")

    dist = dna.get("relationship_distribution") or {}
    if dist:
        st.markdown("**Match distribution:**")
        for tier, count in dist.items():
            if count:
                st.write(f"- {tier}: {count}")

    xrefs = dna.get("cross_references") or []
    if xrefs:
        st.markdown(f"**GEDCOM cross-references ({len(xrefs)}):**")
        for xr in xrefs[:10]:
            st.write(f"- **{xr.get('dna_name')}** ({xr.get('shared_cM')} cM) "
                     f"-> **{xr.get('gedcom_name')}** (`{xr.get('gedcom_id')}`)")

    pc = dna.get("prediction_checks") or {}
    if pc.get("total_with_prediction"):
        st.write(f"**Platform predictions:** {pc.get('consistent', 0)}/{pc['total_with_prediction']} consistent")

    findings = dna.get("findings") or []
    if findings:
        with st.expander("DNA Findings", expanded=True):
            for f in findings:
                st.write(f"- {f}")


# =====================================================================
# CSS
# =====================================================================

_CSS = """
<style>
  [data-testid="stAppViewContainer"] .block-container {
      padding-top: 2.2rem; max-width: 1200px;
  }
  [data-testid="stAppViewContainer"] h1 {
      color: #1a1a1a; font-weight: 700; letter-spacing: -0.01em;
      border-bottom: 3px solid #C41230; padding-bottom: 0.4rem; margin-bottom: 0.2rem;
  }
  [data-testid="stTabs"] button[role="tab"] {
      font-weight: 600; font-size: 0.95rem; padding: 0.45rem 1.2rem;
  }
  .agent-row {
      padding: 0.55rem 0.85rem; margin: 0.3rem 0; background: #F0F2F6;
      border-left: 3px solid #C41230; border-radius: 4px; font-size: 0.95rem;
      display: flex; align-items: center; gap: 0.6rem;
  }
  .agent-row.state-waiting { opacity: 0.55; border-left-color: #B0B0B0; }
  .agent-row.state-done    { border-left-color: #0F6E56; background: #EAF7F1; }
  .agent-row.state-revised { border-left-color: #BA7517; background: #FBF3E4; }
  .agent-row .agent-label  { font-weight: 600; }
  .agent-row .agent-state  { color: #555; }
  .agent-row .agent-detail { color: #8a6d1f; font-style: italic; font-size: 0.85rem; }
  div[data-testid="stAlert"] {
      border-radius: 6px; border-left-width: 5px !important;
  }
</style>
"""


# =====================================================================
# Page setup
# =====================================================================

st.set_page_config(page_title="Multi-Agent Genealogy Research", layout="wide")
st.markdown(_CSS, unsafe_allow_html=True)
st.title("Multi-Agent Genealogical Research")
st.caption("v5 — reconciled: pipeline + family tree + audit + DNA")

# =====================================================================
# Mode selector — Live (runs the pipeline; requires an API key) vs
# Replay (loads a saved pipeline trace; makes no LLM calls).
#
# Replay mode lets graders evaluate the system end-to-end against the
# committed traces in traces/demos/ and traces/redacted/ without
# configuring an Anthropic API key. This was a stated requirement from
# the project's outset.
# =====================================================================
with st.sidebar:
    st.markdown("### Mode")
    app_mode = st.radio(
        "How should the app run?",
        options=["Live (run pipeline)", "Replay (no API key)"],
        index=0,
        key="app_mode",
        help=(
            "**Live** invokes the LangGraph pipeline against the GEDCOM "
            "and DNA you choose. Requires `ANTHROPIC_API_KEY` in `.env` "
            "(and optional vendor keys for cross-vendor experiments).\n\n"
            "**Replay** loads a previously-saved pipeline trace from "
            "`traces/demos/` or `traces/redacted/` and renders the same "
            "tabs as a live run, with no LLM calls. Use this to evaluate "
            "the system without configuring API access."
        ),
    )
    is_replay = app_mode.startswith("Replay")
    st.markdown("---")
    st.caption(
        "**Live**: Pipeline tab runs the graph and writes a new trace.\n\n"
        "**Replay**: Pipeline / Family Tree / DNA Analysis tabs render "
        "from a saved trace. Audit Pass 1 is deterministic and works in "
        "either mode; Audit Pass 2 (LLM) requires Live."
    )

# Grader-facing one-liner: explain what's available on a fresh clone.
# Public GEDCOMs (Kennedy/Queen/Habsburg/Middle Earth) and synthetic DNA demos
# ship with the repo. Personal data dirs are gitignored — Personal entries
# only appear in the dropdowns when you've populated them locally.
if is_replay:
    st.info(
        "**Replay mode** — loading saved pipeline traces from "
        "`traces/demos/` and `traces/redacted/`. **No LLM calls are made.** "
        "To run the pipeline live, switch to Live mode in the sidebar.",
        icon="🎬",
    )
else:
    st.info(
        "**Data:** public GEDCOMs (Kennedy, Queen, Habsburg, Middle Earth) and "
        "synthetic DNA demos ship with the repo. `data/PII Trees/` and `data/DNA/` "
        "are gitignored — Personal entries only appear if you've populated those folders.",
        icon="ℹ️",
    )

tab_pipeline, tab_tree, tab_audit, tab_dna = st.tabs(
    ["Pipeline", "Family Tree", "Audit", "DNA Analysis"]
)


# =====================================================================
# TAB 1: PIPELINE
# =====================================================================

with tab_pipeline:
    # Replay branch — runs first if Replay mode is selected. Skips the live
    # form entirely (gated below) and renders results from a saved trace.
    if is_replay:
        st.markdown("### Pick a saved pipeline trace")
        available_traces = discover_traces()
        if not available_traces:
            st.error(
                "No replay traces found under `traces/demos/` or "
                "`traces/redacted/`. The repo ships pipeline trace demos "
                "(JFK, Maria Theresia, Queen Victoria, plus three "
                "gap-mode traces and one redacted Moore-family trace); "
                "if they're missing, your clone may be incomplete."
            )
        else:
            # Category toggle — choose query-mode (parent investigation)
            # or gap-detection traces. The dropdown below lists only the
            # traces matching the chosen category, so a grader who clicks
            # "Gap detection" sees only the gap-mode demos.
            replay_category = st.radio(
                "Trace category",
                options=["Query mode", "Gap detection mode"],
                horizontal=True,
                index=0,
                key="replay_category",
                help=(
                    "**Query mode** — investigate a known relationship "
                    "(e.g. 'Who are JFK's parents?'). Demos: JFK, Maria "
                    "Theresia, Queen Victoria, plus the redacted Moore "
                    "trace.\n\n"
                    "**Gap detection mode** — fill a missing parental "
                    "link in the GEDCOM. Demos: Kennedy / Habsburg / "
                    "Queen gap-fill runs."
                ),
            )

            # Detect a category change so we can reset the trace selectbox
            # and the loaded trace. Without this, the selectbox would keep
            # a stale value that's no longer in the filtered options list,
            # and the Family Tree / DNA Analysis tabs would render the
            # previous category's trace until the user picked a new one.
            prev_category = st.session_state.get("_replay_category_prev")
            if prev_category is not None and prev_category != replay_category:
                st.session_state.pop("replay_trace_pick", None)
                st.session_state.pop("pipeline_result", None)
                st.session_state.pop("trace_paths", None)
            st.session_state["_replay_category_prev"] = replay_category

            wanted_category = "gap" if replay_category.startswith("Gap") else "query"
            filtered_traces = [
                (label, path)
                for (label, path, cat) in available_traces
                if cat == wanted_category
            ]

            if not filtered_traces:
                st.warning(
                    f"No {replay_category.lower()} traces found in "
                    "`traces/demos/` or `traces/redacted/`."
                )
            else:
                trace_options = [TRACE_NONE_SENTINEL] + [label for label, _ in filtered_traces]
                trace_label_to_path = {label: path for label, path in filtered_traces}
                selected_trace = st.selectbox(
                    "Trace",
                    options=trace_options,
                    index=0,
                    key="replay_trace_pick",
                    help=(
                        "**Demo:** synthetic DNA / public-data trees — fully "
                        "reproducible, no PII.\n\n"
                        "**Redacted:** real-tree run with names pseudonymized "
                        "(PERSON_NNN) — demonstrates real-data behavior "
                        "without exposing identity."
                    ),
                )
                if selected_trace and selected_trace != TRACE_NONE_SENTINEL:
                    trace_path = trace_label_to_path.get(selected_trace)
                    try:
                        loaded = load_trace_from_disk(trace_path)
                    except Exception as exc:
                        st.error(f"Could not load trace: {exc}")
                    else:
                        # Structural validation. A pipeline trace must have
                        # `final_report` and at least one of
                        # `hypotheses` / `profiles` / `trace_log`. Anything
                        # else (a malformed JSON, a different schema, etc.)
                        # would render as empty placeholders downstream;
                        # error out clearly here instead.
                        is_pipeline_trace = (
                            isinstance(loaded, dict)
                            and "final_report" in loaded
                            and any(
                                isinstance(loaded.get(k), list) and loaded.get(k)
                                for k in ("hypotheses", "profiles", "trace_log")
                            )
                        )
                        if not is_pipeline_trace:
                            st.error(
                                f"`{Path(trace_path).name}` doesn't look "
                                "like a pipeline trace. Audit JSONs use "
                                "the Audit-tab loader instead; arbitrary "
                                "JSON files cannot be replayed here."
                            )
                            # Drop any previously-loaded result so the
                            # Family Tree / DNA Analysis tabs don't keep
                            # rendering an earlier trace while this tab
                            # shows the validation-error message.
                            st.session_state.pop("pipeline_result", None)
                            st.session_state.pop("trace_paths", None)
                        else:
                            metadata = loaded.get("trace_metadata") or {}
                            timestamp = metadata.get("timestamp", "?")
                            label = metadata.get("label", "?")
                            st.success(
                                f"Loaded trace **{label}** from "
                                f"{_format_trace_timestamp(timestamp)}. "
                                "Family Tree and DNA Analysis tabs also render "
                                "from this trace."
                            )
                            # Stash so Family Tree + DNA tabs auto-render.
                            st.session_state["pipeline_result"] = loaded
                            render_results(loaded)
                else:
                    # User moved back to the sentinel — clear any previously-loaded
                    # trace from session_state so the Family Tree and DNA Analysis
                    # tabs don't render stale data while this tab shows the
                    # "pick a trace" message.
                    if "pipeline_result" in st.session_state:
                        del st.session_state["pipeline_result"]
                    if "trace_paths" in st.session_state:
                        del st.session_state["trace_paths"]
                    st.info(
                        f"Pick a {replay_category.lower()} trace from "
                        "the dropdown above to render its saved pipeline "
                        "output."
                    )

# Live branch — original form-driven flow. Gated so it does not appear in
# Replay mode. (Using `if not is_replay:` instead of an `else:` block keeps
# the existing 300+ lines of form code at their current indentation.)
if not is_replay:
  with tab_pipeline:
    available_gedcoms = discover_gedcom_files()
    available_dna = discover_dna_files()

    # Mode selector lives OUTSIDE the form so changing it triggers an
    # immediate rerun. Inside the form, the query and target-person inputs
    # disable when Gap detection is selected, giving the user a clear
    # visual signal that those fields are not used in that mode.
    mode_choice = st.radio(
        "Mode",
        options=["Auto-detect", "Query", "Audit", "Gap detection"],
        horizontal=True,
        index=0,
        key="pipeline_mode",
        help=(
            "**Auto-detect** routes based on query keywords "
            "(`audit`, `questionable`, `N generations`, …) — "
            "convenient but invisible.\n\n"
            "**Query** — investigate a specific person/relationship "
            "(full pipeline).\n\n"
            "**Audit** — walk every parent-child link in a subtree "
            "rooted at the target person.\n\n"
            "**Gap detection** — scan the GEDCOM for persons missing "
            "parent links and rank them by available evidence."
        ),
    )
    is_gap_mode = mode_choice == "Gap detection"
    if is_gap_mode:
        st.info(
            "Gap detection scans the entire GEDCOM for persons missing "
            "parent links and ranks candidates by available evidence. "
            "**No query or target person needed** — pick a GEDCOM and "
            "click Run. The query and target-person fields below are "
            "disabled in this mode.",
            icon="🔍",
        )

    with st.form("pipeline_form"):
        st.markdown("### Inputs")

        col_ged, col_dna = st.columns([3, 2])
        with col_ged:
            selectbox_options = [UPLOAD_SENTINEL] + available_gedcoms
            selected_gedcom = st.selectbox(
                "Pick a GEDCOM from data/", options=selectbox_options, index=0,
                help="Choose a file from data/ or upload below. Upload takes precedence.",
            )
            uploaded = st.file_uploader(
                "...or upload (.ged or .zip)", type=["ged", "zip"],
                accept_multiple_files=False,
            )
        with col_dna:
            # Build DNA dropdown options. Sentinel first so the default is "no DNA".
            dna_options = [DNA_NONE_SENTINEL] + [label for label, _ in available_dna]
            dna_label_to_path = {label: path for label, path in available_dna}
            selected_dna_label = st.selectbox(
                "DNA file (optional)", options=dna_options, index=0,
                help=(
                    "Demos (synthetic) ship with the repo. "
                    "Personal files in data/DNA/ are gitignored — "
                    "they only appear if you've populated that folder."
                ),
                disabled=is_gap_mode,
            )
            dna_upload = st.file_uploader(
                "...or upload (.csv)", type=["csv"], key="pipeline_dna_upload",
                help="GEDmatch or MyHeritage match list. Upload takes precedence.",
                disabled=is_gap_mode,
            )

        query = st.text_input(
            "Research query",
            value="Who were the parents of John F. Kennedy?",
            help=(
                "In Auto-detect, phrases like 'audit my tree' or "
                "'going back 3 generations' will trigger Audit mode. "
                "Ignored in Gap detection mode."
            ),
            disabled=is_gap_mode,
        )
        st.markdown("**Target person**" + (" _(not used in Gap detection mode)_" if is_gap_mode else ""))
        c1, c2, c3 = st.columns([2, 1, 2])
        with c1:
            tp_name = st.text_input("Name", value="John F. Kennedy", disabled=is_gap_mode)
        with c2:
            tp_birth = st.text_input("Approx. birth year", value="1917", disabled=is_gap_mode)
        with c3:
            tp_loc = st.text_input("Location", value="Brookline, MA", disabled=is_gap_mode)

        submitted = st.form_submit_button("Run", type="primary")

    if submitted:
        # Resolve GEDCOM source.
        if uploaded is not None:
            source_label = f"uploaded: {uploaded.name}"
            try:
                gedcom_text = extract_gedcom_text(uploaded)
            except Exception as exc:
                st.error(f"Could not read uploaded GEDCOM: {exc}")
                st.stop()
        elif selected_gedcom and selected_gedcom != UPLOAD_SENTINEL:
            source_label = f"data/{selected_gedcom}"
            try:
                gedcom_text = load_gedcom_from_disk(selected_gedcom)
            except Exception as exc:
                st.error(f"Could not read {source_label}: {exc}")
                st.stop()
        else:
            st.error("Pick a GEDCOM from the dropdown or upload one.")
            st.stop()

        if not tp_name.strip():
            st.error("Target person name is required.")
            st.stop()

        # Resolve DNA CSV. Upload takes precedence over the dropdown selection.
        dna_csv = None
        dna_source_label = None
        if dna_upload is not None:
            dna_csv = dna_upload.getvalue().decode("utf-8-sig", errors="replace")
            dna_source_label = f"uploaded: {dna_upload.name}"
        elif selected_dna_label and selected_dna_label != DNA_NONE_SENTINEL:
            dna_path = dna_label_to_path.get(selected_dna_label)
            if dna_path:
                try:
                    dna_csv = load_dna_from_disk(dna_path)
                    dna_source_label = selected_dna_label
                except Exception as exc:
                    st.warning(f"Could not load DNA file {selected_dna_label!r}: {exc}")
                    dna_csv = None

        st.caption(f"GEDCOM source: `{source_label}`")
        if dna_source_label:
            st.caption(f"DNA source: `{dna_source_label}`")

        # Resolve mode. Explicit choice overrides keyword auto-detection.
        if mode_choice == "Query":
            audit_mode, gap_mode = False, False
            mode_reason = "explicit Query mode"
        elif mode_choice == "Audit":
            audit_mode, gap_mode = True, False
            mode_reason = "explicit Audit mode"
        elif mode_choice == "Gap detection":
            audit_mode, gap_mode = False, True
            mode_reason = "explicit Gap detection mode"
        else:  # Auto-detect
            audit_mode = is_audit_query(query)
            gap_mode = False
            # TODO: also auto-detect gap-mode keywords ("missing parents",
            # "broken links", "who are the parents of <unknown person>") and
            # route to gap_mode when matched.
            mode_reason = (
                "auto-detected: keyword match" if audit_mode
                else "auto-detected: standard query"
            )

        # Each submit gets a fresh slate for audit-followup state. The
        # audit branch repopulates audit_problems when Pass 1 finds
        # problems; gap and standard branches leave it cleared. Without
        # this consolidated reset, an audit run that finds zero problems
        # would leave a previous run's problems in session_state and the
        # Deep Audit button would render against stale data.
        for _stale_audit_key in (
            "audit_problems",
            "audit_gedcom_text",
            "audit_persons",
        ):
            st.session_state.pop(_stale_audit_key, None)

        if gap_mode:
            # Gap detection — submit handler does the scan once, then caches
            # the result in session_state so the picker UI below can survive
            # reruns triggered by widget interactions (selectbox / button).
            from tools.gap_scanner import find_research_candidates
            from tools.gedcom_parser import parse_gedcom_text

            with st.spinner("Scanning GEDCOM for missing parent links..."):
                gap_persons = parse_gedcom_text(gedcom_text)
                candidates = find_research_candidates(gap_persons)

            st.session_state["gap_candidates"] = candidates
            st.session_state["gap_gedcom_text"] = gedcom_text
            st.session_state["gap_persons_count"] = len(gap_persons)
            st.session_state["gap_mode_reason"] = mode_reason
            # Source label fingerprint — used by the persistent picker
            # below to invalidate the cache if the user changes GEDCOM
            # without re-clicking Run.
            st.session_state["gap_source_label"] = source_label
            # audit-followup state was already cleared at the top of the
            # submit block. No st.stop() and no further branches: gap
            # mode is a scan-only path on submit. The persistent picker
            # UI below renders the table and the single-gap-pipeline
            # button. The elif on the next line ensures the standard
            # pipeline does NOT also fire.

        elif audit_mode:
            gens = extract_generations_from_query(query)
            st.info(
                f"Routing: **audit mode** ({mode_reason}; {gens} generations). "
                "Running subtree audit."
            )

            from tools.gedcom_parser import parse_gedcom_text
            from tools.subtree_extractor import extract_all_relationships, extract_subtree
            from audit import pass1_audit

            persons = parse_gedcom_text(gedcom_text)
            root, score = _find_person(persons, tp_name.strip(),
                                        birth_year=tp_birth.strip(), location=tp_loc.strip())
            if not root:
                st.error(f"No person matching '{tp_name}' found in the GEDCOM.")
                st.stop()

            st.write(f"Root: **{root.get('name')}** (`{root.get('id')}`) — match score {score:.2f}")

            with st.spinner("Extracting subtree..."):
                subtree = extract_subtree(persons, root["id"], gens, "ancestors")
                relationships = extract_all_relationships(persons, root["id"], gens)

            st.write(f"Subtree: {len(subtree['persons'])} persons, {len(relationships)} relationships")

            with st.spinner("Running deterministic checks (Pass 1)..."):
                t0 = time.time()
                results = pass1_audit(relationships)
                elapsed = time.time() - t0

            st.caption(f"Pass 1 completed in {elapsed:.1f}s")
            render_audit_results(results)

            problems = [r for r in results if r["severity"] != "ok"]
            if problems:
                st.session_state["audit_problems"] = problems
                st.session_state["audit_gedcom_text"] = gedcom_text
                st.session_state["audit_persons"] = persons
            else:
                st.success("All relationships passed deterministic checks.")

        else:
            # Standard pipeline. audit-followup state was already cleared
            # at the top of the submit block.
            st.caption(f"Routing: standard pipeline ({mode_reason})")

            initial_state = {
                "query": query.strip(),
                "target_person": {
                    "name": tp_name.strip(),
                    "approx_birth": tp_birth.strip() or None,
                    "location": tp_loc.strip() or None,
                },
                "gedcom_text": gedcom_text,
                "gedcom_persons": [],
                "dna_csv": dna_csv,
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

            st.subheader("Pipeline progress")
            status_container = st.container()
            status_placeholders = {key: status_container.empty() for key, _ in AGENT_ORDER}

            start = time.time()
            try:
                result = run_pipeline(initial_state, status_placeholders)
            except Exception as exc:
                st.error(f"Pipeline failed: {exc}")
                st.exception(exc)
                st.stop()
            elapsed = time.time() - start

            st.info(f"Pipeline completed in {elapsed:.1f}s. See **Family Tree** and **DNA Analysis** tabs.")

            try:
                trace_paths = save_trace(result, label="streamlit")
            except Exception:
                trace_paths = None

            st.session_state["pipeline_result"] = result
            st.session_state["trace_paths"] = trace_paths

            # Render results inline.
            render_results(result)

    elif "pipeline_result" in st.session_state and not is_gap_mode:
        # Re-render the most recent live result so a user who navigates
        # away (changes mode, scrolls, switches tabs) and back doesn't
        # see only a "previous run cached" placeholder. Skipped in gap
        # mode — the gap picker block below renders its own results.
        st.caption(
            "Showing the most recent run. Click Run to invoke the "
            "pipeline again."
        )
        render_results(st.session_state["pipeline_result"])

    # Deep audit button (appears after audit routing flags problems).
    # audit_problems itself is the freshness marker: the audit submit
    # branch sets it; the gap and standard-query branches pop it. So
    # this block correctly fires for any submit that resolved to audit
    # mode — including auto-detected audit (mode_choice="Auto-detect"
    # with an audit-keyword query), which the previous gating missed.
    if st.session_state.get("audit_problems"):
        problems = st.session_state["audit_problems"]
        deep_n = st.number_input(
            f"Deep audit top N (of {len(problems)} flagged)",
            min_value=1, max_value=len(problems), value=min(5, len(problems)),
            key="pipe_deep_n",
        )
        if st.button(f"Deep Audit Top {deep_n}", key="btn_pipe_deep"):
            from audit import pass2_audit
            with st.spinner(f"Running LLM pipeline on {deep_n} relationships..."):
                pass2 = pass2_audit(
                    problems, st.session_state["audit_gedcom_text"],
                    st.session_state["audit_persons"], max_deep=deep_n,
                )
            render_audit_results(problems, pass2=pass2)

    # ------------------------------------------------------------------
    # Persistent gap-detection picker
    # Renders whenever Gap detection is the active mode AND we've scanned
    # a GEDCOM (results cached in session_state on form submit). Survives
    # reruns triggered by selectbox / button interactions.
    # ------------------------------------------------------------------
    # Detect GEDCOM-source change so we can hide stale gap-scan results
    # if the user switched the file without re-clicking Run.
    _gap_source_mismatch = False
    if is_gap_mode and st.session_state.get("gap_candidates") is not None:
        _cached_source = st.session_state.get("gap_source_label", "")
        _current_source: Optional[str] = None
        if uploaded is not None:
            _current_source = f"uploaded: {uploaded.name}"
        elif selected_gedcom and selected_gedcom != UPLOAD_SENTINEL:
            _current_source = f"data/{selected_gedcom}"
        if (
            _current_source
            and _cached_source
            and _current_source != _cached_source
        ):
            _gap_source_mismatch = True
            # Reset the page-number widget so the next re-scan against
            # a smaller GEDCOM doesn't try to render a non-existent page.
            st.session_state.pop("gap_page", None)
            st.session_state.pop("gap_pick_idx", None)
            st.markdown("---")
            st.warning(
                f"GEDCOM source changed from `{_cached_source}` to "
                f"`{_current_source}` since the last gap scan. Click "
                "**Run** above to re-scan against the new file. The "
                "candidate table is hidden until you re-run."
            )

    if (
        is_gap_mode
        and st.session_state.get("gap_candidates") is not None
        and not _gap_source_mismatch
    ):
        gap_candidates = st.session_state["gap_candidates"]
        gap_gedcom_text = st.session_state["gap_gedcom_text"]
        gap_persons_count = st.session_state.get("gap_persons_count", 0)
        gap_mode_reason = st.session_state.get("gap_mode_reason", "explicit Gap detection mode")

        st.markdown("---")
        st.info(f"Routing: **gap detection** ({gap_mode_reason}).")
        st.write(
            f"Parsed **{gap_persons_count}** persons; found "
            f"**{len(gap_candidates)}** with missing parent links and "
            f"enough data to investigate."
        )

        if not gap_candidates:
            st.success(
                "No gaps found that meet the data-richness threshold "
                "— every person with missing parents lacks enough fields "
                "to investigate productively."
            )
        else:
            # Paginated view — 50 candidates per page, ranked by data-field
            # count. Both the table and the per-gap selectbox draw from the
            # same page slice, so picking a candidate from the selectbox
            # always corresponds to a row visible in the table.
            total = len(gap_candidates)
            PAGE_SIZE = 50
            total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

            page = st.number_input(
                f"Page (50 per page; {total_pages} total)",
                min_value=1,
                max_value=total_pages,
                value=1,
                step=1,
                key="gap_page",
                help=(
                    f"All {total} candidates are ranked by data-field count "
                    "(max 7). Page 1 shows the richest candidates."
                ),
            )
            page = int(page)
            page_start = (page - 1) * PAGE_SIZE
            page_end = min(page_start + PAGE_SIZE, total)
            visible_candidates = gap_candidates[page_start:page_end]

            # Candidate table.
            import pandas as pd
            rows = []
            for cand in visible_candidates:
                p = cand["person"]
                rows.append({
                    "Name": p.get("name") or "(unknown)",
                    "Born": p.get("birth_date") or "-",
                    "Place": p.get("birth_place") or "-",
                    "Missing": cand["missing_role"],
                    "Data fields": cand["data_fields"],
                    "Auto-query": cand["query"],
                })
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption(
                f"Showing candidates {page_start + 1}–{page_end} of {total} "
                f"(page {page} of {total_pages})."
            )

            # Single-gap pipeline picker. The selectbox lists exactly the 50
            # candidates visible in the table above on the current page.
            st.markdown("### Investigate a single gap")
            st.caption(
                "Pick one candidate from the current page and run the full "
                "pipeline on it. Each run takes 30–90 seconds and uses API "
                "credits. Family Tree and DNA Analysis tabs render from the "
                "result. To investigate a candidate from a different page, "
                "change the page number above first."
            )
            cand_labels = [
                f"{c['person'].get('name') or '(unknown)'} — missing "
                f"{c['missing_role']}  ({c['data_fields']} fields)"
                for c in visible_candidates
            ]
            selected_idx = st.selectbox(
                "Gap candidate",
                options=list(range(len(cand_labels))),
                format_func=lambda i: cand_labels[i],
                key="gap_pick_idx",
            )
            selected_cand = visible_candidates[selected_idx]
            role = selected_cand["missing_role"]
            if role == "both":
                role = st.radio(
                    "This person is missing both parents — investigate which first?",
                    options=["father", "mother"],
                    horizontal=True,
                    key="gap_role_pick",
                )

            if st.button(
                "Run full pipeline on this gap",
                type="primary",
                key="btn_gap_run_one",
            ):
                person = selected_cand["person"]
                gap_initial_state = {
                    "query": selected_cand["query"],
                    "target_person": {
                        "name": person.get("name") or "(unknown)",
                        "approx_birth": person.get("birth_date"),
                        "location": person.get("birth_place"),
                        "gap_mode": True,
                        "child_id": person["id"],
                        "missing_role": role,
                    },
                    "gedcom_text": gap_gedcom_text,
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

                # Per-agent progress UI matching the live-pipeline tab.
                with st.container(border=True):
                    gap_status_placeholders = {}
                    for agent_id, label in AGENT_ORDER:
                        gap_status_placeholders[agent_id] = st.empty()
                        render_agent_row(
                            gap_status_placeholders[agent_id], label, "waiting"
                        )

                with st.spinner(
                    f"Investigating {person.get('name') or 'this gap'}..."
                ):
                    try:
                        gap_result = run_pipeline(
                            gap_initial_state, gap_status_placeholders
                        )
                    except Exception as exc:
                        st.error(
                            f"Pipeline failed: {type(exc).__name__}: {exc}"
                        )
                        raise

                # Save trace under the standard path.
                safe_label = "".join(
                    ch if ch.isalnum() or ch in "-_" else "_"
                    for ch in (
                        f"gap_{person.get('name') or 'unknown'}_{role}"
                    )
                )
                gap_trace_paths = save_trace(gap_result, label=safe_label)
                st.session_state["pipeline_result"] = gap_result
                st.session_state["trace_paths"] = gap_trace_paths

                st.success(
                    "Pipeline complete. Results below; Family Tree and DNA "
                    "Analysis tabs also render from this run."
                )
                render_results(gap_result)


# =====================================================================
# TAB 2: FAMILY TREE
# =====================================================================

with tab_tree:
    if "pipeline_result" in st.session_state:
        st.subheader("Immediate family tree")
        st.caption(
            "**Color** — Blue = subject · Green = accepted (conf ≥ 0.75) · "
            "Amber = flag_uncertain / low-conf · Red = rejected / escalated · "
            "Gray = no verdict.  \n"
            "**Border** — Solid = in GEDCOM · Dashed-filled = "
            "proposed gap-fill (not yet in GEDCOM) · Dashed-hollow = "
            "still-missing gap (no proposal).  \n"
            "**Edge label** — `father` / `mother` = in GEDCOM · "
            "`proposed father` / `proposed mother` = pipeline proposal · "
            "`missing father` / `missing mother` = gap that didn't get a proposal."
        )
        dot = build_family_tree(st.session_state["pipeline_result"])
        if dot:
            st.graphviz_chart(dot, use_container_width=True)
        else:
            st.info("No profile produced — cannot draw a tree.")
    else:
        st.info("Run the pipeline from the **Pipeline** tab to see the family tree.")


# =====================================================================
# TAB 3: AUDIT
# =====================================================================

with tab_audit:
    st.header("Subtree Audit")
    st.caption("Select a GEDCOM, pick a root person, and audit N generations.")
    if is_replay:
        st.info(
            "**Replay mode note:** Audit Pass 1 (deterministic Tier 1 + "
            "geographic checks) runs without an API key. Audit Pass 2 "
            "(LLM deep audit) requires `ANTHROPIC_API_KEY`; switch to "
            "Live mode for it. Or load a saved audit run below to see "
            "Pass 1 + Pass 2 results without any API calls.",
            icon="ℹ️",
        )

    # ------------------------------------------------------------------
    # Load saved audit (replay)
    # Available in both Live and Replay modes — saved audits are useful
    # reference artifacts in either mode.
    # ------------------------------------------------------------------
    saved_audits: list[tuple[str, Path]] = []
    for src in (TRACES_DEMOS_DIR, TRACES_REDACTED_DIR):
        if src.is_dir():
            for jp in sorted(src.glob("audit_*.json")):
                if jp.is_file() and not jp.name.endswith(".map.json"):
                    label_prefix = "Demo" if src is TRACES_DEMOS_DIR else "Redacted"
                    saved_audits.append((f"{label_prefix}: {jp.stem}", jp))

    if saved_audits:
        with st.expander("📂 Load a saved audit run (no API calls needed)", expanded=is_replay):
            audit_options = ["(none — run live below)"] + [label for label, _ in saved_audits]
            audit_path_by_label = {label: path for label, path in saved_audits}
            selected_audit_label = st.selectbox(
                "Saved audit",
                options=audit_options,
                index=0,
                key="audit_replay_pick",
                help=(
                    "Picks a previously-saved audit run from "
                    "`traces/demos/audit_*.json`. Loads Pass 1 + Pass 2 "
                    "results directly — no GEDCOM parsing, no LLM calls."
                ),
            )
            if (
                selected_audit_label
                and selected_audit_label != "(none — run live below)"
            ):
                audit_path = audit_path_by_label[selected_audit_label]
                try:
                    saved = json.loads(audit_path.read_text(encoding="utf-8"))
                except Exception as exc:
                    st.error(f"Could not load audit JSON: {exc}")
                else:
                    meta = saved.get("audit_metadata") or {}
                    st.success(
                        f"Loaded **{meta.get('label', '?')}** "
                        f"({_format_trace_timestamp(meta.get('timestamp', '?'))}). "
                        f"Pass 1 ran in {meta.get('pass1_elapsed_sec', '?')}s; "
                        f"Pass 2 in "
                        f"{meta.get('pass2_elapsed_sec', '— skipped')}s."
                    )

                    # Render the saved audit through the same
                    # render_audit_results helper the live path uses.
                    # These values stay LOCAL — we deliberately don't
                    # populate aud_results / aud_text / aud_persons in
                    # session_state, so the loaded audit and the live
                    # audit form below stay independent. A click on the
                    # live form's Deep-Audit button operates only on
                    # the live form's data, not on what was loaded here.
                    pass1 = saved.get("pass1_results") or []
                    pass2 = saved.get("pass2_results")
                    root_loaded = saved.get("root") or {}
                    subtree_loaded = saved.get("subtree") or {}
                    gens_loaded = saved.get("generations", "?")

                    st.write(
                        f"Root: **{root_loaded.get('name', '?')}** "
                        f"(`{root_loaded.get('id', '?')}`); "
                        f"{len(subtree_loaded.get('persons') or [])} persons in "
                        f"the {gens_loaded}-generation subtree; "
                        f"{len(pass1)} relationships audited."
                    )

                    n_imp = sum(1 for r in pass1 if r.get("severity") == "impossible")
                    n_flag = sum(1 for r in pass1 if r.get("severity") == "flagged")
                    n_ok = sum(1 for r in pass1 if r.get("severity") == "ok")
                    st.caption(
                        f"Pass 1: {n_imp} impossible, {n_flag} flagged, {n_ok} ok."
                    )

                    render_audit_results(pass1, pass2=pass2)

                    if pass2 is None:
                        st.caption(
                            "_(This saved run skipped Pass 2 because Pass 1 found "
                            "no questionable relationships.)_"
                        )
        st.markdown("---")

    aud_gedcoms = discover_gedcom_files()
    c_sel, c_up = st.columns(2)
    with c_sel:
        aud_selection = st.selectbox(
            "GEDCOM library", options=["(none)"] + aud_gedcoms,
            index=0, key="audit_ged_select",
        )
    with c_up:
        aud_upload = st.file_uploader("...or upload", type=["ged"], key="audit_ged_upload")

    aud_text: str | None = None
    if aud_upload:
        aud_text = aud_upload.getvalue().decode("utf-8", errors="replace")
    elif aud_selection and aud_selection != "(none)":
        try:
            aud_text = load_gedcom_from_disk(aud_selection)
        except Exception as e:
            st.error(f"Failed to load {aud_selection}: {e}")

    if aud_text is None:
        st.info(
            "Pick a GEDCOM from the dropdown or upload one to begin. "
            "The audit walks every parent-child link in the subtree and "
            "checks for date/age impossibilities and geographic implausibility."
        )

    if aud_text:
        from tools.gedcom_parser import parse_gedcom_text
        persons_aud = parse_gedcom_text(aud_text)
        st.success(f"Parsed {len(persons_aud)} persons")

        c1, c2 = st.columns([3, 1])
        with c1:
            aud_name = st.text_input("Root person name", placeholder="e.g. James Joseph Moore")
        with c2:
            aud_gens = st.slider("Generations", 1, 5, 3, key="audit_gen")

        root_aud = None
        if aud_name:
            root_aud, score = _find_person(persons_aud, aud_name)
            if root_aud:
                st.info(f"Root: **{root_aud.get('name')}** (`{root_aud.get('id')}`) — score {score:.2f}")
            else:
                st.warning(f"No match for '{aud_name}' (best {score:.2f})")

        if root_aud and st.button("Run Audit", type="primary", key="btn_audit"):
            # Clear any stale audit state from a previous run before
            # populating with fresh results. Without this, a Pass 2 click
            # could replay against the previous root/subtree.
            for _stale_key in (
                "aud_results",
                "aud_subtree",
                "aud_root",
                "aud_text",
                "aud_persons",
                "aud_gens",
            ):
                st.session_state.pop(_stale_key, None)

            from tools.subtree_extractor import extract_all_relationships, extract_subtree
            from audit import pass1_audit, pass2_audit, generate_report

            with st.spinner("Extracting subtree..."):
                subtree = extract_subtree(persons_aud, root_aud["id"], aud_gens, "ancestors")
                rels = extract_all_relationships(persons_aud, root_aud["id"], aud_gens)

            st.write(f"Subtree: {len(subtree['persons'])} persons, {len(rels)} relationships")

            with st.spinner("Pass 1: deterministic checks..."):
                t0 = time.time()
                aud_results = pass1_audit(rels)
                elapsed = time.time() - t0

            st.caption(f"Pass 1: {elapsed:.1f}s")
            render_audit_results(aud_results)

            st.session_state["aud_results"] = aud_results
            st.session_state["aud_subtree"] = subtree
            st.session_state["aud_root"] = root_aud
            st.session_state["aud_text"] = aud_text
            st.session_state["aud_persons"] = persons_aud
            st.session_state["aud_gens"] = aud_gens

        if st.session_state.get("aud_results") and any(
            r["severity"] != "ok" for r in st.session_state["aud_results"]
        ):
            probs = [r for r in st.session_state["aud_results"] if r["severity"] != "ok"]
            dn = st.number_input(
                f"Deep audit top N (of {len(probs)})",
                1, len(probs), min(5, len(probs)),
                key="aud_deep_n",
                disabled=is_replay,
            )
            # Pass 2 needs LLM calls. Disable in Replay mode so a click
            # doesn't bubble up an Anthropic-API exception. The
            # Replay-mode banner above already explains this textually;
            # the disabled button + tooltip is the visual reinforcement.
            deep_button_help = (
                "LLM Pass 2 requires an Anthropic API key. "
                "Switch to Live mode in the sidebar to run a deep audit."
                if is_replay else None
            )
            if st.button(
                f"Deep Audit Top {dn}",
                key="btn_aud_deep",
                disabled=is_replay,
                help=deep_button_help,
            ):
                from audit import pass2_audit, generate_report
                with st.spinner(f"Running LLM on {dn} relationships..."):
                    p2 = pass2_audit(probs, st.session_state["aud_text"], st.session_state["aud_persons"], max_deep=dn)
                render_audit_results(probs, pass2=p2)
                report = generate_report(
                    st.session_state["aud_root"], st.session_state["aud_gens"],
                    st.session_state["aud_subtree"], st.session_state["aud_results"], p2,
                )
                st.download_button("Download Audit Report", report, file_name="audit_report.md", mime="text/markdown")


# =====================================================================
# TAB 4: DNA ANALYSIS
# =====================================================================

with tab_dna:
    st.header("DNA Analysis")
    result = st.session_state.get("pipeline_result")
    if result:
        dna = result.get("dna_analysis")
        if dna and dna.get("total_matches", 0) > 0:
            render_dna_analysis(dna)
        else:
            st.info(
                "No DNA data was analyzed in the last pipeline run. "
                "To include DNA evidence, upload a GEDmatch or MyHeritage "
                "CSV file in the **DNA CSV** field on the **Pipeline** tab "
                "and re-run."
            )
    else:
        st.info("Run the pipeline from the **Pipeline** tab first. "
                "Include a DNA CSV upload to see analysis here.")
