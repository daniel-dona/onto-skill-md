---
name: ontology-typo-audit
description: Provides a script and instructions to audit spelling and grammar of every string literal in its declared language. Uses Hunspell via ctypes (compiled from source or system). Optional LanguageTool for grammar. Detects lang-tag mismatches.
license: MIT
compatibility: Requires python3, rdflib, hunspell (build script provided). Optional: language-tool-python.
---

# Ontology Typo Audit

Systematic spelling and grammar audit for OWL/SKOS ontology repositories.
Uses **rdflib** to parse any RDF serialization, then checks every string
literal in its declared language.

**Single script:** `scripts/grammar_audit.py` — extract, audit, report.

**Spell checker:** Hunspell — the same engine used by LibreOffice and Firefox.
Called directly via ctypes — no Python binding needed.

## Setup

### 1. Install Python dependencies

```bash
cd <your-ontology-repo>
python3 -m venv .venv
source .venv/bin/activate

pip install rdflib
```

### 2. Install Hunspell

**Option A: Build from source (recommended — works everywhere, no root)**

```bash
bash scripts/build_hunspell.sh
```

This script:
- Clones hunspell from GitHub (v1.7.3)
- Compiles `libhunspell` as a shared library
- Downloads dictionaries from LibreOffice (68 languages available)
- Installs everything to `~/.local/share/hunspell-built/`

Build dependencies: `g++ make autoconf automake autopoint libtool`

```bash
# Debian/Ubuntu
sudo apt install g++ make autoconf automake autopoint libtool

# Fedora
sudo dnf install gcc-c++ make autoconf automake libtool gettext-devel

# macOS
xcode-select --install
brew install autoconf automake libtool gettext
brew link gettext --force
```

Customize languages:

```bash
# Default: en, es, fr, de, it, pt, nl, ru
bash scripts/build_hunspell.sh

# Specific languages only (faster download)
bash scripts/build_hunspell.sh --langs es,en,de,fr

# Custom install location
bash scripts/build_hunspell.sh --prefix /opt/hunspell --langs es,en
```

Available language codes for `--langs`:
en, es, fr, de, it, pt, nl, ru, ar, ca, gl, ro, sv, cs, da, el, fi, hu,
ko, no, pl, sk, sl, tr, uk, he, id, vi

**Option B: System package (if you have root)**

```bash
# Debian/Ubuntu
sudo apt install libhunspell-dev hunspell-es hunspell-de hunspell-fr

# Fedora
sudo dnf install hunspell-devel hunspell-es

# macOS
brew install hunspell
```

The script auto-detects system-installed hunspell and dictionaries.

### 3. Optional: LanguageTool (for grammar checking)

```bash
pip install language-tool-python
```

> Downloads a Java server (~200 MB) on first use. Requires JRE 8+.

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

### 3. With custom words

```bash
# Inline
python scripts/grammar_audit.py . --word pádel Straßenlaterne

# From file (one per line, # comments)
python scripts/grammar_audit.py . --dict my_words.txt
```

Custom words are added to hunspell's runtime dictionary — they inherit
affixes (plurals, conjugations) if a similar word exists in the dictionary.

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

| Category | Flag | Description |
|----------|------|-------------|
| Spelling errors | (default) | Misspellings, missing accents (Padel→Pádel) |
| Unknown words | (default) | Not in dictionary (proper nouns, acronyms) |
| Grammar errors | `--grammar` | Agreement, articles, verb forms (via LanguageTool) |
| Suspicious lang tags | `--mismatch` | Many errors in declared lang, few in another |
| Missing lang tags | `--dump --no-lang` | Literals with no `@xx` tag |

## How It Works

The script calls `libhunspell` directly via Python's `ctypes` module — no
subprocess, no Python C extension, no pip package for hunspell. This gives:

- **Same speed as native hunspell** (~0.001ms per word)
- **Full affix expansion** — "lámparas" recognized via .aff rules, not just "lámpara"
- **Suggestions** — "automovil" → "automóvil", "lampara" → "lámpara"
- **Runtime word addition** — `--word` terms get affixes if a similar word exists

## Supported Languages

68 languages via LibreOffice dictionaries (run `build_hunspell.sh --langs`).
Common ones:

| Code | Language | Code | Language |
|------|----------|------|----------|
| en | English | es | Spanish |
| fr | French | de | German |
| it | Italian | pt | Portuguese |
| nl | Dutch | ru | Russian |
| ar | Arabic | ca | Catalan |
| gl | Galician | ro | Romanian |
| sv | Swedish | cs | Czech |
| pl | Polish | uk | Ukrainian |
| hu | Hungarian | tr | Turkish |

## Technical Term Whitelist

The script skips common ontology/Semantic Web terms automatically:
RDF, OWL, SKOS, SOSA, QUDT, GeoSPARQL, FOAF, DCAT, PROV, HCHO, NOx, PM10, etc.
Add project-specific terms with `--word` or `--dict`.

## Standardized Report

All skills support `--format report` which outputs a common JSON schema:
```json
{
  "skill": "typo-audit",
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
