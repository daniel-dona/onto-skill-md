#!/usr/bin/env python3
"""
skos_audit.py — SKOS structural audit using rdflib.

Checks:
  1. skos:inScheme references to undefined ConceptSchemes
  2. Concepts without skos:inScheme
  3. ConceptSchemes with no concepts
  4. skos:prefLabel / skos:notation mismatches (when both present)
  5. Missing prefLabel in any language
  6. Duplicate prefLabels within a ConceptScheme
  7. skos:Concept with skos:broader but no skos:inScheme (orphan hierarchy)
  8. Broken skos:broader/narrower links (target concept not found)

Usage:
    python skos_audit.py <repo-path> [-o report.json] [--format json|markdown]

Requires:
    pip install rdflib
"""
import argparse
import json
import os
import sys
import unicodedata
from pathlib import Path

from rdflib import Graph, RDF, RDFS, OWL, Literal, URIRef, Namespace
from rdflib.namespace import SKOS, NamespaceManager
from rdflib.collection import Collection

from rdf_utils import find_rdf_files, compact_uri


def parse_repo(repo_path: str) -> Graph:
    """Parse all RDF files in the repo into a single graph."""
    g = Graph()
    rdf_files = find_rdf_files(repo_path)
    if not rdf_files:
        print(f"[WARN] No RDF files found in {repo_path}", file=sys.stderr)
        return g

    for fpath in rdf_files:
        try:
            g.parse(fpath)
        except Exception as e:
            print(f"[WARN] Could not parse {fpath}: {e}", file=sys.stderr)
    return g


def skos_audit(repo_path: str) -> list[dict]:
    """Run all SKOS structural checks and return a list of issues."""
    g = parse_repo(repo_path)
    issues = []

    if len(g) == 0:
        return issues

    # --- Collect concepts and schemes ---
    concepts = set(g.subjects(RDF.type, SKOS.Concept))
    schemes = set(g.subjects(RDF.type, SKOS.ConceptScheme))
    collections = set(g.subjects(RDF.type, SKOS.Collection))

    # Map: scheme -> set of concepts
    scheme_to_concepts = {s: set() for s in schemes}
    # Map: concept -> set of schemes
    concept_to_schemes = {}

    for concept in concepts:
        in_schemes = set(g.objects(concept, SKOS.inScheme))
        concept_to_schemes[concept] = in_schemes
        for s in in_schemes:
            if s in scheme_to_concepts:
                scheme_to_concepts[s].add(concept)
            else:
                scheme_to_concepts.setdefault(s, set()).add(concept)

    # ---- Check 1: inScheme references to undefined ConceptSchemes ----
    for concept, scheme_set in concept_to_schemes.items():
        for s in scheme_set:
            if s not in schemes:
                issues.append({
                    "severity": "error",
                    "check": "inScheme-undefined",
                    "message": f"Concept {compact_uri(concept, g)} references undefined ConceptScheme {compact_uri(s, g)}",
                    "subject": str(concept),
                    "subject_short": compact_uri(concept, g),
                    "scheme": str(s),
                    "scheme_short": compact_uri(s, g),
                })

    # ---- Check 2: Concepts without skos:inScheme ----
    for concept in concepts:
        if not concept_to_schemes.get(concept):
            issues.append({
                "severity": "warning",
                "check": "no-inScheme",
                "message": f"Concept {compact_uri(concept, g)} has no skos:inScheme",
                "subject": str(concept),
                "subject_short": compact_uri(concept, g),
            })

    # ---- Check 3: ConceptSchemes with no concepts ----
    for scheme in schemes:
        if not scheme_to_concepts.get(scheme):
            issues.append({
                "severity": "warning",
                "check": "empty-scheme",
                "message": f"ConceptScheme {compact_uri(scheme, g)} has no concepts",
                "scheme": str(scheme),
                "scheme_short": compact_uri(scheme, g),
            })

    # ---- Check 4: prefLabel / notation mismatch ----
    for concept in concepts:
        labels_by_lang = {}
        for label in g.objects(concept, SKOS.prefLabel):
            if isinstance(label, Literal) and label.language:
                labels_by_lang.setdefault(str(label.language), []).append(str(label))

        notations = list(g.objects(concept, SKOS.notation))

        for notation in notations:
            not_val = str(notation).lower().strip()
            # Compare against the URI fragment
            uri_str = str(concept)
            if "#" in uri_str:
                fragment = uri_str.split("#")[-1].lower()
            elif "/" in uri_str:
                fragment = uri_str.rsplit("/", 1)[-1].lower()
            else:
                fragment = uri_str.lower()

            # Normalize: remove accents for comparison
            def normalize(s):
                return unicodedata.normalize("NFKD", s).encode("ASCII", "ignore").decode("ASCII").lower().replace(" ", "-")

            # If notation doesn't match URI fragment
            if normalize(not_val) != normalize(fragment):
                # But check if it matches any prefLabel
                matches_label = False
                for lang, labels in labels_by_lang.items():
                    for label in labels:
                        if normalize(label) == normalize(not_val):
                            matches_label = True
                if not matches_label:
                    issues.append({
                        "severity": "info",
                        "check": "notation-mismatch",
                        "message": f"Notation '{notation}' doesn't match URI fragment '{fragment}'",
                        "subject": str(concept),
                        "subject_short": compact_uri(concept, g),
                        "notation": str(notation),
                        "uri_fragment": fragment,
                    })

    # ---- Check 5: Missing prefLabel (concepts with no prefLabel at all) ----
    for concept in concepts:
        pref_labels = list(g.objects(concept, SKOS.prefLabel))
        if not pref_labels:
            # Has altLabel or hiddenLabel but no prefLabel?
            alt_labels = list(g.objects(concept, SKOS.altLabel))
            issues.append({
                "severity": "error",
                "check": "missing-prefLabel",
                "message": f"Concept {compact_uri(concept, g)} has no skos:prefLabel" +
                           (f" (has {len(alt_labels)} altLabel(s))" if alt_labels else ""),
                "subject": str(concept),
                "subject_short": compact_uri(concept, g),
            })

    # ---- Check 6: Duplicate prefLabels within a scheme ----
    for scheme in schemes:
        label_map = {}  # (lang, value) -> [concepts]
        for concept in scheme_to_concepts.get(scheme, []):
            for label in g.objects(concept, SKOS.prefLabel):
                if isinstance(label, Literal) and label.language:
                    key = (str(label.language), str(label.value).lower())
                    label_map.setdefault(key, []).append(concept)

        for (lang, val), concept_list in label_map.items():
            if len(concept_list) > 1:
                concept_strs = [compact_uri(c, g) for c in concept_list]
                issues.append({
                    "severity": "error",
                    "check": "duplicate-prefLabel",
                    "message": f"Duplicate prefLabel '{val}' @{lang} in scheme {compact_uri(scheme, g)}",
                    "scheme": str(scheme),
                    "scheme_short": compact_uri(scheme, g),
                    "lang": lang,
                    "value": val,
                    "concepts": concept_strs,
                })

    # ---- Check 7: Concept with broader but no inScheme ----
    for concept in concepts:
        broader = list(g.objects(concept, SKOS.broader))
        if broader and not concept_to_schemes.get(concept):
            issues.append({
                "severity": "warning",
                "check": "broader-no-inScheme",
                "message": f"Concept {compact_uri(concept, g)} has skos:broader but no skos:inScheme",
                "subject": str(concept),
                "subject_short": compact_uri(concept, g),
            })

    # ---- Check 8: Broken skos:broader/narrower links ----
    for concept in concepts:
        for broader in g.objects(concept, SKOS.broader):
            if broader not in concepts:
                issues.append({
                    "severity": "error",
                    "check": "broken-broader",
                    "message": f"Concept {compact_uri(concept, g)} has skos:broader {compact_uri(broader, g)} which is not defined as skos:Concept",
                    "subject": str(concept),
                    "subject_short": compact_uri(concept, g),
                    "target": str(broader),
                    "target_short": compact_uri(broader, g),
                })

    for concept in concepts:
        for narrower in g.objects(concept, SKOS.narrower):
            if narrower not in concepts:
                issues.append({
                    "severity": "error",
                    "check": "broken-narrower",
                    "message": f"Concept {compact_uri(concept, g)} has skos:narrower {compact_uri(narrower, g)} which is not defined as skos:Concept",
                    "subject": str(concept),
                    "subject_short": compact_uri(concept, g),
                    "target": str(narrower),
                    "target_short": compact_uri(narrower, g),
                })

    return issues


