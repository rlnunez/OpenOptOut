"""
Self-managed Mutual TLS (mTLS) Client Certificate Manager.

Mints a local Certificate Authority (CA) and issues per-device client
certificates bundled as PKCS#12 (.p12) files.

The CA private key, when generated in-app, is encrypted at rest using
Fernet + HKDF via encrypt_password() under settings['security']['mtls']['ca_key_enc'].
It is never logged or exposed via API.
"""

import base64
import datetime
import json
import logging
import os
import re
import uuid
from typing import Optional, Tuple, Dict, Any

from .settings_store import load_settings, save_settings, encrypt_password, decrypt_password, SETTINGS_FILE

logger = logging.getLogger(__name__)


# ── Revocation ──────────────────────────────────────────────────────────────
#
# TLS client-auth (Caddy's client_auth, Traefik's clientAuth, nginx's
# ssl_verify_client) only checks that a certificate was signed by the trusted
# CA -- none of the three support a revocation list in a way this project can
# configure declaratively and identically across all of them. So a revoked
# certificate still authenticates at the TLS layer until it expires, unless
# something downstream also checks. That something is here: the proxy forwards
# the serial of whichever certificate authenticated the connection (see
# deploy/caddy/entrypoint.sh, deploy/traefik/entrypoint.sh,
# deploy/native/nginx-openoptout.conf.example), and backend/main.py's
# reject_revoked_client_certs middleware refuses the request if that serial
# is on this list -- before any route runs.
#
# Revocations can come from two places that don't share a database, and in
# the Docker image don't share a writable directory either:
#   - the admin UI / API (settings.py), when the CA private key is generated
#     and held in-app. The api container can always write its OWN volume
#     (app_data, mounted at /data), never a host bind mount the proxies
#     read -- so this is where it writes.
#   - scripts/openoptout-mtls.sh, used when the CA key is kept OFFLINE and
#     never given to the app at all (the safer default -- see
#     docs/admin/https.md). It runs on the HOST, so it writes under
#     deploy/certs, the directory already bind-mounted read-only into the api
#     container for exactly this.
# The request-time check (is_serial_revoked, below) reads the UNION of both,
# so either path is honored regardless of which one issued or revoked the
# given certificate -- without either writer needing access to the other's
# storage.
EXTERNAL_REVOKED_PATHS = ("/certs/revoked.json", "deploy/certs/revoked.json")  # written by the host script

_revoked_cache: Dict[str, Any] = {"state": None, "forms": frozenset()}


def own_mtls_dir() -> Optional[str]:
    """
    api's own writable directory for mTLS files: an "mtls" subdirectory next
    to SETTINGS_FILE, the same anchor get_secret_key_file_path() uses, so this
    resolves correctly in both deployments without hardcoding either one's
    layout -- Docker's /data (the app_data volume, always writable from
    inside the api container, unlike a host bind mount) and a native
    install's <INSTALL_DIR>/data. Creates the subdirectory if missing.
    """
    base_dir = os.path.dirname(os.path.abspath(SETTINGS_FILE))
    d = os.path.join(base_dir, "mtls")
    try:
        os.makedirs(d, exist_ok=True)
        return d
    except OSError:
        return None


def _own_revoked_path() -> Optional[str]:
    d = own_mtls_dir()
    return os.path.join(d, "revoked.json") if d else None


def _external_revoked_path() -> Optional[str]:
    for p in EXTERNAL_REVOKED_PATHS:
        if os.path.isfile(p):
            return p
    return None


