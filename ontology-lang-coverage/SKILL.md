---
name: ontology-lang-coverage
description: Provides a script and instructions to check translation completeness — every RDF resource must have labels in all expected project languages. Use when maintaining multilingual ontologies to find missing translations before release.
license: MIT
compatibility: Requires python3, rdflib
---

# Ontology Language Coverage

Checks multilingual label coverage across an ontology repository. Discovers
which languages are used and reports every resource missing a
`rdfs:label` / `skos:prefLabel` / `skos:altLabel` in the expected languages.

**Single script:** `scripts/lang_coverage.py`

## What It Detects

| Issue | Description |
|-------|-------------|
| Missing translation | Resource has label in some project languages but not others |
| Extra languages | Resource has a label in a language outside the expected set |
| No labels at all | Resource with no `rdfs:label` or `skos:prefLabel` in any language |

## Setup

```bash
cd <your-ontology-repo>
python3 -m venv .venv
source .venv/bin/activate
pip install rdflib
```
> **After finishing:** deactivate the venv and remove it:
> ```bash
> deactivate && rm -rf .venv
> ```
> Skip this if the user asks to keep the environment.

## Usage

```bash
# Auto-detect target languages from the repo
python scripts/lang_coverage.py . -o COVERAGE_REPORT.md

# Specify target languages explicitly (recommended)
python scripts/lang_coverage.py . --lang en de fr -o report.md

# JSON for CI
python scripts/lang_coverage.py . --lang en de fr --format json
```

## How It Works

The script auto-detects all languages present in the repo. If you specify
`--lang`, it uses that list as the expected set. Any resource that has labels
in some expected languages but not all is flagged as incomplete.

Resources with labels in languages outside the expected set trigger an
"extra language" info note — useful for catching accidental `@fr` labels
in an `en/de`-only project.

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

1. **Always specify `--lang` for accurate results.** Auto-detection may
   include noise from imported vocabularies with labels in unexpected languages.

2. **`skos:altLabel` counts as coverage.** If a resource has an altLabel in
   a language, it is considered covered. Adjust `LABEL_PREDICATES` in the
   script if your project uses different annotation properties.

3. **This is structural coverage, not quality.** Use `ontology-typo-audit`
   to check the grammar of the existing labels.
