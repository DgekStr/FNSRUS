#!/usr/bin/python3
"""Narrow systemd socket helper for the FNSRUS WireGuard client."""

import base64
import ipaddress
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path


UNIT = "fnsrus-wg-client.service"
INTERFACE = "fnsrus"
CONFIG = Path("/etc/wireguard/fnsrus.conf")
ENDPOINT = "192.168.0.39:51820"
PROXY = "10.8.0.1:19450"
PRESERVE_SECRET = "__KEEP_EXISTING__"
MAX_CONFIG_BYTES = 16 * 1024
MAX_REQUEST_BYTES = 40 * 1024
ALLOWED_KEYS = {
    "interface": {"privatekey", "address", "mtu", "table"},
    "peer": {"publickey", "presharedkey", "allowedips", "endpoint", "persistentkeepalive"},
}
KEY_ORDER = {
    "interface": ("privatekey", "address", "mtu", "table"),
    "peer": ("publickey", "presharedkey", "allowedips", "endpoint", "persistentkeepalive"),
}
KEY_NAMES = {
    "privatekey": "PrivateKey", "address": "Address", "mtu": "MTU", "table": "Table",
    "publickey": "PublicKey", "presharedkey": "PresharedKey", "allowedips": "AllowedIPs",
    "endpoint": "Endpoint", "persistentkeepalive": "PersistentKeepalive",
}
SECRET_KEYS = {("interface", "privatekey"), ("peer", "presharedkey")}


class ConfigError(ValueError):
    pass


def systemctl(*arguments):
    return subprocess.run(
        ["/usr/bin/systemctl", *arguments],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
    ).returncode


