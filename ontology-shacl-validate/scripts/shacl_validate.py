#!/usr/bin/env python3
"""
shacl_validate.py — Validate RDF data against SHACL shapes.

Loads all RDF files in a repo, looks for SHACL shapes (or auto-generates minimal
ones), and validates the non-shape triples against them. Reports sh:Violation
results with focus node, path, message, and severity.

Usage:
    python shacl_validate.py <repo-path> [-o report.md] [--shapes shapes.ttl]
      If --shapes is omitted, auto-generates minimal shapes from the schema.

Requires:
    pip install rdflib pyshacl
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

from rdflib import Graph, RDF, RDFS, OWL, XSD, Namespace, BNode

from rdf_utils import load_graph, find_rdf_files, compact_uri

SH = Namespace("http://www.w3.org/ns/shacl#")


def generate_minimal_shapes(g: Graph) -> Graph:
    """
    Auto-generate minimal SHACL shapes from OWL axioms in the graph.
    Each owl:Class → NodeShape with property shapes derived from domains/ranges.
    """
    shapes = Graph()
    shapes.bind("sh", SH)

    for cls in g.subjects(RDF.type, OWL.Class):
        cls_short = compact_uri(cls, g) if hasattr(g, 'namespace_manager') else str(cls)

        # Skip blank nodes, OWL built-ins, and non-URI resources
        if not isinstance(cls, str):
            continue
        if cls.startswith("http://www.w3.org/"):
            continue
        name = cls_short.split(":")[-1] if ":" in cls_short else cls_short.replace("/", "_")

        shape_uri = cls + "Shape"
        shapes.add((shape_uri, RDF.type, SH.NodeShape))
        shapes.add((shape_uri, SH.targetClass, cls))

        # Add property shapes for each datatype/object property in the domain of this class
        for prop in g.subjects(RDFS.domain, cls):
            if not (prop, RDF.type, OWL.DatatypeProperty) in g and \
               not (prop, RDF.type, OWL.ObjectProperty) in g:
                continue
            ps_uri = cls + "_" + (compact_uri(prop, g).split(":")[-1] if hasattr(g, 'namespace_manager') else str(prop).split("/")[-1]) + "Shape"
            shapes.add((shape_uri, SH.property, ps_uri))
            shapes.add((ps_uri, SH.path, prop))
            shapes.add((ps_uri, SH.minCount, XSD.literal(0)))

            # Infer min/max cardinality from OWL restrictions if present
            for restricted in g.subjects(RDFS.subClassOf, cls):
                for restriction in g.objects(restricted, OWL.onProperty):
                    if restriction != prop:
                        continue
                    card = g.value(restricted, OWL.minCardinality) or \
                           g.value(restricted, OWL.qualifiedCardinality)
                    if card:
                        shapes.add((ps_uri, SH.minCount, XSD.literal(int(card))))
                    max_card = g.value(restricted, OWL.maxCardinality)
                    if max_card:
                        shapes.add((ps_uri, SH.maxCount, XSD.literal(int(max_card))))
                    card_exact = g.value(restricted, OWL.cardinality) or \
                                 g.value(restricted, OWL.qualifiedCardinality)
                    if card_exact:
                        shapes.add((ps_uri, SH.minCount, XSD.literal(int(card_exact))))
                        shapes.add((ps_uri, SH.maxCount, XSD.literal(int(card_exact))))

    return shapes


def run_validation(repo_path: str, shapes_path: str | None = None) -> dict:
    """Run SHACL validation and return structured results."""
    g, warnings = load_graph(repo_path)
    if len(g) == 0:
        return {"warnings": warnings, "conforms": True, "violations": [], "violations_count": 0, "shapes_count": 0}

    # 1. Try to extract SHACL shapes from the data graph itself
    shape_types = {str(SH.NodeShape), str(SH.PropertyShape)}
    shape_subjects = set(g.subjects(RDF.type, SH.NodeShape)) | set(g.subjects(RDF.type, SH.PropertyShape))

    if shapes_path:
        shapes_g = Graph()
        shapes_g.parse(shapes_path)
        print(f"[INFO] Loaded shapes from {shapes_path} ({len(shapes_g)} triples)", file=sys.stderr)
    elif shape_subjects:
        # Extract shape definitions including nested blank nodes
        shapes_g = Graph()
        done = set()
        queue = list(shape_subjects)
        while queue:
            s = queue.pop(0)
            if s in done:
                continue
            done.add(s)
            for p, o in g.predicate_objects(s):
                shapes_g.add((s, p, o))
                # Follow blank nodes (property shapes, nested shapes)
                if isinstance(o, BNode) and o not in done:
                    queue.append(o)
        print(f"[INFO] Extracted {len(shape_subjects)} SHACL shapes from data ({len(shapes_g)} triples)", file=sys.stderr)
    else:
        shapes_g = generate_minimal_shapes(g)
        print(f"[INFO] Auto-generated {len(shapes_g)} shape triples from OWL axioms", file=sys.stderr)

    if len(shapes_g) == 0:
        return {"warnings": warnings + ["No SHACL shapes found or generated"], "conforms": True, "violations": [], "violations_count": 0, "shapes_count": 0}

    print(f"[INFO] Shapes graph: {len(shapes_g)} triples, Full graph: {len(g)} triples", file=sys.stderr)

    try:
        import pyshacl
        # Pass full graph — pySHACL separates shapes from data automatically
        conforms, results_graph, results_text = pyshacl.validate(
            g, shacl_graph=shapes_g,
            inference='none', abort_on_first=False,
            allow_warnings=True,
        )
    except Exception as e:
        return {"warnings": warnings + [f"SHACL validation error: {e}"], "conforms": False, "violations": [], "violations_count": 0, "shapes_count": len(shapes_g)}

    violations = []
    for v in results_graph.subjects(RDF.type, SH.ValidationResult):
        entry = {
            "focus_node": str(results_graph.value(v, SH.focusNode) or ""),
            "focus_node_short": compact_uri(results_graph.value(v, SH.focusNode) or "", g) if results_graph.value(v, SH.focusNode) else "",
            "path": str(results_graph.value(v, SH.resultPath) or ""),
            "path_short": compact_uri(results_graph.value(v, SH.resultPath) or "", g) if results_graph.value(v, SH.resultPath) else "",
            "message": str(results_graph.value(v, SH.resultMessage) or ""),
            "severity": str(results_graph.value(v, SH.resultSeverity) or ""),
            "value": str(results_graph.value(v, SH.value) or ""),
        }
        violations.append(entry)

    return {
        "warnings": warnings,
        "conforms": conforms,
        "violations_count": len(violations),
        "shapes_count": len(shape_subjects),
        "violations": violations,
    }


def format_report_markdown(results: dict) -> str:
    lines = ["# SHACL Validation Report", "",
             "_Generated by `ontology-shacl-validate` skill (rdflib + pySHACL)_", ""]

    if results.get("warnings"):
        for w in results["warnings"]:
            lines.append(f"- ⚠️ {w}")
        lines.append("")

    lines.append("## Summary")
    lines.append(f"- **Shapes loaded:** {results['shapes_count']}")
    lines.append(f"- **Violations:** {results['violations_count']}")
    lines.append(f"- **Conforms:** {'✅ Yes' if results['conforms'] else '❌ No'}")
    lines.append("")

    if not results["violations"]:
        lines.append("**Data conforms to all SHACL shapes.** ✅")
        return "\n".join(lines)

    lines.append("## Violations")
    lines.append("")

    by_node = defaultdict(list)
    for v in results["violations"]:
        by_node[v["focus_node_short"] or v["focus_node"]].append(v)

    for node, viols in sorted(by_node.items()):
        lines.append(f"### `{node}` ({len(viols)})")
        lines.append("")
        for v in viols:
            sev = v["severity"].split("#")[-1] if "#" in v["severity"] else v["severity"]
            lines.append(f"- **{sev}** on `{v['path_short'] or v['path']}`: {v['message']}")
            if v.get("value"):
                lines.append(f"  - Value: `{v['value']}`")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Validate RDF data against SHACL shapes")
    parser.add_argument("repo_path", help="Path to the ontology repository")
    parser.add_argument("-o", "--output", help="Output file (.json or .md)")
    parser.add_argument("--shapes", help="Path to external SHACL shapes file (.ttl)")
    parser.add_argument("--format", choices=["json", "markdown", "report"], default="markdown")
    args = parser.parse_args()

    results = run_validation(args.repo_path, shapes_path=args.shapes)

    fmt = args.format
    if args.output:
        ext = Path(args.output).suffix.lower()
        if ext == ".json":
            fmt = "json"

    if fmt == "json":
        output = json.dumps(results, indent=2, ensure_ascii=False)
    elif fmt == "report":
        from report_format import AuditReport
        ar = AuditReport(skill="shacl-validate")
        for v in results.get("violations", []):
            ar.add(file="—", element=v.get("focus_node_short", v.get("focus_node", "")),
                   message=v.get("message", "")[:200], severity="error",
                   check=f"SHACL:{v.get('path_short', v.get('path', ''))}",
                   suggestion="", predicate=v.get("path_short", ""))
        output = ar.to_json()
    else:
        output = format_report_markdown(results)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"[INFO] Report written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
