"""
First-run setup wizard API.

Drives the guided post-admin-creation wizard (roadmap item 11). All steps are
strongly-prompted but SKIPPABLE. The wizard writes to the same settings store the
Settings pages use, so anything set here is immediately live and editable later.

Steps:
  1. database  — SQLite (same machine) vs PostgreSQL (dedicated/remote host).
  2. email     — deployment MODE (shared inbox | per-user), the provider/transport,
                 and an "advanced: separate admin SMTP" toggle. Skippable with a
                 loud warning (opt-outs silently do nothing without email).
  3. deployment — how is HTTPS handled here: OpenOptOut's own front door (Docker, bare metal or a VM — doesn't matter which; Caddy, Traefik, or Cloudflare Tunnel, and for Caddy/Traefik a certificate from Let's Encrypt, Let's Encrypt via Cloudflare DNS, or none yet), a native install's own certbot/win-acme setup (no containers), something that already terminates TLS in front of OpenOptOut either way, or not decided yet? Recorded so the app gives the right guidance and never suggests something that would fight an existing reverse proxy for ports 80/443.
  4. branding  — optional/cosmetic (system name, logo, colors).
  5. summary   — what's configured vs skipped; mark the wizard complete.

State: a `wizard` block in settings — {completed: bool, steps: {name: "done"|"skipped"}}.
The frontend uses it to resume where the operator left off and to show the summary.
"""

import json
import os
import base64
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List
from cryptography.fernet import Fernet

from ..models.database import get_db, User
from ..core.auth import get_current_user
from ..core.settings_store import load_settings, SETTINGS_FILE, get_secret_key

router = APIRouter(prefix="/api/wizard", tags=["wizard"])


def _admin(user: User):
    if not user.is_super_admin:
        raise HTTPException(403, "Super admin access required")


