#!/usr/bin/env bash
# audit-skos-refs.sh — Find skos:inScheme references to undefined ConceptSchemes
# Usage: ./audit-skos-refs.sh <repo-path>

set -euo pipefail
REPO="${1:?Usage: audit-skos-refs.sh <repo-path>}"

echo "# SKOS Scheme Reference Audit: $REPO"
echo

echo "## skos:inScheme references to undefined ConceptSchemes"
echo

python3 - << 'PYEOF'
import os, re

repo = os.environ.get("REPO_ARG", ".")

# Collect all defined ConceptSchemes
schemes = set()
in_scheme_refs = {}  # scheme_uri -> [file:line]

for root, dirs, files in os.walk(repo):
    if ".git" in root:
        continue
    for fname in files:
        if not fname.endswith((".ttl", ".owl")):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, encoding="utf-8") as f:
            content = f.read()

        # Find ConceptScheme definitions
        for m in re.finditer(r'(\w+):(\w+)\s+a\s+skos:ConceptScheme', content):
            prefix, local = m.group(1), m.group(2)
            schemes.add(f"{prefix}:{local}")

        # Find skos:inScheme references
        for i, line in enumerate(content.split("\n"), 1):
            m = re.search(r'skos:inScheme\s+(\w+:\w+)', line)
            if m:
                ref = m.group(1)
                if ref not in in_scheme_refs:
                    in_scheme_refs[ref] = []
                in_scheme_refs[ref].append(f"{fpath}:{i}")

# Report undefined references
for ref, locations in sorted(in_scheme_refs.items()):
    if ref not in schemes:
        print(f"  UNDEFINED: {ref}")
        for loc in locations:
            print(f"    {loc}")
        print()
PYEOF
