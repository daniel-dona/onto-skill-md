---
name: ontology-typo-audit
description: Provides a script and instructions to audit spelling and grammar of every string literal in its declared language. Uses Hunspell (fast) for spelling by default, LanguageTool (slow) for grammar on request. Detects lang-tag mismatches on request. Use when cleaning up ontology labels or before a release.
license: MIT
compatibility: Requires python3, rdflib, hunspell (recommended, fast) or language-tool-python (optional, slow)
---

# Ontology Typo Audit

Systematic spelling and grammar audit for OWL/SKOS ontology repositories.
Uses **rdflib** to parse any RDF serialization, then checks every string
literal in its declared language.

**Single script:** `scripts/grammar_audit.py` — extract, audit, report.

## Two- Tier Checking

| Tier | Tool | Speed | What it catches | When to use |
|------|------|-------|-----------------|-------------|
| 1 (default) | **Hunspell** | ⚡ Instant | Misspellings, missing accents (Pádel vs Padel), unknown words | Always — run this first |
| 2 (optional) | **LanguageTool** | 🐢 ~1s/literal | Grammar errors, agreement, articles + spelling | `--grammar` — only on literals that already have spelling issues |

Ontology labels are short ("Street Lamp", "Pista de Pádel"). Misspellings and
missing accents account for ~90% of real issues. Grammar checking produces
mostly noise on short text. Hence: **Hunspell by default, LanguageTool on
request.**

## Setup

### Hunspell (recommended — fast)

System tool, install once:

```bash
sudo apt install hunspell hunspell-es hunspell-de hunspell-fr   # Debian/Ubuntu
brew install hunspell                                            # macOS
```

Install only the dictionaries for your project's languages. Common packages:

| Language | Package (Debian) |
|----------|-----------------|
| English | `hunspell-en-us` |
| Spanish | `hunspell-es` |
| German | `hunspell-de-de` |
| French | `hunspell-fr` |
| Portuguese | `hunspell-pt-br` |
| Italian | `hunspell-it-it` |
| Catalan | `hunspell-ca` |
| Galician | `hunspell-gl` |

Full list: `apt search hunspell-`

### Python dependencies

```bash
cd <your-ontology-repo>
python3 -m venv .venv
source .venv/bin/activate

pip install rdflib
```

### LanguageTool (optional — for grammar)

Only needed if you want grammar checking (`--grammar`):

```bash
pip install language-tool-python
```

> **Note:** `language-tool-python` downloads a Java-based LanguageTool server
> on first use (~200 MB). Requires JRE 8+. First run may take 30–60s.

> **After finishing:** deactivate the venv and remove it:
> ```bash
> deactivate && rm -rf .venv
> ```
> Skip this if the user asks to keep the environment.

## Workflow

### 1. Explore: dump all literals

```bash
python scripts/grammar_audit.py . --dump --no-lang
```

### 2. Spell check (fast — recommended first pass)

```bash
python scripts/grammar_audit.py . -o SPELL_REPORT.md
```

### 3. Spell + grammar check (slow)

```bash
python scripts/grammar_audit.py . --grammar -o FULL_REPORT.md
```

### 4. Fast mode (quick scan)

```bash
python scripts/grammar_audit.py . --fast
```

### 5. Filter by language

```bash
python scripts/grammar_audit.py . --lang de fr
```

### 6. With lang-mismatch detection

```bash
# Fast with hunspell:
python scripts/grammar_audit.py . --mismatch
# Slow (also checks grammar in every language):
python scripts/grammar_audit.py . --grammar --mismatch
```

### 7. JSON for CI

```bash
python scripts/grammar_audit.py . --format json
```

## What It Detects

| Category | Tool | Description |
|----------|------|-------------|
| Spelling errors | Hunspell | Misspelled words, missing accents |
| Unknown words | Hunspell | Words not in the dictionary (proper nouns, acronyms) |
| Grammar errors | LanguageTool (`--grammar`) | Agreement, wrong verb forms, missing articles |
| Suspicious lang tags | `--mismatch` | Text with many errors in declared language but few in another |
| Missing lang tags | `--dump --no-lang` | Literals with no `@xx` tag |

## Hunspell vs LanguageTool

- **Hunspell is stricter on accents.** "Padel" without accent is flagged in
  Spanish. LanguageTool may or may not flag it depending on context.
- **Hunspell doesn't do grammar.** It won't catch "The bus stop" tagged `@es`
  as a grammar error — but `--mismatch` will catch it as a lang-tag mismatch.
- **Hunspell is ~100x faster.** A repo with 500 literals takes ~1 second with
  Hunspell vs ~5 minutes with LanguageTool.

## Technical Term Whitelist

The script skips common ontology/Semantic Web acronyms (RDF, OWL, SKOS, SOSA,
QUDT, etc.) and chemical formulas (HCHO, NOx, PM10, etc.) during spell-checking.
Add project-specific terms by editing `TECHNICAL_WORDS` in the script.

## Supported Languages

| Tool | Languages |
|------|-----------|
| Hunspell | 70+ languages (depends on installed dictionaries) |
| LanguageTool | 30+ languages (built-in) |

Common BCP47 tags are automatically mapped to the correct dictionary for both
tools.

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

1. **Never edit re-used namespace URIs.** Classes/properties from external
   ontologies must not be modified — only fix labels/comments.

2. **Changing SKOS concept URIs is a breaking change.** Fixing a typo in a
   concept URI means data referencing the old URI will break.

3. **Fix source files, not auto-generated docs.** Fix the canonical source
   (ontology/*.owl, kos/*.ttl), then re-run the generator.

4. **Language tags must match content.** French text tagged `@de` is wrong.
   The audit flags mismatches with `--mismatch`.

5. **Review suggestions before applying.** Short labels, proper nouns, and
   technical acronyms (SOSA, QUDT, GeoSPARQL, OWL, RDF, chemical formulas
   like HCHO/NOx) often trigger false positives. Always verify suggestions
   against domain knowledge before changing labels.

6. **Hunspell unknown words ≠ errors.** Proper names ("Pádel") and domain
   terms may not be in the dictionary. Add them to `TECHNICAL_WORDS` in the
   script if they are correct.
