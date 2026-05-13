---
name: ontology-typo-audit
description: Audits OWL/SKOS ontology repositories for grammar and spelling errors in string literals, wrong language tags, and SKOS structural issues. Uses rdflib for RDF parsing and LanguageTool for grammar checking in 30+ languages. General-purpose — not tied to any specific ontology or language pair.
license: MIT
compatibility: Requires python3, rdflib, language-tool-python
---

# Ontology Typo Audit

Systematic grammar, spelling, and structural audit for OWL/SKOS ontology
repositories. Uses **rdflib** to parse any RDF serialization (Turtle, OWL,
RDF/XML, N-Triples, JSON-LD, etc.) and **LanguageTool** to check every
string literal in its declared language — supporting 30+ languages out of the
box.

## What It Detects

| Category | Examples | Script |
|----------|----------|-------|
| Grammar & spelling errors by lang tag | Missing accents (`Pista de Padel` → `Pista de Pádel`), agreement errors, typos | `grammar_audit.py` |
| Suspicious lang tags | Spanish text tagged `@en` or vice versa | `grammar_audit.py` |
| Missing lang tags | Literals without `@en`/`@es`/etc. | `rdf_extract.py --no-lang` |
| SKOS structural issues | Undefined `skos:inScheme`, broken `skos:broader`, duplicate `prefLabel`, notation mismatches | `skos_audit.py` |

## Setup

Create a virtual environment and install dependencies:

```bash
cd <your-ontology-repo>
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install rdflib language-tool-python
```

> **Note:** `language-tool-python` downloads a Java-based LanguageTool server
> on first use (~200 MB). Requires a Java runtime (JRE 8+). On first run it
> may take 30–60 seconds to initialize.

## Workflow

### 1. Explore: extract all string literals with lang tags

Discover what's in the repo — every literal, its language, subject, and
predicate:

```bash
python scripts/rdf_extract.py . --summary --no-lang
```

Output (JSON to stdout, summary to stderr):

```json
[
  {
    "file": "ontology/onto.ttl",
    "subject": "http://example.com/onto#StreetLamp",
    "subject_short": ":StreetLamp",
    "predicate": "http://www.w3.org/2000/01/rdf-schema#label",
    "predicate_short": "rdfs:label",
    "value": "Street Lamp",
    "lang": "en"
  },
  ...
]
```

Save to file:

```bash
python scripts/rdf_extract.py . -o literals.json --summary
```

### 2. Audit grammar and spelling

Run LanguageTool on every literal in its declared language:

```bash
python scripts/grammar_audit.py . -o GRAMMAR_REPORT.md
```

Filter by language:

```bash
python scripts/grammar_audit.py . --lang es en -o report.md
```

JSON output for CI:

```bash
python scripts/grammar_audit.py . -o grammar.json --format json
```

The report groups issues by language and shows:
- The literal text and its context
- The grammar rule triggered and the error message
- Suggested corrections
- Which subjects/predicates are affected
- ⚠️ Lang tag mismatch warnings (when text looks like a different language than its tag)

### 3. Audit SKOS structure

Check for 8 categories of SKOS issues:

```bash
python scripts/skos_audit.py . -o SKOS_REPORT.md
```

Checks performed:
1. `skos:inScheme` references to undefined `ConceptScheme`s
2. Concepts with no `skos:inScheme`
3. Empty `ConceptScheme`s (no concepts)
4. `skos:notation` / URI fragment mismatches
5. Missing `skos:prefLabel`
6. Duplicate `prefLabel` within a scheme
7. Concept with `skos:broader` but no `skos:inScheme`
8. Broken `skos:broader`/`skos:narrower` links

### 4. Full audit (both checks at once)

```bash
python scripts/grammar_audit.py . -o GRAMMAR_REPORT.md
python scripts/skos_audit.py . -o SKOS_REPORT.md
```

## How It Works

```
┌─────────────────────┐
│  RDF files in repo  │
│  (.ttl, .owl, .rdf, │
│   .nt, .jsonld, …)  │
└────────┬────────────┘
         │ rdflib parses all
         ▼
┌─────────────────────┐     ┌──────────────────────┐
│  rdf_extract.py     │     │  skos_audit.py        │
│  Extract literals   │     │  Navigate graph:      │
│  with lang tags     │     │  concepts, schemes,   │
└────────┬────────────┘     │  broader/narrower,     │
         │                  │  prefLabels, notations │
         ▼                  └──────────┬─────────────┘
┌─────────────────────┐                │
│  grammar_audit.py   │                ▼
│  LanguageTool per   │      SKOS_REPORT.md
│  declared lang tag  │     (or .json)
└────────┬────────────┘
         ▼
  GRAMMAR_REPORT.md
  (or .json)
```

## Supported Languages

LanguageTool supports 30+ languages. Common BCP47 tags are automatically mapped:

| Tag | Language | Tag | Language |
|-----|----------|-----|----------|
| `en` | English | `fr` | French |
| `es` | Spanish | `de` | German |
| `pt` | Portuguese | `it` | Italian |
| `nl` | Dutch | `pl` | Polish |
| `ca` | Catalan | `gl` | Galician |
| `ja` | Japanese | `zh` | Chinese |
| `ar` | Arabic | `ru` | Russian |
| `ko` | Korean | `sv` | Swedish |
| `uk` | Ukrainian | `ro` | Romanian |

Full list: <https://dev.languagetool.org/languages>

## Important Rules

1. **Never edit re-used namespace URIs.** Classes/properties from external
   ontologies (e.g. `sosa:`, `schema:`, `dct:`) must not be modified — only
   fix labels/comments in *your* serialization.

2. **Changing SKOS concept URIs is a breaking change.** Fixing a typo in a
   concept URI means any data referencing the old URI will break. Document
   this in the PR and consider `owl:deprecated` + new URI, or
   `skos:exactMatch` to the corrected URI.

3. **Fix source files, not auto-generated docs.** The `documentation/`
   directory is usually regenerated by Widoco or similar tools. Fix the
   canonical source (ontology/*.owl, kos/*.ttl), then re-run the generator.

4. **Language tags must match content.** `"Underground station"@es` is wrong;
   it should be `@en`. The grammar audit flags these as "lang tag mismatch"
   when the text produces many errors in the declared language but few in
   another.

5. **Review LanguageTool suggestions before applying.** Short labels
   (proper nouns, acronyms, URI-style names) often trigger false positives.
   The script already disables the noisiest rules, but always review.

6. **For SKOS, `skos:notation` uses unaccented forms.** e.g.
   `pista-de-padel`, while `skos:prefLabel` uses proper orthography:
   `Pista de Pádel`.
