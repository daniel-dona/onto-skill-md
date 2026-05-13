---
name: ontology-lang-coverage
description: Checks that every RDF resource (class, property, SKOS concept) has labels in all expected project languages. Reports missing translations and resources with unexpected language tags. Uses only rdflib.
license: MIT
compatibility: Requires python3, rdflib
---

# Ontology Language Coverage

Checks multilingual label coverage across an ontology repository. Discovers
which languages are used and reports every resource missing a
`rdfs:label` / `skos:prefLabel` / `skos:altLabel` in the expected languages.

**Single script:** `scripts/lang_coverage.py`

## What It Detects

| Issue | Example |
|-------|---------|
| Missing translation | `:StreetLamp` has `rdfs:label "Street Lamp"@en` but no `@es` label in a bilingual project |
| Extra languages | Resource has `@fr` label in an en/es-only project |
| No labels at all | Resource with no `rdfs:label` or `skos:prefLabel` in any language |

## Setup

```bash
cd <your-ontology-repo>
python3 -m venv .venv
source .venv/bin/activate

pip install rdflib
```

## Usage

```bash
# Auto-detect target languages
python scripts/lang_coverage.py . -o COVERAGE_REPORT.md

# Explicit target languages
python scripts/lang_coverage.py . --lang es en fr -o report.md

# JSON for CI
python scripts/lang_coverage.py . --lang es en --format json
```

## Important Rules

1. **Decide your project languages first.** If your project is en/es, use `--lang en es`.
   Otherwise auto-detection may include noise from imported vocabularies.

2. **`skos:altLabel` counts as coverage.** If a resource has an altLabel in a language,
   it is considered covered for that language. Adjust `LABEL_PREDICATES` in the script
   if your project uses different annotation properties.

3. **This is structural coverage, not quality.** Use `ontology-typo-audit` to check
   the grammar of the existing labels.
