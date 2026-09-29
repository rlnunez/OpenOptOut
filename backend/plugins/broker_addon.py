"""
Broker add-on packaging, validation, and synchronization module (Roadmap Item 1).

Decouples broker-specific opt-out logic from the core platform by packaging
each broker as an independent add-on conforming to the typed plugin layout:
    <plugins_root>/brokers/<plugin_id>/
        ├── manifest.json
        ├── spec.json
        └── (optional assets / custom code)

Manifest specifies:
    - id: unique slug (e.g., "broker-fastpeoplesearch" or "fastpeoplesearch")
    - type: "brokers"
    - spec_file: relative path to declarative spec (defaults to "spec.json")
    - captcha_plugin_id: optional preferred CAPTCHA solver plugin ID
    - is_property_broker: boolean
    - difficulty: "easy" | "medium" | "hard"

Declarative spec (spec.json) defines:
    - BrokerSpec schema (broker_id, name, method, opt_out_url, steps, email, success criteria)
"""

import json
import logging
import os
import shutil
import tempfile
import zipfile
from typing import Optional, Tuple, List, Dict, Any

from .permissions import PluginManifest
try:
    from ..core.interpreter.broker_spec import BrokerSpec
except (ImportError, ValueError):
    try:
        from core.interpreter.broker_spec import BrokerSpec
    except (ImportError, ValueError):
        from app.core.interpreter.broker_spec import BrokerSpec

log = logging.getLogger(__name__)

DEFAULT_SPEC_FILE = "spec.json"


def validate_broker_spec_file(plugin_dir: str, spec_filename: str = DEFAULT_SPEC_FILE) -> Tuple[Optional[BrokerSpec], List[str]]:
    """
    Validate that the declarative spec file exists, is valid JSON, and adheres to the
    BrokerSpec schema. Returns (spec, errors).
    """
    errors: List[str] = []
    if ".." in spec_filename or spec_filename.startswith(("/", "\\")):
        return None, ["spec_file must be a relative path without directory traversal"]

    spec_path = os.path.join(plugin_dir, spec_filename)
    if not os.path.isfile(spec_path):
        return None, [f"specification file not found: {spec_filename}"]

    try:
        with open(spec_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return None, [f"unable to parse {spec_filename} as JSON: {e}"]

    if not isinstance(data, dict):
        return None, [f"{spec_filename} must contain a top-level JSON object"]

    try:
        spec = BrokerSpec.from_dict(data)
    except Exception as e:
        return None, [f"error constructing BrokerSpec from {spec_filename}: {e}"]

    spec_errors = spec.validate()
    if spec_errors:
        errors.extend(spec_errors)
        return None, errors

    return spec, []


def inspect_broker_addon(plugin_dir: str, manifest: PluginManifest) -> Dict[str, Any]:
    """
    Inspect a broker add-on directory: validate its declarative specification and verify
    alignment with the plugin manifest.
    """
    spec_filename = manifest.spec_file or DEFAULT_SPEC_FILE
    spec, errors = validate_broker_spec_file(plugin_dir, spec_filename)

    spec_dict = None
    if spec:
        spec_dict = spec.to_dict()
        # Verify slug consistency if manifest declares broker_id
        if manifest.broker_id and manifest.broker_id != spec.broker_id:
            errors.append(f"manifest.broker_id ('{manifest.broker_id}') does not match spec.broker_id ('{spec.broker_id}')")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "spec_file": spec_filename,
        "spec": spec_dict,
        "broker_id": spec.broker_id if spec else (manifest.broker_id or manifest.id),
        "name": spec.name if spec else manifest.name,
        "method": spec.method if spec else "form",
        "opt_out_url": spec.opt_out_url if spec else "",
        "steps_count": len(spec.steps) if (spec and spec.steps) else 0,
        "has_email_spec": bool(spec and spec.email),
        "captcha_plugin_id": manifest.captcha_plugin_id,
        "is_property_broker": manifest.is_property_broker,
        "difficulty": manifest.difficulty or "medium",
    }


