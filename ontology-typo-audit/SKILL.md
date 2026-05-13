---
name: ontology-typo-audit
description: Provides a script and instructions to audit spelling and grammar of every string literal in its declared language. Uses Hunspell via ctypes. Dictionaries auto-downloaded from LibreOffice based on the project's language tags. Optional LanguageTool for grammar.
license: MIT
compatibility: Requires python3, rdflib, hunspell (build script provided). Optional: language-tool-python.
---

# Ontology Typo Audit

Systematic spelling and grammar audit for OWL/SKOS ontology repositories.
Uses **rdflib** to parse any RDF serialization, then checks every string
literal in its declared language.

**Single script:** `scripts/grammar_audit.py` — extract, audit, report.

**Dictionaries auto-downloaded** from LibreOffice based on the project's
language tags. No manual dictionary management needed.

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
# Auto-detect languages from your ontology repo:
bash scripts/build_hunspell.sh --repo .

# Or explicit languages:
bash scripts/build_hunspell.sh --langs es,en,de

# Default: English only
bash scripts/build_hunspell.sh
```

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

**Option B: System package (if you have root)**

```bash
# Debian/Ubuntu
sudo apt install libhunspell-dev hunspell-es hunspell-de

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

## How Dictionaries Work

**Dictionaries are auto-downloaded based on the project's language tags.**

When you run `grammar_audit.py` on a repo:

1. Scan all RDF files → extract `@lang` tags (e.g. `@es`, `@en`, `@de`)
2. Map lang tags to hunspell dictionaries (e.g. `es` → `es_ES.aff` + `es_ES.dic`)
3. Check if dictionaries exist locally (in `~/.local/share/hunspell-built/` or system dirs)
4. **Download missing dictionaries** from LibreOffice automatically
5. Run spell check

If no language tags are found in the project → defaults to English.

This means: **different projects automatically get the right dictionaries.**
A Spanish ontology gets `es_ES`, a German one gets `de_DE_frami`, etc.

## Workflow

### 1. Explore: dump all literals and their languages

```bash
python scripts/grammar_audit.py . --dump --no-lang
```

### 2. Spell check (auto-downloads needed dictionaries)

```bash
python scripts/grammar_audit.py . -o SPELL_REPORT.md
```

### 3. With custom words (domain terms not in dictionaries)

```bash
# Inline
python scripts/grammar_audit.py . --word pádel Straßenlaterne

# From file (one per line, # comments)
python scripts/grammar_audit.py . --dict my_words.txt
```

Custom words are added to hunspell's runtime dictionary. They inherit
affixes (plurals, conjugations) if a similar word exists.

### 4. Spell + grammar check (slow)

```bash
python scripts/grammar_audit.py . --grammar -o FULL_REPORT.md
```

### 5. With lang-mismatch detection

```bash
python scripts/grammar_audit.py . --mismatch
```

### 6. Filter by language (only check these)

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
subprocess, no Python C extension, no pip package for hunspell.

- **Same speed as native hunspell** (~0.001ms per word)
- **Full affix expansion** — "lámparas" recognized via .aff rules
- **Suggestions** — "automovil" → "automóvil"
- **Runtime word addition** — `--word` terms get affixes if similar word exists

## Supported Languages

60+ via LibreOffice dictionaries. Common ones:

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

Full list: see `BCP47_TO_DICT` in `grammar_audit.py`.

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
