"""
Authentication provider chain.
Each provider is independently enabled via settings.
On login, providers are tried in order: LDAP → OIDC → SIP2 → local.
Super admin always falls back to local regardless.

Provider configs stored encrypted in settings file under 'auth_providers'.
"""

import logging, socket, hashlib, json, os
from typing import Optional
from dataclasses import dataclass, field

from .settings_store import load_settings, decrypt_password

log = logging.getLogger(__name__)


@dataclass
class AuthResult:
    success: bool
    provider: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    error: Optional[str] = None
    external_id: Optional[str] = None   # provider's user ID (for OIDC)
    # Claims used by the SSO sign-in policy (core/sso_policy.py):
    email_verified: Optional[bool] = None   # True/False if the IdP says; None = not stated
    hd: Optional[str] = None                # Google Workspace hosted domain claim
    groups: list = field(default_factory=list)


# ── Settings helpers ──────────────────────────────────────────────────────────

def get_provider_config(provider: str) -> dict:
    s = load_settings()
    return s.get("auth_providers", {}).get(provider, {})


def provider_enabled(provider: str) -> bool:
    return get_provider_config(provider).get("enabled", False)


# ── LDAP ──────────────────────────────────────────────────────────────────────

# ── LDAP / LDAPS ─────────────────────────────────────────────────────────────
#
# Three transport modes (settings: auth_providers.ldap.tls_mode):
#   "ldaps"    TLS from the first byte, default port 636 (ldaps://)
#   "starttls" plain connect on 389, then upgrade to TLS before any credentials
#   "none"     unencrypted — staff passwords cross the network in clear text
# Certificate verification is ALWAYS on for ldaps/starttls. The server sends each
# user's real password through this connection, so there is deliberately no
# "skip verification" switch; for an internal/enterprise CA (typical for Active
# Directory) or a self-signed home-lab cert, paste the CA certificate instead
# (auth_providers.ldap.ca_cert_pem).

LDAP_TIMEOUT = 10
_SYSTEM_CA_BUNDLE = "/etc/ssl/certs/ca-certificates.crt"


def ldap_tls_mode(cfg: dict) -> str:
    m = str(cfg.get("tls_mode", "") or "").strip().lower()
    if m in ("ldaps", "starttls", "none"):
        return m
    # Brand-new configuration: default to LDAPS.
    if not cfg.get("host") and "use_tls" not in cfg:
        return "ldaps"
    # Back-compat with older settings (host scheme + use_tls checkbox).
    if str(cfg.get("host", "")).strip().lower().startswith("ldaps://"):
        return "ldaps"
    return "starttls" if cfg.get("use_tls", True) else "none"


def ldap_uri(cfg: dict) -> str:
    """Build the connection URI from host (+ optional port) and the TLS mode.
    The TLS mode is authoritative: a stale ldap:// or ldaps:// prefix on the
    host is replaced so the selected mode is what actually happens."""
    import re
    mode = ldap_tls_mode(cfg)
    host = re.sub(r"^ldaps?://", "", str(cfg.get("host", "") or "localhost").strip(),
                  flags=re.I).rstrip("/")
    port = None
    if host.startswith("["):                      # [IPv6]:port
        h, _, rest = host[1:].partition("]")
        if rest.startswith(":") and rest[1:].isdigit():
            port = int(rest[1:])
        host = f"[{h}]"
    elif host.count(":") == 1 and host.rsplit(":", 1)[1].isdigit():
        host, p = host.rsplit(":", 1)
        port = int(p)
    if cfg.get("port"):
        port = int(cfg["port"])
    if not port:
        port = 636 if mode == "ldaps" else 389
    scheme = "ldaps" if mode == "ldaps" else "ldap"
    return f"{scheme}://{host}:{port}"


def _ldap_ca_file(pem: str) -> str:
    """python-ldap needs the CA as a file. Write the pasted PEM to a stable path
    keyed by its hash (idempotent, no temp-file litter)."""
    import hashlib, tempfile
    base = os.getenv("LDAP_CA_DIR") or os.path.join(os.getenv("DATA_DIR", "/data"), "ldap_ca")
    try:
        os.makedirs(base, exist_ok=True)
    except OSError:
        base = os.path.join(tempfile.gettempdir(), "privacyshield_ldap_ca")
        os.makedirs(base, exist_ok=True)
    path = os.path.join(base, hashlib.sha256(pem.encode()).hexdigest()[:16] + ".pem")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(pem.strip() + "\n")
    return path


