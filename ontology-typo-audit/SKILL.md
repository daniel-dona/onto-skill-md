---
name: ontology-typo-audit
description: Provides a script and instructions to audit spelling and grammar of every string literal in its declared language. Uses pyspellchecker (pip-only, fast) for spelling by default, LanguageTool (optional, slow) for grammar on request. Detects lang-tag mismatches on request. Use when cleaning up ontology labels or before a release.
license: MIT
compatibility: Requires python3, rdflib, pyspellchecker. Optional: language-tool-python (for grammar).
---

# Ontology Typo Audit

Systematic spelling and grammar audit for OWL/SKOS ontology repositories.
Uses **rdflib** to parse any RDF serialization, then checks every string
literal in its declared language.

**Single script:** `scripts/grammar_audit.py` — extract, audit, report.

**All dependencies via pip.** No system tools required.

## Two-Tier Checking

| Tier | Tool | Install | Speed | What it catches |
|------|------|---------|-------|-----------------|
| 1 (default) | **pyspellchecker** | `pip install pyspellchecker` | ⚡ Instant | Misspellings, missing accents, unknown words |
| 2 (optional) | **LanguageTool** | `pip install language-tool-python` | 🐢 ~1s/literal | Grammar errors, agreement, articles, context-dependent errors |

Ontology labels are short ("Street Lamp", "Pista de Pádel"). Misspellings and
missing accents account for ~90% of real issues. Grammar checking produces
mostly noise on short text. Hence: **pyspellchecker by default, LanguageTool
on request.**

## What pyspellchecker Catches (and Doesn't)

✅ **Catches:**
- Missing accents: "Padel" → suggests "Pádel", "Lampara" → "Lámpara"
- Misspellings: "pubic" (flagged as unknown in short labels), unknown words
- Custom dictionaries: domain terms loaded via `--dict` or `--word`

⚠️ **Doesn't catch (use `--grammar`):**
- Context-dependent errors: "pubic transport" (both words valid in English)
- Grammar: "The bus stop" tagged `@es` (use `--mismatch` instead)
- Languages beyond the 8 supported: ca, gl, ro, sv, cs, da, el, fi, hu, ko,
  no, sk, sl, tr, uk, he, ja, zh (use `--grammar` for these)

## Setup

```bash
cd <your-ontology-repo>
python3 -m venv .venv
source .venv/bin/activate

pip install rdflib pyspellchecker
```

For grammar checking (optional):

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

## Supported Languages

| Tool | Languages |
|------|-----------|
| pyspellchecker | **en**, **es**, **de**, **fr**, **pt**, **it**, **nl**, **ru**, **ar** (8 base + variants) |
| LanguageTool (`--grammar`) | 30+ (en, es, de, fr, pt, it, nl, pl, ru, uk, ja, zh, ar, ca, cs, da, el, fi, gl, he, hi, hu, ko, no, ro, sk, sl, sv, tl, tr, fa) |

If your project uses a language not supported by pyspellchecker (e.g. ca, gl,
sv), use `--grammar` which falls back to LanguageTool for those languages.

## Workflow

### 1. Explore: dump all literals

```bash
python scripts/grammar_audit.py . --dump --no-lang
```

### 2. Spell check (fast — recommended first pass)

```bash
python scripts/grammar_audit.py . -o SPELL_REPORT.md
```

### 3. With custom dictionary words

```bash
# Add domain-specific terms so they aren't flagged as errors
python scripts/grammar_audit.py . --word pádel Straße --dict my_words.txt
```

The `--dict` file format: one word per line, `#` comments allowed.

### 4. Spell + grammar check (slow)

```bash
python scripts/grammar_audit.py . --grammar -o FULL_REPORT.md
```

### 5. With lang-mismatch detection

```bash
python scripts/grammar_audit.py . --mismatch
```

### 6. Filter by language

```bash
python scripts/grammar_audit.py . --lang de fr
```

### 7. Fast mode (quick scan)

```bash
python scripts/grammar_audit.py . --fast
```

### 8. JSON for CI

```bash
python scripts/grammar_audit.py . --format json
```

## What It Detects

| Category | Tool | Flag | Description |
|----------|------|------|-------------|
| Spelling errors | pyspellchecker | (default) | Misspellings, missing accents |
| Unknown words | pyspellchecker | (default) | Not in dictionary (proper nouns, acronyms) |
| Grammar errors | LanguageTool | `--grammar` | Agreement, articles, verb forms |
| Suspicious lang tags | pyspellchecker | `--mismatch` | Text has many errors in declared language but few in another |
| Missing lang tags | (dump only) | `--dump --no-lang` | Literals with no `@xx` tag |

## Custom Dictionaries

Ontologies use domain-specific terms (proper nouns, acronyms) that aren't in
standard dictionaries. Add them to avoid false positives:

```bash
# Inline
python scripts/grammar_audit.py . --word pádel Straßenlaterne SOSA QUDT

# From file (one word per line, # comments)
python scripts/grammar_audit.py . --dict ontology_words.txt
```

The script also skips a built-in whitelist of Semantic Web terms (RDF, OWL,
SKOS, SOSA, QUDT, etc.) and chemical formulas (HCHO, NOx, PM10, etc.).

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
   Use `--mismatch` to detect these.

5. **Review suggestions before applying.** Short labels, proper nouns, and
   technical acronyms often trigger false positives. Always verify suggestions
   against domain knowledge before changing labels.

6. **Unknown word ≠ error.** Proper names and domain terms may not be in the
   dictionary. Add them with `--word` or `--dict` if they are correct.
