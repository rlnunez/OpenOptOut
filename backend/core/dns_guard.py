"""
DNS-rebinding and SSRF protection for outbound HTTP requests and browser sessions.

Provides:
  - is_public_ip(addr): Verifies that an IP is not private, loopback, link-local,
    reserved, multicast, unspecified, CGNAT, or IPv4-mapped private.
  - public_host(host): Resolves host once and asserts all resolved addresses are public.
  - safe_dns_context(): Context manager that hooks socket.getaddrinfo to block
    DNS-rebinding attacks where a hostname resolves to a public IP during pre-checks
    but rebinds to an internal/private address at socket connection time.
  - assert_safe_url(url): The one check every admin/plugin-configured-URL call site
    in this app needs before making a request — used to be copy-pasted (with small,
    drifting variations) into webhooks.py, auth_providers.py, registry_sync.py,
    routers/saml.py, and others. Centralized so a fix here fixes all of them.
"""

import contextlib
import ipaddress
import socket
from typing import Optional, Union

# Known cloud-metadata endpoints — is_public_ip's is_link_local check already
# catches the 169.254.0.0/16 ones once resolved, but checking the raw host
# first means a response never even triggers a DNS lookup, and catches the
# cloud-specific DNS names (which may not always resolve the same way).
CLOUD_METADATA_HOSTS = frozenset({
    "169.254.169.254", "169.254.170.2", "metadata.google.internal",
    "metadata", "instance-data", "100.100.100.200",
})


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


def assert_safe_url(url: str, schemes=("http", "https"), allow_local: bool = False) -> str:
    """Parse an admin/plugin-configured URL and assert it's safe to fetch right
    now: an allowed scheme, a non-empty host, not a known cloud-metadata
    address, and resolves only to public IPs (public_host). Raises ValueError
    with a plain-language reason on any failure; returns the lowercased
    hostname on success.

    This only covers the pre-flight check — callers must still wrap the
    actual request in safe_dns_context() to catch DNS-rebinding between this
    check and the connection itself, and apply any app-specific restriction
    (e.g. "must also be on this broker's own domain") on top."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower().strip()
    if scheme not in schemes:
        raise ValueError("unsupported URL scheme")
    host = (parsed.hostname or "").lower().strip()
    if not host:
        raise ValueError("missing host in address")
    if host in CLOUD_METADATA_HOSTS or host.startswith("169.254."):
        raise ValueError("prohibited address (cloud metadata)")
    if allow_local and host in ("127.0.0.1", "localhost"):
        return host
    if not public_host(host):
        raise ValueError("prohibited address (private or non-public host)")
    return host


@contextlib.contextmanager
def safe_dns_context(allow_local: bool = False):
    """Context manager intercepting socket.getaddrinfo to prevent DNS-rebinding attacks.
    Every IP resolved during the block is validated against is_public_ip; resolves to
    internal or non-public addresses raise ValueError immediately, aborting the connection."""
    real_getaddrinfo = socket.getaddrinfo

    def safe_getaddrinfo(host, port, *args, **kwargs):
        res = real_getaddrinfo(host, port, *args, **kwargs)
        if allow_local and str(host).lower() in ("127.0.0.1", "localhost"):
            return res
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

