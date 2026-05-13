#!/usr/bin/env python3
"""
rdf_utils.py — Shared RDF utilities for ontology skills.

Provides:
  - find_rdf_files(repo_path) — discover all parseable RDF files in a repo
  - load_graph(repo_path)     — parse all RDF files into a single rdflib.Graph
  - compact_uri(uri, graph)   — shorten a URI using namespace prefixes

This file is copied into each skill's scripts/ directory so skills remain
self-contained (no cross-skill imports).

Requires: pip install rdflib
"""
import os
import sys
from pathlib import Path

from rdflib import Graph, RDF, RDFS, OWL, SKOS, Literal, URIRef

# RDF file extensions rdflib can parse
RDF_EXTS = {".ttl", ".owl", ".rdf", ".rdfs", ".nt", ".jsonld", ".n3", ".trig", ".nq"}


def find_rdf_files(repo_path: str) -> list[str]:
    """Walk repo and return all parseable RDF files."""
    rdf_files = []
    for root, dirs, files in os.walk(repo_path):
        # Skip hidden and dependency dirs
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in (
            "node_modules", "__pycache__", ".venv", "venv", "build", "dist"
        )]
        for fname in sorted(files):
            if Path(fname).suffix.lower() in RDF_EXTS:
                rdf_files.append(os.path.join(root, fname))
    return rdf_files


def load_graph(repo_path: str) -> tuple[Graph, list[str]]:
    """Parse all RDF files into a single Graph. Returns (graph, warnings)."""
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


def compact_uri(uri: URIRef, g: Graph) -> str:
    """Try to represent a URI as prefix:localname."""
    nm = g.namespace_manager
    try:
        prefix, namespace, name = nm.compute_qname(uri, generate=False)
        return f"{prefix}:{name}"
    except Exception:
        try:
            prefix, namespace, name = nm.compute_qname(uri, generate=True)
            return f"{prefix}:{name}"
        except Exception:
            return str(uri)
