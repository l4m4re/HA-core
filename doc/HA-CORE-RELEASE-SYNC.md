# Home Assistant release synchronization

The official Home Assistant Core repository is configured as the `upstream`
remote. The `ha-core-release` branch is a clean pointer to the current official
release. Keep local project changes on a separate `research/` branch.

The project branch cannot itself fast-forward to an official release because it
contains project-specific commits. The release pointer can fast-forward, then
the project branch can be rebased onto that release.

## Advance to a new release

Fetch official tags and select the latest stable release:

```bash
git fetch upstream --tags
git tag --sort=-version:refname --list '20*' | head
```

Use a separate worktree for the clean release branch, so an in-progress
development checkout stays untouched:

```bash
git worktree add ../HA-core-release ha-core-release
git -C ../HA-core-release merge --ff-only 2026.9.3
```

Create a new project branch in a separate worktree and rebase it onto the new
release. The existing project branch remains available for comparison:

```bash
git worktree add -b research/ha-dev-2026.9.3 ../HA-core-release-sync research/ha-dev-2026.9.2-candidate
git -C ../HA-core-release-sync rebase --onto 2026.9.3 2026.9.2
```

Review the rebase result and resolve conflicts before changing the active
development worktree. Do not force-push a rewritten branch that others use.

## Current baseline

As of 2026-09-18, `ha-core-release` points at Home Assistant Core 2026.9.2
(`33c3e0cca60e73a8c4970ee677d75b8bc6464cdf`). The local development candidate
`research/ha-dev-2026.9.2-candidate` was replayed on that baseline. HA Core
application source and tests have no project-specific changes; local changes
are in the devcontainer wrapper, staging tools, project documentation, and
external submodule patches.
