---
name: ontology-syntax-validate
description: Provides a script and instructions to validate RDF syntax of every file in a repository using rapper (raptor2) with rdflib fallback. Covers Turtle, RDF/XML, N-Triples, JSON-LD, and more. Use before any other ontology check — if files don't parse, nothing else works.
license: MIT
compatibility: Requires rapper (apt install raptor2-utils) or rdflib (pip install rdflib)
---

# Ontology Syntax Validation

Validates that every RDF file in a repository is syntactically valid. Uses
**rapper** from [raptor2](https://librdf.org/raptor/) (the reference RDF parser
from the W3C ecosystem) as primary validator. Falls back to **rdflib** if
rapper is not installed.

**Single script:** `scripts/syntax_validate.py`

## Supported Formats

| Extension | Format | Parser |
|-----------|--------|--------|
| `.ttl` | Turtle | rapper / rdflib |
| `.owl` | RDF/XML | rapper / rdflib |
| `.rdf` | RDF/XML | rapper / rdflib |
| `.nt` | N-Triples | rapper / rdflib |
| `.nq` | N-Quads | rapper |
| `.trig` | TriG | rapper / rdflib |
| `.jsonld` | JSON-LD | rapper / rdflib |
| `.html`, `.xhtml` | RDFa | rapper |

## Setup

Rapper is a system tool — install once:

```bash
sudo apt install raptor2-utils    # Debian/Ubuntu
brew install raptor               # macOS
```

For the rdflib fallback (if rapper is unavailable), use a venv:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install rdflib
```
> **After finishing:** deactivate the venv and remove it:
> ```bash
> deactivate && rm -rf .venv
> ```
> Skip this if the user asks to keep the environment.

No virtual environment needed if you only use rapper (it's a system tool).

## Usage

```bash
python scripts/syntax_validate.py . -o SYNTAX_REPORT.md

# Force rdflib even if rapper is installed
python scripts/syntax_validate.py . --rdflib

# JSON output
python scripts/syntax_validate.py . --format json
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

1. **Syntax validation is the first gate.** If a file doesn't parse, no other
   skill (typo, SKOS, OOPS, SHACL) can process it. Run this first.

2. **rapper is stricter than rdflib.** It may flag valid-but-ambiguous
   constructs as warnings. Treat rapper errors as authoritative.

3. **Large files may time out.** Use `--rdflib` for files over 10K triples if
   rapper is slow (default 30s timeout per file).
