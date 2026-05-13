---
name: ontology-skos-audit
description: Audits SKOS concept schemes for structural integrity: broken inScheme references, missing prefLabels, duplicate labels, notation mismatches, orphan hierarchies, and broken broader/narrower links. Uses rdflib to parse any RDF serialization. General-purpose — not tied to any specific ontology.
license: MIT
compatibility: Requires python3, rdflib
---

# Ontology SKOS Audit

Structural integrity audit for SKOS concept schemes. Uses **rdflib** to
parse any RDF serialization (Turtle, OWL, RDF/XML, N-Triples, JSON-LD, etc.)
and navigate the SKOS graph to detect 8 categories of structural issues.

## What It Detects

| Check | Severity | Description |
|-------|----------|-------------|
| `inScheme-undefined` | ❌ Error | `skos:inScheme` references a ConceptScheme that is never defined in the repo |
| `no-inScheme` | ⚠️ Warning | Concept has no `skos:inScheme` — orphaned from any ConceptScheme |
| `empty-scheme` | ⚠️ Warning | ConceptScheme has no concepts |
| `missing-prefLabel` | ❌ Error | Concept has no `skos:prefLabel` (required by SKOS) |
| `duplicate-prefLabel` | ❌ Error | Two concepts in the same scheme have identical `prefLabel` + lang |
| `notation-mismatch` | ℹ️ Info | `skos:notation` value doesn't match the URI fragment or any `prefLabel` |
| `broader-no-inScheme` | ⚠️ Warning | Concept has `skos:broader` but no `skos:inScheme` |
| `broken-broader` | ❌ Error | `skos:broader` target is not defined as a `skos:Concept` |
| `broken-narrower` | ❌ Error | `skos:narrower` target is not defined as a `skos:Concept` |

## Setup

Create a virtual environment and install dependencies:

```bash
cd <your-ontology-repo>
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install rdflib
```

## Workflow

### 1. Run the audit

```bash
python scripts/skos_audit.py . -o SKOS_REPORT.md
```

### 2. JSON output for CI pipelines

```bash
python scripts/skos_audit.py . -o skos_issues.json --format json
```

Example JSON entry:

```json
{
  "severity": "error",
  "check": "inScheme-undefined",
  "message": "Concept :StreetLamp references undefined ConceptScheme ex:MissingScheme",
  "subject_short": ":StreetLamp",
  "scheme_short": "ex:MissingScheme"
}
```

## How It Works

```
┌─────────────────────┐
│  RDF files in repo  │
│  (.ttl, .owl, .rdf, │
│   .nt, .jsonld, …)  │
└────────┬────────────┘
         │ rdflib parses all into one graph
         ▼
┌─────────────────────┐
│  skos_audit.py      │
│  SPARQL-like graph  │
│  traversal:          │
│    skos:Concept     │
│    skos:ConceptScheme│
│    skos:inScheme    │
│    skos:broader     │
│    skos:narrower    │
│    skos:prefLabel   │
│    skos:notation    │
└────────┬────────────┘
         ▼
  SKOS_REPORT.md
  (or .json)
```

## Important Rules

1. **`missing-prefLabel` is always an error.** SKOS requires `skos:prefLabel`
   on every `skos:Concept`. A concept with only `skos:altLabel` is not valid.

2. **`duplicate-prefLabel` within a scheme is almost always wrong.** Two
   concepts in the same scheme should not share the same label since
   `prefLabel` is meant to be unique per language.

3. **`notation-mismatch` is informational, not always wrong.** The script
   normalizes accents and spaces before comparing. A mismatch may be
   intentional (e.g. legacy notation) — review manually.

4. **`empty-scheme` may be intentional** if the scheme is defined in a
   different file not scanned. Adjust the repo path accordingly.

5. **For SKOS, `skos:notation` uses unaccented forms.** e.g.
   `pista-de-padel`, while `skos:prefLabel` uses proper orthography:
   `Pista de Pádel`.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "No RDF files found" | The script skips hidden dirs (`.git`, `.venv`, etc.). Ensure your SKOS files are in a non-excluded directory. |
| Empty report when issues exist | Check that the SKOS files use correct namespace prefixes (rdflib requires prefix declarations in each file). |
| `Compact_uri` shows full URIs instead of prefix:name | Add `@prefix` declarations to your SKOS files for cleaner output. |
