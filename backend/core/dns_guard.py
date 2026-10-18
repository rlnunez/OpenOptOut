"""
DNS-rebinding and SSRF protection for outbound HTTP requests and browser sessions.

Provides:
  - is_public_ip(addr): Verifies that an IP is not private, loopback, link-local,
    reserved, multicast, unspecified, CGNAT, or IPv4-mapped private.
  - public_host(host): Resolves host once and asserts all resolved addresses are public.
  - safe_dns_context(): Context manager that hooks socket.getaddrinfo to block
    DNS-rebinding attacks where a hostname resolves to a public IP during pre-checks
    but rebinds to an internal/private address at socket connection time.
"""

import contextlib
import ipaddress
import socket
from typing import Optional, Union


def is_public_ip(addr: Union[str, ipaddress.IPv4Address, ipaddress.IPv6Address]) -> bool:
    """True if addr is a valid public IP; False for private, loopback, link-local,
    reserved, multicast, unspecified, 0.0.0.0/8, or 100.64.0.0/10."""
    try:
        if isinstance(addr, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
            ip = addr
        else:
            ip = ipaddress.ip_address(str(addr).strip())
    except Exception:
        return False

    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped

    if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
            or ip.is_multicast or ip.is_unspecified):
        return False

    if ip.version == 4:
        val = int(ip)
        # 0.0.0.0/8 (current network / wildcard)
        if (val >> 24) == 0:
            return False
        # 100.64.0.0/10 (CGNAT / Shared Address Space)
        if (val >> 22) == 401:
            return False
        # 255.255.255.255 (broadcast)
        if val == 0xFFFFFFFF:
            return False

    return True


def public_host(host: str) -> bool:
    """True if all addresses for host resolve to public IPs.
    Fails closed on resolution errors or empty answers."""
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except Exception:
        return False
    if not infos:
        return False
    for *_, addr in infos:
        try:
            if not is_public_ip(addr[0]):
                return False
        except Exception:
            return False
    return True


@contextlib.contextmanager
def safe_dns_context():
    """Context manager intercepting socket.getaddrinfo to prevent DNS-rebinding attacks.
    Every IP resolved during the block is validated against is_public_ip; resolves to
    internal or non-public addresses raise ValueError immediately, aborting the connection."""
    real_getaddrinfo = socket.getaddrinfo

    def safe_getaddrinfo(host, port, *args, **kwargs):
        res = real_getaddrinfo(host, port, *args, **kwargs)
        for *_, addr in res:
            try:
                if not is_public_ip(addr[0]):
                    raise ValueError(f"Host {host} resolves to non-public IP: {addr[0]}")
            except ValueError:
                raise
            except Exception:
                pass
        return res

    socket.getaddrinfo = safe_getaddrinfo
    try:
        yield
    finally:
        socket.getaddrinfo = real_getaddrinfo

