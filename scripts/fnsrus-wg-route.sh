#!/bin/sh
set -eu

interface=fnsrus
config=/etc/wireguard/fnsrus.conf
proxy_address=10.8.0.1/32

case "${1:-}" in
  up)
    if ! /usr/bin/wg show "$interface" >/dev/null 2>&1; then
      /usr/bin/wg-quick up "$config"
    fi
    /usr/sbin/ip -4 route replace "$proxy_address" dev "$interface"
    ;;
  down)
    /usr/sbin/ip -4 route del "$proxy_address" dev "$interface" 2>/dev/null || true
    if /usr/bin/wg show "$interface" >/dev/null 2>&1; then
      /usr/bin/wg-quick down "$config"
    fi
    ;;
  *)
    echo "usage: $0 {up|down}" >&2
    exit 2
    ;;
esac