---
name: ontology-shacl-validate
description: Provides a script and instructions to validate instance data against SHACL shapes using pySHACL, auto-generating shapes from OWL axioms if needed. Use when checking data quality or enforcing schema constraints.
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
> **After finishing:** deactivate the venv and remove it:
> ```bash
> deactivate && rm -rf .venv
> ```
> Skip this if the user asks to keep the environment.

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


## Output Files

**Never write files into the repository without permission.** Before generating
any report or output file, ask the user where to save it (e.g. `-o ../report.md`
or an absolute path outside the repo). The default output path in script
examples is only a suggestion — always confirm with the user first.

## Important Rules

1. **Auto-generated shapes are minimal.** They only cover cardinality constraints
   from `owl:minCardinality`/`owl:maxCardinality` restrictions. For richer validation
   (pattern, datatype, class membership), write explicit SHACL shapes.

2. **SHACL validates instances, not schemas.** The script separates shape definitions
   from data triples automatically. If you have no instances yet, the validation
   will pass trivially.

3. **Combine with OOPS.** OOPS checks schema design pitfalls. SHACL checks data
   quality. Together they cover the full ontology lifecycle.
