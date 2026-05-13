---
name: ontology-full-audit
description: Provides instructions to orchestrate a complete ontology evaluation across 7 dimensions (syntax, text, translations, SKOS, OWL design, data quality, logic). Use before any ontology release to produce a comprehensive audit report with prioritized recommendations.
license: MIT
---

# Ontology Full Audit

A complete audit of an ontology repository. Each dimension must be checked in
order, and findings reported with severity: ❌ error (blocks release),
⚠️ warning (should fix), ℹ️ info (advisory).

## Prerequisites

One venv with all dependencies:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install rdflib language-tool-python requests pyshacl owlready2 pyoxigraph
```
> **After finishing:** deactivate the venv and remove it:
> ```bash
> deactivate && rm -rf .venv
> ```
> Skip this if the user asks to keep the environment.

Rapper for syntax validation is a system tool:

```bash
sudo apt install raptor2-utils
```

---

## Audit Dimensions

### 1. Syntax — `ontology-syntax-validate`

**Every RDF file must parse.**

Walk the repository. For every `.ttl`, `.owl`, `.rdf`, `.rdfs`, `.nt`,
`.jsonld`, `.n3`, `.trig`, `.nq` file, attempt to parse it as RDF. Any file
that fails to parse is a syntax error — report file path, line, and the
parser's error message.

- ❌ Any parse error → block. Nothing else can be checked until all files parse.

## 2. Text Quality — `ontology-typo-audit`

**Every string literal must have correct grammar and spelling in its declared
language.**

Extract every string literal with a language tag (`rdfs:label`, `rdfs:comment`,
`skos:prefLabel`, `skos:altLabel`, `skos:definition`, and any other annotation
property). For each literal, check grammar and spelling in the language
indicated by its tag. Report the text, the error, and a suggested correction.

The set of languages checked is whatever is present in the data — no
assumptions about which languages exist. If a literal tagged `@X` produces
many errors in language X but few in language Y, flag a possible lang-tag
mismatch (text may be tagged with the wrong language).

- ⚠️ Grammar/spelling errors → review suggestions; short labels and proper names
  may be false positives.

## 3. Translation Completeness — `ontology-lang-coverage`

**Every labelled resource must have labels in every expected project
language.**

The expected languages must be declared explicitly (not guessed). For each
resource carrying labels, check that it has at least one label in every
expected language. Also flag labels in languages outside the expected set.

- ⚠️ Missing translation → add the label or document the gap.
- ℹ️ Extra language → may be accidental; verify.

## 4. SKOS Integrity — `ontology-skos-audit`

**If SKOS concept schemes are present, they must be structurally sound.**

Check that: every `skos:Concept` has a `skos:inScheme` pointing to a defined
`skos:ConceptScheme`; every scheme has at least one concept; `skos:prefLabel`
is present and unique per scheme+language; `skos:notation` is consistent with
URI naming; `skos:broader`/`skos:narrower` links point to existing concepts.

- ❌ Missing `prefLabel`, undefined scheme reference, duplicate `prefLabel`
  within a scheme → fix.
- ⚠️ Orphan concept (no `inScheme`), empty scheme, notation mismatch → review.

## 5. OWL Design Pitfalls — `ontology-oops-scan`

**The ontology must be free of common modelling mistakes.**

Check for: missing human-readable annotations on classes and properties;
classes that should be disjoint but aren't; properties missing domain or range;
properties with multiple domains/ranges (interpreted as intersection in OWL,
usually a bug); properties missing their inverse declaration; naming convention
inconsistencies across the ontology.

- ❌ Multiple domains/ranges on a property → fix immediately (OWL intersection
  semantics are almost never intended).
- ⚠️ Missing disjointness, missing domain/range, missing inverse, unconnected
  elements → fix where applicable; some may be intentional.
- ℹ️ Missing annotations, naming inconsistencies → improve progressively.

## 6. Data Validation — `ontology-shacl-validate`

**If instance data exists with SHACL shapes, instances must conform.**

If shapes are defined (`sh:NodeShape`, `sh:PropertyShape`), validate every
instance against its target shape. If no shapes exist but the schema implies
constraints (cardinality, datatype), check instances against those constraints.

- ❌ Constraint violation → fix the data or adjust the shape.
- ℹ️ If no instances or no shapes exist, this dimension is trivially satisfied.

## 7. Logical Consistency — `ontology-reasoner-check`

**The ontology must not contain logical contradictions.**

Using an OWL 2 DL reasoner, check for: unsatisfiable classes (can never have
instances under current axioms); non-trivial inferred equivalences (two
different classes that the reasoner proves are the same); global inconsistency
(every class is unsatisfiable — the whole ontology is contradictory).

- ❌ Unsatisfiable classes or global inconsistency → block. Find and fix the
  contradictory axioms (usually disjointness combined with subclassing,
  conflicting domain/range, or inconsistent cardinalities).
- ℹ️ Inferred equivalences → review; may be intentional synonyms or modelling
  redundancy.

## Reporting

After completing all dimensions, produce a single report with:

1. **Summary table** — one row per dimension, with pass/fail status and issue
   counts split by severity.

2. **Detailed findings** — per dimension, list each issue with file, element,
   severity, description, and suggestion.

3. **Recommendations** — prioritised list of actions: errors first, then
   warnings, then info items.

## Output Files

**Never write files into the repository without permission.** Before generating
any report or output file, ask the user where to save it (e.g. `-o ../report.md`
or an absolute path outside the repo). The default output path in script
examples is only a suggestion — always confirm with the user first.

