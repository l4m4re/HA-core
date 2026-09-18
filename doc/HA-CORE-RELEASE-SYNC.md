# Home Assistant release synchronization

The official Home Assistant Core repository is configured as the `upstream`
remote. The `ha-core-release` branch is a clean pointer to the current official
release. Keep project changes on a `research/` branch and use the current
working directory for release updates.

The project branch contains project-specific commits, so it cannot fast-forward
to an official release. Advance the clean release pointer, then rebase the
project branch onto that release in this same working directory.

## Advance to a new release

Fetch official tags and select the latest stable release:

```bash
git fetch upstream --tags
git tag --sort=-version:refname --list '20*' | head
```

Finish or commit current work, then update and publish the clean release
pointer:

```bash
git switch ha-core-release
git merge --ff-only 2026.9.3
git push origin ha-core-release
```

Rebase the project branch onto the new release and publish the updated branch
to the project origin:

```bash
git switch research/ha-dev-2026.9.2-candidate
git rebase --onto 2026.9.3 2026.9.2
git push --force-with-lease origin research/ha-dev-2026.9.2-candidate
```

Resolve and review conflicts before pushing. Keep Growatt and broker changes as
commits in their own repositories; update their gitlinks in this repository.
Do not store or apply submodule patch files here.

## Current baseline

As of 2026-09-18, `ha-core-release` points at Home Assistant Core 2026.9.2
(`33c3e0cca60e73a8c4970ee677d75b8bc6464cdf`). The active development branch is
`research/ha-dev-2026.9.2-candidate`. HA Core application source and tests have
no project-specific changes; local changes are in the devcontainer wrapper,
staging tools, project documentation, and the Growatt and broker submodules.
