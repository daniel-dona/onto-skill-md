---
name: ontology-oops-scan
description: Provides a script and instructions to validate OWL ontologies via the OOPS! REST API, detecting 40+ design pitfalls with severity levels. Use before ontology releases or in CI to catch modelling mistakes early.
license: MIT
compatibility: Requires bash, python3, rdflib, requests. OOPS! API is public and free (no key required).
---

# Ontology OOPS! Scan

Validate an ontology repository against the [OOPS! (OntOlogy Pitfall Scanner!)](https://oops.linkeddata.es/) REST API.
OOPS! analyses OWL ontologies for **41 common pitfalls** grouped by severity
(Critical / Important / Minor) and returns structured results with the
affected elements.

## What OOPS! Detects

The full catalogue is at <https://oops.linkeddata.es/catalogue.jsp>. Key pitfalls:

| Code | Name | Severity |
|------|------|----------|
| P02 | Polysemous elements | Important |
| P04 | Creating unconnected ontology elements | Minor |
| P05 | Defining wrong equivalence relationships | Important |
| P06 | Inverse not declared | Important |
| P07 | Equivalent properties not declared | Important |
| P08 | Missing annotations | Minor |
| P10 | Missing disjointness | Important |
| P11 | Missing domain or range | Important |
| P13 | Inverse relationships not explicitly declared | Minor |
| P21 | Defining multiple domains/ranges | Critical |
| P22 | Using different naming conventions | Minor |
| P24 | Using RDF in an OWL ontology | Important |
| P36 | URI contains file extension | Minor |
| P37 | Ontology not available | Minor |
| P40 | Namespace hijacking | Important |

## Setup

Create a virtual environment and install dependencies:

```bash
cd <your-ontology-repo>
python3 -m venv .venv
source .venv/bin/activate

pip install rdflib requests
```
> **After finishing:** deactivate the venv and remove it:
> ```bash
> deactivate && rm -rf .venv
> ```
> Skip this if the user asks to keep the environment.

> **Tip:** If you also use the `ontology-typo-audit` skill, install all deps at once:
> ```bash
> pip install rdflib language-tool-python requests
> ```

## Workflow

### 1. Scan the entire repo

The script uses `rdflib` to discover and merge **all** RDF files
(`.ttl`, `.owl`, `.rdf`, `.nt`, `.jsonld`, `.n3`, `.trig`, `.nq`) in the
repository, serializes them as RDF/XML, and submits the combined ontology to
the OOPS! REST API.

```bash
python scripts/oops_scan.py . -o OOPS_REPORT.md
```

### 2. Scan only specific pitfalls

If you only care about certain pitfalls, pass their codes:

```bash
python scripts/oops_scan.py . --pitfalls P04,P08,P10,P13
```

### 3. JSON output

For programmatic consumption or CI pipelines:

```bash
python scripts/oops_scan.py . -o oops_report.json --format json
```

### 4. Dry run (test serialization without hitting the API)

```bash
python scripts/oops_scan.py . --dry-run
# Saves the merged RDF/XML to dry_run_ontology.owl for inspection
```

### 5. Large ontologies — increase timeout

The OOPS! server can take a while on large ontologies (> 500 triples):

```bash
python scripts/oops_scan.py . --timeout 300
```

## How It Works

```
┌─────────────────┐       ┌──────────────┐       ┌──────────────────┐
│  RDF files in    │  rdflib│  Single RDF/  │  POST  │  OOPS! REST API   │
│  repo (.ttl,    │ ─────► │  XML graph   │ ─────► │  oops.linkeddata.es│
│  .owl, .rdf…)   │ merge │  (merged)     │ XML    │  (pitfall analysis)│
└─────────────────┘       └──────────────┘       └──────────────────┘
                                                          │
                                                          ▼
                                                   ┌──────────────┐
                                                   │  Parsed report │
                                                   │  (.md / .json) │
                                                   └──────────────┘
```

1. **`rdflib`** discovers and parses all RDF files → merges into one `Graph`
2. The graph is serialized as **RDF/XML** (the format OOPS! requires)
3. An **XML payload** is built: `<OOPSRequest><OntologyContent><![CDATA[…]]></OntologyContent></OOPSRequest>`
4. POSTed to `https://oops.linkeddata.es/rest` (Content-Type: `application/xml`)
5. The **XML response** is parsed into structured pitfalls, warnings, and suggestions
6. Rendered as **Markdown** or **JSON**


## Output Files

**Never write files into the repository without permission.** Before generating
any report or output file, ask the user where to save it (e.g. `-o ../report.md`
or an absolute path outside the repo). The default output path in script
examples is only a suggestion — always confirm with the user first.

## Important Rules

1. **The ontology must be reachable or self-contained.** OOPS! can also scan
   via URI, but this script sends the full RDF content (no external deps).
   If your ontology imports others via `owl:imports`, make sure those files
   are also in the repo so rdflib can merge them.

2. **P21 (multiple domains/ranges) is Critical.** When OOPS! flags P21, it
   means a property has multiple `rdfs:domain` or `rdfs:range` axioms, which
   in OWL-DL is interpreted as **intersection** (not union). This is almost
   always a modelling error — fix it immediately.

3. **P08 (missing annotations) is Minor but matters.** Every class and
   property should have at least `rdfs:label` and `rdfs:comment` (or
   `skos:prefLabel` / `skos:definition` for SKOS concepts).

4. **P10 (missing disjointness) is often a false positive.** Not every pair
   of classes needs a `owl:disjointWith` axiom. Use judgement — add it only
   where overlap would cause reasoning errors.

5. **OOPS! is a heuristic scanner, not a validator.** It detects _pitfalls_
   (common modelling mistakes), not OWL syntax errors. For SHACL/OWL
   constraint validation, use a separate tool (e.g. `pySHACL`, `Pellet`).

6. **OOPS! server may be slow.** The public instance at `oops.linkeddata.es`
   can take 30–120 seconds for large ontologies. Use `--timeout` accordingly.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `HTTP 500` from OOPS! | The RDF/XML may have encoding issues. Try `--dry-run` and inspect the serialized file. |
| Timeout | Use `--timeout 300` or split the ontology into smaller files. |
| Empty response | The merged graph may be empty — check that your RDF files are in the repo root (not in an excluded directory). |
| `requests.ConnectionError` | The OOPS! server may be down. Check <https://oops.linkeddata.es/> in a browser. |

## References

- **OOPS! website:** <https://oops.linkeddata.es/>
- **API docs:** <https://oops.linkeddata.es/webservice.html>
- **Pitfall catalogue:** <https://oops.linkeddata.es/catalogue.jsp>
- **Paper:** Poveda-Villalón, M., Gómez-Pérez, A., & Suárez-Figueroa, M.C. (2014). *OOPS! (OntOlogy Pitfall Scanner!): An On-line Tool for Ontology Evaluation.* International Journal on Semantic Web and Information Systems, 10(2), 7-34. DOI: [10.4018/ijswis.2014040102](https://doi.org/10.4018/ijswis.2014040102)
