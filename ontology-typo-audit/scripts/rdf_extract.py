#!/usr/bin/env python3
"""
rdf_extract.py — Extract all string literals with their language tags from an RDF repository.

Uses rdflib to parse .ttl, .owl, .rdf, .nt, .jsonld files and outputs a JSON report
with every literal, its lang tag, subject, predicate, source file and line (when available).

Usage:
    python rdf_extract.py <repo-path> [-o output.json] [--no-lang]
"""
import argparse
import json
import os
import sys
from pathlib import Path

from rdflib import Graph, Namespace, RDF, RDFS, OWL, SKOS, Literal, URIRef
from rdflib.namespace import NamespaceManager

from rdf_utils import find_rdf_files, compact_uri

# Common label/annotation predicates we care about for audit relevance
LABEL_PREDICATES = {
    RDFS.label,
    SKOS.prefLabel,
    SKOS.altLabel,
    SKOS.hiddenLabel,
    RDFS.comment,
    OWL.deprecated,
    SKOS.definition,
    SKOS.scopeNote,
    SKOS.example,
    SKOS.changeNote,
    SKOS.editorialNote,
    SKOS.historyNote,
}


def extract_literals(repo_path: str, include_no_lang: bool = False) -> list[dict]:
    """Parse all RDF files and extract string literals with lang tags."""
    results = []
    rdf_files = find_rdf_files(repo_path)

    if not rdf_files:
        print(f"[WARN] No RDF files found in {repo_path}", file=sys.stderr)
        return results

    for fpath in rdf_files:
        g = Graph()
        try:
            g.parse(fpath, format=None)  # rdflib auto-detects
        except Exception as e:
            print(f"[WARN] Could not parse {fpath}: {e}", file=sys.stderr)
            continue

        rel_path = os.path.relpath(fpath, repo_path)

        for s, p, o in g.triples((None, None, None)):
            if not isinstance(o, Literal):
                continue
            # Skip non-string datatypes (integers, booleans, etc.)
            if o.datatype and o.datatype not in (
                None,
                "http://www.w3.org/2001/XMLSchema#string",
                "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString",
            ):
                continue
            # Skip empty literals
            if not o.value or not str(o.value).strip():
                continue

            lang = str(o.language) if o.language else None

            if not include_no_lang and lang is None:
                continue

            predicate_local = compact_uri(p, g)
            subject_local = compact_uri(s, g)

            entry = {
                "file": rel_path,
                "subject": str(s),
                "subject_short": subject_local,
                "predicate": str(p),
                "predicate_short": predicate_local,
                "value": str(o.value),
                "lang": lang,
            }
            results.append(entry)

    return results


# _compact_uri removed — use rdf_utils.compact_uri instead


def main():
    parser = argparse.ArgumentParser(description="Extract string literals with lang tags from RDF files")
    parser.add_argument("repo_path", help="Path to the ontology repository")
    parser.add_argument("-o", "--output", help="Output JSON file (default: stdout)")
    parser.add_argument("--no-lang", action="store_true",
                        help="Include literals without a language tag")
    parser.add_argument("--summary", action="store_true",
                        help="Print a summary to stderr")
    args = parser.parse_args()

    literals = extract_literals(args.repo_path, include_no_lang=args.no_lang)

    # Sort by file, then subject, then predicate, then lang
    literals.sort(key=lambda x: (x["file"], x["subject"], x["predicate"], x["lang"] or ""))

    output = json.dumps(literals, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        print(output)

    if args.summary:
        langs = {}
        predicates = {}
        files = set()
        for lit in literals:
            langs[lit["lang"] or "(none)"] = langs.get(lit["lang"] or "(none)", 0) + 1
            predicates[lit["predicate_short"]] = predicates.get(lit["predicate_short"], 0) + 1
            files.add(lit["file"])
        print("\n--- Summary ---", file=sys.stderr)
        print(f"  Files parsed:     {len(files)}", file=sys.stderr)
        print(f"  Total literals:   {len(literals)}", file=sys.stderr)
        print(f"  By language:", file=sys.stderr)
        for lang, count in sorted(langs.items()):
            print(f"    {lang}: {count}", file=sys.stderr)
        print(f"  Top predicates:", file=sys.stderr)
        for pred, count in sorted(predicates.items(), key=lambda x: -x[1])[:10]:
            print(f"    {pred}: {count}", file=sys.stderr)


if __name__ == "__main__":
    main()
