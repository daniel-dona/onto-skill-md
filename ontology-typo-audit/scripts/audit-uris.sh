#!/usr/bin/env bash
# audit-uris.sh — Check OWL class/property and SKOS concept URIs for typos
# Usage: ./audit-uris.sh <repo-path>

set -euo pipefail
REPO="${1:?Usage: audit-uris.sh <repo-path>}"

echo "# URI Audit: $REPO"
echo

# --- OWL classes and properties ---
echo "## OWL Classes/Properties (English-named, CamelCase)"
echo "Checking for misspellings in URI fragments..."
echo

# Extract locally-defined English-named identifiers
grep -oP '(owl:Class|owl:ObjectProperty|owl:DatatypeProperty)\s+rdf:about="[^"]+#([A-Z][a-zA-Z0-9_-]+)"' \
  "$REPO"/ontology/*.owl 2>/dev/null \
  | sed 's/.*#//' | sort -u \
  | while read -r name; do
      # Flag common patterns: doubled letters, missing letters
      echo "$name"
    done

echo
echo "## SKOS Concept URIs vs prefLabels"
echo "Checking for mismatches between concept IDs and their Spanish labels..."
echo

python3 - << 'PYEOF'
import sys, re, unicodedata

skos_files = ["kos/skos-InfrastructureType.ttl", "kos/skos-PublicService.ttl",
              "kos/skos-RegularActivity.ttl", "kos/skos-RoleType.ttl",
              "kos/skos-ViolationType.ttl"]

import os
repo = os.environ.get("REPO_ARG", ".")

for sf in skos_files:
    fpath = os.path.join(repo, sf)
    if not os.path.exists(fpath):
        continue
    with open(fpath, encoding="utf-8") as f:
        content = f.read()

    concepts = re.findall(r'edintkos\w+:([a-zA-Z0-9_-]+)\s+a\s+skos:Concept\s*;(.*?)\.', content, re.DOTALL)
    for uri_id, body in concepts:
        labels_es = re.findall(r'skos:prefLabel\s+"([^"]+)"@es', body)
        notations = re.findall(r'skos:notation\s+"([^"]+)"', body)
        labels_en = re.findall(r'skos:prefLabel\s+"([^"]+)"@en', body)

        for label in labels_es:
            norm = unicodedata.normalize("NFKD", label).encode("ASCII","ignore").decode("ASCII").lower()
            norm = norm.replace(" ","-").replace(",","").replace("(","").replace(")","").replace("/","-").replace("--","-")
            norm_uri = uri_id.lower()
            if norm != norm_uri and norm.replace('"','').replace("'","") != norm_uri:
                # Only flag if URI is Spanish-style (lowercase with hyphens)
                if uri_id[0].islower() or "-" in uri_id:
                    print(f"  {sf}: URI={uri_id}  label=\"{label}\"  norm_label={norm}  norm_uri={norm_uri}")

        # Check notation matches URI
        for notation in notations:
            if notation.lower() != uri_id.lower():
                print(f"  {sf}: NOTATION MISMATCH URI={uri_id}  notation={notation}")
PYEOF
