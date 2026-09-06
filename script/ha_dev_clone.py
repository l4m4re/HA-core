"""Prepare a disposable Home Assistant production clone for safe boot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

QUARANTINE_DIR = ".ha-dev-quarantine"
CONFIG_ENTRY_FILE = ".storage/core.config_entries"
AUTH_FILES = (
    ".storage/auth",
    ".storage/auth_provider.homeassistant",
    ".storage/http.auth",
    ".storage/onboarding",
)

SAFE_CONFIGURATION = """# Generated for the disposable HA-DEV-1R clone.
# The production configuration is preserved in .ha-dev-quarantine/.
homeassistant:
  name: HA DEV CLONE
  unit_system: metric
  time_zone: Europe/Amsterdam

default_config:

automation: []
script: []
scene: []
command_line: []
light: []
rest: []
utility_meter: {}
python_script:

logger:
  default: info
"""


def _quarantine_dir(config_dir: Path) -> Path:
    path = config_dir / QUARANTINE_DIR
    path.mkdir(exist_ok=True)
    return path


def _preserve(path: Path, destination: Path) -> None:
    if path.exists() or path.is_symlink():
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(path, destination, follow_symlinks=False)


def _write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def quarantine(config_dir: Path, allowed_domains: set[str]) -> None:
    """Disable live entries and replace action-capable YAML with a safe overlay."""

    entries_path = config_dir / CONFIG_ENTRY_FILE
    if not entries_path.is_file():
        raise SystemExit(f"missing config entry store: {entries_path}")

    quarantine_dir = _quarantine_dir(config_dir)
    original_entries = quarantine_dir / "core.config_entries.production.json"
    _preserve(entries_path, original_entries)

    entries = json.loads(entries_path.read_text(encoding="utf-8"))
    changed = 0
    for entry in entries["data"]["entries"]:
        if entry.get("domain") not in allowed_domains:
            if entry.get("disabled_by") != "user":
                changed += 1
            entry["disabled_by"] = "user"
    _write_json(entries_path, entries)

    configuration_path = config_dir / "configuration.yaml"
    _preserve(configuration_path, quarantine_dir / "configuration.production.yaml")
    configuration_path.write_text(SAFE_CONFIGURATION, encoding="utf-8")

    for relative_path in AUTH_FILES:
        source = config_dir / relative_path
        destination = quarantine_dir / relative_path
        if source.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.replace(destination)

    print(f"quarantined={changed}")
    print(f"allowed_domains={','.join(sorted(allowed_domains)) or '<none>'}")
    print(f"preserved={quarantine_dir}")


def validate(config_dir: Path, allowed_domains: set[str]) -> None:
    """Verify the clone has no unexpectedly enabled live config entry."""

    entries_path = config_dir / CONFIG_ENTRY_FILE
    entries = json.loads(entries_path.read_text(encoding="utf-8"))
    enabled = [
        f"{entry['domain']}:{entry.get('title', '')}"
        for entry in entries["data"]["entries"]
        if not entry.get("disabled_by") and entry.get("domain") not in allowed_domains
    ]
    if enabled:
        raise SystemExit("unexpectedly enabled entries: " + ", ".join(enabled))
    if "influxdb:" in (config_dir / "configuration.yaml").read_text(encoding="utf-8"):
        raise SystemExit("legacy influxdb writer remains in DEV configuration")
    print("quarantine_valid=true")


def main() -> int:
    """Run the clone quarantine or validation command."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("quarantine", "validate"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("config_dir", type=Path)
        subparser.add_argument("--allow-domain", action="append", default=[])
    args = parser.parse_args()
    domains = set(args.allow_domain)
    if args.command == "quarantine":
        quarantine(args.config_dir, domains)
    else:
        validate(args.config_dir, domains)
    return 0


if __name__ == "__main__":
    sys.exit(main())
