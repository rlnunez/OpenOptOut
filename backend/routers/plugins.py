"""
Plugin management API (super admin only, except the upload wizard).

Plugins live at <plugins root>/<type>/<id>/ (see plugins/layout.py). Uploads
and installs put them there based on the manifest's type.

Endpoints:
  GET    /api/plugins                 — list installed plugins + status
  GET    /api/plugins/types           — plugin types and their folders
  GET    /api/plugins/available       — discover plugins on disk not yet registered
  POST   /api/plugins/install         — register a discovered plugin (disabled)
  POST   /api/plugins/{id}/enable     — grant permissions + enable + launch
  POST   /api/plugins/{id}/disable    — stop + disable
  DELETE /api/plugins/{id}            — uninstall (stop + remove registration)
  GET    /api/plugins/{id}/audit      — audit log for a plugin
  GET    /api/plugins/status          — manager + sandbox status
  GET    /api/plugins/permissions     — permission catalog (for the UI)
  POST   /api/plugins/upload/inspect  — check a zip: its type and where it would go
  POST   /api/plugins/upload          — upload a plugin zip bundle

The two upload endpoints are open to super admins and to users a super admin
has granted can_upload_plugins. Uploaded plugins are always installed
disabled; enabling one (granting its permissions) stays super-admin only.
"""

import os
import json
import stat
import shutil
import zipfile
import logging
import tempfile
from contextlib import contextmanager
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models.database import get_db, User, InstalledPlugin, PluginAuditLog, PluginViolation
from ..core.auth import require_super_admin, get_current_user
from ..plugins.permissions import PluginManifest, Permission, PERMISSION_INFO, PLUGIN_TYPES
from ..plugins.manager import get_manager
from ..plugins import layout

router = APIRouter(prefix="/api/plugins", tags=["plugins"])
log = logging.getLogger(__name__)

# Upload limits: a plugin is a manifest plus a little code, so these are
# generous while still refusing zip bombs.
MAX_UPLOAD_BYTES    = 50 * 1024 * 1024
MAX_EXTRACTED_BYTES = 200 * 1024 * 1024
MAX_ENTRIES         = 5000


def _plugins_dir() -> str:
    return layout.plugins_root()


def require_plugin_uploader(current_user: User = Depends(get_current_user)) -> User:
    """Super admins, plus users a super admin has granted can_upload_plugins.
    Delegated uploaders are refused while the plugin system is denied."""
    if current_user.is_super_admin:
        return current_user
    if not getattr(current_user, "can_upload_plugins", False):
        raise HTTPException(403, "Uploading plugins requires permission from a super admin")
    from ..core.settings_store import load_settings
    if load_settings().get("plugins", {}).get("denied", False):
        raise HTTPException(403, "The plugin system is currently denied by a super admin")
    return current_user


def _type_info(manifest: PluginManifest) -> dict:
    ptype = manifest.effective_type
    return {
        "type": ptype,
        "type_label": PLUGIN_TYPES.get(ptype, {}).get("label", ptype),
        "type_inferred": manifest.type_inferred,
        "data_only": manifest.is_data_only,
    }


def _unsafe_zip_entry(info: zipfile.ZipInfo) -> Optional[str]:
    name = info.filename
    parts = name.split("/")
    if name.startswith("/") or "\\" in name or ".." in parts or \
            (len(name) > 1 and name[1] == ":"):
        return f"unsafe path in zip bundle: {name!r}"
    if stat.S_ISLNK(info.external_attr >> 16):
        return f"symbolic links aren't allowed in plugin bundles: {name!r}"
    return None


