#!/usr/bin/python3
"""Narrow systemd socket helper for toggling the FNSRUS WireGuard client."""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path


UNIT = "fnsrus-wg-client.service"
INTERFACE = "fnsrus"
CONFIG = Path("/etc/wireguard/fnsrus.conf")
ENDPOINT = "192.168.0.39:51820"
PROXY = "10.8.0.1:19450"
MAX_REQUEST_BYTES = 128


def systemctl(*arguments):
    return subprocess.run(
        ["/usr/bin/systemctl", *arguments],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
    ).returncode


def status():
    configured = CONFIG.is_file()
    active = systemctl("is-active", "--quiet", UNIT) == 0
    enabled = systemctl("is-enabled", "--quiet", UNIT) == 0
    handshake = False
    if active:
        try:
            output = subprocess.check_output(
                ["/usr/bin/wg", "show", INTERFACE, "latest-handshakes"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
            now = int(time.time())
            handshake = any(
                int(parts[1]) > 0 and now - int(parts[1]) < 180
                for line in output.splitlines()
                if len(parts := line.split()) == 2
            )
        except (OSError, ValueError, subprocess.SubprocessError):
            handshake = False
    return {
        "ok": True,
        "configured": configured,
        "enabled": enabled,
        "active": active,
        "handshake": handshake,
        "endpoint": ENDPOINT,
        "proxy": PROXY,
    }


def handle(command, enabled=None):
    if command == "status":
        return status()
    if command not in {"connect", "disconnect", "save", "enable", "disable"}:
        return {"ok": False, "error": "invalid_command"}
    if not CONFIG.is_file():
        return {"ok": False, "error": "not_configured"}
    if command == "save":
        if not isinstance(enabled, bool):
            return {"ok": False, "error": "invalid_request"}
        result = systemctl("enable" if enabled else "disable", UNIT)
    elif command == "enable":
        result = systemctl("start", UNIT)
    elif command == "disable":
        result = systemctl("stop", UNIT)
    elif command == "connect":
        result = systemctl("enable", "--now", UNIT)
    else:
        result = systemctl("disable", "--now", UNIT)
    if result != 0:
        return {"ok": False, "error": "systemd_failed", **status()}
    return status()


def main():
    raw = sys.stdin.buffer.readline(MAX_REQUEST_BYTES + 1)
    if len(raw) > MAX_REQUEST_BYTES:
        response = {"ok": False, "error": "request_too_large"}
    else:
        try:
            request = json.loads(raw or b"{}")
            command = request.get("command") if isinstance(request, dict) else None
            enabled = request.get("enabled") if isinstance(request, dict) else None
            response = handle(command, enabled)
        except (ValueError, TypeError):
            response = {"ok": False, "error": "invalid_request"}
    sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()