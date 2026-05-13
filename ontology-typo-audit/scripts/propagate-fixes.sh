#!/usr/bin/env bash
# propagate-fixes.sh — Apply typo patterns from source to auto-generated docs
# Usage: ./propagate-fixes.sh <repo-path> <old1> <new1> [<old2> <new2> ...]
#   Or:  ./propagate-fixes.sh <repo-path> --from-diff   (auto-detect from git diff)
#
# Example:
#   ./propagate-fixes.sh . meassuring measuring "Trafic Monitoring" "Traffic Monitoring"

set -euo pipefail
REPO="${1:?Usage: propagate-fixes.sh <repo-path> [--from-diff | old1 new1 ...]}"
shift

cd "$REPO"

if [[ "$1" == "--from-diff" ]]; then
  # Extract replacement pairs from the current git diff in source files
  echo "Auto-detecting replacements from git diff..."
  PAIRS=()
  while IFS= read -r line; do
    # Parse diff hunk: -<old and +<new
    if [[ "$line" =~ ^-([^+-].*) ]] && [[ "$line" != "^---" ]]; then
      OLD="${BASH_REMATCH[1]}"
      # Read next line for the replacement
      read -r nextline
      if [[ "$nextline" =~ ^\+([^+].*) ]]; then
        NEW="${BASH_REMATCH[1]}"
        # Only add if the change looks like a word replacement (not full line rewrite)
        if [[ ${#OLD} -lt 80 ]] && [[ ${#NEW} -lt 80 ]]; then
          PAIRS+=("$OLD" "$NEW")
          echo "  Detected: '$OLD' -> '$NEW'"
        fi
      fi
    fi
  done < <(git diff -- ontology/ kos/ examples/ documentation/resources/ | grep '^[+-]')
  set -- "${PAIRS[@]}"
fi

if [[ $# -eq 0 ]]; then
  echo "No replacements to propagate."
  exit 0
fi

if [[ $(( $# % 2 )) -ne 0 ]]; then
  echo "Error: replacements must come in pairs (old new)"
  exit 1
fi

echo
echo "Propagating fixes to documentation/ ..."

python3 - << PYEOF
import os, sys

repo = "."
pairs = sys.argv[1:]

# Group into (old, new) pairs
replacements = []
for i in range(0, len(pairs), 2):
    replacements.append((pairs[i], pairs[i+1]))

docs_dir = os.path.join(repo, "documentation")
fixed_files = []

for root, dirs, files in os.walk(docs_dir):
    for fname in files:
        if not fname.endswith(('.ttl', '.owl', '.rdf', '.nt', '.jsonld', '.html', '.css')):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, encoding='utf-8') as f:
            content = f.read()
        original = content
        for old, new in replacements:
            content = content.replace(old, new)
        if content != original:
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(content)
            fixed_files.append(fpath)

for f in fixed_files:
    print(f"  Fixed: {f}")
print(f"\nTotal documentation/ files fixed: {len(fixed_files)}")
PYEOF "$@"
