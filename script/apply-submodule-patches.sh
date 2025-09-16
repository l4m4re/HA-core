#!/usr/bin/env bash
# Apply stored submodule patches back into the respective submodule working trees.
set -euo pipefail

ROOT_DIR="$(realpath "$(dirname "$0")/..")"
PATCH_ROOT="$ROOT_DIR/submodule-patches"

if [[ ! -d "$PATCH_ROOT" ]]; then
  echo "No submodule patches directory found at $PATCH_ROOT" >&2
  exit 0
fi

if [[ $# -gt 0 ]]; then
  declare -a PATCHES=()
  for arg in "$@"; do
    if [[ -f "$arg" ]]; then
      PATCHES+=("$(realpath "$arg")")
    elif [[ -f "$PATCH_ROOT/$arg" ]]; then
      PATCHES+=("$(realpath "$PATCH_ROOT/$arg")")
    else
      echo "Patch file not found: $arg" >&2
      exit 1
    fi
  done
else
  mapfile -t PATCHES < <(find "$PATCH_ROOT" -type f -name '*.patch' | sort)
fi

if [[ ${#PATCHES[@]} -eq 0 ]]; then
  echo "No submodule patches to apply." >&2
  exit 0
fi

for patch_path in "${PATCHES[@]}"; do
  rel_path="${patch_path#$PATCH_ROOT/}"
  submodule_path="${rel_path%/*}"
  if [[ -z "$submodule_path" ]]; then
    echo "Unable to determine submodule for patch $rel_path" >&2
    exit 1
  fi
  target_dir="$ROOT_DIR/$submodule_path"
  if [[ ! -d "$target_dir" ]]; then
    echo "Submodule directory missing for patch $rel_path (expected $target_dir)" >&2
    exit 1
  fi

  echo "Applying $rel_path to $submodule_path"
  (cd "$target_dir" && git apply --3way "$patch_path")

done

echo "Patches applied. Review each submodule, make commits, and then remove or archive applied patches." >&2
