---
name: ontology-vocab-audit
description: Audits external vocabulary usage — extracts all external namespaces, checks URI resolution, detects owl:imports, and flags local terms that reinvent standard vocabularies (FOAF, DC, SKOS, RDFS, OWL, etc.). Uses rdflib + requests.
license: MIT
compatibility: Requires python3, rdflib, requests
---

# Ontology Vocabulary Audit

Audits external vocabulary usage and dependency health. Extracts all external
namespaces, checks whether they resolve, detects `owl:imports`, and flags local
terms that duplicate well-known standard vocabulary terms.

**Single script:** `scripts/vocab_audit.py`

## What It Detects

| Issue | Example |
|-------|---------|
| Broken namespace URIs | `http://example.com/old-vocab#` returns 404 |
| Unresolvable owl:imports | Imported ontology no longer available |
| Vocabulary reinvention | Local `:label` instead of `rdfs:label`, local `:prefLabel` instead of `skos:prefLabel` |
| Unknown namespaces | Namespaces without a known standard vocabulary mapping |

## Setup

```bash
cd <your-ontology-repo>
python3 -m venv .venv
source .venv/bin/activate

pip install rdflib requests
```

## Usage

```bash
python scripts/vocab_audit.py . -o VOCAB_REPORT.md

# Skip HTTP checks (offline mode)
python scripts/vocab_audit.py . --no-check -o report.md

# Longer timeout for slow servers
python scripts/vocab_audit.py . --timeout 30
```

## Important Rules

1. **Namespace resolution ≠ vocabulary availability.** A 200 OK does not mean
   the ontology is well-designed. It only means the URI is reachable.

2. **Reinvention is sometimes intentional.** If your `:label` property has
   different semantics than `rdfs:label`, it's fine. The script flags it for review,
   not as an error.

3. **owl:imports may point to local files.** If an import URI is a relative path
   that resolves within the repo, it will show as broken if the file isn't found.
