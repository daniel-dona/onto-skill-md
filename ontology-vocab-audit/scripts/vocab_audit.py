#!/usr/bin/env python3
"""
vocab_audit.py — Audit external vocabulary usage and URI resolution.

Parses all RDF files, extracts external namespaces (via owl:imports, namespace
prefixes, and referenced URIs), checks HTTP resolution, and detects local terms
that duplicate well-known standard vocabularies (FOAF, DC, SKOS, OWL, RDFS, etc.).

Usage:
    python vocab_audit.py <repo-path> [-o report.md] [--timeout 10]

Requires:
    pip install rdflib requests
"""
import argparse
import json
import os
import re
import sys
import concurrent.futures
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse, urljoin

import requests
from rdflib import Graph, RDF, RDFS, OWL, SKOS, Namespace
from rdflib.namespace import split_uri

from rdf_utils import load_graph, find_rdf_files, compact_uri

# Well-known vocabularies for detecting local reinvention
# Maps standard predicate to its local name and vocabulary
KNOWN_VOCABS = {
    str(RDFS.label): ("rdfs:label", "RDFS"),
    str(RDFS.comment): ("rdfs:comment", "RDFS"),
    str(RDFS.seeAlso): ("rdfs:seeAlso", "RDFS"),
    str(RDFS.isDefinedBy): ("rdfs:isDefinedBy", "RDFS"),
    str(RDF.type): ("rdf:type", "RDF"),
    str(OWL.sameAs): ("owl:sameAs", "OWL"),
    str(SKOS.prefLabel): ("skos:prefLabel", "SKOS"),
    str(SKOS.altLabel): ("skos:altLabel", "SKOS"),
    str(SKOS.definition): ("skos:definition", "SKOS"),
    str(SKOS.broader): ("skos:broader", "SKOS"),
    str(SKOS.narrower): ("skos:narrower", "SKOS"),
    str(SKOS.related): ("skos:related", "SKOS"),
    str(SKOS.inScheme): ("skos:inScheme", "SKOS"),
}

# Common vocabulary base URIs for grouping
KNOWN_VOCAB_BASES = {
    "http://purl.org/dc/": "Dublin Core",
    "http://xmlns.com/foaf/": "FOAF",
    "http://schema.org/": "Schema.org",
    "http://www.w3.org/ns/prov": "PROV-O",
    "http://purl.org/goodrelations/": "GoodRelations",
    "http://www.w3.org/2004/02/skos/": "SKOS",
    "http://www.w3.org/2002/07/owl": "OWL",
    "http://www.w3.org/2000/01/rdf-schema": "RDFS",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns": "RDF",
    "http://www.w3.org/2001/XMLSchema": "XSD",
    "http://qudt.org/": "QUDT",
    "http://www.ontologydesignpatterns.org/": "ODP",
    "http://purl.obolibrary.org/obo/": "OBO",
    "http://purl.org/iot/": "IoT-O",
    "https://saref.etsi.org/": "SAREF",
    "http://www.w3.org/ns/sosa/": "SOSA/SSN",
}


def extract_external_namespaces(repo_path: str) -> dict:
    """Extract all external namespace URIs and their usage."""
    g, warnings = load_graph(repo_path)
    if len(g) == 0:
        return {"warnings": warnings, "namespaces": {}, "imports": []}

    ns_map = {}  # prefix -> uri
    ns_usage = defaultdict(int)  # uri -> count
    imports = []

    # Collect from namespace manager
    for prefix, uri in g.namespace_manager.namespaces():
        if str(uri).startswith("http://") or str(uri).startswith("https://"):
            ns_map[prefix] = str(uri)

    # Count actual usage per prefix
    for s, p, o in g.triples((None, None, None)):
        for elem in (s, p, o):
            uri_str = str(elem)
            for prefix, ns_uri in ns_map.items():
                if uri_str.startswith(ns_uri):
                    ns_usage[ns_uri] += 1
                    break

    # owl:imports
    for o in g.objects(None, OWL.imports):
        imports.append({
            "uri": str(o),
            "resolves": None,  # checked later
        })

    # Build sorted namespace list
    namespaces = {}
    for ns_uri in sorted(set(list(ns_map.values()) + list(ns_usage.keys()))):
        if ns_uri.startswith("http://") or ns_uri.startswith("https://"):
            known = KNOWN_VOCAB_BASES.get(ns_uri) or KNOWN_VOCAB_BASES.get(ns_uri.rstrip("/#"))
            namespaces[ns_uri] = {
                "known_name": known,
                "usage_count": ns_usage.get(ns_uri, 0),
            }

    return {"warnings": warnings, "namespaces": namespaces, "imports": imports}


def check_uri_resolution(uri: str, timeout: int = 10) -> dict:
    """Try to HEAD a URI and return status info."""
    try:
        resp = requests.head(uri, timeout=timeout, allow_redirects=True,
                            headers={"Accept": "text/turtle,application/rdf+xml,text/html"})
        return {"uri": uri, "status": resp.status_code, "final_url": resp.url}
    except requests.exceptions.Timeout:
        return {"uri": uri, "status": "timeout", "final_url": ""}
    except requests.exceptions.ConnectionError:
        return {"uri": uri, "status": "connection_error", "final_url": ""}
    except Exception as e:
        return {"uri": uri, "status": f"error: {e}", "final_url": ""}


def check_all_uris(uris: list[str], timeout: int = 10, max_workers: int = 5) -> list[dict]:
    """Check resolution of all URIs in parallel."""
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(check_uri_resolution, u, timeout): u for u in uris}
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
    return sorted(results, key=lambda r: r["uri"])


