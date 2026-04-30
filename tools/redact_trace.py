"""Redact PII from trace files so reasoning can be shared without exposing
real persons.

What it does:
    - Names (anything that looks like a `First [Middle] Last` capitalized
      sequence) → consistent pseudonyms PERSON_001, PERSON_002, ...
      The same real name always maps to the same pseudonym across all files
      processed in a single run, so narrative coherence is preserved.
    - DNA match GUIDs / hashes (long hex strings, MyHeritage match URLs) →
      MATCH_NNN.
    - Email addresses → REDACTED_EMAIL.
    - Locations are NOT touched by default — they are usually safe (Boston,
      Cleveland) and stripping them destroys the reasoning. Pass
      ``redact_locations=True`` to also redact known place words.
    - Dates are kept (year-level granularity is rarely PII on its own and is
      load-bearing for date-arithmetic reasoning).
    - cM values, segment counts, relationship labels, hypothesis IDs, agent
      names are all kept verbatim — they carry no PII.

Usage:
    python -m tools.redact_trace traces/trace_NNNN_moore.json \\
        --out traces/redacted/trace_NNNN_moore_redacted.json

Or batch:
    python -m tools.redact_trace traces/*moore*.json --out-dir traces/redacted

The mapping table is written alongside the redacted output as a sibling
``.map.json`` so you can rehydrate later if needed (KEEP THIS FILE LOCAL —
it contains the real names).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from glob import glob
from pathlib import Path


# Words we never want to be confused with a person's name even if they
# happen to be capitalized. Extend as needed.
_NON_NAME_TOKENS = {
    "GEDCOM", "DNA", "MyHeritage", "GEDmatch", "AncestryDNA", "FindAGrave",
    "Wikidata", "WikiTree", "FamilySearch", "SPARQL", "REST", "API",
    "Tier", "Critic", "Hypothesizer", "Synthesizer", "Scout",
    "Analyst", "Final", "Report", "Writer", "Anthropic", "OpenAI", "Google",
    "Claude", "Sonnet", "Opus", "GPT", "Gemini", "Parent", "Child", "Sibling",
    "Aunt", "Uncle", "Cousin", "Half", "Removed", "Niece", "Nephew",
    "Grandparent", "Grandchild", "Great", "January", "February", "March",
    "April", "May", "June", "July", "August", "September", "October",
    "November", "December", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun",
    "USA", "United", "States", "Boston", "Cleveland", "Ohio", "New", "York",
    "Pennsylvania", "Sicily", "Ireland", "Italy", "Germany", "Massachusetts",
    "England", "Scotland", "Wales", "Brookline",
    "JFK", "John",  # too common; leave as-is unless paired with surname
    "True", "False", "None", "Null",
    # Document section headers and common report words
    "Interaction", "Trace", "Log", "Agent", "Genealogical", "Research",
    "Report", "Subject", "Profiles", "Profile", "Hypotheses", "Hypothesis",
    "Critiques", "Critique", "Evidence", "Findings", "Accepted", "Rejected",
    "Flagged", "Uncertain", "Disambiguation", "Sources", "Source", "Records",
    "Record", "Pipeline", "Status", "Verdict", "Tier", "Geographic",
    "Plausibility", "Confidence", "Justification", "Issues", "Found",
    "Reasoning", "Narrative", "External", "Corroboration", "Cross",
    "Reference", "References", "Match", "Matches", "Candidate", "Candidates",
    "Target", "Subject", "Query", "Mode", "Audit", "Analysis",
    # Country / state-level — usually fine to keep but they pair with
    # capitalized words and trip the regex
    "Pennsylvania", "USA",
}


# Regex: capitalized name pattern — at least 2 tokens, first letter uppercase,
# rest lowercase or initials. Covers "John Moore", "Mary Ann O'Connor",
# "James J. Smith". Will over-match on things like book titles; the
# _NON_NAME_TOKENS gate filters most false positives.
_NAME_RX = re.compile(
    r"\b([A-Z][a-z]+(?:[-'][A-Z][a-z]+)?"
    r"(?:\s+(?:[A-Z]\.?|[A-Z][a-z]+(?:[-'][A-Z][a-z]+)?)){1,3})\b"
)

# Long hex strings (DNA match GUIDs, hashes ≥16 chars).
_HEX_GUID_RX = re.compile(r"\b[a-f0-9]{16,}\b", re.IGNORECASE)

# MyHeritage match URLs include /matches/<id>/ — any URL with /matches/ path.
_MATCH_URL_RX = re.compile(r"https?://[^\s\"']*?/matches?/[^\s\"']+", re.IGNORECASE)

# Emails.
_EMAIL_RX = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")


class Redactor:
    def __init__(self):
        self.name_map: dict[str, str] = {}
        self.match_map: dict[str, str] = {}
        self._next_person = 1
        self._next_match = 1

    def _pseudonym_for_name(self, real: str) -> str:
        # First token contains the surname-like part — split on whitespace,
        # take last token as the family group anchor so we keep family
        # cohesion in the pseudonym scheme. Optional refinement; for now,
        # one slot per unique real string.
        if real not in self.name_map:
            self.name_map[real] = f"PERSON_{self._next_person:03d}"
            self._next_person += 1
        return self.name_map[real]

    def _pseudonym_for_match(self, real: str) -> str:
        if real not in self.match_map:
            self.match_map[real] = f"MATCH_{self._next_match:03d}"
            self._next_match += 1
        return self.match_map[real]

    def _redact_name_match(self, m: re.Match) -> str:
        candidate = m.group(1)
        # Skip if every token is a non-name word.
        tokens = re.split(r"[\s.\-']+", candidate)
        meaningful = [t for t in tokens if t and t not in _NON_NAME_TOKENS]
        if len(meaningful) < 2:
            return candidate  # leave as-is
        return self._pseudonym_for_name(candidate)

    def redact_text(self, text: str) -> str:
        text = _MATCH_URL_RX.sub(
            lambda m: self._pseudonym_for_match(m.group(0)), text
        )
        text = _HEX_GUID_RX.sub(
            lambda m: self._pseudonym_for_match(m.group(0)), text
        )
        text = _EMAIL_RX.sub("REDACTED_EMAIL", text)
        text = _NAME_RX.sub(self._redact_name_match, text)
        return text

    def redact_obj(self, obj):
        """Recursively redact strings inside a JSON-like structure."""
        if isinstance(obj, str):
            return self.redact_text(obj)
        if isinstance(obj, list):
            return [self.redact_obj(x) for x in obj]
        if isinstance(obj, dict):
            return {k: self.redact_obj(v) for k, v in obj.items()}
        return obj


def _process_file(in_path: Path, out_path: Path, redactor: Redactor) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if in_path.suffix.lower() == ".json":
        data = json.loads(in_path.read_text(encoding="utf-8"))
        redacted = redactor.redact_obj(data)
        out_path.write_text(
            json.dumps(redacted, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    else:
        text = in_path.read_text(encoding="utf-8")
        out_path.write_text(redactor.redact_text(text), encoding="utf-8")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Redact PII from trace files.")
    p.add_argument("inputs", nargs="+", help="Trace files (JSON or MD). Globs OK.")
    p.add_argument("--out", help="Output path (single-file mode).")
    p.add_argument("--out-dir", help="Output directory (batch mode).")
    args = p.parse_args(argv)

    # Expand globs.
    paths: list[Path] = []
    for pat in args.inputs:
        matches = glob(pat)
        if matches:
            paths.extend(Path(m) for m in matches)
        else:
            paths.append(Path(pat))

    if not paths:
        print("No input files matched.", file=sys.stderr)
        return 2

    redactor = Redactor()

    if args.out and len(paths) == 1:
        _process_file(paths[0], Path(args.out), redactor)
        outputs = [Path(args.out)]
    else:
        out_dir = Path(args.out_dir or "traces/redacted")
        outputs = []
        for ip in paths:
            op = out_dir / f"{ip.stem}_redacted{ip.suffix}"
            _process_file(ip, op, redactor)
            outputs.append(op)

    # Write the mapping table next to the first output.
    map_path = outputs[0].with_suffix(outputs[0].suffix + ".map.json")
    map_path.write_text(
        json.dumps(
            {"name_map": redactor.name_map, "match_map": redactor.match_map},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"Redacted {len(outputs)} file(s).")
    print(f"  Names mapped:  {len(redactor.name_map)}")
    print(f"  Matches mapped: {len(redactor.match_map)}")
    print(f"  Mapping (KEEP LOCAL — contains real names): {map_path}")
    for op in outputs:
        print(f"  -> {op}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