def _serial_text_forms(raw: Any) -> set:
    """Every plausible textual form (decimal, and lowercase hex with any ':' or
    whitespace separators stripped) of one certificate serial number.

    The three proxies don't all format a serial the same way when forwarding
    it (nginx's $ssl_client_serial is colon-separated hex; the Go-based
    proxies' placeholders may give decimal or hex), and the on-disk stores
    here are decimal (openssl's -set_serial and cryptography's
    random_serial_number() both work in decimal). Comparing every form either
    side could plausibly be in, rather than assuming one, means this doesn't
    depend on a proxy formatting detail no single source documents the same
    way for all three.
    """
    s = str(raw).strip()
    if not s:
        return set()
    forms = {s.lower()}
    cleaned = s.replace(":", "").replace(" ", "").replace("-", "").lower()
    forms.add(cleaned)
    try:
        forms.add(str(int(s, 10)))
    except ValueError:
        pass
    try:
        n = int(cleaned, 16)
        forms.add(str(n))
        forms.add(format(n, "x"))
    except ValueError:
        pass
    return forms


def _read_one_serials_file(path: str) -> list:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        raw = data.get("revoked_serials", []) if isinstance(data, dict) else data
        if raw is None:
            return []
        if isinstance(raw, (str, int)):
            # PowerShell's ConvertTo-Json collapses a single-element array to a
            # bare scalar unless told otherwise -- treat one serial the same as
            # a list of one, rather than iterating a string's characters below.
            return [raw]
        return list(raw)
    except Exception as e:
        logger.warning("Could not read revoked client-certificate serials from %s: %s", path, e)
        return []


def load_revoked_serial_forms() -> frozenset:
    """All textual forms of every revoked serial, unioned across whichever of
    the two revocation stores exist on this host. Cached against both files'
    mtimes (as a pair) so the per-request check (main.py) re-reads only when
    either one actually changed."""
    own_path = _own_revoked_path()
    ext_path = _external_revoked_path()
    state = []
    for p in (own_path, ext_path):
        try:
            state.append((p, os.path.getmtime(p)) if p and os.path.isfile(p) else (p, None))
        except OSError:
            state.append((p, None))
    state = tuple(state)
    if _revoked_cache["state"] == state:
        return _revoked_cache["forms"]

    raw_serials: list = []
    for p, mtime in state:
        if p and mtime is not None:
            raw_serials += _read_one_serials_file(p)
    forms = set()
    for s in raw_serials:
        forms |= _serial_text_forms(s)
    result = frozenset(forms)
    _revoked_cache.update({"state": state, "forms": result})
    return result


def write_revoked_serials_file(serials) -> bool:
    """Persist the app's own half of the revoked-serial list -- certificates
    revoked through the admin UI/API, when the CA key is held in-app. Writes
    under /data/mtls (api's own volume), never to the host-script's
    deploy/certs path, which this process can only read. Overwrites with the
    complete current list (not an append), so a certificate un-revoked here
    doesn't linger."""
    path = _own_revoked_path()
    if not path:
        return False
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"revoked_serials": sorted({str(s) for s in serials or []})}, f, indent=2)
            f.write("\n")
        return True
    except OSError as e:
        logger.warning("Could not write revoked client-certificate serials to %s: %s", path, e)
        return False


def is_serial_revoked(raw_serial: Optional[str]) -> bool:
    """True if the serial the proxy reports for this request's client
    certificate (in whatever format it used) is on the revoked list."""
    if not raw_serial:
        return False
    return bool(_serial_text_forms(raw_serial) & load_revoked_serial_forms())


def generate_ca(days: int = 3650) -> Tuple[str, str]:
    """
    Generate an RSA 4096 self-signed Certificate Authority (CA) certificate and private key.
    Returns (ca_cert_pem, ca_key_pem).
    """
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "OpenOptOut Client CA"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "OpenOptOut"),
    ])

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=days))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=False,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    ca_cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    ca_key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    return ca_cert_pem, ca_key_pem