def detect_reinvention(repo_path: str) -> list[dict]:
    """
    Detect local terms that semantically duplicate standard vocabulary terms.
    Flag predicates with local names matching standard ones but different namespace.
    """
    g, _ = load_graph(repo_path)
    if len(g) == 0:
        return []

    reinventions = []

    # Get the main ontology namespace(s)
    local_ns = set()
    for s in g.subjects(RDF.type, OWL.Ontology):
        local_ns.add(str(s))
    # Also infer from classes
    for cls in g.subjects(RDF.type, OWL.Class):
        uri = str(cls)
        if "#" in uri:
            local_ns.add(uri.split("#")[0] + "#")
        else:
            local_ns.add(uri.rsplit("/", 1)[0] + "/")

    # Check each predicate against known vocab
    for p in set(g.predicates()):
        p_str = str(p)
        # Skip known vocab predicates themselves
        if any(p_str.startswith(base) for base in KNOWN_VOCAB_BASES.keys()):
            continue
        # Check if this is a local predicate that duplicates a standard one
        local_name = p_str.split("#")[-1] if "#" in p_str else p_str.rsplit("/", 1)[-1]

        for known_uri, (known_compact, vocab_name) in KNOWN_VOCABS.items():
            known_local = known_uri.split("#")[-1] if "#" in known_uri else known_uri.rsplit("/", 1)[-1]
            if local_name.lower() == known_local.lower() and p_str != known_uri:
                reinventions.append({
                    "local_uri": p_str,
                    "local_short": compact_uri(p, g),
                    "duplicates": known_compact,
                    "vocabulary": vocab_name,
                    "standard_uri": known_uri,
                })
                break

    return reinventions


def format_report_markdown(report: dict) -> str:
    lines = ["# Ontology Vocabulary Audit Report", "",
             "_Generated by `ontology-vocab-audit` skill (rdflib + requests)_", ""]

    # Namespaces
    namespaces = report.get("namespaces", {})
    imports = report.get("imports", [])
    uri_checks = report.get("uri_checks", [])
    reinventions = report.get("reinventions", [])

    lines.append("## External Namespaces")
    lines.append("")

    if namespaces:
        lines.append("| Namespace | Known Vocabulary | Usage Count |")
        lines.append("|-----------|-----------------|-------------|")
        for ns, info in sorted(namespaces.items()):
            known = info["known_name"] or "—"
            count = info["usage_count"]
            lines.append(f"| `{ns}` | {known} | {count} |")
        lines.append("")
    else:
        lines.append("No external namespaces detected.")
        lines.append("")

    # Imports
    if imports:
        lines.append("## owl:imports")
        lines.append("")
        for imp in imports:
            status = f"→ {imp['status']}" if imp.get("status") else ""
            lines.append(f"- `{imp['uri']}` {status}")
        lines.append("")

    # URI resolution
    broken = [r for r in uri_checks if r["status"] != 200]
    if uri_checks:
        resolved = len(uri_checks) - len(broken)
        lines.append(f"## URI Resolution ({resolved}/{len(uri_checks)} OK)")
        lines.append("")
        if broken:
            lines.append("| URI | Status | Final URL |")
            lines.append("|-----|--------|-----------|")
            for r in broken:
                lines.append(f"| `{r['uri']}` | {r['status']} | `{r['final_url']}` |")
            lines.append("")
        else:
            lines.append("All URIs resolve successfully. ✅")
            lines.append("")

    # Reinvention
    if reinventions:
        lines.append("## Possible Vocabulary Reinvention")
        lines.append("")
        lines.append("| Local Term | Duplicates | Standard Vocabulary |")
        lines.append("|------------|-----------|---------------------|")
        for r in reinventions:
            lines.append(f"| `{r['local_short']}` | {r['duplicates']} | {r['vocabulary']} |")
        lines.append("")
        lines.append("_Consider replacing local terms with the standard vocabulary equivalents._")
        lines.append("")
    else:
        lines.append("## Vocabulary Reinvention")
        lines.append("")
        lines.append("No local terms duplicate standard vocabulary terms. ✅")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Audit external vocabulary usage and URI resolution")
    parser.add_argument("repo_path", help="Path to the ontology repository")
    parser.add_argument("-o", "--output", help="Output file (.json or .md)")
    parser.add_argument("--timeout", type=int, default=10,
                        help="HTTP timeout per URI (default: 10s)")
    parser.add_argument("--no-check", action="store_true",
                        help="Skip HTTP URI resolution check")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    args = parser.parse_args()

    print(f"[INFO] Extracting namespaces from {args.repo_path}...", file=sys.stderr)
    report = extract_external_namespaces(args.repo_path)

    # URI resolution check
    uris_to_check = list(report["namespaces"].keys())
    for imp in report.get("imports", []):
        uris_to_check.append(imp["uri"])

    uris_to_check = sorted(set(uris_to_check))
    print(f"[INFO] Checking {len(uris_to_check)} URIs...", file=sys.stderr)
    report["uri_checks"] = check_all_uris(uris_to_check, timeout=args.timeout) if uris_to_check else []

    # Update import status
    for imp in report.get("imports", []):
        for check in report["uri_checks"]:
            if check["uri"] == imp["uri"]:
                imp["status"] = check["status"]
                break

    # Reinvention detection
    print(f"[INFO] Checking for vocabulary reinvention...", file=sys.stderr)
    report["reinventions"] = detect_reinvention(args.repo_path)

    fmt = args.format
    if args.output:
        ext = Path(args.output).suffix.lower()
        if ext == ".json":
            fmt = "json"

    if fmt == "json":
        # Remove non-serializable Graph objects
        output = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    else:
        output = format_report_markdown(report)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"[INFO] Report written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
