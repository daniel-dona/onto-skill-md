#!/usr/bin/env bash
# report.sh — Generate a Markdown typo report for an ontology repo
# Usage: ./report.sh <repo-path>

set -euo pipefail
REPO="${1:?Usage: report.sh <repo-path>}"

echo "# Typo Report: $(basename "$REPO")"
echo
echo "Generated on $(date -I) by ontology-typo-audit skill"
echo

echo "| # | Fichero | Typo | Corrección |"
echo "|---|---------|------|-----------|"

# Run codespell (requires config at /tmp/codespell_config)
N=0
if [[ -f /tmp/codespell_config ]] && command -v codespell &>/dev/null; then
  while IFS=: read -r file line typo; do
    N=$((N+1))
    echo "| $N | \`$file:$line\` | $typo | (review needed) |"
  done < <(cd "$REPO" && codespell --config /tmp/codespell_config . 2>/dev/null \
    | grep -oP '^[^:]+:\d+: (\S+)' \
    | sed 's/:\([0-9]*\): /\1:/')
fi

echo
echo "---"
echo "_This report is auto-generated. Review each entry for false positives before applying fixes._"
