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
import logging
import os
import re
import uuid
from typing import Optional, Tuple, Dict, Any

from .settings_store import load_settings, save_settings, encrypt_password, decrypt_password

logger = logging.getLogger(__name__)


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
    """Write public CA cert to deploy/certs/client-ca.pem if directory exists."""
    for d in ("deploy/certs", "/certs"):
        if os.path.isdir(d):
            try:
                target = os.path.join(d, "client-ca.pem")
                with open(target, "w", encoding="utf-8") as f:
                    f.write(ca_pem.strip() + "\n")
                return True
            except Exception as e:
                logger.warning("Could not sync client CA to %s: %s", d, e)
    return False


def mint_client_cert(
    ca_cert_pem: str,
    ca_key_pem: str,
    device_name: str,
    password: str = "",
    days: int = 365,
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

    encryption = (
        serialization.BestAvailableEncryption(password.encode("utf-8"))
        if password
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

