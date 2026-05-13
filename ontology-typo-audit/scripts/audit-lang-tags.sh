#!/usr/bin/env bash
# audit-lang-tags.sh — Check for inverted or wrong @en/@es language tags
# Usage: ./audit-lang-tags.sh <repo-path>

set -euo pipefail
REPO="${1:?Usage: audit-lang-tags.sh <repo-path>}"

echo "# Language Tag Audit: $REPO"
echo

echo "## Potential @en/@es tag swaps (Spanish text tagged @en or vice versa)"
echo

python3 - << 'PYEOF'
import os, re

repo = os.environ.get("REPO_ARG", ".")

# Common Spanish words that should never appear in @en text
spanish_words = re.compile(
    r'\b(de|del|la|el|en|es|un|una|los|las|por|para|con|sin|sobre|entre|'
    r'tipo|servicio|actividad|centro|equipamiento|infraestructura|'
    r'propiedad|observación|medición|tráfico|rol|violación)\b',
    re.IGNORECASE
)

# Common English words that should never appear in @es text
english_words = re.compile(
    r'\b(the|of|and|or|for|in|on|with|from|by|to|is|are|type|service|'
    r'activity|center|facility|infrastructure|property|observation|'
    r'measurement|traffic|role|violation)\b',
    re.IGNORECASE
)

for root, dirs, files in os.walk(repo):
    if ".git" in root:
        continue
    for fname in files:
        if not fname.endswith((".ttl", ".owl")):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                # Find @en tagged strings with Spanish content
                for m in re.finditer(r'"([^"]+)"@en', line):
                    text = m.group(1)
                    if len(text) > 10 and spanish_words.search(text):
                        spanish_matches = spanish_words.findall(text)
                        # Exclude proper names and abbreviations
                        if len(spanish_matches) >= 2:
                            print(f"  {fpath}:{i}: @en but Spanish? \"{text[:80]}\"")

                # Find @es tagged strings with English content
                for m in re.finditer(r'"([^"]+)"@es', line):
                    text = m.group(1)
                    if len(text) > 10 and english_words.search(text):
                        english_matches = english_words.findall(text)
                        if len(english_matches) >= 2:
                            print(f"  {fpath}:{i}: @es but English? \"{text[:80]}\"")
PYEOF
