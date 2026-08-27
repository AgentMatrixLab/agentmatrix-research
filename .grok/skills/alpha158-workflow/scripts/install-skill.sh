#!/usr/bin/env bash
# Install alpha158-workflow skill to ~/.grok/skills for global Grok discovery.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
DEST="${HOME}/.grok/skills/alpha158-workflow"

mkdir -p "${HOME}/.grok/skills"
rm -rf "$DEST"
cp -R "$SKILL_DIR" "$DEST"

echo "Installed alpha158-workflow skill to:"
echo "  $DEST"
echo ""
echo "Verify with: grok inspect"
echo "Invoke with: /alpha158-workflow"