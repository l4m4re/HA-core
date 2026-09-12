#!/usr/bin/env python3
"""Manage the persistent Home Assistant staging instance."""

# This is a command-line controller; its public functions are CLI subcommands.
# ruff: noqa: D103

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGING_ROOT = REPO_ROOT / ".staging"
CONFIG_DIR = STAGING_ROOT / "ha-config"
STATE_PATH = STAGING_ROOT / "state.json"
PID_PATH = STAGING_ROOT / "ha.pid"
LOG_PATH = STAGING_ROOT / "home-assistant.log"
ENTITY_REGISTRY_PATH = CONFIG_DIR / ".storage" / "core.entity_registry"
LOVELACE_DASHBOARD_PATH = CONFIG_DIR / ".storage" / "lovelace.dashboard_staging"
LOVELACE_REGISTRY_PATH = CONFIG_DIR / ".storage" / "lovelace_dashboards"
STAGING_DASHBOARD_SOURCE = REPO_ROOT / "script" / "ha_staging_dashboard.json"
GROWATT_SOURCE = (
    REPO_ROOT
    / "external"
    / "Homeassistant-Growatt-Local-Modbus"
    / "custom_components"
    / "growatt_local"
)
CONTROL_DOMAINS = {
    "localtuya",
    "rpi_gpio_pwm",
    "rpi_power",
    "shelly",
    "tuya",
}
SENSITIVE_STORAGE = (
    ".storage/auth",
    ".storage/auth_provider.homeassistant",
    ".storage/http.auth",
    ".storage/onboarding",
    ".storage/core.uuid",
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def fail(message: str) -> int:
    print(f"Error: {message}", file=sys.stderr)
    return 2


def require_staging_path(path: Path) -> None:
    resolved = path.resolve()
    root = STAGING_ROOT.resolve()
    if resolved == root or root not in resolved.parents:
        raise RuntimeError(f"refusing non-staging path: {path}")


def read_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {
            "schema": 1,
            "config_dir": str(CONFIG_DIR),
        }
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    state.pop("owner", None)
    state.pop("owner_expires_at", None)
    state.pop("mode", None)
    state.pop("control_armed", None)
    return state


def write_state(state: dict[str, Any]) -> None:
    STAGING_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(STATE_PATH)


def storage_path(relative: str) -> Path:
    path = CONFIG_DIR / relative
    require_staging_path(path)
    return path


def load_entries() -> dict[str, Any]:
    path = storage_path(".storage/core.config_entries")
    if not path.exists():
        return {
            "version": 1,
            "minor_version": 1,
            "key": "core.config_entries",
            "data": {"entries": []},
        }
    return json.loads(path.read_text(encoding="utf-8"))


def configure_growatt() -> None:
    path = storage_path(".storage/core.config_entries")
    if not path.exists():
        return
    document = load_entries()
    found = False
    for entry in document.get("data", {}).get("entries", []):
        if entry.get("domain") != "growatt_local":
            continue
        found = True
        data = entry.setdefault("data", {})
        data["ip_address"] = "192.168.1.148"
        data["port"] = 5021
        data["address"] = 1
        data["inverter_power_control"] = True
        entry["disabled_by"] = None
    if found:
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def enable_growatt_control_entities() -> None:
    """Keep all Growatt control entities enabled in staging."""

    if not ENTITY_REGISTRY_PATH.exists():
        return
    document = json.loads(ENTITY_REGISTRY_PATH.read_text(encoding="utf-8"))
    changed = False
    for entity in document.get("data", {}).get("entities", []):
        if entity.get("platform") != "growatt_local":
            continue
        domain = entity.get("entity_id", "").split(".", 1)[0]
        if domain not in {"number", "switch"}:
            continue
        if entity.get("disabled_by") is not None:
            entity["disabled_by"] = None
            changed = True
    if changed:
        ENTITY_REGISTRY_PATH.write_text(
            json.dumps(document, indent=2) + "\n", encoding="utf-8"
        )


def install_staging_dashboard() -> None:
    """Install the bounded engineering dashboard in staging storage."""

    if not STAGING_DASHBOARD_SOURCE.exists():
        return
    config = json.loads(STAGING_DASHBOARD_SOURCE.read_text(encoding="utf-8"))
    dashboard = {
        "version": 1,
        "minor_version": 1,
        "key": "lovelace.dashboard_staging",
        "data": {"config": config},
    }
    LOVELACE_DASHBOARD_PATH.write_text(
        json.dumps(dashboard, indent=2) + "\n", encoding="utf-8"
    )

    if not LOVELACE_REGISTRY_PATH.exists():
        return
    registry = json.loads(LOVELACE_REGISTRY_PATH.read_text(encoding="utf-8"))
    items = registry.setdefault("data", {}).setdefault("items", [])
    staging_item = {
        "id": "dashboard_staging",
        "show_in_sidebar": True,
        "icon": "mdi:solar-power",
        "title": "Growatt Staging",
        "require_admin": False,
        "mode": "storage",
        "url_path": "growatt-staging",
    }
    if staging_item not in items:
        items[:] = [item for item in items if item.get("id") != staging_item["id"]]
        items.append(staging_item)
        LOVELACE_REGISTRY_PATH.write_text(
            json.dumps(registry, indent=2) + "\n", encoding="utf-8"
        )


def apply_staging_overrides(reset_sensitive_storage: bool = False) -> None:
    require_staging_path(CONFIG_DIR)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    custom_components = CONFIG_DIR / "custom_components"
    custom_components.mkdir(parents=True, exist_ok=True)
    component = custom_components / "growatt_local"
    if component.is_symlink() or component.exists():
        if component.is_dir() and not component.is_symlink():
            shutil.rmtree(component)
        else:
            component.unlink()
    component.symlink_to(GROWATT_SOURCE)

    if reset_sensitive_storage:
        for relative in SENSITIVE_STORAGE:
            path = CONFIG_DIR / relative
            if path.exists() or path.is_symlink():
                path.unlink()

    (CONFIG_DIR / "automations.yaml").write_text("[]\n", encoding="utf-8")
    (CONFIG_DIR / "scripts.yaml").write_text("{}\n", encoding="utf-8")
    (CONFIG_DIR / "scenes.yaml").write_text("[]\n", encoding="utf-8")
    (CONFIG_DIR / "configuration.yaml").write_text(
        """# Generated by script/ha-staging.py; production YAML is kept in .ha-staging-source.
homeassistant:
  name: Home Assistant STAGING
  unit_system: metric
  time_zone: Europe/Amsterdam
  internal_url: http://localhost:8123
default_config:
frontend:
  themes: !include_dir_merge_named themes
automation: []
script: []
scene: []
python_script:
logger:
  default: info
  logs:
    custom_components.growatt_local: debug
    pymodbus: debug
recorder:
  purge_keep_days: 30
""",
        encoding="utf-8",
    )

    document = load_entries()
    for entry in document.get("data", {}).get("entries", []):
        if entry.get("domain") in CONTROL_DOMAINS:
            entry["disabled_by"] = "user"
    path = storage_path(".storage/core.config_entries")
    if path.exists():
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    configure_growatt()
    enable_growatt_control_entities()
    install_staging_dashboard()


def sync(source: Path) -> None:
    source = source.resolve()
    if not source.is_dir():
        raise RuntimeError(f"source is not a directory: {source}")
    if source == CONFIG_DIR.resolve() or CONFIG_DIR.resolve() in source.parents:
        raise RuntimeError("staging config cannot be its own sync source")
    STAGING_ROOT.mkdir(parents=True, exist_ok=True)
    snapshot = STAGING_ROOT / "source-snapshot"
    require_staging_path(snapshot)
    if snapshot.exists():
        shutil.rmtree(snapshot)
    subprocess.run(
        ["rsync", "-a", "--delete", f"{source}/", f"{snapshot}/"],
        check=True,
    )
    if CONFIG_DIR.exists():
        shutil.rmtree(CONFIG_DIR)
    shutil.copytree(snapshot, CONFIG_DIR, symlinks=True)
    source_record = CONFIG_DIR / ".ha-staging-source"
    source_record.mkdir(exist_ok=True)
    for filename in (
        "configuration.yaml",
        "automations.yaml",
        "scripts.yaml",
        "scenes.yaml",
    ):
        original = snapshot / filename
        if original.exists():
            shutil.copy2(original, source_record / filename)
    state = read_state()
    state.update(
        {
            "schema": 1,
            "config_dir": str(CONFIG_DIR),
            "source_snapshot": str(snapshot),
            "synced_from": str(source),
            "synced_at": now_iso(),
        }
    )
    write_state(state)
    apply_staging_overrides(reset_sensitive_storage=True)
    print(f"staging_config={CONFIG_DIR}")
    print("growatt_writes=enabled")
    print("Growatt endpoint=192.168.1.148:5021 unit=1")


def validate(state: dict[str, Any]) -> None:
    if not CONFIG_DIR.is_dir():
        raise RuntimeError(f"staging config does not exist: {CONFIG_DIR}")
    if CONFIG_DIR.resolve() == Path("/config").resolve():
        raise RuntimeError("staging config resolves to production /config")
    if "5020" in (CONFIG_DIR / "configuration.yaml").read_text(encoding="utf-8"):
        raise RuntimeError("staging YAML contains the production Growatt port")
    entries = load_entries().get("data", {}).get("entries", [])
    growatt_found = False
    for entry in entries:
        if entry.get("domain") != "growatt_local":
            continue
        growatt_found = True
        data = entry.get("data", {})
        if data.get("port") != 5021 or data.get("ip_address") != "192.168.1.148":
            raise RuntimeError(
                "Growatt staging entry is not pinned to 192.168.1.148:5021"
            )
        if not data.get("inverter_power_control"):
            raise RuntimeError("Growatt power control is disabled in staging")
    if not growatt_found:
        raise RuntimeError("staging source has no growatt_local config entry")


def process_running() -> bool:
    if not PID_PATH.exists():
        return False
    try:
        pid = int(PID_PATH.read_text(encoding="ascii"))
        os.kill(pid, 0)
    except OSError, ValueError:
        return False
    return True


def start() -> None:
    state = read_state()
    validate(state)
    if process_running():
        raise RuntimeError("staging Home Assistant is already running")
    STAGING_ROOT.mkdir(parents=True, exist_ok=True)
    log = LOG_PATH.open("a", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-m",
            "homeassistant",
            "--config",
            str(CONFIG_DIR),
            "--skip-pip",
            "--log-no-color",
        ],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "PYTHONUNBUFFERED": "1",
        },
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    PID_PATH.write_text(f"{process.pid}\n", encoding="ascii")
    print(f"pid={process.pid}")
    print("url=http://localhost:8123")
    print("growatt_writes=enabled")
    print(f"log={LOG_PATH}")