@contextmanager
def _extracted_bundle(file: UploadFile):
    """Save an uploaded zip, check it, extract it to a temp dir, and yield
    (plugin_dir, manifest, manifest_errors). The temp dir is removed after."""
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(400, "Plugin bundle must be a .zip file")
    with tempfile.TemporaryDirectory() as tmp:
        zpath = os.path.join(tmp, "bundle.zip")
        size = 0
        with open(zpath, "wb") as f:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, f"Plugin bundle is larger than "
                                             f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
                f.write(chunk)
        extract_dir = os.path.join(tmp, "extracted")
        try:
            with zipfile.ZipFile(zpath) as z:
                infos = z.infolist()
                if len(infos) > MAX_ENTRIES:
                    raise HTTPException(400, f"Plugin bundle has more than {MAX_ENTRIES} files")
                if sum(i.file_size for i in infos) > MAX_EXTRACTED_BYTES:
                    raise HTTPException(400, "Plugin bundle is too large once extracted")
                for info in infos:
                    problem = _unsafe_zip_entry(info)
                    if problem:
                        raise HTTPException(400, problem)
                z.extractall(extract_dir)
        except zipfile.BadZipFile:
            raise HTTPException(400, "Invalid zip file")

        # Find manifest.json: the shallowest one (at the root, or inside a single
        # top-level folder, which is how most zip tools package a directory).
        manifest_dir = None
        for root, dirs, files in os.walk(extract_dir):
            dirs.sort()
            if "manifest.json" in files:
                manifest_dir = root
                break
        if not manifest_dir:
            raise HTTPException(400, "No manifest.json found in bundle")
        try:
            manifest = layout.read_manifest(manifest_dir)
        except Exception as e:
            raise HTTPException(400, f"manifest.json could not be read: {e}")
        yield manifest_dir, manifest, manifest.validate()


def _email_inspection(manifest: PluginManifest, plugin_dir: str):
    """Email-provider plugins are a trusted class (they may send PII to a mail
    API), so the host inspects their source for hidden/hardcoded recipients."""
    if "email_provider" not in (manifest.hooks or []):
        return None
    from ..plugins.email_inspector import inspect_email_plugin, summarize_findings
    return summarize_findings(inspect_email_plugin(plugin_dir))


def _register(db: Session, manifest: PluginManifest, install_path: str) -> InstalledPlugin:
    row = InstalledPlugin(
        plugin_id=manifest.id, name=manifest.name, version=manifest.version,
        author=manifest.author, description=manifest.description,
        manifest_json=json.dumps(manifest.to_dict()),
        granted_permissions="[]", enabled=False, install_path=install_path,
        status="stopped",
    )
    db.add(row); db.commit()
    return row


def _audit(db: Session, plugin_id: str, action: str, actor_id: Optional[int], detail: str = ""):
    db.add(PluginAuditLog(plugin_id=plugin_id, action=action, actor_id=actor_id, detail=detail))
    db.commit()


# ---- schemas ----

class PluginOut(BaseModel):
    plugin_id: str
    name: str
    version: str
    type: str = "general"
    type_label: str = ""
    type_inferred: bool = False
    data_only: bool = False
    install_path: str = ""
    author: Optional[str]
    description: Optional[str]
    enabled: bool
    status: str
    permissions_requested: list[str]
    permissions_granted: list[str]
    hooks: list[str]
    methods: list[str] = []
    events: list[str] = []
    outbound_domains: list[str] = []
    needs_reapproval: bool = False
    requires_pii_network_exception: bool = False
    pii_network_justification: str = ""
    crash_count: int
    last_error: Optional[str]

    class Config:
        from_attributes = False


class EnableRequest(BaseModel):
    # The admin explicitly confirms which requested permissions to grant.
    # Must be a subset of what the manifest requests.
    granted_permissions: list[str]
    # When re-enabling a plugin flagged for re-approval after a manifest breach,
    # the admin must acknowledge the declared method list again.
    acknowledge_methods: bool = False
    # SEPARATE, explicit confirmation required ONLY when granting BOTH read_pii
    # and network together. This is deliberately distinct from the normal
    # permission checkboxes — granting this combination is the one action in
    # the whole plugin system that can let a plugin exfiltrate member data, so
    # it gets its own typed acknowledgment rather than living inside the
    # general grant flow.
    confirm_pii_network_exception: bool = False


# ---- endpoints ----

@router.get("/methods")
def method_catalog(_: User = Depends(require_super_admin)):
    """The full host-method catalog: each callable method + the permission it needs."""
    from ..plugins.permissions import HOST_METHODS
    return HOST_METHODS


