# ipmap/utils/ipmath.py

from __future__ import annotations

import ipaddress
from typing import Tuple


# ==========================
# Basic IPv4 helpers
# ==========================

def is_ipv4(s: str) -> bool:
    """
    Return True if s looks like a valid IPv4 address (a.b.c.d).
    """
    try:
        ipaddress.IPv4Address(s)
        return True
    except Exception:
        return False


def is_ipv4_cidr(s: str) -> bool:
    """
    Return True if s looks like a valid IPv4 CIDR string (a.b.c.d/len).
    """
    try:
        ipaddress.IPv4Network(s, strict=False)
        return True
    except Exception:
        return False


def ipv4_to_int(ip: str) -> int:
    """
    Convert IPv4 string -> integer.
    """
    return int(ipaddress.IPv4Address(ip))


def int_to_ipv4(value: int) -> str:
    """
    Convert integer -> IPv4 string.
    """
    return str(ipaddress.IPv4Address(value))


# ==========================
# CIDR normalization
# ==========================

def normalize_ip_or_cidr(ip_or_cidr: str, default_prefix_len: int = 32) -> Tuple[str, int]:
    """
    Normalize an IP or CIDR string into (network_address, prefix_len).

    Examples:
      "1.2.3.4"        -> ("1.2.3.4", 32)
      "1.2.3.4/24"     -> ("1.2.3.0", 24)
      "1.2.3.4/32"     -> ("1.2.3.4", 32)
    """
    ip_or_cidr = ip_or_cidr.strip()
    if not ip_or_cidr:
        raise ValueError("Empty IP string")

    if "/" in ip_or_cidr:
        net = ipaddress.IPv4Network(ip_or_cidr, strict=False)
        return str(net.network_address), net.prefixlen

    # No slash: treat as address with default prefix length
    if default_prefix_len == 32:
        addr = ipaddress.IPv4Address(ip_or_cidr)
        return str(addr), 32

    net = ipaddress.IPv4Network(f"{ip_or_cidr}/{default_prefix_len}", strict=False)
    return str(net.network_address), net.prefixlen


def cidr_contains(container: str, member: str) -> bool:
    """
    Return True if CIDR `container` contains IP or CIDR `member`.

    Examples:
      cidr_contains("10.0.0.0/8", "10.1.2.3")      -> True
      cidr_contains("10.0.0.0/16", "10.1.2.0/24")  -> False
    """
    net_container = ipaddress.IPv4Network(container, strict=False)
    if "/" in member:
        net_member = ipaddress.IPv4Network(member, strict=False)
        return net_member.subnet_of(net_container)
    else:
        addr = ipaddress.IPv4Address(member)
        return addr in net_container


def is_private(ip_or_cidr: str) -> bool:
    """
    True if the IP or network is RFC1918 private.
    """
    if "/" in ip_or_cidr:
        net = ipaddress.IPv4Network(ip_or_cidr, strict=False)
        return net.is_private
    else:
        addr = ipaddress.IPv4Address(ip_or_cidr)
        return addr.is_private


# ==========================
# Bucket index helpers
# ==========================

def ip_to_octets(ip: str) -> Tuple[int, int, int, int]:
    """
    Convert 'a.b.c.d' into tuple of ints (a, b, c, d).
    """
    parts = ip.split(".")
    if len(parts) != 4:
        raise ValueError(f"Not an IPv4 address: {ip!r}")
    a, b, c, d = (int(p) for p in parts)
    for v in (a, b, c, d):
        if v < 0 or v > 255:
            raise ValueError(f"Invalid octet in {ip!r}")
    return a, b, c, d


def ip_to_16_bucket(ip: str) -> Tuple[int, int, str]:
    """
    Return (bucket_x, bucket_y, label) for /16 view.

      bucket_x = first octet
      bucket_y = second octet
      label    = "a.b"
    """
    a, b, _, _ = ip_to_octets(ip)
    return a, b, f"{a}.{b}"


def ip_to_24_bucket(ip: str) -> Tuple[int, int, int, int, int, str]:
    """
    Return (bucket16_x, bucket16_y, bucket24_index, bucket24_x, bucket24_y, label)
    for /24 view, matching your notebook logic.

      bucket16_x    = a
      bucket16_y    = b
      bucket24_index= c             (0–255 inside the /16)
      bucket24_x    = c // 16       (0–15)
      bucket24_y    = c % 16        (0–15)
      label         = "a.b.c"
    """
    a, b, c, _ = ip_to_octets(ip)
    bucket24_index = c
    bucket24_x = bucket24_index // 16
    bucket24_y = bucket24_index % 16
    label = f"{a}.{b}.{c}"
    return a, b, bucket24_index, bucket24_x, bucket24_y, label


def ip_to_32_bucket(ip: str) -> Tuple[int, int, int, int, int, int, int, str]:
    """
    Return
      (bucket16_x, bucket16_y,
       bucket24_index, bucket24_x, bucket24_y, bucket32_index, bucket32_x, bucket32_y, label)
    for /32 view, matching your notebook's layout.

      bucket16_x     = a
      bucket16_y     = b
      bucket24_index = c
      bucket24_x     = c // 16
      bucket24_y     = c % 16
      bucket32_index = d
      bucket32_x     = d // 16
      bucket32_y     = d % 16
      label          = "a.b.c.d"
    """
    a, b, c, d = ip_to_octets(ip)
    bucket24_index = c
    bucket24_x = bucket24_index // 16
    bucket24_y = bucket24_index % 16
    bucket32_index = d
    bucket32_x = bucket32_index // 16
    bucket32_y = bucket32_index % 16
    label = f"{a}.{b}.{c}.{d}"
    return (
        a,
        b,
        bucket24_index,
        bucket24_x,
        bucket24_y,
        bucket32_index,
        bucket32_x,
        bucket32_y,
        label,
    )
