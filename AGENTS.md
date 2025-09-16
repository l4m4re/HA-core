# Bootstrapping

Make sure to run `script/bootstrap-linux-native` after cloning this repository to set up the development environment and install the git hooks and to activate the Python virtual environment.

# Codex Workflow Notes

This repository primarily acts as the devcontainer wrapper for the Growatt and broker projects. The new git hook workflow keeps submodule changes out of commits while still preserving work as patches.

## Submodule patch workflow

- The `script/bootstrap-linux-native` script installs a `pre-commit` hook that runs `script/submodule-pre-commit.sh`.
- On commit, any modified submodule is converted into a patch stored at `submodule-patches/<submodule>/<timestamp>.patch`.
- After the patch is captured, the hook resets the submodule back to the commit recorded in this repository so the pending commit only contains patch artifacts.
- The patches are staged automatically. Commit them alongside your HA-core changes.
- To apply a patch inside the actual submodule repository, use `script/apply-submodule-patches.sh` (it replays all stored patches by default, or accept paths).
- Once the patch has been applied and a real submodule PR created, remember to remove the consumed patch file from this repository.

This replaces the old `pre-commit install` step and avoids the heavy HA-core linting hooks when using this repo purely for the devcontainer workflow.
