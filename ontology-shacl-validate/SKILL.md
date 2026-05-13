---
name: ontology-shacl-validate
description: Validates RDF instance data against SHACL shapes, auto-generating minimal shapes from OWL axioms if none exist. Use when checking data quality or when instance data must conform to a schema.
license: MIT
compatibility: Requires python3, rdflib, pyshacl
---

# Ontology SHACL Validation

Validates RDF instance data against SHACL shapes. If you don't have shapes yet,
the script auto-generates minimal ones from `owl:Class` + `rdfs:domain`/`range` axioms.

**Single script:** `scripts/shacl_validate.py`

## What It Detects

| Issue | Example |
|-------|---------|
| Missing required property | `:Person` has no `:name` but `owl:minCardinality 1` → violation |
| Wrong datatype | `:age "twenty"` but SHACL shape expects `xsd:integer` |
| Cardinality violation | Multiple values for a functional property |
| Missing classes | Resources of a class that has no instances (info-only) |

## Setup

```bash
cd <your-ontology-repo>
python3 -m venv .venv
source .venv/bin/activate

pip install rdflib pyshacl
```

## Usage

```bash
# Auto-generate shapes from schema axioms
python scripts/shacl_validate.py . -o SHACL_REPORT.md

# Use your own shapes file
python scripts/shacl_validate.py . --shapes shapes.ttl -o report.md

# JSON for CI
python scripts/shacl_validate.py . --format json
```

## Standardized Report

All skills support `--format report` which outputs a common JSON schema:
```json
{
  "skill": "skill-name",
  "summary": {"errors": N, "warnings": N, "info": N},
  "issues": [{"file": ".ttl", "element": ":Class", "message": "...",
              "severity": "error|warning|info", "check": "RULE",
              "suggestion": "fix"}]
}
```
This format is consumed by `ontology-full-audit` to produce unified reports.

## Important Rules

1. **Auto-generated shapes are minimal.** They only cover cardinality constraints
   from `owl:minCardinality`/`owl:maxCardinality` restrictions. For richer validation
   (pattern, datatype, class membership), write explicit SHACL shapes.

2. **SHACL validates instances, not schemas.** The script separates shape definitions
   from data triples automatically. If you have no instances yet, the validation
   will pass trivially.

3. **Combine with OOPS.** OOPS checks schema design pitfalls. SHACL checks data
   quality. Together they cover the full ontology lifecycle.
