#!/usr/bin/env python3
"""
oops_scan.py — Validate an ontology via the OOPS! (OntOlogy Pitfall Scanner) REST API.

Uses rdflib to load and merge all RDF files in a repository, serializes the
combined graph as RDF/XML, then POSTs it to https://oops.linkeddata.es/rest
for pitfall analysis. The XML response is parsed and rendered as a Markdown
or JSON report.

Usage:
    python oops_scan.py <repo-path> [-o report.md] [--format markdown|json]
                              [--pitfalls P04,P08,...] [--timeout 60]

Requires:
    pip install rdflib requests

References:
    - OOPS! API docs: https://oops.linkeddata.es/webservice.html
    - Pitfall catalogue: https://oops.linkeddata.es/catalogue.jsp
    - Paper: Poveda-Villalón et al., "OOPS! (OntOlogy Pitfall Scanner!)",
      IJSWIS 10(2), 2014, pp. 7-34.
"""
import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from rdflib import Graph

from rdf_utils import find_rdf_files

OOPS_REST_URL = "https://oops.linkeddata.es/rest"

# --------------------------------------------------------------------------- #
# 1. Load & serialize
# --------------------------------------------------------------------------- #

def load_ontology(repo_path: str) -> tuple[Graph, list[str]]:
    """Parse all RDF files in the repo into a single graph.  Return (graph, warnings)."""
    g = Graph()
    warnings = []
    rdf_files = find_rdf_files(repo_path)
    if not rdf_files:
        warnings.append(f"No RDF files found in {repo_path}")
        return g, warnings

    for fpath in rdf_files:
        try:
            g.parse(fpath)
        except Exception as e:
            warnings.append(f"Could not parse {fpath}: {e}")

    return g, warnings


def serialize_to_rdfxml(g: Graph) -> str:
    """Serialize the graph as RDF/XML (the format OOPS expects)."""
    return g.serialize(format="xml")


# --------------------------------------------------------------------------- #
# 2. Call OOPS! REST API
# --------------------------------------------------------------------------- #