def ldap_connect(cfg: dict):
    """Open a connection with the configured TLS mode, verification, and
    timeouts. StartTLS is completed before returning, so no credentials are ever
    sent before encryption is in place."""
    import ldap as ldaplib
    mode = ldap_tls_mode(cfg)
    conn = ldaplib.initialize(ldap_uri(cfg))
    conn.protocol_version = ldaplib.VERSION3
    conn.set_option(ldaplib.OPT_REFERRALS, 0)
    timeout = int(cfg.get("timeout") or LDAP_TIMEOUT)
    conn.set_option(ldaplib.OPT_NETWORK_TIMEOUT, timeout)
    conn.set_option(ldaplib.OPT_TIMEOUT, timeout)
    if mode in ("ldaps", "starttls"):
        conn.set_option(ldaplib.OPT_X_TLS_REQUIRE_CERT, ldaplib.OPT_X_TLS_DEMAND)
        pem = (cfg.get("ca_cert_pem") or "").strip()
        if pem:
            conn.set_option(ldaplib.OPT_X_TLS_CACERTFILE, _ldap_ca_file(pem))
        elif os.path.exists(_SYSTEM_CA_BUNDLE):
            conn.set_option(ldaplib.OPT_X_TLS_CACERTFILE, _SYSTEM_CA_BUNDLE)
        conn.set_option(ldaplib.OPT_X_TLS_NEWCTX, 0)   # must be the LAST TLS option
        if mode == "starttls":
            conn.start_tls_s()
    return conn


# ── Certificate checks (renewal-safe trust + expiry monitoring) ───────────────
#
# Short-lived certificates (Let's Encrypt: 90 days, renewed around day 60; the
# industry maximum drops to 47 days by 2029) are fine as long as we trust the
# ISSUING CA, not the server's own certificate: every connection re-verifies
# chain + hostname + dates, so each renewed certificate validates automatically.
# These helpers (1) stop an admin from pasting the server's own certificate,
# which would break at the next renewal, and (2) report how close the live
# certificate is to expiry, so a failed auto-renewal is caught before logins break.

def _cert_info(cert) -> dict:
    import datetime
    from cryptography import x509
    from cryptography.x509.oid import NameOID, ExtensionOID

    def label(name):
        cn = name.get_attributes_for_oid(NameOID.COMMON_NAME)
        return cn[0].value if cn else name.rfc4514_string()
    try:
        is_ca = cert.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS).value.ca
    except x509.ExtensionNotFound:
        is_ca = None
    now = datetime.datetime.now(datetime.timezone.utc)
    not_after = cert.not_valid_after_utc
    not_before = cert.not_valid_before_utc
    return {
        "subject": label(cert.subject), "issuer": label(cert.issuer),
        "is_ca": is_ca, "self_signed": cert.issuer == cert.subject,
        "not_after": not_after.isoformat(),
        "days_left": (not_after - now).days,
        "lifetime_days": max(1, (not_after - not_before).days),
    }


def classify_ca_pem(pem: str) -> dict:
    """
    Check a pasted "CA certificate". Returns {"certs": [...], "errors": [...],
    "warnings": [...]}. Errors block saving:
      - a server (leaf) certificate issued by some CA — it would stop working at
        the next renewal; paste the ISSUING CA instead;
      - an expired certificate.
    Warnings: a self-signed server certificate (fine for a home lab, but it must
    be re-pasted if regenerated), or a CA expiring within 30 days.
    """
    from cryptography import x509
    certs = x509.load_pem_x509_certificates(pem.encode())
    out = {"certs": [], "errors": [], "warnings": []}
    for c in certs:
        i = _cert_info(c)
        out["certs"].append(i)
        if i["days_left"] < 0:
            out["errors"].append(f"'{i['subject']}' expired on {i['not_after'][:10]}.")
        if i["is_ca"] is not True and not i["self_signed"]:
            out["errors"].append(
                f"'{i['subject']}' is a server certificate issued by '{i['issuer']}', not a "
                "CA certificate. It would stop working the next time the server's certificate "
                f"renews. Paste the certificate of the issuing CA ('{i['issuer']}') instead.")
        elif i["is_ca"] is False and i["self_signed"]:
            out["warnings"].append(
                f"'{i['subject']}' is a self-signed server certificate. That works, but if "
                "the server's certificate is ever regenerated you'll need to paste the new one.")
        elif 0 <= i["days_left"] <= 30:
            out["warnings"].append(f"CA '{i['subject']}' expires in {i['days_left']} days.")
    return out


