---
name: ontology-reasoner-check
description: Provides a script and instructions to check OWL logical consistency using the HermiT reasoner. Detects unsatisfiable classes, equivalences, and global inconsistency. Use before release to catch contradictory axioms that break reasoning.
license: MIT
compatibility: Requires python3, rdflib, owlready2
---

# Ontology Reasoner Consistency Check

Runs the **HermiT** OWL reasoner on the merged ontology to detect logical
contradictions. Reports unsatisfiable classes, non-trivial equivalences, and
global ontology inconsistency.

**Single script:** `scripts/reasoner_check.py`

## What It Detects

| Issue | Example |
|-------|---------|
| Unsatisfiable class | `:SquareCircle` defined as `owl:intersectionOf (:Square :Circle)` and `:Square owl:disjointWith :Circle` |
| Global inconsistency | `owl:Thing ≡ owl:Nothing` — the whole ontology is contradictory |
| Non-trivial equivalences | `:Person ≡ :Human` inferred because both have identical necessary+sufficient conditions |

## Setup

```bash
cd <your-ontology-repo>
python3 -m venv .venv
source .venv/bin/activate

pip install rdflib owlready2
```
> **After finishing:** deactivate the venv and remove it:
> ```bash
> deactivate && rm -rf .venv
> ```
> Skip this if the user asks to keep the environment.

> **Note:** `owlready2` bundles HermiT as a precompiled wheel. No Java required.
> The first time it runs, it may compile the native module, which takes a few seconds.

## Usage

```bash
# Reason over all merged RDF files
python scripts/reasoner_check.py . -o REASONER_REPORT.md

# Reason over a specific file
python scripts/reasoner_check.py . --only-file ontology/main.owl

# JSON output
python scripts/reasoner_check.py . --format json
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

1. **Unsatisfiable classes are always bugs.** A class that can never have instances
   indicates contradictory axioms. Check domain/range restrictions, disjointness, and
   cardinality constraints.

2. **Global inconsistency is critical.** If HermiT reports `owl:Nothing ≡ owl:Thing`,
   the entire ontology is logically broken. Fix unsatisfiable classes first — they're
   usually the root cause.

3. **Non-trivial equivalences may be intentional.** If `:Person ≡ :Human`, you may
   want to merge them or use `owl:equivalentClass`. The script flags them for review.

4. **Reasoning can be slow on large ontologies.** HermiT is optimized for OWL 2 DL.
   For very large ontologies (> 5000 classes), it may take several minutes.
