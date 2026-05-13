# Ontology Skill Examples

Test ontologies for validating each skill. Every `.ttl` file is
self-contained and exhibits the issues the corresponding skill should detect.

## Usage

To validate a skill against its test data, run the skill script pointing
at the example directory:

```bash
cd <onto-skill-md>

# Grammar & spelling
python ontology-typo-audit/scripts/grammar_audit.py examples/typos

# SKOS structural integrity
python ontology-skos-audit/scripts/skos_audit.py examples/skos

# OOPS! pitfall scan
python ontology-oops-scan/scripts/oops_scan.py examples/oops

# Language coverage
python ontology-lang-coverage/scripts/lang_coverage.py examples/lang-coverage --lang es en

# SHACL validation
python ontology-shacl-validate/scripts/shacl_validate.py examples/shacl

# Vocabulary audit
python ontology-vocab-audit/scripts/vocab_audit.py examples/vocab

# Reasoner consistency
python ontology-reasoner-check/scripts/reasoner_check.py examples/reasoner

# Syntax validation (first gate — run before everything else)
python ontology-syntax-validate/scripts/syntax_validate.py examples/syntax
```

## Expected Issues per Example

| Example | Skill | Expected Findings |
|---------|-------|-------------------|
| `typos/test.ttl` | typo-audit | 3 spelling/accent errors, 1 lang tag mismatch |
| `skos/test.ttl` | skos-audit | 1 orphan concept, 1 empty scheme, 2 duplicate labels, 1 notation mismatch, 1 missing prefLabel |
| `oops/test.ttl` | oops-scan | P08 (missing annotations), P10 (missing disjointness), P11 (missing domain/range), P13 (no inverse) |
| `lang-coverage/test.ttl` | lang-coverage | 2 resources missing translations, 1 extra language |
| `shacl/test.ttl` | shacl-validate | 2 violations (missing name, wrong datatype, short postal code) |
| `vocab/test.ttl` | vocab-audit | 1 broken import, 2 reinventions (:label, :sameAs), 1 unresolvable namespace |
| `reasoner/test.ttl` | reasoner-check | 1 unsatisfiable class (:SquareCircle), 1 equivalence (:Person ≡ :Human) |
| `syntax/broken.ttl` | syntax-validate | 1 file with parse errors ❌ |
| `syntax/valid.ttl` | syntax-validate | 1 file OK, 0 errors ✅ |
