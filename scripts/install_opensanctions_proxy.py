"""Prepare a restricted OpenSanctions proxy from the existing sing-box outbound."""

import json
import os
import tempfile
from pathlib import Path


SOURCE_CONFIG = Path("/etc/sing-box-happ-server/config.json")
DESTINATION = Path("/etc/sing-box-admin/fnsrus-opensanctions")
OUTBOUND_TAG = "auto-9"
PROXY_ADDRESS = "10.8.0.1"
PROXY_PORT = 19450
WG_INTERFACE = "wg0"
WG_CLIENT_ADDRESS = "10.8.0.5"


def build_proxy_config(source):
    outbound = next(
        (item for item in source.get("outbounds", []) if item.get("tag") == OUTBOUND_TAG),
        None,
    )
    if not isinstance(outbound, dict) or outbound.get("type") != "hysteria2":
        raise ValueError(f"Expected a Hysteria2 outbound named {OUTBOUND_TAG}.")

    config = {
        "log": {"level": "warning"},
        "inbounds": [{
            "type": "socks",
            "tag": "fnsrus-opensanctions-in",
            "listen": PROXY_ADDRESS,
            "listen_port": PROXY_PORT,
        }],
        "outbounds": [outbound],
        "route": {"final": OUTBOUND_TAG, "auto_detect_interface": True},
    }
    if source.get("dns"):
        config["dns"] = source["dns"]

    firewall = f"""table inet fnsrus_opensanctions_proxy {{
    chain input {{
        type filter hook input priority -10; policy accept;
        iifname \"{WG_INTERFACE}\" ip daddr {PROXY_ADDRESS} tcp dport {PROXY_PORT} ip saddr != {WG_CLIENT_ADDRESS} drop
    }}
}}
"""
    return config, firewall


def atomic_write(path, content, mode):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def main():
    if os.geteuid() != 0:
        raise SystemExit("Run this installer as root on the WireGuard server.")
    source = json.loads(SOURCE_CONFIG.read_text(encoding="utf-8"))
    try:
        config, firewall = build_proxy_config(source)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    atomic_write(DESTINATION / "config.json", json.dumps(config, ensure_ascii=False) + "\n", 0o600)
    atomic_write(DESTINATION / "firewall.nft", firewall, 0o600)
    print(f"Prepared restricted SOCKS proxy on {PROXY_ADDRESS}:{PROXY_PORT} via {OUTBOUND_TAG}.")


if __name__ == "__main__":
    main()