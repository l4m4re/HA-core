#!/usr/bin/env bash
# Capture submodule changes as patch files during pre-commit and reset submodules.
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel)"
PATCH_ROOT="$ROOT_DIR/submodule-patches"
mkdir -p "$PATCH_ROOT"

mapfile -t SUBMODULES < <(git config --file "$ROOT_DIR/.gitmodules" --get-regexp path 2>/dev/null | awk '{print $2}')

if [[ ${#SUBMODULES[@]} -eq 0 ]]; then
  exit 0
fi

created_patches=()

for submodule in "${SUBMODULES[@]}"; do
  SUB_PATH="$ROOT_DIR/$submodule"
  if [[ ! -d "$SUB_PATH/.git" && ! -f "$SUB_PATH/.git" ]]; then
    continue
  fi

  status=$(git -C "$SUB_PATH" status --porcelain --untracked-files=all)
  if [[ -z "$status" ]]; then
    continue
  fi

  mapfile -t UNTRACKED < <(git -C "$SUB_PATH" ls-files --others --exclude-standard)
  if [[ ${#UNTRACKED[@]} -gt 0 ]]; then
    (cd "$SUB_PATH" && git add -N -- "${UNTRACKED[@]}")
  fi

  timestamp=$(date -u +"%Y%m%d-%H%M%S")
  module_patch_dir="$PATCH_ROOT/$submodule"
  mkdir -p "$module_patch_dir"
  patch_file="$module_patch_dir/${timestamp}.patch"

  if ! git -C "$SUB_PATH" diff --binary HEAD > "$patch_file"; then
    (cd "$SUB_PATH" && git reset --mixed HEAD)
    rm -f "$patch_file"
    echo "Failed to create patch for submodule $submodule" >&2
    exit 1
  fi

  if [[ ! -s "$patch_file" ]]; then
    (cd "$SUB_PATH" && git reset --mixed HEAD)
    rm -f "$patch_file"
    echo "Submodule $submodule reported changes but produced an empty patch." >&2
    echo "Commit aborted. Please review the submodule state manually." >&2
    exit 1
  fi

  (cd "$SUB_PATH" && git reset --hard HEAD >/dev/null)
  (cd "$SUB_PATH" && git clean -fdx >/dev/null)
  git submodule update --init --checkout "$submodule" >/dev/null

  rel_patch="${patch_file#$ROOT_DIR/}"
  git add "$rel_patch"
  created_patches+=("$rel_patch")
  echo "Captured $submodule changes into $rel_patch"
done

if [[ ${#created_patches[@]} -gt 0 ]]; then
  printf '\nSubmodule patches staged for commit:\n' >&2
  printf '  %s\n' "${created_patches[@]}" >&2
  printf '\nUse script/apply-submodule-patches.sh to reapply them when updating submodules.\n' >&2
fi

exit 0
