"""
Auto-provisioning for the email-provider plugins PrivacyShield ships with
(Gmail, Outlook, Yahoo — source under backend/plugins/bundled/email/, installed
into <plugins root>/email/<id>/ like any other email plugin).

Connecting an OAuth account (POST /api/email-oauth/*) only obtains and stores
tokens — it talks to Google/Microsoft/Yahoo directly and has nothing to do
with the plugin system. ACTUALLY sending mail through that account needs a
running email-provider plugin process that knows how to call that provider's
API using those tokens, which is a separate thing entirely: the plugin
system is opt-in (off by default) and the matching plugin still needs to be
installed and enabled, same as any plugin an admin uploads by hand.

An operator who just picked "Gmail" in the setup wizard and connected their
account has no reason to know any of that, or to separately go visit
Settings → Plugin system and Settings → Plugins to finish the job — so
ensure_provider_plugin() does it for them, lazily, the first time a send
actually needs it: turn the plugin system on if it's off, install the
matching bundled plugin if it isn't yet, and enable + launch it, granting
exactly the permissions its manifest declares (it's first-party, ships with
the app, and is still run through the same hidden-recipient inspection as
any upload — trusted, not unchecked). This also self-heals existing
deployments where an admin already connected OAuth before this existed —
nothing needs to be redone.
"""

import json
import logging
import os

log = logging.getLogger(__name__)

# provider_key (as stored in settings["email"]["provider"], and as ConnectOAuth
# in the wizard sends it) -> the bundled plugin source dir that serves it. The
# source is never run in place: it's copied into <plugins root>/email/<id>/ and
# the copy is what gets installed (see plugins/layout.py, sync_bundled).
_BUNDLED_EMAIL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                  "plugins", "bundled", "email")
_PROVIDER_TO_PLUGIN_DIR = {
    "gmail":   os.path.join(_BUNDLED_EMAIL_DIR, "email-gmail"),
    "outlook": os.path.join(_BUNDLED_EMAIL_DIR, "email-outlook"),
    "yahoo":   os.path.join(_BUNDLED_EMAIL_DIR, "email-yahoo"),
}


def has_bundled_plugin(provider_key: str) -> bool:
    path = _PROVIDER_TO_PLUGIN_DIR.get(provider_key)
    return bool(path and os.path.isfile(os.path.join(path, "manifest.json")))


def ensure_provider_plugin(provider_key: str, db_session_factory=None) -> bool:
    """
    Make sure the bundled plugin for provider_key is installed, enabled, and
    running. Returns True if it's ready (or already was); False if there's no
    bundled plugin for this provider, or provisioning failed for some reason
    (logged, never raises — callers should just fall back to SMTP as before).
    """
    plugin_dir = _PROVIDER_TO_PLUGIN_DIR.get(provider_key)
    if not plugin_dir or not os.path.isfile(os.path.join(plugin_dir, "manifest.json")):
        return False

    try:
        from ..models.database import SessionLocal, InstalledPlugin
        from .settings_store import load_settings, SETTINGS_FILE
        from ..plugins.permissions import PluginManifest, Permission
        from ..plugins.email_inspector import inspect_email_plugin, summarize_findings
        from ..plugins import get_manager, init_plugin_system
        from ..plugins import layout

        manifest = PluginManifest.from_dict(json.load(open(os.path.join(plugin_dir, "manifest.json"))))
        errors = manifest.validate()
        if errors:
            log.error("Bundled plugin %s failed validation, not provisioning: %s", provider_key, errors)
            return False
        root = layout.plugins_root()

        Session = db_session_factory or SessionLocal
        db = Session()
        try:
            row = db.query(InstalledPlugin).filter(InstalledPlugin.plugin_id == manifest.id).first()

            # An admin's own plugin registered under the same id (not a copy of
            # ours) is left exactly as it is — never replaced by the built-in.
            ours = row is None or layout.is_bundled_copy(row.install_path) or \
                not os.path.isdir(row.install_path or "") or \
                layout.is_strictly_inside(row.install_path, layout.BUNDLED_ROOT)
            if not ours:
                log.info("Plugin %s at %s isn't the built-in copy; leaving it to the admin",
                         manifest.id, row.install_path)
                return bool(row.enabled and row.status == "running")

            # Same hidden-recipient inspection an admin's manual upload goes
            # through — first-party doesn't mean unchecked.
            findings = summarize_findings(inspect_email_plugin(plugin_dir))
            if findings["high"]:
                log.error("Bundled plugin %s has high-severity findings, refusing to "
                         "auto-install: %s", provider_key, findings["high"])
                return False
            # Copy into <root>/email/<id>/ (or refresh the copy after an upgrade).
            install_path = layout.sync_bundled(plugin_dir, root, manifest)
            if row is not None and row.install_path != install_path:
                row.install_path = install_path
                db.commit()

            if row is None:
                row = InstalledPlugin(
                    plugin_id=manifest.id, name=manifest.name, version=manifest.version,
                    author=manifest.author, description=manifest.description,
                    manifest_json=json.dumps(manifest.to_dict()),
                    granted_permissions="[]", enabled=False, install_path=install_path,
                    status="stopped",
                )
                db.add(row); db.commit()
                log.info("Auto-installed bundled plugin %s for provider '%s'", manifest.id, provider_key)
            else:
                # Bundled plugins are first-party and ship with the app image —
                # refresh the stored snapshot to match what's currently on disk
                # (this is metadata bookkeeping for the admin UI's plugin list;
                # manager.py's own launch path now reads the on-disk file
                # directly regardless, so this isn't what makes a manifest fix
                # actually take effect — that's already true without this —
                # but leaving the DB's own copy stale would still be a
                # confusing thing for an admin to see in Settings -> Plugins).
                stored = json.loads(row.manifest_json)
                if stored != manifest.to_dict():
                    row.manifest_json = json.dumps(manifest.to_dict())
                    row.name = manifest.name
                    row.version = manifest.version
                    row.description = manifest.description
                    db.commit()
                    log.info("Refreshed stored manifest for bundled plugin %s "
                            "(on-disk copy changed since it was installed)", manifest.id)

            already_running = bool(row.enabled and row.status == "running")

            if not row.enabled:
                granting = set(manifest.permissions)   # first-party + already inspected above
                row.granted_permissions = json.dumps(sorted(granting))
                row.enabled = True
                row.status = "starting"
                row.crash_count = 0
                row.last_error = None
                row.needs_reapproval = False
                db.commit()
                log.info("Auto-enabled bundled plugin %s (granted: %s)", manifest.id, sorted(granting))

            # Make sure the plugin SYSTEM itself is actually running — it's
            # opt-in and off by default, but an operator who picked an OAuth
            # provider clearly wants this to work, so turn it on for them
            # rather than leave a working configuration silently inert.
            mgr = get_manager()
            if mgr is None:
                s = load_settings()
                pcfg = s.setdefault("plugins", {})
                if not pcfg.get("enabled"):
                    pcfg["enabled"] = True
                    with open(SETTINGS_FILE, "w") as f:
                        json.dump(s, f, indent=2)
                    log.info("Enabled the plugin system (was off) to run the %s provider plugin.", provider_key)
                mgr = init_plugin_system()

            if mgr is None:
                log.error("Plugin system still not running after init attempt — can't launch %s", provider_key)
                return False

            if not already_running:
                granted = set(json.loads(row.granted_permissions or "[]"))
                mgr.launch_plugin(manifest, row.install_path, granted)
                row.status = "running"
                db.commit()

            return True
        finally:
            db.close()
    except Exception as e:
        log.error("Auto-provisioning failed for provider '%s': %s", provider_key, e)
        return False