def sync_proxy_ca_file(ca_pem: str) -> bool:
    """
    Write the public CA cert where the Caddy/Traefik containers can read it.

    In the Docker Compose image, the api container has no write access to
    /certs (the proxies mount that host directory read-only; it's where an
    admin manually places an offline-held CA or custom certs). So this also
    writes to /data/mtls, the one path the api container can always write
    (app_data, the volume it already owns) -- the proxy entrypoints read it
    back at /app-data/mtls (same volume, mounted read-only there). Returns
    True if at least one candidate was written; a write failing on one
    candidate (e.g. /certs not writable, as in Docker) doesn't stop the others.
    """
    wrote = False
    candidates = [own_mtls_dir()] + ["deploy/certs", "/certs"]
    for d in candidates:
        if not d or not os.path.isdir(d):
            continue
        try:
            target = os.path.join(d, "client-ca.pem")
            with open(target, "w", encoding="utf-8") as f:
                f.write(ca_pem.strip() + "\n")
            wrote = True
        except Exception as e:
            logger.warning("Could not sync client CA to %s: %s", d, e)
    return wrote


def mint_client_cert(
    ca_cert_pem: str,
    ca_key_pem: str,
    device_name: str,
    passphrase: Optional[str] = None,  # nosec: B107 -- optional export passphrase for PKCS#12 bundle
    days: int = 365,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Issue a client certificate for a device/browser signed by the CA,
    and package it into a PKCS#12 bundle (.p12).
    """
    from cryptography import x509
    from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12

    ca_cert = x509.load_pem_x509_certificate(ca_cert_pem.encode("utf-8"))
    ca_key = serialization.load_pem_private_key(ca_key_pem.encode("utf-8"), password=None)

    client_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    clean_name = re.sub(r"[^\w\s.-]", "", device_name).strip() or "client"
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, clean_name),
    ])

    now = datetime.datetime.now(datetime.timezone.utc)
    expires = now + datetime.timedelta(days=days)
    serial_num = x509.random_serial_number()

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(client_key.public_key())
        .serial_number(serial_num)
        .not_valid_before(now)
        .not_valid_after(expires)
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(client_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    enc_pass = passphrase if passphrase is not None else kwargs.get("password")
    encryption = (
        serialization.BestAvailableEncryption(enc_pass.encode("utf-8"))
        if enc_pass
        else serialization.NoEncryption()
    )

    p12_bytes = pkcs12.serialize_key_and_certificates(
        name=clean_name.encode("utf-8"),
        key=client_key,
        cert=cert,
        cas=[ca_cert],
        encryption_algorithm=encryption,
    )

    slug = re.sub(r"[^\w.-]", "-", clean_name).strip("-") or "client-cert"
    return {
        "device_name": clean_name,
        "serial": str(serial_num),
        "issued_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "p12_base64": base64.b64encode(p12_bytes).decode("ascii"),
        "filename": f"{slug}.p12",
    }


def get_mtls_status() -> Dict[str, Any]:
    """Return the current mTLS configuration, CA status, and issued clients."""
    from .cert_monitor import client_mtls_ca_status

    s = load_settings()
    sec = s.get("security", {}) or {}
    mtls_cfg = sec.get("mtls", {}) or {}

    env_val = os.getenv("CLIENT_MTLS", "").strip().lower()
    env_enabled = env_val in ("on", "true", "1")
    is_enabled = env_enabled or bool(mtls_cfg.get("enabled", False))

    mode = os.getenv("CLIENT_MTLS_MODE", "").strip().lower() or mtls_cfg.get("mode", "require")
    ca_status = client_mtls_ca_status()

    return {
        "enabled": is_enabled,
        "env_enabled": env_enabled,
        "mode": mode,
        "has_ca": bool(ca_status and ca_status.get("level") != "error"),
        "ca_status": ca_status,
        "can_mint_in_app": bool(mtls_cfg.get("ca_key_enc")),
        "clients": mtls_cfg.get("clients", []),
        "commands": {
            "linux": "./scripts/enable-https.sh --client-mtls",
            "windows": ".\\scripts\\enable-https.ps1 -ClientMtls",
        },
    }

