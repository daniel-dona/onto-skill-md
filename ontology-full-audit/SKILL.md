---
name: ontology-full-audit
description: Coordinator skill that runs a complete ontology evaluation by orchestrating the other audit skills in a logical order — from syntax to logic. Produces a consolidated report of all findings.
license: MIT
compatibility: Requires all individual skill dependencies installed
---

# Ontology Full Audit

Orchestrates a complete evaluation of an ontology repository by running each
audit skill in order — from the most fundamental checks (syntax) to the most
advanced (logical consistency).

**No new scripts.** This skill instructs the agent to run the existing tools
in a planned sequence and produce a unified report.

Each audit skill supports `--format report` which outputs a **standardized JSON
schema** — same structure across all skills, easy to merge programmatically.

## Prerequisites

One venv with all dependencies:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install rdflib language-tool-python requests pyshacl owlready2 pyoxigraph
```

## Audit Sequence

Run in this order. Each step gates the next — if a step fails hard, fix it
before continuing.

### Phase 1 — Fundamentals (must pass)

**1. Syntax validation.** If files don't parse, nothing else works.

```bash
python ontology-syntax-validate/scripts/syntax_validate.py <repo> -o 01_syntax.md
```

> ❌ **Gate:** any parse error → fix immediately, re-run, then continue.

### Phase 2 — Text quality

**2. Grammar and spelling.** Every string literal in its declared language.

```bash
python ontology-typo-audit/scripts/grammar_audit.py <repo> -o 02_typos.md
```

**3. Language coverage.** Are labels present in all project languages?

```bash
python ontology-lang-coverage/scripts/lang_coverage.py <repo> --lang <L1> <L2> ... -o 03_coverage.md
```

> Specify your project's target languages explicitly with `--lang`.

### Phase 3 — Structure

**4. SKOS integrity.** If the repo contains SKOS concept schemes.

```bash
python ontology-skos-audit/scripts/skos_audit.py <repo> -o 04_skos.md
```

**5. OWL pitfalls.** Design-level issues via OOPS! API (needs internet).

```bash
python ontology-oops-scan/scripts/oops_scan.py <repo> -o 05_oops.md
```

> ⏱️ Can take 30–120s. Skip with `--dry-run` to test serialization first.

### Phase 4 — Data and logic

**6. SHACL validation.** Instance data against shapes (if instances exist).

```bash
python ontology-shacl-validate/scripts/shacl_validate.py <repo> -o 06_shacl.md
```

**7. Reasoner consistency.** Unsatisfiable classes, global inconsistency.

```bash
python ontology-reasoner-check/scripts/reasoner_check.py <repo> -o 07_reasoner.md
```

> ❌ **Gate:** unsatisfiable classes = contradictory axioms. Fix before release.

### Phase 5 — Deployment (optional)

**8. SPARQL endpoint.** Serve the ontology for interactive exploration.

```bash
python ontology-sparql-endpoint/scripts/deploy_endpoint.py <repo>
```

## Consolidated Report

After running all phases, aggregate the Markdown reports:

```bash
cat 01_syntax.md 02_typos.md 03_coverage.md 04_skos.md 05_oops.md 06_shacl.md 07_reasoner.md > FULL_AUDIT.md
```

Or generate a summary table:

```bash
echo "# Full Audit Summary" > SUMMARY.md
echo "" >> SUMMARY.md
echo "| Phase | Skill | Status | Issues |" >> SUMMARY.md
echo "|-------|-------|--------|--------|" >> SUMMARY.md

for f in 01_syntax.md 02_typos.md 03_coverage.md 04_skos.md 05_oops.md 06_shacl.md 07_reasoner.md; do
  if grep -q "No .* found\|conforms\|consistent.*✅\|passed successfully\|All resources have" "$f" 2>/dev/null; then
    echo "| $(head -1 "$f" | sed 's/# //') | ✅ | 0 |" >> SUMMARY.md
  else
    echo "| $(head -1 "$f" | sed 's/# //') | ❌ | see report |" >> SUMMARY.md
  fi
done
```

## Decision Matrix

| Finding | Action |
|---------|--------|
| Syntax errors (01) | **Block release.** Fix immediately. |
| Grammar errors (02) | Fix before release. Review suggestions — some may be false positives. |
| Missing translations (03) | Add labels. If intentional, note in `--lang` list and re-run. |
| SKOS errors (04) | Fix `inScheme`, `prefLabel`, broken links. Duplicates may be intentional. |
| Critical OOPS pitfalls (05) | Fix P21 (multiple domains), P04 (unconnected). Minor pitfalls are advisory. |
| SHACL violations (06) | Fix data or relax shapes. If no instances, skip this phase. |
| Unsatisfiable classes (07) | **Block release.** Contradictory axioms break reasoning. |

## One-liner (when all deps are ready)

```bash
python ontology-syntax-validate/scripts/syntax_validate.py . -o 01_syntax.md && \
python ontology-typo-audit/scripts/grammar_audit.py . -o 02_typos.md && \
python ontology-lang-coverage/scripts/lang_coverage.py . -o 03_coverage.md && \
python ontology-skos-audit/scripts/skos_audit.py . -o 04_skos.md && \
python ontology-oops-scan/scripts/oops_scan.py . -o 05_oops.md && \
python ontology-shacl-validate/scripts/shacl_validate.py . -o 06_shacl.md && \
python ontology-reasoner-check/scripts/reasoner_check.py . -o 07_reasoner.md && \
echo "Full audit complete. See FULL_AUDIT.md"
```

## Programmatic Consumption

Every skill supports `--format report` which outputs a common JSON schema:

```json
{
  "skill": "typo-audit",
  "summary": {"errors": 0, "warnings": 5, "info": 0},
  "issues": [
    {"file": "onto.ttl", "element": ":StreetLamp",
     "message": "Possible spelling mistake", "severity": "warning",
     "check": "MORFOLOGIK_RULE_ES", "suggestion": "Lámpara"}
  ]
}
```

This makes it easy to merge reports programmatically:

```python
import json, glob
all_issues = []
for f in glob.glob("*_report.json"):
    report = json.load(open(f))
    all_issues.extend(report["issues"])

# Sort by severity
all_issues.sort(key=lambda i: {"error": 0, "warning": 1, "info": 2}[i["severity"]])

print(f"Total issues: {len(all_issues)}")
for issue in all_issues:
    print(f"[{issue['severity']}] {issue['skill']}: {issue['message']}")
```