def call_oops(rdf_content: str, pitfalls: str = "", timeout: int = 120) -> requests.Response:
    """
    Build the XML payload expected by OOPS! and POST it.

    Parameters
    ----------
    rdf_content : str
        The ontology in RDF/XML format.
    pitfalls : str
        Comma-separated pitfall codes to scan (e.g. "P04,P08").
        Empty string → all pitfalls.
    timeout : int
        Request timeout in seconds.

    Returns
    -------
    requests.Response
    """
    payload = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<OOPSRequest>'
        '<OntologyURI></OntologyURI>'
        f'<OntologyContent><![CDATA[{rdf_content}]]></OntologyContent>'
        f'<Pitfalls>{pitfalls}</Pitfalls>'
        '<OutputFormat>XML</OutputFormat>'
        '</OOPSRequest>'
    )
    response = requests.post(
        OOPS_REST_URL,
        data=payload.encode("utf-8"),
        headers={"Content-Type": "application/xml"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response


# --------------------------------------------------------------------------- #
# 3. Parse OOPS! XML response
# --------------------------------------------------------------------------- #

OOPS_NS = "http://www.oeg-upm.net/oops"


def _tag(local: str) -> str:
    return f"{{{OOPS_NS}}}{local}"


def parse_oops_response(xml_text: str) -> dict:
    """
    Parse the OOPS! XML response into a structured dict.

    Returns
    -------
    dict with keys:
        pitfalls : list[dict]  — detected pitfalls
        warnings : list[dict]   — detected warnings (OOPS "warning" type)
        suggestions : list[dict] — detected suggestions
    Each item has: code, name, description, importance, affected_elements
    """
    root = ET.fromstring(xml_text)
    result = {"pitfalls": [], "warnings": [], "suggestions": []}

    # --- Pitfalls ---
    for pf in root.findall(_tag("Pitfall")):
        entry = {
            "code": _text(pf, "Code"),
            "name": _text(pf, "Name"),
            "description": _text(pf, "Description"),
            "importance": _text(pf, "Importance"),
            "num_affected": _text(pf, "NumberAffectedElements"),
            "affected_elements": [],
            "no_inverse_suggestions": [],
            "might_be_equivalent_properties": [],
            "might_be_equivalent_attributes": [],
        }
        affects = pf.find(_tag("Affects"))
        if affects is not None:
            for ae in affects.findall(_tag("AffectedElement")):
                entry["affected_elements"].append(ae.text or "")
            # NoInverseSuggestion
            for nis in affects.findall(_tag("NoInverseSuggestion")):
                inv = [ae.text or "" for ae in nis.findall(_tag("AffectedElement"))]
                entry["no_inverse_suggestions"].append(inv)
            # MightBeEquivalentProperty
            for mbep in affects.findall(_tag("MightBeEquivalentProperty")):
                equiv = [ae.text or "" for ae in mbep.findall(_tag("AffectedElement"))]
                entry["might_be_equivalent_properties"].append(equiv)
            # MightBeEquivalentAttribute
            for mbea in affects.findall(_tag("MightBeEquivalentAttribute")):
                equiv = [ae.text or "" for ae in mbea.findall(_tag("AffectedElement"))]
                entry["might_be_equivalent_attributes"].append(equiv)
        result["pitfalls"].append(entry)

    # --- Warnings ---
    for wf in root.findall(_tag("Warning")):
        entry = {
            "name": _text(wf, "Name"),
            "affected_elements": [],
        }
        affects = wf.find(_tag("Affects"))
        if affects is not None:
            for ae in affects.findall(_tag("AffectedElement")):
                entry["affected_elements"].append(ae.text or "")
        result["warnings"].append(entry)

    # --- Suggestions ---
    for sf in root.findall(_tag("Suggestion")):
        entry = {
            "name": _text(sf, "Name"),
            "description": _text(sf, "Description"),
            "affected_elements": [],
        }
        affects = sf.find(_tag("Affects"))
        if affects is not None:
            for ae in affects.findall(_tag("AffectedElement")):
                entry["affected_elements"].append(ae.text or "")
        result["suggestions"].append(entry)

    return result


def _text(element: ET.Element, local: str) -> str:
    """Safely get text from a child element."""
    child = element.find(_tag(local))
    return (child.text or "").strip() if child is not None else ""


# --------------------------------------------------------------------------- #
# 4. Markdown report
# --------------------------------------------------------------------------- #

IMPORTANCE_ICON = {
    "Critical": "🔴",
    "Important": "🟠",
    "Minor": "🟡",
}


def format_report_markdown(report: dict) -> str:
    """Render the OOPS! report as Markdown."""
    lines = ["# OOPS! Ontology Pitfall Scan Report", ""]
    lines.append("_Generated by `ontology-oops-scan` skill (rdflib + OOPS! REST API)_")
    lines.append("")

    total = len(report["pitfalls"]) + len(report["warnings"]) + len(report["suggestions"])
    if total == 0:
        lines.append("**No pitfalls, warnings or suggestions detected.** ✅")
        return "\n".join(lines)

    # --- Summary table ---
    lines.append("## Summary")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|----------|-------|")
    by_severity = {}
    for pf in report["pitfalls"]:
        sev = pf.get("importance", "Unknown")
        by_severity[sev] = by_severity.get(sev, 0) + 1
    for sev in ["Critical", "Important", "Minor"]:
        count = by_severity.get(sev, 0)
        if count:
            icon = IMPORTANCE_ICON.get(sev, "")
            lines.append(f"| {icon} {sev} | {count} |")
    if report["warnings"]:
        lines.append(f"| ⚠️ Warnings | {len(report['warnings'])} |")
    if report["suggestions"]:
        lines.append(f"| 💡 Suggestions | {len(report['suggestions'])} |")
    lines.append("")

    # --- Pitfalls ---
    if report["pitfalls"]:
        lines.append("## Pitfalls")
        lines.append("")
        for pf in report["pitfalls"]:
            icon = IMPORTANCE_ICON.get(pf.get("importance", ""), "⚪")
            lines.append(f"### {icon} {pf['code']}: {pf['name']}")
            lines.append(f"- **Severity:** {pf['importance']}")
            lines.append(f"- **Affected elements:** {pf['num_affected']}")
            lines.append(f"- **Description:** {pf['description']}")
            lines.append("")

            if pf["affected_elements"]:
                lines.append("**Affected elements:**")
                lines.append("")
                for ae in pf["affected_elements"]:
                    lines.append(f"- `{ae}`")
                lines.append("")

            if pf["no_inverse_suggestions"]:
                lines.append("**Missing inverse relationships:**")
                lines.append("")
                for pair in pf["no_inverse_suggestions"]:
                    lines.append(f"- {' , '.join(f'`{u}`' for u in pair)}")
                lines.append("")

            if pf["might_be_equivalent_properties"]:
                lines.append("**Possibly equivalent object properties:**")
                lines.append("")
                for pair in pf["might_be_equivalent_properties"]:
                    lines.append(f"- {' ≡ '.join(f'`{u}`' for u in pair)}")
                lines.append("")

            if pf["might_be_equivalent_attributes"]:
                lines.append("**Possibly equivalent data properties:**")
                lines.append("")
                for pair in pf["might_be_equivalent_attributes"]:
                    lines.append(f"- {' ≡ '.join(f'`{u}`' for u in pair)}")
                lines.append("")

    # --- Warnings ---
    if report["warnings"]:
        lines.append("## Warnings")
        lines.append("")
        for wf in report["warnings"]:
            lines.append(f"### ⚠️ {wf['name']}")
            if wf["affected_elements"]:
                for ae in wf["affected_elements"]:
                    lines.append(f"- `{ae}`")
            lines.append("")

    # --- Suggestions ---
    if report["suggestions"]:
        lines.append("## Suggestions")
        lines.append("")
        for sf in report["suggestions"]:
            lines.append(f"### 💡 {sf['name']}")
            if sf["description"]:
                lines.append(f"{sf['description']}")
            if sf["affected_elements"]:
                for ae in sf["affected_elements"]:
                    lines.append(f"- `{ae}`")
            lines.append("")

    # --- Reference ---
    lines.append("---")
    lines.append("")
    lines.append("**Pitfall catalogue:** https://oops.linkeddata.es/catalogue.jsp")
    lines.append("")
    lines.append("**Citation:** Poveda-Villalón, M., Gómez-Pérez, A., & Suárez-Figueroa, M.C. (2014). "
                 "OOPS! (OntOlogy Pitfall Scanner!): An On-line Tool for Ontology Evaluation. "
                 "*International Journal on Semantic Web and Information Systems*, 10(2), 7-34.")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 5. Main
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(
        description="Validate an ontology with OOPS! (OntOlogy Pitfall Scanner)"
    )
    parser.add_argument("repo_path", help="Path to the ontology repository")
    parser.add_argument("-o", "--output", help="Output file (.md or .json)")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown",
                        help="Output format (default: markdown)")
    parser.add_argument("--pitfalls", default="",
                        help="Comma-separated pitfall codes to scan (e.g. P04,P08). Default: all")
    parser.add_argument("--timeout", type=int, default=120,
                        help="HTTP request timeout in seconds (default: 120)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Serialize the ontology but do not send to OOPS! (for testing)")
    args = parser.parse_args()

    # 1. Load ontology
    print(f"[INFO] Loading RDF files from {args.repo_path}...", file=sys.stderr)
    g, warnings = load_ontology(args.repo_path)
    for w in warnings:
        print(f"[WARN] {w}", file=sys.stderr)

    if len(g) == 0:
        print("[ERROR] Empty graph. Nothing to scan.", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Loaded {len(g)} triples.", file=sys.stderr)

    # 2. Serialize as RDF/XML
    print("[INFO] Serializing to RDF/XML...", file=sys.stderr)
    rdfxml = serialize_to_rdfxml(g)
    print(f"[INFO] Serialized {len(rdfxml)} bytes.", file=sys.stderr)

    if args.dry_run:
        print("[INFO] Dry run — not sending to OOPS!.", file=sys.stderr)
        Path("dry_run_ontology.owl").write_text(rdfxml, encoding="utf-8")
        print("[INFO] Saved to dry_run_ontology.owl", file=sys.stderr)
        return

    # 3. Call OOPS!
    print(f"[INFO] Sending to OOPS! at {OOPS_REST_URL}...", file=sys.stderr)
    try:
        response = call_oops(rdfxml, pitfalls=args.pitfalls, timeout=args.timeout)
    except requests.exceptions.Timeout:
        print("[ERROR] OOPS! request timed out. Try --timeout with a larger value.", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.ConnectionError as e:
        print(f"[ERROR] Cannot reach OOPS! server: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] OOPS! responded with status {response.status_code}.", file=sys.stderr)

    # 4. Parse response
    try:
        report = parse_oops_response(response.text)
    except ET.ParseError as e:
        print(f"[ERROR] Cannot parse OOPS! XML response: {e}", file=sys.stderr)
        print(response.text[:2000], file=sys.stderr)
        sys.exit(1)

    # 5. Output
    fmt = args.format
    if args.output:
        ext = Path(args.output).suffix.lower()
        if ext == ".json":
            fmt = "json"

    if fmt == "json":
        output_text = json.dumps(report, indent=2, ensure_ascii=False)
    else:
        output_text = format_report_markdown(report)

    if args.output:
        Path(args.output).write_text(output_text, encoding="utf-8")
        print(f"[INFO] Report written to {args.output}", file=sys.stderr)
    else:
        print(output_text)


if __name__ == "__main__":
    main()