def format_report_markdown(issues: list[dict]) -> str:
    """Format issues as Markdown."""
    lines = ["# SKOS Structural Audit Report", ""]
    lines.append("Generated by `ontology-skos-audit` skill (rdflib)")
    lines.append("")

    if not issues:
        lines.append("**No SKOS structural issues found.** ✅")
        return "\n".join(lines)

    lines.append(f"**{len(issues)} issues found.**")
    lines.append("")

    # Group by check type
    by_check = {}
    for issue in issues:
        by_check.setdefault(issue["check"], []).append(issue)

    icons = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}
    for check, check_issues in sorted(by_check.items()):
        severity = check_issues[0].get("severity", "info")
        icon = icons.get(severity, "")
        lines.append(f"## {icon} {check} ({len(check_issues)})")
        lines.append("")

        for issue in check_issues:
            lines.append(f"- {issue['message']}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="SKOS structural audit using rdflib")
    parser.add_argument("repo_path", help="Path to the ontology repository")
    parser.add_argument("-o", "--output", help="Output file (.json or .md)")
    parser.add_argument("--format", choices=["json", "markdown", "report"], default="markdown",
                        help="Output format (default: markdown)")
    args = parser.parse_args()

    issues = skos_audit(args.repo_path)

    fmt = args.format
    if args.output:
        ext = Path(args.output).suffix.lower()
        if ext == ".json":
            fmt = "json"

    if fmt == "json":
        output_text = json.dumps(issues, indent=2, ensure_ascii=False)
    elif fmt == "report":
        from report_format import AuditReport
        ar = AuditReport(skill="skos-audit")
        for iss in issues:
            ar.add(file="—", element=iss.get("subject_short", iss.get("scheme_short", "")),
                   message=iss["message"], severity=iss.get("severity", "info"),
                   check=iss.get("check", ""),
                   suggestion=iss.get("target_short", ""))
        output_text = ar.to_json()
    else:
        output_text = format_report_markdown(issues)

    if args.output:
        Path(args.output).write_text(output_text, encoding="utf-8")
        print(f"[INFO] Report written to {args.output}", file=sys.stderr)
    else:
        print(output_text)


if __name__ == "__main__":
    main()
