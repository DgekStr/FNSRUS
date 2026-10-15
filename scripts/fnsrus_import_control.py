#!/usr/bin/python3
"""Narrow systemd control helper for OpenSanctions imports."""

import json
import os
import re
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path


IMPORT_UNIT = "fnsrus-opensanctions-import.service"
IMPORT_TEMPLATE = "fnsrus-opensanctions-import@{}.service"
IMPORT_PATTERN = "fnsrus-opensanctions-import@*.service"
ARCHIVE_TEMPLATE = "fnsrus-opensanctions-archive@{}.service"
ARCHIVE_PATTERN = "fnsrus-opensanctions-archive@*.service"
STATUS_FILE = Path("/var/lib/mcp-fns/opensanctions-import-status.json")
ARCHIVE_STATUS_FILE = Path("/var/lib/mcp-fns/opensanctions-archive-status.json")
CONTROL_LOCK = Path("/run/fnsrus-import-control.lock")
MAX_REQUEST_BYTES = 512
ACTIVE_STATES = {"starting", "checking", "running", "retrying", "stopping", "indexing", "validating"}
VERSION_PATTERN = re.compile(r"[0-9]{14}-[a-z0-9]+")


def systemctl(*arguments, timeout=10):
    return subprocess.run(
        ["/usr/bin/systemctl", *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def read_import_status():
    try:
        status = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return status if isinstance(status, dict) else {}


def active_units():
    units = []
    result = systemctl(
        "list-units", "--type=service", "--state=active,activating",
        "--plain", "--no-legend", IMPORT_UNIT, IMPORT_PATTERN, ARCHIVE_PATTERN,
    )
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            unit = line.split(maxsplit=1)[0] if line.split() else ""
            if unit and unit not in units:
                units.append(unit)
    return units


@contextmanager
def control_lock():
    CONTROL_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with CONTROL_LOCK.open("a+") as lock_file:
        try:
            import fcntl
        except ImportError:
            fcntl = None
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def status():
    import_status = read_import_status()
    state = import_status.get("state", "not_started")
    units = active_units()
    if not units and state in ACTIVE_STATES:
        state = "interrupted"
    expected_version = None
    archive_version = None
    import_units = []
    archive_units = []
    for unit in units:
        match = re.fullmatch(r"fnsrus-opensanctions-import@([0-9]{14}-[a-z0-9]+)\.service", unit)
        if match:
            import_units.append(unit)
            expected_version = match.group(1)
            continue
        match = re.fullmatch(r"fnsrus-opensanctions-archive@([0-9]{14}-[a-z0-9]+)\.service", unit)
        if match:
            archive_units.append(unit)
            archive_version = match.group(1)
            continue
        if unit == IMPORT_UNIT:
            import_units.append(unit)
    archive_status = {}
    try:
        value = json.loads(ARCHIVE_STATUS_FILE.read_text(encoding="utf-8"))
        archive_status = value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        pass
    return {
        "ok": True,
        "active": bool(units),
        "import_active": bool(import_units),
        "archive_active": bool(archive_units),
        "state": state,
        "units": units,
        "expected_version": expected_version,
        "archive_version": archive_version,
        "archive_state": archive_status.get("state", "not_started"),
    }


def start(expected_version):
    if not isinstance(expected_version, str) or not VERSION_PATTERN.fullmatch(expected_version):
        return {"ok": False, "error": "invalid_version"}
    with control_lock():
        current_status = read_import_status()
        state = current_status.get("state", "not_started")
        if state == "ready_to_publish":
            return {"ok": False, "error": "publish_required"}
        units = active_units()
        if units:
            return {"ok": False, "error": "import_busy", "units": units}
        unit = IMPORT_TEMPLATE.format(expected_version)
        try:
            result = systemctl("start", unit, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return {"ok": False, "error": "systemd_unavailable"}
        if result.returncode != 0:
            return {"ok": False, "error": "systemd_start_failed"}
        return {"ok": True, "active": True, "unit": unit}


def stop(expected_version):
    if not isinstance(expected_version, str) or not VERSION_PATTERN.fullmatch(expected_version):
        return {"ok": False, "error": "invalid_version"}
    with control_lock():
        unit = IMPORT_TEMPLATE.format(expected_version)
        if unit not in active_units():
            return {"ok": False, "error": "import_not_active"}
        try:
            result = systemctl("stop", "--no-block", unit, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return {"ok": False, "error": "systemd_unavailable"}
        if result.returncode != 0:
            return {"ok": False, "error": "systemd_stop_failed"}
        return {"ok": True, "active": True, "stopping": True, "unit": unit}


def start_archive(expected_version):
    if not isinstance(expected_version, str) or not VERSION_PATTERN.fullmatch(expected_version):
        return {"ok": False, "error": "invalid_version"}
    with control_lock():
        units = active_units()
        if units:
            return {"ok": False, "error": "import_busy", "units": units}
        unit = ARCHIVE_TEMPLATE.format(expected_version)
        try:
            result = systemctl("start", unit, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return {"ok": False, "error": "systemd_unavailable"}
        if result.returncode != 0:
            return {"ok": False, "error": "systemd_start_failed"}
        return {"ok": True, "active": True, "unit": unit}


def stop_archive(expected_version):
    if not isinstance(expected_version, str) or not VERSION_PATTERN.fullmatch(expected_version):
        return {"ok": False, "error": "invalid_version"}
    with control_lock():
        unit = ARCHIVE_TEMPLATE.format(expected_version)
        if unit not in active_units():
            return {"ok": False, "error": "archive_not_active"}
        try:
            result = systemctl("stop", "--no-block", unit, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return {"ok": False, "error": "systemd_unavailable"}
        if result.returncode != 0:
            return {"ok": False, "error": "systemd_stop_failed"}
        return {"ok": True, "active": True, "stopping": True, "unit": unit}


def handle(request):
    if not isinstance(request, dict):
        return {"ok": False, "error": "invalid_request"}
    command = request.get("command")
    if command == "status":
        return status()
    if command == "start":
        return start(request.get("expected_version"))
    if command == "stop":
        return stop(request.get("expected_version"))
    if command == "archive_start":
        return start_archive(request.get("expected_version"))
    if command == "archive_stop":
        return stop_archive(request.get("expected_version"))
    return {"ok": False, "error": "invalid_command"}


def main():
    raw = sys.stdin.buffer.readline(MAX_REQUEST_BYTES + 1)
    if len(raw) > MAX_REQUEST_BYTES:
        response = {"ok": False, "error": "request_too_large"}
    else:
        try:
            response = handle(json.loads(raw or b"{}"))
        except (ValueError, TypeError):
            response = {"ok": False, "error": "invalid_request"}
    sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()