def parse_config(text):
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_CONFIG_BYTES:
        raise ConfigError("invalid_config_size")
    sections = {}
    current = None
    for line_number, raw_line in enumerate(text.lstrip("\ufeff").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section_name = line[1:-1].strip().casefold()
            if section_name not in ALLOWED_KEYS or section_name in sections:
                raise ConfigError("invalid_config_sections")
            sections[section_name] = {}
            current = section_name
            continue
        if current is None or "=" not in line:
            raise ConfigError("invalid_config_syntax")
        key, value = (part.strip() for part in line.split("=", 1))
        key = key.casefold()
        value = value.split("#", 1)[0].strip()
        if key not in ALLOWED_KEYS[current] or key in sections[current]:
            raise ConfigError("unsupported_or_duplicate_config_key")
        sections[current][key] = value
    if set(sections) != {"interface", "peer"}:
        raise ConfigError("interface_and_peer_required")
    return sections


def _validate_key(value):
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        raise ConfigError("invalid_wireguard_key") from None
    if len(decoded) != 32:
        raise ConfigError("invalid_wireguard_key")


def validate_config(sections):
    interface = sections["interface"]
    peer = sections["peer"]
    if not interface.get("privatekey") or not interface.get("address"):
        raise ConfigError("interface_privatekey_and_address_required")
    if not peer.get("publickey") or not peer.get("allowedips") or not peer.get("endpoint"):
        raise ConfigError("peer_publickey_allowedips_endpoint_required")
    for section, key in (("interface", "privatekey"), ("peer", "publickey"), ("peer", "presharedkey")):
        value = sections[section].get(key)
        if value and value != PRESERVE_SECRET:
            _validate_key(value)
    try:
        interface_addresses = [ipaddress.ip_interface(value.strip()) for value in interface["address"].split(",")]
        allowed_networks = [ipaddress.ip_network(value.strip(), strict=False)
                            for value in peer["allowedips"].split(",")]
    except ValueError:
        raise ConfigError("invalid_wireguard_network") from None
    if interface_addresses != [ipaddress.ip_interface("10.8.0.5/32")]:
        raise ConfigError("wireguard_interface_address_must_remain_proxy_peer")
    if allowed_networks != [ipaddress.ip_network("10.8.0.1/32")]:
        raise ConfigError("wireguard_allowedips_must_remain_proxy_only")
    if interface.get("mtu"):
        try:
            mtu = int(interface["mtu"])
        except ValueError:
            raise ConfigError("invalid_wireguard_mtu") from None
        if not 576 <= mtu <= 9000:
            raise ConfigError("invalid_wireguard_mtu")
    if interface.get("table", "off").casefold() != "off":
        raise ConfigError("wireguard_table_must_be_off")
    endpoint = peer["endpoint"]
    if endpoint.startswith("["):
        match = re.fullmatch(r"\[([^]]+)\]:([0-9]{1,5})", endpoint)
        if not match:
            raise ConfigError("invalid_wireguard_endpoint")
        try:
            ipaddress.IPv6Address(match.group(1))
        except ValueError:
            raise ConfigError("invalid_wireguard_endpoint") from None
        port = int(match.group(2))
    else:
        host, separator, port_text = endpoint.rpartition(":")
        if not separator or not host or not re.fullmatch(r"[A-Za-z0-9.-]+", host):
            raise ConfigError("invalid_wireguard_endpoint")
        try:
            port = int(port_text)
        except ValueError:
            raise ConfigError("invalid_wireguard_endpoint") from None
    if not 1 <= port <= 65535:
        raise ConfigError("invalid_wireguard_endpoint")
    if peer.get("persistentkeepalive"):
        try:
            keepalive = int(peer["persistentkeepalive"])
        except ValueError:
            raise ConfigError("invalid_wireguard_keepalive") from None
        if not 0 <= keepalive <= 65535:
            raise ConfigError("invalid_wireguard_keepalive")


def render_config(sections, redact_secrets=False):
    lines = []
    for section in ("interface", "peer"):
        if lines:
            lines.append("")
        lines.append(f"[{section.title()}]")
        for key in KEY_ORDER[section]:
            value = sections[section].get(key)
            if value is None:
                continue
            if redact_secrets and (section, key) in SECRET_KEYS:
                value = PRESERVE_SECRET
            lines.append(f"{KEY_NAMES[key]} = {value}")
    return "\n".join(lines) + "\n"


def read_config():
    try:
        sections = parse_config(CONFIG.read_text(encoding="ascii"))
        validate_config(sections)
        return sections
    except (OSError, UnicodeError, ConfigError):
        return None


def save_config(text):
    if CONFIG.is_symlink():
        raise ConfigError("unsafe_config_path")
    existing = read_config()
    sections = parse_config(text)
    for section, key in SECRET_KEYS:
        if sections[section].get(key) == PRESERVE_SECRET:
            old_value = existing[section].get(key) if existing else None
            if not old_value:
                raise ConfigError("wireguard_secret_required")
            sections[section][key] = old_value
    validate_config(sections)
    rendered = render_config(sections)
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(prefix=".fnsrus-wg-", dir=CONFIG.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, CONFIG)
        if os.name != "nt":
            directory_descriptor = os.open(CONFIG.parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def systemd_state(action, *arguments):
    return subprocess.run(
        ["/usr/bin/systemctl", action, *arguments],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
    ).returncode == 0


def status():
    configured = CONFIG.is_file()
    active = systemd_state("is-active", "--quiet", UNIT)
    enabled = systemd_state("is-enabled", "--quiet", UNIT)
    handshake = False
    sections = read_config() if configured else None
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
        "endpoint": sections["peer"].get("endpoint", ENDPOINT) if sections else ENDPOINT,
        "proxy": PROXY,
        "config_text": render_config(sections, redact_secrets=True) if sections else "",
        "config_error": configured and sections is None,
    }


def handle(command, enabled=None, config_text=None):
    if command == "status":
        return status()
    if command == "save_config":
        if not isinstance(config_text, str):
            return {"ok": False, "error": "invalid_config"}
        try:
            save_config(config_text)
        except ConfigError:
            return {"ok": False, "error": "invalid_config"}
        except OSError:
            return {"ok": False, "error": "config_write_failed"}
        result = status()
        result["config_saved"] = True
        result["restart_required"] = result["active"]
        return result
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
    if not result:
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
            config_text = request.get("config") if isinstance(request, dict) else None
            response = handle(command, enabled, config_text)
        except (ValueError, TypeError):
            response = {"ok": False, "error": "invalid_request"}
    sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()