def expiry_level(days_left: int, lifetime_days: int) -> str:
    """ok / warning / expired. A certificate close to expiry usually means its
    automatic renewal has stopped working. The threshold scales with lifetime:
    ~14 days for 90-day certs, ~8 days for 47-day certs, 1 day for very short ones."""
    if days_left < 0:
        return "expired"
    threshold = max(1, min(14, lifetime_days // 6))
    return "warning" if days_left <= threshold else "ok"


def ldap_cert_status(cfg: dict) -> dict:
    """Connect (with full verification) and report the live server certificate."""
    import datetime
    mode = ldap_tls_mode(cfg)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if mode == "none":
        return {"level": "none", "checked_at": now,
                "message": "Unencrypted connection — there is no certificate to check."}
    import ldap as ldaplib
    from cryptography import x509
    conn = None
    try:
        conn = ldap_connect(cfg)
        try:   # an operation completes the TLS handshake for LDAPS
            conn.simple_bind_s(cfg.get("bind_dn", ""), decrypt_password(cfg.get("bind_password_enc", "")))
        except ldaplib.INVALID_CREDENTIALS:
            pass   # TLS is still established; the certificate is readable
        der = conn.get_option(ldaplib.OPT_X_TLS_PEERCERT)
    except Exception as e:
        return {"level": "error", "checked_at": now, "message": ldap_diagnose(cfg) or ldap_tls_hint(e)}
    finally:
        if conn is not None:
            try: conn.unbind_s()
            except Exception: pass
    i = _cert_info(x509.load_der_x509_certificate(der))
    level = expiry_level(i["days_left"], i["lifetime_days"])
    msg = {
        "ok": f"Valid until {i['not_after'][:10]} ({i['days_left']} days), issued by {i['issuer']}.",
        "warning": (f"Certificate expires in {i['days_left']} days ({i['not_after'][:10]}). If it "
                    "normally renews automatically, renewal may have stopped working."),
        "expired": f"Certificate EXPIRED on {i['not_after'][:10]}. Directory sign-in will fail.",
    }[level]
    return {"level": level, "checked_at": now, "message": msg, **i}


def run_ldap_cert_check() -> dict:
    """Admin "check now": run the certificate monitor and return the LDAP result."""
    from .cert_monitor import run_cert_checks
    return run_cert_checks().get("results", {}).get("ldap") or {"level": "disabled"}


def ldap_diagnose(cfg: dict) -> str:
    """
    Classify an LDAP connection failure for the admin (test button only).
    OpenLDAP reports most TLS failures as just "Can't contact LDAP server", so for
    LDAPS we do our own TLS handshake with the same CA to say WHICH problem it is.
    """
    import re
    m = re.match(r"^ldaps?://(\[?[^\]/]+?\]?):(\d+)$", ldap_uri(cfg))
    if not m:
        return ""
    host, port = m.group(1).strip("[]"), int(m.group(2))
    timeout = int(cfg.get("timeout") or LDAP_TIMEOUT)
    if ldap_tls_mode(cfg) != "ldaps":
        try:
            socket.create_connection((host, port), timeout=timeout).close()
            return ""   # StartTLS needs an LDAP exchange first; reachability is all we can check
        except OSError as e:
            return f"Cannot reach {host}:{port} ({e}). Check the host, port, and firewall."
    msg = tls_diagnose(host, port, (cfg.get("ca_cert_pem") or "").strip(), "", timeout,
                       service="directory")
    return msg.replace("paste that CA certificate in the settings",
                       "paste that CA certificate in the LDAP settings")


def ldap_tls_hint(err) -> str:
    """Admin-facing explanation of a connection failure (test button only)."""
    info = ""
    if hasattr(err, "args") and err.args and isinstance(err.args[0], dict):
        info = str(err.args[0].get("info", "") or err.args[0].get("desc", ""))
    low = (info or str(err)).lower()
    if "certificate" in low or "verify" in low or "ssl" in low or "tls" in low:
        return ("TLS certificate could not be verified. If your directory uses an "
                "internal or self-signed CA, paste that CA certificate in the LDAP "
                f"settings. ({info or err})")
    return f"Could not connect to the directory server. ({info or err})"


def try_ldap_auth(username: str, password: str) -> AuthResult:
    """
    Authenticate via LDAP bind (Active Directory, OpenLDAP, FreeIPA, …).
    """
    cfg = get_provider_config("ldap")
    if not cfg.get("enabled"):
        return AuthResult(success=False, provider="ldap", error="disabled")

    # SECURITY: reject empty credentials BEFORE touching the directory. An LDAP
    # simple bind with a DN and an EMPTY password is an "unauthenticated bind"
    # that many servers (Active Directory by default) report as SUCCESS — which
    # would let anyone sign in as any directory user by leaving the password blank.
    if not username or not str(username).strip() or not password or not str(password).strip():
        return AuthResult(success=False, provider="ldap", error="Invalid credentials")

    conn = None
    try:
        import ldap as ldaplib   # python-ldap
        import ldap.filter       # submodule — NOT loaded by "import ldap" alone
        base_dn   = cfg.get("base_dn", "")
        bind_dn   = cfg.get("bind_dn", "")                     # service account DN
        bind_pw   = decrypt_password(cfg.get("bind_password_enc", ""))
        user_attr = cfg.get("user_attr", "sAMAccountName")     # AD default
        name_attr = cfg.get("name_attr", "displayName")
        email_attr= cfg.get("email_attr", "mail")

        conn = ldap_connect(cfg)
        conn.simple_bind_s(bind_dn, bind_pw)
        results = conn.search_s(
            base_dn, ldaplib.SCOPE_SUBTREE,
            f"({user_attr}={ldap.filter.escape_filter_chars(username.strip())})",
            [name_attr, email_attr],
        )
        entries = [(dn, attrs) for dn, attrs in results if dn]   # drop referrals
        if len(entries) != 1:
            # 0 = unknown user; >1 = ambiguous username — refuse rather than guess.
            return AuthResult(success=False, provider="ldap", error="Invalid credentials")
        user_dn, attrs = entries[0]

        conn.simple_bind_s(user_dn, password)   # verify the user's password

        def first(attr):
            v = attrs.get(attr) or [b""]
            v = v[0]
            return v.decode() if isinstance(v, bytes) else str(v)
        full_name = first(name_attr)
        email = first(email_attr) or f"{username.strip()}@{cfg.get('email_domain', 'local')}"
        return AuthResult(success=True, provider="ldap", email=email,
                          full_name=full_name or username.strip())

    except Exception as e:
        try:
            import ldap as ldaplib
            if isinstance(e, ldaplib.INVALID_CREDENTIALS):
                return AuthResult(success=False, provider="ldap", error="Invalid credentials")
        except ImportError:
            pass
        log.error("LDAP auth error: %s", e)
        # Don't leak server details to the login form; admins see them via the test button.
        return AuthResult(success=False, provider="ldap",
                          error="Directory sign-in is unavailable right now.")
    finally:
        if conn is not None:
            try:
                conn.unbind_s()
            except Exception:
                pass


# ── SIP2 ILS presets ─────────────────────────────────────────────────────────

SIP2_ILS_PRESETS = {
    "generic": {
        "label": "Generic SIP2",
        "port_plain": 6001,
        "port_tls":   6443,
        "note": "Standard SIP2 defaults. Works with most ILS systems.",
    },
    "koha": {
        "label": "Koha",
        "port_plain": 6001,
        "port_tls":   6443,
        "note": (
            "Koha supports SIP2 over TLS natively from version 22.05+. "
            "Enable in koha-conf.xml under <sip_server>. "
            "Use the borrowernumber as institution_id if your setup requires it."
        ),
    },
    "sierra": {
        "label": "Sierra (Innovative Interfaces)",
        "port_plain": 6001,
        "port_tls":   6443,
        "note": (
            "Sierra SIP2 is configured in the Sierra Admin App under "
            "Admin → SIP2 Configuration. TLS requires Sierra 5.1+. "
            "Set institution_id to your Sierra location code."
        ),
    },
    "symphony": {
        "label": "SirsiDynix Symphony",
        "port_plain": 6001,
        "port_tls":   6443,
        "note": (
            "Symphony SIP2 quirks: "
            "(1) Some versions require the SIP2 login message (93) before TLS negotiation "
            "completes — if you see connection resets, try disabling the ILS login. "
            "(2) Symphony may use a pipe character (|) or the FS character (0x1C) as field "
            "separator depending on configuration — the standard pipe is used here. "
            "(3) TLS support requires Symphony 3.5+ with the SIPServer module and a valid "
            "certificate configured in sipserver.conf. "
            "(4) The patron barcode field (AA) must exactly match the patron's ID in Symphony. "
            "(5) If BLN is returned (valid patron = No), check that the patron record is active "
            "and not blocked in Symphony. "
            "Contact SirsiDynix support for the correct institution_id value."
        ),
    },
    "polaris": {
        "label": "Polaris (Innovative)",
        "port_plain": 6001,
        "port_tls":   6443,
        "note": (
            "Polaris SIP2 is enabled in the Polaris Administration Console under "
            "System → SIP2 Server Settings. TLS requires Polaris 7.0+. "
            "Use your organization's SIP2 access account credentials for ils_login."
        ),
    },
    "evergreen": {
        "label": "Evergreen",
        "port_plain": 6001,
        "port_tls":   6443,
        "note": (
            "Evergreen SIP2 is configured in oils_sip.xml. "
            "TLS is supported via stunnel as a wrapper — configure stunnel to listen "
            "on 6443 and forward to the plain SIP2 port. "
            "Set institution_id to your Evergreen org unit shortname."
        ),
    },
    "alma": {
        "label": "Ex Libris Alma",
        "port_plain": 6001,
        "port_tls":   6443,
        "note": (
            "Alma SIP2 is configured in the Integration Profiles in Alma. "
            "The SIP2 password is set per integration profile, not per patron. "
            "Use the Alma institution code as institution_id. "
            "Contact your Ex Libris CSM for TLS certificate details."
        ),
    },
}


# ── Direct-TLS helpers (shared by LDAPS and SIP2 over TLS) ────────────────────

def tls_context(ca_pem: str = "", ca_path: str = ""):
    """TLS client context with verification ALWAYS on (chain + hostname), TLS 1.2+.
    Trusts the system roots plus an optional pasted CA (internal / self-signed)."""
    import ssl
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    if ca_pem:
        ctx.load_verify_locations(cadata=ca_pem)
    if ca_path and os.path.exists(ca_path):
        ctx.load_verify_locations(cafile=ca_path)
    return ctx


def tls_diagnose(host: str, port: int, ca_pem: str = "", ca_path: str = "",
                 timeout: int = 10, service: str = "server") -> str:
    """Explain why a direct-TLS connection fails (admin test button). '' = fine."""
    import ssl
    try:
        raw = socket.create_connection((host, port), timeout=timeout)
    except OSError as e:
        return f"Cannot reach {host}:{port} ({e}). Check the host, port, and firewall."
    try:
        with tls_context(ca_pem, ca_path).wrap_socket(raw, server_hostname=host):
            return ""
    except ssl.SSLCertVerificationError as e:
        reason = getattr(e, "verify_message", "") or str(e)
        low = reason.lower()
        if "expired" in low:
            return (f"The {service}'s certificate has EXPIRED. Renew it on the {service} "
                    "(if it normally renews automatically, that renewal has failed).")
        if "not yet valid" in low:
            return (f"The {service}'s certificate is not valid yet. Check the clock on this "
                    f"server and on the {service}.")
        if "hostname" in low or "match" in low:
            return (f"The certificate does not match the host name '{host}' ({reason}). "
                    "Use the exact name on the certificate.")
        return (f"The {service}'s certificate is not trusted ({reason}). If it comes from an "
                "internal CA or is self-signed, paste that CA certificate in the settings.")
    except ssl.SSLError as e:
        return f"TLS handshake failed ({e}). Is TLS really enabled on this port?"
    except OSError as e:
        return f"Connection failed during TLS ({e})."


def tls_peer_cert_status(host: str, port: int, ca_pem: str = "", ca_path: str = "",
                         timeout: int = 10, service: str = "server",
                         server_name: str = "", verify: bool = True) -> dict:
    """
    Report the live certificate's expiry. server_name = the name to request (SNI)
    when connecting to a different host (e.g. Caddy on the Docker network).
    verify=False ONLY reads the certificate's dates for expiry monitoring — no
    data is ever sent over that connection.
    """
    import datetime, ssl
    from cryptography import x509
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    sni = server_name or host
    try:
        raw = socket.create_connection((host, port), timeout=timeout)
        if verify:
            ctx = tls_context(ca_pem, ca_path)
        else:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        with ctx.wrap_socket(raw, server_hostname=sni) as tls:
            der = tls.getpeercert(binary_form=True)
    except Exception as e:
        msg = (tls_diagnose(host, port, ca_pem, ca_path, timeout, service) if verify and sni == host
               else f"Could not read the {service}'s certificate ({e}).")
        return {"level": "error", "checked_at": now,
                "message": msg or f"Could not connect to the {service}."}
    i = _cert_info(x509.load_der_x509_certificate(der))
    level = expiry_level(i["days_left"], i["lifetime_days"])
    msg = {
        "ok": f"Valid until {i['not_after'][:10]} ({i['days_left']} days), issued by {i['issuer']}.",
        "warning": (f"Certificate expires in {i['days_left']} days ({i['not_after'][:10]}). If it "
                    "normally renews automatically, renewal may have stopped working."),
        "expired": f"Certificate EXPIRED on {i['not_after'][:10]}. Sign-in will fail.",
    }[level]
    return {"level": level, "checked_at": now, "message": msg, **i}


# ── SIP2 (library ILS) ────────────────────────────────────────────────────────
# Plain SIP2 (TCP, port 6001) or SIP2 over TLS (typically 6443). SIP2 is plain
# ASCII, so without TLS card numbers and PINs cross the network readable.
#
# TLS verification is ALWAYS on (there is deliberately no "skip verification"
# switch): paste the ILS's CA certificate for an internal or self-signed CA.
# Responses are parsed field-by-field — never by substring search, because the
# ILS echoes the barcode back and a barcode like "BLYCQY1" would otherwise look
# like "valid patron + valid PIN".

SIP2_LOGIN_MSG   = "9300CN{login_id}|CO{password}|"
SIP2_PATRON_MSG  = "63001{date}          AO{institution}|AA{barcode}|AD{pin}|"
SIP2_DATE_FMT    = "%Y%m%d    %H%M%S"
SIP2_MAX_RESPONSE = 64 * 1024
SIP2_PATRON_FIXED_LEN = 61   # "64" + status(14) + lang(3) + date(18) + 6 counts x 4


def _sip2_checksum(msg: str) -> str:
    total = sum(ord(c) for c in msg)
    return format((-total) & 0xFFFF, '04X')


def sip2_value_safe(v) -> bool:
    """SIP2 fields are '|'-delimited and messages end at CR. Reject delimiters,
    control characters, and non-ASCII so user input can't inject fields or a
    second message into the ILS conversation."""
    return isinstance(v, str) and v != "" and all(32 <= ord(c) < 127 and c != "|" for c in v)


def _sip2_send(sock, msg: str) -> str:
    """Send a SIP2 message and read one response (bounded)."""
    msg_with_check = msg + "AY0AZ"
    msg_with_check += _sip2_checksum(msg_with_check)
    sock.sendall((msg_with_check + "\r").encode("ascii"))
    response = b""
    while not response.endswith(b"\r"):
        chunk = sock.recv(4096)
        if not chunk:
            break
        response += chunk
        if len(response) > SIP2_MAX_RESPONSE:
            raise ValueError("SIP2 response too long")
    return response.decode("ascii", errors="replace").strip()


def sip2_parse_patron_response(resp: str) -> dict:
    """
    Parse a SIP2 Patron Information Response (64) into {code: value}. Variable
    fields start after the fixed-length header and are '|'-delimited; only the
    FIRST occurrence of each code counts. Returns {} if malformed.
    """
    if not resp.startswith("64") or len(resp) < SIP2_PATRON_FIXED_LEN:
        return {}
    fields = {}
    for part in resp[SIP2_PATRON_FIXED_LEN:].split("|"):
        if len(part) >= 2 and part[:2] not in fields:
            fields[part[:2]] = part[2:]
    return fields


def _sip2_connect(host: str, port: int, timeout: int, use_tls: bool,
                  ca_pem: str = "", ca_path: str = ""):
    """Open a socket to the ILS; for SIP2 over TLS, verify chain + hostname."""
    raw_sock = socket.create_connection((host, port), timeout=timeout)
    raw_sock.settimeout(timeout)
    if not use_tls:
        return raw_sock
    return tls_context(ca_pem, ca_path).wrap_socket(raw_sock, server_hostname=host)


def sip2_endpoint(cfg: dict) -> tuple:
    use_tls = bool(cfg.get("use_tls", False))
    port = int(cfg.get("port") or (6443 if use_tls else 6001))
    return cfg.get("host", "localhost"), port, use_tls


def try_sip2_auth(barcode: str, pin: str) -> AuthResult:
    """
    Authenticate a library patron via SIP2 (message 63/64), optionally over TLS.
    ILS compatibility: Koha 22.x+, Sierra 5.x+, Polaris 7.x, Evergreen 3.x, Alma.
    """
    import ssl
    cfg = get_provider_config("sip2")
    if not cfg.get("enabled"):
        return AuthResult(success=False, provider="sip2", error="disabled")

    generic = "Invalid library card number or PIN."
    barcode = (barcode or "").strip()
    pin = pin or ""
    # Blank PIN or unsafe characters: refuse before contacting the ILS.
    if not sip2_value_safe(barcode) or not sip2_value_safe(pin) or not pin.strip():
        return AuthResult(success=False, provider="sip2", error=generic)

    host, port, use_tls = sip2_endpoint(cfg)
    institution  = cfg.get("institution_id", "")
    ils_login    = cfg.get("ils_login", "")
    ils_password = decrypt_password(cfg.get("ils_password_enc", ""))
    timeout      = int(cfg.get("timeout_seconds", 10))
    if use_tls and cfg.get("verify_cert") is False:
        log.warning("SIP2: legacy verify_cert=false is ignored — verification is always "
                    "on. Paste the ILS CA certificate if sign-in fails.")

    try:
        from datetime import datetime
        date_str = datetime.utcnow().strftime(SIP2_DATE_FMT)
        sock = _sip2_connect(host, port, timeout, use_tls,
                             (cfg.get("ca_cert_pem") or "").strip(), cfg.get("ca_cert_path") or "")
        try:
            if ils_login:
                resp = _sip2_send(sock, SIP2_LOGIN_MSG.format(login_id=ils_login, password=ils_password))
                if not resp.startswith("941"):          # 941 = login ok
                    log.error("SIP2: ILS service-account login failed")
                    return AuthResult(success=False, provider="sip2",
                                      error="Library sign-in is unavailable right now.")
            resp = _sip2_send(sock, SIP2_PATRON_MSG.format(
                date=date_str, institution=institution, barcode=barcode, pin=pin))
        finally:
            try: sock.close()
            except Exception: pass

        fields = sip2_parse_patron_response(resp)
        if fields.get("BL") != "Y" or fields.get("CQ") != "Y":
            # Same message whether the card or the PIN was wrong (no card enumeration).
            return AuthResult(success=False, provider="sip2", error=generic)

        name = fields.get("AE", "").strip()
        email = f"{barcode}@{cfg.get('email_domain', 'library.local')}"
        log.info("SIP2%s auth OK: host=%s:%s", "S" if use_tls else "", host, port)
        return AuthResult(success=True, provider="sip2", email=email,
                          full_name=name or f"Patron {barcode}", external_id=barcode)

    except (ssl.SSLError, ssl.SSLCertVerificationError) as e:
        log.error("SIP2 TLS error (%s:%s): %s", host, port, e)
    except (socket.timeout, TimeoutError):
        log.error("SIP2 timeout (%s:%s)", host, port)
    except OSError as e:
        log.error("SIP2 connection error (%s:%s): %s", host, port, e)
    except Exception as e:
        log.error("SIP2 auth error: %s", e)
    # Details go to the log / admin test button, not the patron login form.
    return AuthResult(success=False, provider="sip2", error="Library sign-in is unavailable right now.")


def sip2_cert_status(cfg: dict) -> dict:
    import datetime
    host, port, use_tls = sip2_endpoint(cfg)
    if not use_tls:
        return {"level": "none", "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "message": "Unencrypted SIP2 — there is no certificate to check."}
    return tls_peer_cert_status(host, port, (cfg.get("ca_cert_pem") or "").strip(),
                                cfg.get("ca_cert_path") or "", int(cfg.get("timeout_seconds", 10)),
                                service="ILS")


# ── Generic OIDC (covers Google, Microsoft, Okta, Auth0, Keycloak, etc.) ──────

def get_oidc_login_url(provider_key: str, redirect_uri: str, state: str) -> Optional[str]:
    """
    Build the authorization URL to redirect the user to for OIDC login.
    Called by the /api/auth/oidc/{provider}/login endpoint.
    """
    cfg = get_provider_config(provider_key)
    if not cfg.get("enabled"):
        return None

    import urllib.parse
    params = {
        "response_type": "code",
        "client_id":     cfg["client_id"],
        "redirect_uri":  redirect_uri,
        "scope":         cfg.get("scope", "openid email profile"),
        "state":         state,
    }
    # Google: if exactly one allowed domain is configured, send it as the `hd`
    # hint so the account picker shows the right accounts. This is only a UI
    # hint — the hd claim is ENFORCED server-side by core/sso_policy.py.
    domains = [d.strip().lower() for d in str(cfg.get("allowed_domains", "")).split(",") if d.strip()]
    if provider_key == "google" and len(domains) == 1:
        params["hd"] = domains[0]
    auth_url = cfg.get("authorization_endpoint") or _discover_endpoint(cfg, "authorization_endpoint")
    return f"{auth_url}?{urllib.parse.urlencode(params)}"


def exchange_oidc_code(provider_key: str, code: str, redirect_uri: str) -> AuthResult:
    """
    Exchange authorization code for tokens and extract user info.
    Handles Google, Microsoft, and generic OIDC providers.
    """
    cfg = get_provider_config(provider_key)
    if not cfg.get("enabled"):
        return AuthResult(success=False, provider=provider_key, error="disabled")

    try:
        import httpx

        client_id     = cfg["client_id"]
        client_secret = decrypt_password(cfg.get("client_secret_enc", ""))
        token_endpoint = cfg.get("token_endpoint") or _discover_endpoint(cfg, "token_endpoint")
        userinfo_endpoint = cfg.get("userinfo_endpoint") or _discover_endpoint(cfg, "userinfo_endpoint")

        # Exchange code for tokens
        resp = httpx.post(token_endpoint, data={
            "grant_type":    "authorization_code",
            "code":          code,
            "redirect_uri":  redirect_uri,
            "client_id":     client_id,
            "client_secret": client_secret,
        }, timeout=10)
        resp.raise_for_status()
        tokens = resp.json()

        access_token = tokens.get("access_token")
        if not access_token:
            return AuthResult(success=False, provider=provider_key, error="No access token returned")

        # Fetch user info
        user_resp = httpx.get(userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
        user_resp.raise_for_status()
        user_info = user_resp.json()

        email     = user_info.get("email")
        from_fallback = False
        if not email:
            # upn / preferred_username are NOT verified email claims — accept them
            # only as identifiers, and mark the email unverified for the policy.
            email = user_info.get("upn") or user_info.get("preferred_username")
            from_fallback = True
        full_name = user_info.get("name") or user_info.get("displayName") or \
                    f"{user_info.get('given_name','')} {user_info.get('family_name','')}".strip()
        ext_id    = user_info.get("sub") or user_info.get("oid")

        if not email:
            return AuthResult(success=False, provider=provider_key, error="No email returned from provider")

        ev = user_info.get("email_verified")
        if isinstance(ev, str):
            ev = ev.strip().lower() == "true"
        groups = user_info.get("groups") or []
        if isinstance(groups, str):
            groups = [groups]
        return AuthResult(
            success=True, provider=provider_key,
            email=email, full_name=full_name or email,
            external_id=ext_id,
            email_verified=(None if from_fallback else (ev if isinstance(ev, bool) else None)),
            hd=user_info.get("hd"),
            groups=[str(g) for g in groups],
        )

    except Exception as e:
        log.error(f"OIDC exchange error ({provider_key}): {e}")
        return AuthResult(success=False, provider=provider_key, error=str(e))


def _discover_endpoint(cfg: dict, field: str) -> str:
    """Fetch OIDC discovery document and cache endpoints."""
    discovery_url = cfg.get("discovery_url")
    if not discovery_url:
        raise ValueError(f"No {field} or discovery_url configured")
    try:
        import httpx
        doc = httpx.get(f"{discovery_url.rstrip('/')}/.well-known/openid-configuration", timeout=10).json()
        return doc[field]
    except Exception as e:
        raise ValueError(f"OIDC discovery failed: {e}")


# ── Well-known OIDC presets ───────────────────────────────────────────────────

OIDC_PRESETS = {
    "google": {
        "label":             "Google Workspace",
        "discovery_url":     "https://accounts.google.com",
        "scope":             "openid email profile",
        "note":              "Create OAuth2 credentials at console.cloud.google.com. Set authorized redirect URI to https://yourdomain/api/auth/oidc/google/callback",
    },
    "microsoft": {
        "label":             "Microsoft Entra ID (Azure AD)",
        "discovery_url":     "https://login.microsoftonline.com/{tenant_id}/v2.0",
        "scope":             "openid email profile User.Read",
        "note":              "Register an app at portal.azure.com → Azure Active Directory → App registrations. Replace {tenant_id} with your directory tenant ID.",
    },
    "okta": {
        "label":             "Okta",
        "discovery_url":     "https://{your-domain}.okta.com/oauth2/default",
        "scope":             "openid email profile",
        "note":              "Create an OIDC Web Application in your Okta admin console.",
    },
    "auth0": {
        "label":             "Auth0",
        "discovery_url":     "https://{your-domain}.auth0.com",
        "scope":             "openid email profile",
        "note":              "Create a Regular Web Application in your Auth0 dashboard.",
    },
    "keycloak": {
        "label":             "Keycloak (self-hosted)",
        "discovery_url":     "https://{your-domain}/realms/{realm-name}",
        "scope":             "openid email profile",
        "note":              "Create a client in your Keycloak realm with 'openid-connect' protocol.",
    },
    "custom": {
        "label":             "Custom OIDC provider",
        "scope":             "openid email profile",
        "note":              "Enter your provider's discovery URL or individual endpoints manually.",
    },
}
