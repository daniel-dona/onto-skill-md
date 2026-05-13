---
name: ontology-full-audit
description: Provides instructions to orchestrate a complete ontology evaluation across 7 dimensions (syntax, text, translations, SKOS, OWL design, data quality, logic). Use before any ontology release to produce a comprehensive audit report with prioritized recommendations.
license: MIT
---

# Ontology Full Audit

A complete audit of an ontology repository. This skill does **not** have its
own scripts — it is an **orchestrator** that runs the other 7 skills in
sequence and combines their results into a unified report.

> **⚠️ Read and follow each skill's own `SKILL.md` before running it.**
> Each skill has its own setup (venv, dependencies, CLI flags) and important
> rules. This document only tells you *what order* to run them and *what to
> report* — the *how* is in each skill's documentation.

---

## Prerequisites

**This skill has no dependencies of its own.** Each sub-skill manages its own
environment. Before starting the audit:

1. **Read the `SKILL.md` of every skill listed below.**
2. **Set up each skill's environment as described in its own Setup section.**
   Do **not** guess or assume — every skill documents exactly what it needs.
3. **Run the dimensions in order.** Syntax validation must pass before anything
   else, because files that don't parse cannot be audited.

---

## Audit Dimensions (run in this order)

### 1. Syntax — `ontology-syntax-validate`

**Every RDF file must parse.**

**👉 Read `ontology-syntax-validate/SKILL.md`** for setup, usage, and the
`--format report` flag that produces standardized JSON output.

If any file fails to parse, **stop here**. Nothing else can be checked until
all files parse cleanly.

- ❌ Any parse error → block. Fix syntax before continuing.

---

### 2. Text Quality — `ontology-typo-audit`

**Every string literal must have correct grammar and spelling in its declared
language.**

**👉 Read `ontology-typo-audit/SKILL.md`** for setup (requires
`language-tool-python`), supported languages, `--lang` filtering, and
important caveats about false positives on technical terms.

- ⚠️ Grammar/spelling errors → review suggestions; short labels and proper
  names may be false positives.

---

### 3. Translation Completeness — `ontology-lang-coverage`

**Every labelled resource must have labels in every expected project
language.**

**👉 Read `ontology-lang-coverage/SKILL.md`** for setup, the `--lang` flag
(required — do not auto-detect), and what counts as coverage.

- ⚠️ Missing translation → add the label or document the gap.
- ℹ️ Extra language → may be accidental; verify.

---

### 4. SKOS Integrity — `ontology-skos-audit`

**If SKOS concept schemes are present, they must be structurally sound.**

**👉 Read `ontology-skos-audit/SKILL.md`** for setup, the full list of 8
checks with severities, and rules about `prefLabel` uniqueness and
notation conventions.

- ❌ Missing `prefLabel`, undefined scheme reference, duplicate `prefLabel`
  within a scheme → fix.
- ⚠️ Orphan concept (no `inScheme`), empty scheme, notation mismatch → review.

---

### 5. OWL Design Pitfalls — `ontology-oops-scan`

**The ontology must be free of common modelling mistakes.**

**👉 Read `ontology-oops-scan/SKILL.md`** for setup (requires `requests`),
the `--pitfalls` filter, `--timeout` for large ontologies, and `--dry-run`
for testing serialization before hitting the API.

- ❌ Multiple domains/ranges on a property (P21) → fix immediately.
- ⚠️ Missing disjointness, domain/range, inverse, unconnected elements →
  fix where applicable; some may be intentional.
- ℹ️ Missing annotations, naming inconsistencies → improve progressively.

---

### 6. Data Validation — `ontology-shacl-validate`

**If instance data exists with SHACL shapes, instances must conform.**

**👉 Read `ontology-shacl-validate/SKILL.md`** for setup (requires
`pyshacl`), how to provide custom shapes with `--shapes`, and what the
auto-generated shapes cover (minimal — cardinality only).

- ❌ Constraint violation → fix the data or adjust the shape.
- ℹ️ If no instances or no shapes exist, this dimension is trivially satisfied.

---

### 7. Logical Consistency — `ontology-reasoner-check`

**The ontology must not contain logical contradictions.**

**👉 Read `ontology-reasoner-check/SKILL.md`** for setup (requires
`owlready2`), the `--only-file` option, and performance notes for large
ontologies.

- ❌ Unsatisfiable classes or global inconsistency → block. Fix contradictory
  axioms (usually disjointness + subclassing, conflicting domain/range, or
  inconsistent cardinalities).
- ℹ️ Inferred equivalences → review; may be intentional synonyms or
  modelling redundancy.

---

## Reporting

After completing all dimensions, produce a single report with:

1. **Summary table** — one row per dimension, with pass/fail status and issue
   counts split by severity.

2. **Detailed findings** — per dimension, list each issue with file, element,
   severity, description, and suggestion. Use the `--format report` JSON
   output from each skill — all 7 skills produce the same standardized schema.

3. **Recommendations** — prioritised list of actions: errors first, then
   warnings, then info items.

## Output Files

**Never write files into the repository without permission.** Before generating
any report or output file, ask the user where to save it (e.g. `-o ../report.md`
or an absolute path outside the repo). The default output path in script
examples is only a suggestion — always confirm with the user first.