@router.get("/permissions")
def permission_catalog(_: User = Depends(require_super_admin)):
    """The full permission catalog with labels, risk levels, and descriptions."""
    return PERMISSION_INFO


@router.get("/types")
def plugin_types(_: User = Depends(require_plugin_uploader)):
    """Plugin types, in display order: each one's folder, label and rules."""
    return [
        {"type": t, "label": r["label"], "folder": f"{t}/",
         "data_only": bool(r.get("data_only")),
         "required_hooks": sorted(r.get("required_hooks", ()))}
        for t, r in PLUGIN_TYPES.items()
    ]


@router.get("/status")
def plugin_system_status(_: User = Depends(require_super_admin)):
    mgr = get_manager()
    if not mgr:
        return {"active": False, "reason": "Plugin system not enabled or gRPC unavailable"}
    return {"active": True, **mgr.status()}


@router.get("")
def list_plugins(db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    rows = db.query(InstalledPlugin).order_by(InstalledPlugin.installed_at.desc()).all()
    out = []
    for r in rows:
        manifest = json.loads(r.manifest_json)
        m = PluginManifest.from_dict(manifest)
        out.append(PluginOut(
            plugin_id=r.plugin_id, name=r.name, version=r.version, author=r.author,
            install_path=r.install_path or "", **_type_info(m),
            description=r.description, enabled=r.enabled, status=r.status,
            permissions_requested=manifest.get("permissions", []),
            permissions_granted=json.loads(r.granted_permissions or "[]"),
            hooks=manifest.get("hooks", []),
            methods=manifest.get("methods", []),
            events=manifest.get("events", []),
            outbound_domains=manifest.get("outbound_domains", []),
            needs_reapproval=bool(getattr(r, "needs_reapproval", False)),
            requires_pii_network_exception=manifest.get("requires_pii_network_exception", False),
            pii_network_justification=manifest.get("pii_network_justification", ""),
            crash_count=r.crash_count or 0, last_error=r.last_error,
        ))
    return out


@router.get("/available")
def available_plugins(db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    """Plugins present on disk (in any type folder) that aren't yet registered."""
    registered = {r.plugin_id for r in db.query(InstalledPlugin.plugin_id).all()}
    available = []
    for f in layout.scan(_plugins_dir()):
        if f.manifest is None:
            log.warning("Bad manifest in %s: %s", f.path, f.errors)
            continue
        m = f.manifest
        if m.id in registered:
            continue
        available.append({
            "plugin_id": m.id, "name": m.name, "version": m.version,
            "author": m.author, "description": m.description,
            "permissions": m.permissions, "hooks": m.hooks,
            "path": f.path, **_type_info(m),
            "folder": f.folder_type, "legacy_location": f.legacy_location,
            "destination": layout.relative_install_dir(m),
            "valid": f.valid, "errors": f.errors,
        })
    return available


@router.post("/install")
def install_plugin(path: str, db: Session = Depends(get_db),
                   current: User = Depends(require_super_admin)):
    """
    Register a plugin already on disk under the plugins root. It is installed
    DISABLED — no code runs and no permissions are granted until an admin
    explicitly enables it. A plugin found outside its type folder (e.g. the
    old flat layout) is moved into <root>/<type>/<id>/ first.
    """
    root = _plugins_dir()
    if not layout.is_strictly_inside(path, root):
        raise HTTPException(400, "Only plugins inside the plugins directory can be installed "
                                 "from disk; upload anything else as a .zip")
    if not os.path.isfile(os.path.join(path, "manifest.json")):
        raise HTTPException(404, "manifest.json not found at that path")

    m = layout.read_manifest(path)
    errors = m.validate()
    if errors:
        raise HTTPException(400, f"Invalid manifest: {'; '.join(errors)}")

    if db.query(InstalledPlugin).filter(InstalledPlugin.plugin_id == m.id).first():
        raise HTTPException(400, f"Plugin '{m.id}' is already installed")

    inspection = _email_inspection(m, path)
    if inspection and inspection["high"]:
        raise HTTPException(400,
            "Email-provider plugin rejected: it appears to send to a hardcoded/hidden "
            f"recipient (possible data exfiltration). Findings: {inspection['high']}")

    dest = layout.install_dir(root, m)
    if os.path.realpath(path) != os.path.realpath(dest):
        if os.path.exists(dest):
            raise HTTPException(409, f"Can't move this plugin into {layout.relative_install_dir(m)}: "
                                     "something is already there")
        layout.ensure_layout(root)
        layout.place_directory(path, dest, move=True)

    _register(db, m, dest)
    _audit(db, m.id, "installed", current.id, f"v{m.version} -> {layout.relative_install_dir(m)}")
    return {"installed": True, "plugin_id": m.id, "enabled": False,
            "destination": layout.relative_install_dir(m), **_type_info(m),
            "note": "Plugin installed but disabled. Enable it to grant permissions and run it."}


@router.post("/upload/inspect")
def inspect_upload(file: UploadFile = File(...), expected_type: Optional[str] = None,
                   db: Session = Depends(get_db),
                   current: User = Depends(require_plugin_uploader)):
    """
    Step 1 of the upload wizard: check a plugin zip without installing it.
    Reports its type, the folder it would be installed into, what it asks
    for, and anything that would stop the install.
    """
    with _extracted_bundle(file) as (plugin_dir, m, errors):
        problems = list(errors)
        if expected_type and m.effective_type != expected_type:
            problems.append(f"this is a '{m.effective_type}' plugin; only "
                            f"'{expected_type}' plugins can be uploaded here")
        if db.query(InstalledPlugin).filter(InstalledPlugin.plugin_id == m.id).first():
            problems.append(f"a plugin with id '{m.id}' is already installed")
        else:
            dest = layout.install_dir(_plugins_dir(), m)
            if layout.is_bundled_copy(dest):
                problems.append(f"{layout.relative_install_dir(m)} holds a built-in plugin")
            elif os.path.exists(dest) and not current.is_super_admin:
                problems.append(f"{layout.relative_install_dir(m)} already has files in it; "
                                "ask a super admin to install or clear it")
        inspection = _email_inspection(m, plugin_dir)
        if inspection and inspection["high"]:
            problems.append("it appears to send email to a hardcoded/hidden recipient "
                            f"(possible data exfiltration): {inspection['high']}")
        return {
            "plugin_id": m.id, "name": m.name, "version": m.version,
            "author": m.author, "description": m.description,
            **_type_info(m),
            "destination": layout.relative_install_dir(m),
            "permissions": m.permissions, "hooks": m.hooks,
            "outbound_domains": m.outbound_domains,
            "email_inspection": inspection,
            "can_install": not problems,
            "problems": problems,
            "enable_requires_super_admin": not current.is_super_admin,
        }


@router.post("/upload")
def upload_plugin(file: UploadFile = File(...), expected_type: Optional[str] = None,
                  db: Session = Depends(get_db),
                  current: User = Depends(require_plugin_uploader)):
    """
    Upload a plugin as a .zip bundle containing manifest.json + code (or data,
    for language packs and themes). It is validated, extracted into
    <plugins root>/<type>/<id>/ based on its manifest, and registered DISABLED.
    expected_type (e.g. "email" from the setup wizard's email step) refuses a
    plugin of any other type.
    """
    with _extracted_bundle(file) as (plugin_dir, m, errors):
        if errors:
            raise HTTPException(400, f"Invalid manifest: {'; '.join(errors)}")
        if expected_type and m.effective_type != expected_type:
            raise HTTPException(400, f"This is a '{m.effective_type}' plugin; only "
                                     f"'{expected_type}' plugins can be uploaded here")

        # SECURITY: email-provider plugins are a trusted class (they may send PII
        # to a mail API), so they're exempt from the read_pii+network block — but
        # in exchange the host inspects them for hidden/hardcoded recipients before
        # trusting them. BLOCK install on a high-severity finding (a hidden To/Cc/Bcc).
        email_inspection = _email_inspection(m, plugin_dir)
        if email_inspection and email_inspection["high"]:
            raise HTTPException(400,
                "Email-provider plugin rejected: it appears to send to a "
                "hardcoded/hidden recipient (possible data exfiltration). "
                f"Findings: {email_inspection['high']}")

        if db.query(InstalledPlugin).filter(InstalledPlugin.plugin_id == m.id).first():
            raise HTTPException(400, f"Plugin '{m.id}' is already installed")

        root = _plugins_dir()
        dest = layout.install_dir(root, m)
        # Files already at the destination belong to no installed plugin (that
        # was checked above): leftovers from an uninstall, or a folder a super
        # admin placed but hasn't installed yet. Only a super admin may replace
        # them, and never a copy of a built-in plugin.
        if layout.is_bundled_copy(dest):
            raise HTTPException(409, f"{layout.relative_install_dir(m)} holds a built-in plugin")
        if os.path.exists(dest) and not current.is_super_admin:
            raise HTTPException(409, f"{layout.relative_install_dir(m)} already has files in it; "
                                     "ask a super admin to install or clear it")
        layout.ensure_layout(root)
        layout.place_directory(plugin_dir, dest, move=False)

    _register(db, m, dest)
    _audit(db, m.id, "uploaded", current.id,
           f"v{m.version} -> {layout.relative_install_dir(m)}"
           + ("" if current.is_super_admin else f" (delegated uploader: {current.email})"))
    return {"installed": True, "plugin_id": m.id, "enabled": False,
            **_type_info(m),
            "destination": layout.relative_install_dir(m),
            "requested_permissions": m.permissions,
            "is_email_provider": "email_provider" in (m.hooks or []),
            "email_inspection": email_inspection,
            "enable_requires_super_admin": not current.is_super_admin}


@router.post("/{plugin_id}/enable")
def enable_plugin(plugin_id: str, req: EnableRequest, db: Session = Depends(get_db),
                  current: User = Depends(require_super_admin)):
    """
    Enable a plugin, granting the confirmed permissions, and launch it.
    granted_permissions must be a subset of what the manifest requests.
    """
    row = db.query(InstalledPlugin).filter(InstalledPlugin.plugin_id == plugin_id).first()
    if not row:
        raise HTTPException(404, "Plugin not installed")

    manifest = PluginManifest.from_dict(json.loads(row.manifest_json))
    requested = set(manifest.permissions)
    granting  = set(req.granted_permissions)

    if manifest.is_data_only:
        # Language packs and themes: nothing to grant and nothing to launch.
        row.enabled = True
        row.status = "data"
        row.enabled_at = datetime.utcnow()
        row.enabled_by = current.id
        db.commit()
        _audit(db, plugin_id, "enabled", current.id, f"{manifest.effective_type} (data only)")
        return {"enabled": True, "granted_permissions": []}

    # If this plugin was flagged for re-approval after a manifest-integrity
    # violation (it called an undeclared host method), the admin must explicitly
    # re-acknowledge its declared method list before it can run again.
    if getattr(row, "needs_reapproval", False) and not req.acknowledge_methods:
        raise HTTPException(
            409,
            "This plugin was disabled for calling a host method it did not declare. "
            "Review its declared methods and re-enable with acknowledge_methods=true "
            "to confirm you accept the current manifest."
        )

    # Can't grant a permission the plugin never requested
    invalid = granting - requested
    if invalid:
        raise HTTPException(400, f"Cannot grant permissions not requested by the plugin: {invalid}")

    # ── read_pii + network is BLOCKED BY DEFAULT ────────────────────────────
    # This is the combination that lets a plugin see member data AND reach the
    # network — the one path that can actually exfiltrate PII. Granting both
    # together requires: the manifest to have declared the narrow exception
    # with a justification (checked at install time), the admin to grant both
    # here, AND a SEPARATE, distinct confirmation flag on this request. Missing
    # any of the three refuses the enable outright.
    #
    # EXCEPT: email-provider plugins are exempt from needing that declared
    # exception at all — PluginManifest.validate() already exempts them for
    # exactly this reason (sending member identifiers to a mail API is their
    # legitimate function, not a red flag), so a plugin that installs cleanly
    # must also be enable-able with the permissions it actually needs to run.
    # Without this, EVERY email-provider plugin — including the ones this app
    # ships with (Gmail/Outlook/Yahoo) — would install successfully and then
    # be permanently un-enableable, since they declare read_pii+network but
    # never requires_pii_network_exception (they don't need to). They still
    # go through the separate hidden-recipient inspection at upload time.
    from ..plugins.permissions import Permission as _P
    is_email_provider = (_P.EMAIL_PROVIDER.value in requested and "email_provider" in manifest.hooks)
    granting_both = _P.READ_PII.value in granting and _P.NETWORK.value in granting
    if granting_both and is_email_provider:
        log.info("Granting read_pii+network to email-provider plugin %s (exempt from the "
                "general exception gate; inspected for hidden recipients at upload time). "
                "Declared outbound domains: %s", plugin_id, manifest.outbound_domains)
        _audit(db, plugin_id, "pii_network_granted_email_provider", current.id,
               f"domains: {manifest.outbound_domains}")
    elif granting_both:
        if not manifest.requires_pii_network_exception:
            raise HTTPException(
                400,
                "Refusing to grant 'read_pii' and 'network' together: this plugin's manifest "
                "did not declare the narrow exception for this combination. It cannot be granted "
                "regardless of admin action unless the plugin author updates the manifest."
            )
        if not req.confirm_pii_network_exception:
            raise HTTPException(
                409,
                "Granting 'read_pii' and 'network' together requires a SEPARATE explicit "
                "confirmation beyond the normal permission grant, because this combination can "
                "exfiltrate member data. Justification on file: "
                f"\"{manifest.pii_network_justification}\". Declared outbound domains: "
                f"{manifest.outbound_domains}. Re-submit with confirm_pii_network_exception=true "
                "to proceed — this plugin will be placed under heavy egress monitoring."
            )
        log.warning(
            "Super admin %s granted read_pii+network to plugin %s (heavy monitoring active). "
            "Justification: %s", current.id, plugin_id, manifest.pii_network_justification,
        )
        _audit(db, plugin_id, "pii_network_exception_granted", current.id,
               f"justification: {manifest.pii_network_justification}; domains: {manifest.outbound_domains}")

    # A hook won't work without its permission — warn by refusing enable if the
    # admin dropped a permission a declared hook needs.
    from ..plugins.permissions import HOOK_PERMISSION
    for hook in manifest.hooks:
        needed = HOOK_PERMISSION.get(hook)
        if needed and needed not in granting:
            raise HTTPException(
                400,
                f"Hook '{hook}' requires permission '{needed}', which was not granted. "
                f"Grant it or the plugin cannot function."
            )

    row.granted_permissions = json.dumps(sorted(granting))
    row.enabled = True
    row.status = "starting"
    row.enabled_at = datetime.utcnow()
    row.enabled_by = current.id
    row.crash_count = 0
    row.last_error = None
    row.needs_reapproval = False   # cleared on deliberate re-approval
    db.commit()
    _audit(db, plugin_id, "enabled", current.id,
           f"granted: {sorted(granting)}; methods: {manifest.methods}")

    mgr = get_manager()
    if mgr:
        try:
            mgr.launch_plugin(manifest, row.install_path, granting)
        except Exception as e:
            raise HTTPException(500, f"Enabled but failed to launch: {e}")
    else:
        raise HTTPException(503, "Plugin manager not running — enable the plugin system and restart")

    return {"enabled": True, "granted_permissions": sorted(granting)}


@router.post("/{plugin_id}/disable")
def disable_plugin(plugin_id: str, db: Session = Depends(get_db),
                   current: User = Depends(require_super_admin)):
    row = db.query(InstalledPlugin).filter(InstalledPlugin.plugin_id == plugin_id).first()
    if not row:
        raise HTTPException(404, "Plugin not installed")
    row.enabled = False
    row.status = "stopped"
    db.commit()
    _audit(db, plugin_id, "disabled", current.id)

    mgr = get_manager()
    if mgr:
        mgr._stop_plugin(plugin_id, reason="disabled by admin")
    return {"enabled": False}


@router.delete("/{plugin_id}")
def uninstall_plugin(plugin_id: str, remove_files: bool = False,
                     db: Session = Depends(get_db),
                     current: User = Depends(require_super_admin)):
    row = db.query(InstalledPlugin).filter(InstalledPlugin.plugin_id == plugin_id).first()
    if not row:
        raise HTTPException(404, "Plugin not installed")

    mgr = get_manager()
    if mgr:
        mgr._stop_plugin(plugin_id, reason="uninstalled")

    install_path = row.install_path
    db.delete(row)
    db.commit()
    _audit(db, plugin_id, "uninstalled", current.id)

    if remove_files and install_path and os.path.isdir(install_path):
        # Only remove if it's strictly inside the managed plugins dir (safety).
        # commonpath, not a string prefix: "/data/plugins-other" starts with
        # "/data/plugins" but isn't inside it; and never the root itself.
        if layout.is_strictly_inside(install_path, _plugins_dir()):
            shutil.rmtree(install_path, ignore_errors=True)

    return {"uninstalled": True}


@router.get("/{plugin_id}/audit")
def plugin_audit(plugin_id: str, db: Session = Depends(get_db),
                 _: User = Depends(require_super_admin)):
    rows = (db.query(PluginAuditLog)
            .filter(PluginAuditLog.plugin_id == plugin_id)
            .order_by(PluginAuditLog.created_at.desc())
            .limit(100).all())
    return [{"action": r.action, "detail": r.detail, "actor_id": r.actor_id,
             "created_at": r.created_at.isoformat()} for r in rows]


@router.get("/violations/all")
def all_violations(limit: int = 100, db: Session = Depends(get_db),
                   _: User = Depends(require_super_admin)):
    """Recent security violations across all plugins (for the monitoring dashboard)."""
    from ..plugins.monitor import VIOLATION_TYPES
    rows = (db.query(PluginViolation)
            .order_by(PluginViolation.created_at.desc())
            .limit(limit).all())
    return [{
        "plugin_id": r.plugin_id, "type": r.vtype,
        "label": VIOLATION_TYPES.get(r.vtype, {}).get("label", r.vtype),
        "severity": r.severity, "detail": r.detail,
        "action_taken": r.action_taken,
        "created_at": r.created_at.isoformat(),
    } for r in rows]


@router.get("/{plugin_id}/violations")
def plugin_violations(plugin_id: str, db: Session = Depends(get_db),
                      _: User = Depends(require_super_admin)):
    from ..plugins.monitor import VIOLATION_TYPES
    rows = (db.query(PluginViolation)
            .filter(PluginViolation.plugin_id == plugin_id)
            .order_by(PluginViolation.created_at.desc())
            .limit(100).all())
    return [{
        "type": r.vtype, "label": VIOLATION_TYPES.get(r.vtype, {}).get("label", r.vtype),
        "severity": r.severity, "detail": r.detail, "action_taken": r.action_taken,
        "created_at": r.created_at.isoformat(),
    } for r in rows]


# ── In-app plugin documentation (super-admin only) ────────────────────────────
# Serves the canonical plugin guides that live next to the plugin code, so the
# in-app Help pages are always in sync with the source docs (single source of
# truth). See backend/plugins/docs/.

_PLUGIN_DOC_FILES = {
    "using":   "USING_PLUGINS.md",
    "writing": "WRITING_PLUGINS.md",
}


@router.get("/docs/{doc}")
def plugin_doc(doc: str, _: User = Depends(require_super_admin)):
    """
    Return the raw Markdown of a plugin guide for in-app rendering.
    doc = 'using' (administrator guide) | 'writing' (developer guide).
    """
    fname = _PLUGIN_DOC_FILES.get(doc)
    if not fname:
        raise HTTPException(404, "Unknown plugin doc")
    # Docs ship inside the plugins package: backend/plugins/docs/<file>.md
    docs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "plugins", "docs")
    path = os.path.join(docs_dir, fname)
    if not os.path.isfile(path):
        raise HTTPException(404, f"Plugin doc not found on disk: {fname}")
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        raise HTTPException(500, f"Could not read plugin doc: {e}")
    return {"doc": doc, "filename": fname, "markdown": content}