def sync_broker_from_addon(db, manifest: PluginManifest, plugin_dir: str, enabled: bool = False):
    """
    Synchronize a broker record in the database with an installed broker add-on.
    Creates the Broker row if missing, or updates it if existing.
    """
    try:
        from ..models.database import Broker, OptOutMethod, Difficulty, BrokerStatus
    except (ImportError, ValueError):
        try:
            from models.database import Broker, OptOutMethod, Difficulty, BrokerStatus
        except (ImportError, ValueError):
            from app.models.database import Broker, OptOutMethod, Difficulty, BrokerStatus

    spec_filename = manifest.spec_file or DEFAULT_SPEC_FILE
    spec, errors = validate_broker_spec_file(plugin_dir, spec_filename)
    if not spec:
        log.error("Cannot sync broker add-on %s: spec errors: %s", manifest.id, errors)
        raise ValueError(f"Invalid broker add-on spec: {'; '.join(errors)}")

    def safe_enum(val, enum_cls, default):
        try:
            return enum_cls(val.lower()) if val else default
        except (ValueError, AttributeError):
            return default

    # Match by plugin_id first, then by exact name
    broker = db.query(Broker).filter(
        (Broker.plugin_id == manifest.id) | (Broker.name.ilike(spec.name.strip()))
    ).first()

    opt_method = safe_enum(spec.method, OptOutMethod, OptOutMethod.form)
    diff = safe_enum(manifest.difficulty, Difficulty, Difficulty.medium)

    if broker:
        broker.plugin_id = manifest.id
        broker.name = spec.name
        if spec.opt_out_url:
            broker.opt_out_url = spec.opt_out_url
        broker.method = opt_method
        broker.difficulty = diff
        if spec.notes:
            broker.notes = spec.notes
        if manifest.captcha_plugin_id:
            broker.captcha_plugin_id = manifest.captcha_plugin_id
        if manifest.is_property_broker:
            broker.is_property_broker = True
        if enabled:
            broker.enabled = True
    else:
        broker = Broker(
            name=spec.name.strip(),
            opt_out_url=spec.opt_out_url,
            method=opt_method,
            difficulty=diff,
            status=BrokerStatus.compliant,
            notes=spec.notes or f"Installed from broker add-on {manifest.id}",
            plugin_id=manifest.id,
            captcha_plugin_id=manifest.captcha_plugin_id or None,
            is_property_broker=manifest.is_property_broker,
            enabled=enabled,
        )
        db.add(broker)

    db.commit()
    db.refresh(broker)
    log.info("Synced broker add-on %s to Broker ID=%s (%s)", manifest.id, broker.id, broker.name)
    return broker


def deactivate_broker_addon(db, plugin_id: str):
    """
    Handle disabling or uninstalling a broker add-on by disabling the associated Broker.
    """
    try:
        from ..models.database import Broker
    except (ImportError, ValueError):
        try:
            from models.database import Broker
        except (ImportError, ValueError):
            from app.models.database import Broker

    brokers = db.query(Broker).filter(Broker.plugin_id == plugin_id).all()
    for b in brokers:
        b.enabled = False
    db.commit()
    log.info("Deactivated %d broker(s) linked to plugin %s", len(brokers), plugin_id)


def get_broker_spec_for_broker(db, broker) -> Optional[BrokerSpec]:
    """
    Retrieve the declarative BrokerSpec for a broker if backed by an installed, enabled add-on.
    Returns None if no add-on is associated or if the spec cannot be read.
    """
    if db is None or broker is None:
        return None

    try:
        from ..models.database import InstalledPlugin
    except (ImportError, ValueError):
        try:
            from models.database import InstalledPlugin
        except (ImportError, ValueError):
            from app.models.database import InstalledPlugin

    plugin_row = None
    if getattr(broker, "plugin_id", None):
        plugin_row = db.query(InstalledPlugin).filter(
            InstalledPlugin.plugin_id == broker.plugin_id,
            InstalledPlugin.enabled == True
        ).first()

    # Fallback: search by conventional plugin_id if broker.plugin_id not set
    if not plugin_row:
        slug = (broker.name or "").lower().strip().replace(" ", "-").replace("_", "-")
        candidate_ids = [f"broker-{slug}", slug, f"broker_{slug}"]
        plugin_row = db.query(InstalledPlugin).filter(
            InstalledPlugin.plugin_id.in_(candidate_ids),
            InstalledPlugin.enabled == True
        ).first()

    if not plugin_row or not plugin_row.install_path or not os.path.isdir(plugin_row.install_path):
        return None

    try:
        manifest_data = json.loads(plugin_row.manifest_json or "{}")
        spec_filename = manifest_data.get("spec_file") or DEFAULT_SPEC_FILE
        spec, errors = validate_broker_spec_file(plugin_row.install_path, spec_filename)
        if spec:
            return spec
        log.warning("Broker add-on %s has spec errors: %s", plugin_row.plugin_id, errors)
    except Exception as e:
        log.warning("Failed to load spec for broker add-on %s: %s", plugin_row.plugin_id, e)

    return None


def package_broker_addon(addon_dir: str, output_zip_path: str) -> str:
    """
    Package a broker add-on directory into a clean .zip bundle ready for distribution or upload.
    Validates manifest and spec before bundling.
    """
    manifest_path = os.path.join(addon_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        raise ValueError("Cannot package broker add-on: missing manifest.json")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)
    manifest = PluginManifest.from_dict(manifest_data)
    manifest_errors = manifest.validate()
    if manifest_errors:
        raise ValueError(f"Invalid manifest: {'; '.join(manifest_errors)}")

    if manifest.effective_type != "brokers":
        raise ValueError(f"Expected plugin type 'brokers', got '{manifest.effective_type}'")

    spec_filename = manifest.spec_file or DEFAULT_SPEC_FILE
    spec, spec_errors = validate_broker_spec_file(addon_dir, spec_filename)
    if spec_errors:
        raise ValueError(f"Invalid broker spec: {'; '.join(spec_errors)}")

    os.makedirs(os.path.dirname(os.path.abspath(output_zip_path)), exist_ok=True)
    with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(addon_dir):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
            for file in files:
                if file.startswith(".") or file.endswith((".pyc", ".pyo")):
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, addon_dir)
                z.write(full_path, rel_path)

    return output_zip_path