def stop() -> None:
    pid: int | None = None
    if PID_PATH.exists():
        try:
            pid = int(PID_PATH.read_text(encoding="ascii"))
            os.kill(pid, signal.SIGTERM)
            print(f"stopping pid={pid}")
        except (OSError, ValueError) as exc:
            print(f"staging process already stopped: {exc}")
        if pid is not None:
            for _ in range(30):
                if not process_running():
                    break
                time.sleep(1)
    else:
        print("staging Home Assistant is not running")
    PID_PATH.unlink(missing_ok=True)
    write_state(read_state())


def restart() -> None:
    """Restart staging without changing its persistent configuration."""

    stop()
    start()


def reset_recorder() -> None:
    state = read_state()
    validate(state)
    if process_running():
        raise RuntimeError("stop staging before resetting its Recorder")
    for name in (
        "home-assistant_v2.db",
        "home-assistant_v2.db-shm",
        "home-assistant_v2.db-wal",
    ):
        path = CONFIG_DIR / name
        if path.exists():
            path.unlink()
    print("staging Recorder files removed; production Recorder was not touched")


def status() -> None:
    state = read_state()
    validate(state)
    print(
        json.dumps(
            {**state, "running": process_running(), "url": "http://localhost:8123"},
            indent=2,
        )
    )


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    sync_parser = sub.add_parser(
        "sync", help="copy a production snapshot into persistent staging"
    )
    sync_parser.add_argument("source", type=Path)
    sub.add_parser("start")
    sub.add_parser("stop")
    sub.add_parser("restart")
    sub.add_parser("status")
    sub.add_parser("reset-recorder")
    return ap


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "sync":
            sync(args.source)
        elif args.command == "start":
            start()
        elif args.command == "stop":
            stop()
        elif args.command == "restart":
            restart()
        elif args.command == "status":
            status()
        elif args.command == "reset-recorder":
            reset_recorder()
        else:  # pragma: no cover - argparse enforces the command tree
            return fail("unknown command")
    except (
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
    ) as exc:
        return fail(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
