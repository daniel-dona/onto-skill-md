---
name: ontology-typo-audit
description: Provides a script and instructions to audit spelling and grammar of every string literal in its declared language. Uses Hunspell via ctypes (autodetected, no install) or pyspellchecker (pip-only) for spelling, LanguageTool (optional, slow) for grammar. Detects lang-tag mismatches on request.
license: MIT
compatibility: Requires python3, rdflib, pyspellchecker. Optional: language-tool-python (grammar). Hunspell autodetected if present.
---

# Ontology Typo Audit

Systematic spelling and grammar audit for OWL/SKOS ontology repositories.
Uses **rdflib** to parse any RDF serialization, then checks every string
literal in its declared language.

**Single script:** `scripts/grammar_audit.py` — extract, audit, report.

**Minimum deps: pip only.** Hunspell auto-detected if present (better quality).

## Three-Tier Checking

| Tier | Tool | Install | Speed | What it catches |
|------|------|---------|-------|-----------------|
| 1a | **Hunspell (ctypes)** | Already on most Linux | ⚡ Instant | Misspellings, accents, affixes, 25+ languages |
| 1b | **pyspellchecker** | `pip install pyspellchecker` | ⚡ Instant | Misspellings, accents, 8 languages |
| 2 | **LanguageTool** | `pip install language-tool-python` | 🐢 ~1s/literal | Grammar, agreement, 30+ languages |

The script tries them in order: hunspell (if the C library is on the system)
→ pyspellchecker → LanguageTool. **You only need pyspellchecker** — hunspell
is a bonus if available.

### Why Hunspell when available?

- **More languages** (25+ vs 8 for pyspellchecker) — dictionaries usually
  already installed on Linux (`apt install hunspell-es` etc.)
- **Better affix handling** — hunspell .aff files generate all inflected forms
  (plurals, conjugations), so "lámparas" is recognized, not just "lámpara"
- **Same speed** — ctypes call is ~0.001ms per word

### pyspellchecker as fallback

- Pure Python, pip-only, 0 system dependencies
- 8 base languages: en, es, de, fr, pt, it, nl, ru, ar + variants
- Catches missing accents (Padel→Pádel, Lampara→Lámpara)
- Custom dictionaries via `--dict` / `--word` for domain terms

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
> on first use (~200 MB). Requires JRE 8+.

> **After finishing:** deactivate the venv and remove it:
> ```bash
> deactivate && rm -rf .venv
> ```
> Skip this if the user asks to keep the environment.

### Optional: Hunspell dictionaries

If libhunspell is already on the system (most Linux distros), install
dictionaries for your project's languages:

```bash
# Debian/Ubuntu
sudo apt install hunspell-es hunspell-de hunspell-fr

# Fedora
sudo dnf install hunspell-es hunspell-de

# macOS
brew install hunspell
```

The script auto-detects libhunspell and any installed dictionaries. No
configuration needed.

## Supported Languages

| Tool | Languages |
|------|-----------|
| Hunspell (autodetected) | 25+ (depends on installed dictionaries — `dpkg -l 'hunspell-*'`) |
| pyspellchecker | **en**, **es**, **de**, **fr**, **pt**, **it**, **nl**, **ru**, **ar** |
| LanguageTool (`--grammar`) | 30+ (en, es, de, fr, pt, it, nl, pl, ru, uk, ja, zh, ar, ca, cs, ...) |

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
| Spelling errors | hunspell/pyspellchecker | (default) | Misspellings, missing accents |
| Unknown words | hunspell/pyspellchecker | (default) | Not in dictionary |
| Grammar errors | LanguageTool | `--grammar` | Agreement, articles, verb forms |
| Suspicious lang tags | spell checker | `--mismatch` | Many errors in declared lang, few in another |
| Missing lang tags | (dump only) | `--dump --no-lang` | Literals with no `@xx` tag |

## Custom Dictionaries

Ontologies use domain-specific terms that aren't in standard dictionaries:

```bash
# Inline
python scripts/grammar_audit.py . --word pádel Straßenlaterne SOSA QUDT

# From file
python scripts/grammar_audit.py . --dict ontology_words.txt
```

The script also skips a built-in whitelist: RDF, OWL, SKOS, SOSA, QUDT,
GeoSPARQL, FOAF, DCAT, PROV, HCHO, NOx, PM10, etc.

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
or an absolute path outside the repo).

## Important Rules

1. **Never edit re-used namespace URIs.** Classes/properties from external
   ontologies must not be modified — only fix labels/comments.

2. **Changing SKOS concept URIs is a breaking change.** Fixing a typo in a
   concept URI means data referencing the old URI will break.

3. **Fix source files, not auto-generated docs.** Fix the canonical source
   (ontology/*.owl, kos/*.ttl), then re-run the generator.

4. **Language tags must match content.** Use `--mismatch` to detect mismatches.

5. **Review suggestions before applying.** Short labels, proper nouns, and
   technical acronyms often trigger false positives.

6. **Unknown word ≠ error.** Proper names and domain terms may not be in the
   dictionary. Add them with `--word` or `--dict` if correct.
