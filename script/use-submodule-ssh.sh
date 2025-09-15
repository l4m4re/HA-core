#!/usr/bin/env bash
# Switch submodule remotes to SSH form for contributors with write access.
set -euo pipefail

repo_root="$(dirname "$0")/.."
cd "$repo_root"

declare -A remotes=(
  ["external/Homeassistant-Growatt-Local-Modbus"]="git@github.com:l4m4re/Homeassistant-Growatt-Local-Modbus.git"
  ["external/growatt-rtu-broker"]="git@github.com:l4m4re/growatt-rtu-broker.git"
)

for path in "${!remotes[@]}"; do
  url="${remotes[$path]}"
  if [ -d "$path" ]; then
    echo "Setting $path remote to $url"
    git submodule set-url "$path" "$url"
  else
    echo "Skipping $path (directory not present)"
  fi
done

git submodule sync

echo "Submodule remotes updated. Future submodule operations will use SSH."
