---
name: ontology-syntax-validate
description: Validates RDF syntax of all files in a repository using rapper (raptor2) or rdflib. Supports Turtle, RDF/XML, N-Triples, N-Quads, TriG, JSON-LD, and RDFa. Reports parse errors with file, line, column, and message.
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

```bash
# Recommended: install rapper (fast, battle-tested, all formats)
sudo apt install raptor2-utils    # Debian/Ubuntu
brew install raptor               # macOS

# Fallback (slower, Turtle/RDF/XML/NT/JSON-LD only)
pip install rdflib
```

No virtual environment needed if you only use rapper (it's a system tool).

## Usage

```bash
python scripts/syntax_validate.py . -o SYNTAX_REPORT.md

# Force rdflib even if rapper is installed
python scripts/syntax_validate.py . --rdflib

# JSON output
python scripts/syntax_validate.py . --format json
```

## Important Rules

1. **Syntax validation is the first gate.** If a file doesn't parse, no other
   skill (typo, SKOS, OOPS, SHACL) can process it. Run this first.

2. **rapper is stricter than rdflib.** It may flag valid-but-ambiguous
   constructs as warnings. Treat rapper errors as authoritative.

3. **Large files may time out.** Use `--rdflib` for files over 10K triples if
   rapper is slow (default 30s timeout per file).
