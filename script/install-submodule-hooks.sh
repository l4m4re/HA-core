#!/usr/bin/env bash
# Install git hooks that capture submodule work as patches for later application.
set -euo pipefail

ROOT_DIR="$(realpath "$(dirname "$0")/..")"
HOOK_SOURCE="$ROOT_DIR/script/git-hooks/pre-commit"
HOOK_DEST="$ROOT_DIR/.git/hooks/pre-commit"

if [[ ! -d "$ROOT_DIR/.git" ]]; then
  echo "Skipping hook installation; .git directory not found." >&2
  exit 0
fi

mkdir -p "$(dirname "$HOOK_DEST")"
cp "$HOOK_SOURCE" "$HOOK_DEST"
chmod +x "$HOOK_DEST"

echo "Installed pre-commit hook to capture submodule patches." >&2
