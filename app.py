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
UPLOAD_SENTINEL = "-- upload instead --"
DNA_NONE_SENTINEL = "-- no DNA file --"


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

    parent_specs = []
    if family.get("father"):
        parent_specs.append(("father", family["father"]))
    if family.get("mother"):
        parent_specs.append(("mother", family["mother"]))

    with dot.subgraph() as s:
        s.attr(rank="same")
        for idx, (role, ref) in enumerate(parent_specs):
            ref = ref or {}
            nid = f"parent_{idx}"
            rid = ref.get("record_id") or ""
            hyp, crit, esc = lookup_critique(rid)
            b, d = lookup_dates(rid)
            s.node(nid, _node_label(ref.get("name") or "?", b, d, f"{role.upper()} {_verdict_footer(crit, esc)}"), **_color_for(hyp, crit, esc))
            dot.edge(nid, "subject", label=role)

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

tab_pipeline, tab_tree, tab_audit, tab_dna = st.tabs(
    ["Pipeline", "Family Tree", "Audit", "DNA Analysis"]
)


# =====================================================================
# TAB 1: PIPELINE
# =====================================================================

with tab_pipeline:
    available_gedcoms = discover_gedcom_files()
    available_dna = discover_dna_files()

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
            )
            dna_upload = st.file_uploader(
                "...or upload (.csv)", type=["csv"], key="pipeline_dna_upload",
                help="GEDmatch or MyHeritage match list. Upload takes precedence.",
            )

        query = st.text_input(
            "Research query",
            value="Who were the parents of John F. Kennedy?",
        )
        st.markdown("**Target person**")
        c1, c2, c3 = st.columns([2, 1, 2])
        with c1:
            tp_name = st.text_input("Name", value="John F. Kennedy")
        with c2:
            tp_birth = st.text_input("Approx. birth year", value="1917")
        with c3:
            tp_loc = st.text_input("Location", value="Brookline, MA")

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

        # Query routing.
        audit_mode = is_audit_query(query)
        if audit_mode:
            gens = extract_generations_from_query(query)
            st.info(f"Routing: **audit mode** ({gens} generations). Running subtree audit.")

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
            # Standard pipeline.
            st.caption("Routing: standard pipeline")

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

    elif "pipeline_result" in st.session_state:
        st.info("A previous run is cached. Submit again to re-run, or see the other tabs.")

    # Deep audit button (appears after audit routing flags problems).
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


# =====================================================================
# TAB 2: FAMILY TREE
# =====================================================================

with tab_tree:
    if "pipeline_result" in st.session_state:
        st.subheader("Immediate family tree")
        st.caption(
            "Blue = subject | Green = accepted (conf >= 0.75) | "
            "Amber = flag_uncertain / low-conf | Red = rejected / escalated | Gray = no verdict"
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
            dn = st.number_input(f"Deep audit top N (of {len(probs)})", 1, len(probs), min(5, len(probs)), key="aud_deep_n")
            if st.button(f"Deep Audit Top {dn}", key="btn_aud_deep"):
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