def _fernet() -> Fernet:
    raw = get_secret_key()
    # Repeat the key until it fills 32 bytes. Identical to the old
    # `(raw * 4)[:32]` for keys of 8+ chars (existing data still decrypts),
    # but no longer crashes on a shorter SECRET_KEY.
    _kb = raw.encode() or b"\0"
    padded = (_kb * (32 // len(_kb) + 1))[:32]
    return Fernet(base64.urlsafe_b64encode(padded))


def _encrypt(v: str) -> str:
    return _fernet().encrypt(v.encode()).decode() if v else ""


def _load() -> dict:
    return load_settings()


def _save(data: dict):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _wizard_state(s: dict) -> dict:
    return s.get("wizard", {"completed": False, "steps": {}})


def _mark_step(step: str, status: str):
    s = _load()
    wiz = _wizard_state(s)
    wiz.setdefault("steps", {})[step] = status
    s["wizard"] = wiz
    _save(s)
    return wiz


# ── State ─────────────────────────────────────────────────────────────────────

@router.get("/email-providers")
def list_email_providers(db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)):
    """
    List email-provider plugins available to choose in the wizard's email step —
    the built-in ones plus any the operator has uploaded. Lets someone bring
    their own provider (Proton, Apple, etc.) by uploading a plugin, then use it
    right here during setup.
    """
    _admin(user)
    from ..models.database import InstalledPlugin
    out = []
    for p in db.query(InstalledPlugin).all():
        try:
            manifest = json.loads(p.manifest_json or "{}")
        except Exception:
            manifest = {}
        if "email_provider" in (manifest.get("hooks") or []):
            out.append({
                "plugin_id": p.plugin_id,
                "name": p.name,
                "enabled": bool(p.enabled),
                "author": p.author,
                "description": p.description,
            })
    return {"providers": out}


@router.get("/state")
def get_state(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Current wizard progress — what's done/skipped, and whether email is set
    (so the summary can warn if it isn't)."""
    _admin(user)
    s = _load()
    wiz = _wizard_state(s)
    email = s.get("email", {})
    email_configured = bool(email.get("mode")) and (
        email.get("provider") or email.get("smtp_host"))
    return {
        "completed": wiz.get("completed", False),
        "steps": wiz.get("steps", {}),
        "email_configured": email_configured,
        "db_kind": s.get("database", {}).get("kind", "sqlite"),
        "reverse_proxy": s.get("deployment", {}).get("reverse_proxy", "unset"),
    }


# ── Step 1: Database ──────────────────────────────────────────────────────────

class DatabaseStep(BaseModel):
    kind: str                       # "sqlite" | "postgres"
    # postgres only:
    host: Optional[str] = None
    port: Optional[int] = 5432
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    sslmode: Optional[str] = "prefer"


@router.post("/database")
def save_database(body: DatabaseStep, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """
    Save the database choice. SQLite is assumed same-machine (no connection
    details). PostgreSQL requires a host — it is NOT assumed to be localhost;
    the operator points at a dedicated/remote server. The password is encrypted.

    NOTE: changing the DB target takes effect on next restart (the app reads DB
    config at startup) — the wizard records the choice and the summary tells the
    operator a restart is needed if they changed it.
    """
    _admin(user)
    if body.kind not in ("sqlite", "postgres"):
        raise HTTPException(400, "kind must be 'sqlite' or 'postgres'")
    s = _load()
    if body.kind == "postgres":
        if not body.host or not body.database or not body.username:
            raise HTTPException(400, "PostgreSQL requires host, database, and username "
                                     "(a dedicated/remote server — not assumed localhost)")
        s["database"] = {
            "kind": "postgres",
            "host": body.host.strip(), "port": body.port or 5432,
            "database": body.database.strip(), "username": body.username.strip(),
            "password_enc": _encrypt(body.password or ""),
            "sslmode": body.sslmode or "prefer",
        }
    else:
        s["database"] = {"kind": "sqlite"}
    _save(s)
    _mark_step("database", "done")
    return {"ok": True, "kind": body.kind,
            "restart_required": body.kind == "postgres"}


# ── Step 2: Email ─────────────────────────────────────────────────────────────

class EmailStep(BaseModel):
    mode: str                          # "shared" | "per_user"
    provider: Optional[str] = None     # provider_key of an installed email plugin, or "smtp"
    # For the shared/admin account when using generic SMTP (not OAuth):
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = 587
    imap_host: Optional[str] = None
    imap_port: Optional[int] = 993
    username: Optional[str] = None
    password: Optional[str] = None
    tls: Optional[str] = "starttls"
    from_address: Optional[str] = None
    # Advanced: separate admin SMTP (off by default)
    separate_admin_smtp: bool = False
    admin_smtp_host: Optional[str] = None
    admin_smtp_port: Optional[int] = 587
    admin_username: Optional[str] = None
    admin_password: Optional[str] = None


@router.post("/email")
def save_email(body: EmailStep, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """
    Save the email deployment mode + transport. Preserves the ability to switch
    modes later (an admin setting), which is what the grace-period migration acts
    on. OAuth providers store their credentials via their own connect flow; this
    endpoint stores the generic-SMTP account details (encrypted) when that's the
    chosen transport.
    """
    _admin(user)
    if body.mode not in ("shared", "per_user"):
        raise HTTPException(400, "mode must be 'shared' or 'per_user'")
    s = _load()
    from ..core.email_grace import maybe_snapshot_grace_period
    maybe_snapshot_grace_period(
        current_settings=s,
        new_email_config=body.model_dump(),
        new_mode=body.mode,
    )
    email = s.get("email", {})
    email["mode"] = body.mode
    email["provider"] = body.provider or ""
    email["separate_admin_smtp"] = bool(body.separate_admin_smtp)
    # Generic-SMTP account details (only meaningful for the smtp transport / shared).
    if body.provider == "smtp" or body.smtp_host:
        email.update({
            "smtp_host": (body.smtp_host or "").strip(),
            "smtp_port": body.smtp_port or 587,
            "imap_host": (body.imap_host or "").strip(),
            "imap_port": body.imap_port or 993,
            "smtp_username": (body.username or "").strip(),
            "smtp_password_enc": _encrypt(body.password or ""),
            "smtp_tls": body.tls or "starttls",
            "from_address": (body.from_address or "").strip(),
        })
    if body.separate_admin_smtp:
        email["admin_smtp"] = {
            "host": (body.admin_smtp_host or "").strip(),
            "port": body.admin_smtp_port or 587,
            "username": (body.admin_username or "").strip(),
            "password_enc": _encrypt(body.admin_password or ""),
        }
    s["email"] = email
    _save(s)
    _mark_step("email", "done")
    return {"ok": True, "mode": body.mode}


# ── Step 3: Branding ──────────────────────────────────────────────────────────

class BrandingStep(BaseModel):
    system_name: Optional[str] = None
    primary_color: Optional[str] = None
    # No logo_url field here on purpose: the actual logo is a file, uploaded
    # separately via POST /api/branding/logo (the same endpoint Settings uses,
    # and what the wizard's drag-and-drop now calls directly). GET
    # /api/branding/config always derives logo_url from whether that file
    # exists on disk — it never reads a stored string — so a logo_url here
    # would only ever be silently ignored dead data.


@router.post("/branding")
def save_branding(body: BrandingStep, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """Optional cosmetic branding. Writes to the same branding block Settings uses.
    The logo itself is handled by POST /api/branding/logo, not here."""
    _admin(user)
    s = _load()
    b = s.get("branding", {})
    if body.system_name is not None:
        b["system_name"] = body.system_name.strip()
    if body.primary_color is not None:
        b["primary_color"] = body.primary_color.strip()
    s["branding"] = b
    _save(s)
    _mark_step("branding", "done")
    return {"ok": True}


# ── Step 3.5: Deployment / reverse proxy ────────────────────────────────────
#
# This does NOT start or configure anything by itself — whether the managed path means a sibling Docker container (Caddy or Traefik) or a native install's own nginx/systemd setup, either needs an action outside the running app (a restart, or a one-time certbot/win-acme run). This step only RECORDS which situation the deployment is in, so the app can:
#   - stop nagging admins who already have HTTPS handled by something else (and, importantly, never suggest a step that would try to bind ports 80/443 that an existing proxy is already using), and
#   - point admins who chose "managed" or "native" at the right script/doc until the site is actually reached over https.
#
# Docker vs. native is the real technical fork here — NOT deployment "size". Docker Engine running on a VM (the common enterprise pattern) or on bare metal behaves identically from OpenOptOut's side; "native" means no containers at all (systemd + nginx + certbot on Linux, or a Windows Service + IIS + win-acme on Windows) — see docs/NATIVE_INSTALL.md.

class DeploymentStep(BaseModel):
    reverse_proxy: str                  # "managed" | "native" | "external" | "none"
    domain: Optional[str] = None        # optional, cosmetic — shown back in the summary
    # Only for "managed": which front door, then (Caddy/Traefik only) where the certificate comes from. Recorded so the summary can hand back the exact enable-https command; nothing is started from here.
    front_door: Optional[str] = None    # "caddy" | "traefik" | "cloudflare-tunnel"
    certificate: Optional[str] = None   # "letsencrypt" | "cloudflare-dns" | "none"
    rate_limit: Optional[bool] = None   # Caddy/Traefik: per-visitor limits (default on)
    cloudflare_proxy: Optional[bool] = None  # Caddy/Traefik + cloudflare-dns only


FRONT_DOORS = ("caddy", "traefik", "cloudflare-tunnel")
CERTIFICATES = ("letsencrypt", "cloudflare-dns", "none")

# Shown wherever Cloudflare Tunnel is chosen. Kept here so the API, summary and UI say the same thing.
CLOUDFLARE_PROXY_WARNING = (
    "Cloudflare proxy: Cloudflare decrypts all traffic to this site, so its servers can see "
    "everything people send and receive here (names, home addresses, phone numbers, emails, "
    "sign-in tokens). In the Cloudflare dashboard, set the DNS record to Proxied and SSL/TLS "
    "to Full (strict), and forward ports 80/443 to this server — only Cloudflare is let in.")

TUNNEL_WARNING = ("Cloudflare Tunnel: Cloudflare decrypts all traffic to this site, so its "
                  "servers can see everything people send and receive here (names, home "
                  "addresses, phone numbers, emails, sign-in tokens). For no open ports "
                  "without that, use Caddy or Traefik with Let's Encrypt via Cloudflare DNS.")


def enable_https_commands(front_door: str, certificate: str, domain: str = "",
                          rate_limit: bool = True, cloudflare_proxy: bool = False) -> dict:
    """The exact host commands for a managed deployment's choices, for both Linux/macOS and Windows. Domain is only included if it's plainly a hostname list (it ends up in a command the admin copies into a shell)."""
    import re
    fd = front_door if front_door in FRONT_DOORS else "caddy"
    sh = ["./scripts/enable-https.sh", "--proxy", fd]
    ps = [".\\scripts\\enable-https.ps1", "-Proxy", fd]
    if fd != "cloudflare-tunnel":
        cert = certificate if certificate in CERTIFICATES else "letsencrypt"
        sh += ["--cert", cert]; ps += ["-Cert", cert]
        if cloudflare_proxy and cert == "cloudflare-dns":
            sh += ["--cloudflare-proxy"]; ps += ["-CloudflareProxy"]
        if not rate_limit:
            sh += ["--no-rate-limit"]; ps += ["-NoRateLimit"]
    d = (domain or "").replace(" ", "")
    if d and re.fullmatch(r"[A-Za-z0-9.-]+(,[A-Za-z0-9.-]+)*", d):
        sh += ["--domain", d]; ps += ["-Domain", d]
    return {"linux": " ".join(sh), "windows": " ".join(ps)}


@router.post("/deployment")
def save_deployment(body: DeploymentStep, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """
    reverse_proxy:
      managed  — running via Docker (bare metal or a VM — Docker doesn't care which), nothing else already on ports 80/443. Let OpenOptOut's own Caddy (default) or Traefik container get and renew certificates. Guidance keeps pointing at scripts/enable-https.sh (Linux/macOS) or .ps1 (Windows), run on the host, until HTTPS is live.
      native   — no containers at all: OpenOptOut runs as a native process
                 (systemd on Linux, a Windows Service on Windows). HTTPS is
                 handled directly on the host too — certbot + nginx on Linux,
                 win-acme + IIS on Windows. Guidance points at
                 scripts/enable-https-native.sh (Linux) or docs/NATIVE_INSTALL.md
                 (Windows, since IIS/win-acme setup isn't reasonably a single
                 script) until HTTPS is live.
      external — something else (a load balancer, another team's reverse
                 proxy) already terminates TLS in front of OpenOptOut,
                 whether OpenOptOut itself runs in Docker or natively. The
                 plain-HTTP nag is suppressed for this choice: if that's true,
                 people are already reaching the site over https and the
                 browser-side check confirms it; if the admin is wrong, it's a
                 deliberate call they made, not something for the wizard to
                 second-guess.
      none     — genuinely internal/plaintext (e.g. an isolated LAN). Accepted,
                 but the warning stays since nothing external verified it's safe.
    """
    _admin(user)
    if body.reverse_proxy not in ("managed", "native", "external", "none"):
        raise HTTPException(400, "reverse_proxy must be 'managed', 'native', 'external', or 'none'")
    deployment = {
        "reverse_proxy": body.reverse_proxy,
        "domain": (body.domain or "").strip()[:255],
    }
    if body.reverse_proxy == "managed":
        front_door = body.front_door or "caddy"
        if front_door not in FRONT_DOORS:
            raise HTTPException(400, "front_door must be 'caddy', 'traefik', or 'cloudflare-tunnel'")
        deployment["front_door"] = front_door
        if front_door != "cloudflare-tunnel":
            certificate = body.certificate or "letsencrypt"
            if certificate not in CERTIFICATES:
                raise HTTPException(400, "certificate must be 'letsencrypt', 'cloudflare-dns', or 'none'")
            deployment["certificate"] = certificate
            deployment["rate_limit"] = body.rate_limit is not False
            if body.cloudflare_proxy and certificate != "cloudflare-dns":
                raise HTTPException(400, "Cloudflare's proxy needs the 'cloudflare-dns' certificate option")
            deployment["cloudflare_proxy"] = bool(body.cloudflare_proxy)
    s = _load()
    s["deployment"] = deployment
    _save(s)
    _mark_step("deployment", "done")
    return {"ok": True}


# ── Skip a step / finish ──────────────────────────────────────────────────────

class SkipStep(BaseModel):
    step: str


@router.post("/skip")
def skip_step(body: SkipStep, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """Record that a step was skipped (all steps are skippable)."""
    _admin(user)
    if body.step not in ("database", "email", "deployment", "branding"):
        raise HTTPException(400, "unknown step")
    _mark_step(body.step, "skipped")
    return {"ok": True, "skipped": body.step}


@router.post("/complete")
def complete(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Mark the wizard finished. Returns a summary of what was configured vs skipped,
    including a warning if email was skipped (opt-outs won't work) or the DB was
    changed (restart needed).
    """
    _admin(user)
    s = _load()
    wiz = _wizard_state(s)
    wiz["completed"] = True
    s["wizard"] = wiz
    _save(s)

    steps = wiz.get("steps", {})
    email = s.get("email", {})
    email_ok = bool(email.get("mode")) and (email.get("provider") or email.get("smtp_host"))
    reverse_proxy = s.get("deployment", {}).get("reverse_proxy", "unset")
    warnings = []
    if not email_ok:
        warnings.append("Email is not configured — opt-outs will not be sent until "
                        "you set it up in Settings → Email.")
    if s.get("database", {}).get("kind") == "postgres":
        warnings.append("PostgreSQL was configured — restart the app for the new "
                        "database connection to take effect.")
    deployment = s.get("deployment", {})
    commands = None
    if reverse_proxy == "managed":
        front_door = deployment.get("front_door", "caddy")
        certificate = deployment.get("certificate", "letsencrypt")
        commands = enable_https_commands(front_door, certificate, deployment.get("domain", ""),
                                         rate_limit=deployment.get("rate_limit", True),
                                         cloudflare_proxy=deployment.get("cloudflare_proxy", False))
        warnings.append("Your front door isn't on yet: run the command shown below on the server, "
                        "then restart the containers.")
        if front_door == "cloudflare-tunnel":
            warnings.append(TUNNEL_WARNING)
        elif deployment.get("cloudflare_proxy"):
            warnings.append(CLOUDFLARE_PROXY_WARNING)
        elif certificate == "none":
            warnings.append("You chose no certificate for now, so traffic stays unencrypted. Run the "
                            "same script again later and pick Let's Encrypt or Cloudflare DNS.")
    elif reverse_proxy == "native":
        warnings.append("Run scripts/enable-https-native.sh (Linux) or follow the Windows steps "
                        "in docs/NATIVE_INSTALL.md (IIS + win-acme) to turn on HTTPS for this "
                        "native install.")
    elif reverse_proxy == "none":
        warnings.append("No reverse proxy is protecting this deployment — traffic is "
                        "unencrypted. Put it behind HTTPS before real people use it.")
    return {
        "ok": True,
        "steps": steps,
        "email_configured": email_ok,
        "reverse_proxy": reverse_proxy,
        "enable_https_commands": commands,
        "warnings": warnings,
    }
