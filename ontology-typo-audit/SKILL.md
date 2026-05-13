---
name: ontology-typo-audit
description: Audits OWL/SKOS ontology repositories for grammar and spelling errors in string literals and wrong language tags. Uses rdflib for RDF parsing and LanguageTool for grammar checking in 30+ languages. General-purpose — not tied to any specific ontology or language pair.
license: MIT
compatibility: Requires python3, rdflib, language-tool-python
---

# Ontology Typo Audit

Systematic grammar and spelling audit for OWL/SKOS ontology repositories.
Uses **rdflib** to parse any RDF serialization and **LanguageTool** to check
every string literal in its declared language.

**Single script:** `scripts/grammar_audit.py` — extract, audit, report.

## What It Detects

| Category | Description |
|----------|-------------|
| Spelling errors | Misspelled words in the language of the lang tag |
| Grammar errors | Agreement errors, wrong verb forms, missing articles |
| Suspicious lang tags | Text that produces many errors in its declared language but few in another language present in the repo |
| Missing lang tags | Literals with no `@xx` tag (`--dump --no-lang`) |

## Setup

```bash
cd <your-ontology-repo>
python3 -m venv .venv
source .venv/bin/activate

pip install rdflib language-tool-python
```

> **Note:** `language-tool-python` downloads a Java-based LanguageTool server
> on first use (~200 MB). Requires JRE 8+. First run may take 30–60s.

## Workflow

### 1. Explore: dump all literals

```bash
python scripts/grammar_audit.py . --dump --no-lang
```

### 2. Audit everything

```bash
python scripts/grammar_audit.py . -o GRAMMAR_REPORT.md
```

### 3. Filter by language

```bash
# Only check specific languages
python scripts/grammar_audit.py . --lang de fr
```

### 4. JSON for CI

```bash
python scripts/grammar_audit.py . --format json
```

The report groups issues by language and shows the text, error rule,
suggested correction, and which subjects/predicates are affected.

## Lang Tag Mismatch Detection

When a literal produces many errors in its declared language but few in
another language present in the repo, the script flags a possible mismatch.
This works for ANY combination of languages — no hardcoded pairs.

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
   ontologies must not be modified — only fix labels/comments.

2. **Changing SKOS concept URIs is a breaking change.** Fixing a typo in a
   concept URI means data referencing the old URI will break.

3. **Fix source files, not auto-generated docs.** Fix the canonical source
   (ontology/*.owl, kos/*.ttl), then re-run the generator.

4. **Language tags must match content.** French text tagged `@de` is wrong.
   The audit flags mismatches by comparing error rates across all languages
   present in the repo.

5. **Review LanguageTool suggestions before applying.** Short labels
   (proper nouns, acronyms) often trigger false positives.
