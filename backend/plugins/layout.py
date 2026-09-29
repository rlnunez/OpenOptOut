"""
Typed plugin directory layout.

Every plugin lives at <plugins root>/<type>/<plugin id>/, where <type> is one of
permissions.PLUGIN_TYPES (email, captcha, forms, discovery, brokers, themes,
languages, general) and comes from the plugin's manifest:

    /data/plugins/
    ├── email/email-gmail/manifest.json
    ├── captcha/...
    └── languages/...

This module is the single place that knows that layout:

  - plugins_root()        where the root is (PLUGINS_DIR env, then settings)
  - install_dir()         where a given manifest belongs
  - scan()                every plugin on disk, tagged with its folder type
  - sync_bundled()        copy a built-in plugin (backend/plugins/bundled/) into
                          the root, refreshing the copy when the app ships a
                          new version
  - migrate_installed()   move installs from the old flat layout
                          (<root>/<id>/) and old bundled paths into place

Paths are compared with is_strictly_inside(), never a string prefix.
"""

import hashlib
import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Optional

from .permissions import PLUGIN_TYPES, PluginManifest

log = logging.getLogger(__name__)

DEFAULT_ROOT = "/data/plugins"

# Built-in plugins ship inside the app, laid out the same way
# (bundled/email/email-gmail/). They are copied into the plugins root before
# they're installed, so every installed plugin lives under one root.
BUNDLED_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bundled")

# Written into each copy of a bundled plugin. Holds the hash of the source it
# was copied from, and marks the directory as ours to refresh: a directory
# without it (say, an admin's own upload using the same id) is never overwritten.
BUNDLED_MARKER = ".privacyshield-bundled"

_COPY_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", BUNDLED_MARKER)


def plugins_root() -> str:
    env = os.getenv("PLUGINS_DIR")
    if env:
        return env
    # Imported at call time (not module load) so this module has no hard
    # dependency on the settings layer, and so tests can swap load_settings.
    try:
        from ..core import settings_store
    except (ImportError, ValueError):
        from core import settings_store
    return settings_store.load_settings().get("plugins", {}).get("plugins_dir") or DEFAULT_ROOT


def is_strictly_inside(path: str, root: str) -> bool:
    """True if path resolves to somewhere below root (not root itself).
    commonpath, not a string prefix: "/data/plugins-other" starts with
    "/data/plugins" but isn't inside it. Symlinks are resolved first."""
    p, r = os.path.realpath(path), os.path.realpath(root)
    return p != r and os.path.commonpath([p, r]) == r


def ensure_layout(root: str) -> None:
    """Create the root and one subdirectory per plugin type."""
    for ptype in PLUGIN_TYPES:
        os.makedirs(os.path.join(root, ptype), exist_ok=True)


def install_dir(root: str, manifest: PluginManifest) -> str:
    return os.path.join(root, manifest.effective_type, manifest.id)


def relative_install_dir(manifest: PluginManifest) -> str:
    """For display: "email/email-gmail/"."""
    return f"{manifest.effective_type}/{manifest.id}/"


def read_manifest(plugin_dir: str) -> PluginManifest:
    with open(os.path.join(plugin_dir, "manifest.json")) as f:
        return PluginManifest.from_dict(json.load(f))


def placement_errors(manifest: PluginManifest, folder_type: Optional[str]) -> list[str]:
    """A plugin must sit in the folder for its type. folder_type None means the
    old flat layout, which is tolerated (and migrated) rather than an error."""
    if folder_type is not None and manifest.effective_type != folder_type:
        return [f"manifest type is '{manifest.effective_type}' but the plugin is in "
                f"the '{folder_type}/' folder"]
    return []


@dataclass
class FoundPlugin:
    path: str
    folder_type: Optional[str]              # None = old flat layout (<root>/<id>/)
    manifest: Optional[PluginManifest]
    errors: list = field(default_factory=list)

    @property
    def legacy_location(self) -> bool:
        return self.folder_type is None

    @property
    def valid(self) -> bool:
        return self.manifest is not None and not self.errors


def _inspect(plugin_dir: str, folder_type: Optional[str]) -> FoundPlugin:
    try:
        manifest = read_manifest(plugin_dir)
    except Exception as e:
        return FoundPlugin(plugin_dir, folder_type, None, [f"unreadable manifest.json: {e}"])
    errors = manifest.validate() + placement_errors(manifest, folder_type)
    return FoundPlugin(plugin_dir, folder_type, manifest, errors)


def scan(root: str) -> list[FoundPlugin]:
    """Every plugin under root: <root>/<type>/<id>/ plus any leftovers in the
    old flat layout (<root>/<id>/). Hidden entries (staging dirs) are skipped."""
    found = []
    if not os.path.isdir(root):
        return found
    for entry in sorted(os.listdir(root)):
        entry_path = os.path.join(root, entry)
        if entry.startswith(".") or not os.path.isdir(entry_path):
            continue
        if entry in PLUGIN_TYPES:
            for pid in sorted(os.listdir(entry_path)):
                pdir = os.path.join(entry_path, pid)
                if not pid.startswith(".") and os.path.isfile(os.path.join(pdir, "manifest.json")):
                    found.append(_inspect(pdir, entry))
        elif os.path.isfile(os.path.join(entry_path, "manifest.json")):
            found.append(_inspect(entry_path, None))
    return found


# ── Moving files into place ───────────────────────────────────────────────────

def place_directory(src: str, dest: str, *, move: bool) -> None:
    """Copy (or move) src to dest, replacing whatever is at dest. The new copy
    is staged next to dest and swapped in with renames, so dest is never a
    half-written directory."""
    parent = os.path.dirname(dest)
    os.makedirs(parent, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=f".{os.path.basename(dest)}-", dir=parent)
    try:
        staged = os.path.join(staging, "new")
        if move:
            shutil.move(src, staged)
        else:
            shutil.copytree(src, staged, ignore=_COPY_IGNORE)
        if os.path.exists(dest):
            os.rename(dest, os.path.join(staging, "old"))
        os.rename(staged, dest)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def dir_hash(path: str) -> str:
    """SHA-256 over every file's relative path and contents (ignoring caches and
    the bundled marker). Used for bundled-copy refresh and install integrity."""
    h = hashlib.sha256()
    for base, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for name in sorted(files):
            if name == BUNDLED_MARKER or name.endswith(".pyc"):
                continue
            full = os.path.join(base, name)
            h.update(os.path.relpath(full, path).encode() + b"\0")
            with open(full, "rb") as f:
                h.update(f.read())
            h.update(b"\0")
    return h.hexdigest()


def is_bundled_copy(path: str) -> bool:
    return os.path.isfile(os.path.join(path or "", BUNDLED_MARKER))


def bundled_plugins() -> dict:
    """plugin id -> source directory, for every valid built-in plugin."""
    return {f.manifest.id: f.path for f in scan(BUNDLED_ROOT) if f.valid}


def sync_bundled(src: str, root: str, manifest: PluginManifest) -> str:
    """Make <root>/<type>/<id>/ an up-to-date copy of the built-in plugin at src
    and return its path. Copies only when missing or when the source changed
    (an app upgrade). Refuses to overwrite a directory that isn't a bundled
    copy, so an admin's own plugin with the same id is never clobbered."""
    dest = install_dir(root, manifest)
    want = dir_hash(src)
    marker = os.path.join(dest, BUNDLED_MARKER)
    if os.path.isdir(dest):
        if not os.path.isfile(marker):
            raise RuntimeError(f"{dest} exists and isn't a copy of the built-in plugin; "
                               f"not overwriting it")
        with open(marker) as f:
            if f.read().strip() == want:
                return dest
    ensure_layout(root)
    place_directory(src, dest, move=False)
    with open(marker, "w") as f:
        f.write(want + "\n")
    log.info("Copied built-in plugin %s into %s", manifest.id, dest)
    return dest


# ── Upgrading existing installs ───────────────────────────────────────────────

def migrate_installed(root: str, session_factory) -> list[str]:
    """
    Bring every registered plugin into the typed layout, updating its
    InstalledPlugin.install_path:

      - built-in plugins (registered from the app's bundled dir, including the
        old flat bundled paths that no longer exist) are copied to
        <root>/<type>/<id>/ and refreshed there when the app ships a new version
      - plugins in the old flat layout (<root>/<id>/) are moved to <root>/<type>/<id>/
      - plugins installed from outside the root are left where they are

    Safe to run on every startup; returns a list of what it changed. Never
    moves a plugin onto an existing directory.
    """
    from ..models.database import InstalledPlugin

    ensure_layout(root)
    bundled = bundled_plugins()
    changes = []
    db = session_factory()
    try:
        for row in db.query(InstalledPlugin).all():
            path = row.install_path or ""
            try:
                src = bundled.get(row.plugin_id)
                from_bundled = src and (
                    not os.path.isdir(path)
                    or is_strictly_inside(path, BUNDLED_ROOT)
                    or is_bundled_copy(path))
                if from_bundled:
                    manifest = read_manifest(src)
                    new_path = sync_bundled(src, root, manifest)
                    # Refreshed from the app's own source: that's the approved code.
                    fresh = dir_hash(new_path)
                    if row.code_hash != fresh:
                        row.code_hash = fresh
                        db.commit()
                elif os.path.isdir(path) and is_strictly_inside(path, root):
                    manifest = (read_manifest(path)
                                if os.path.isfile(os.path.join(path, "manifest.json"))
                                else PluginManifest.from_dict(json.loads(row.manifest_json)))
                    new_path = install_dir(root, manifest)
                    if os.path.realpath(path) != os.path.realpath(new_path):
                        if os.path.exists(new_path):
                            log.warning("Not moving plugin %s from %s: %s already exists",
                                        row.plugin_id, path, new_path)
                            continue
                        place_directory(path, new_path, move=True)
                else:
                    if not os.path.isdir(path):
                        log.warning("Plugin %s is registered at %s, which doesn't exist",
                                    row.plugin_id, path)
                    continue
                if os.path.realpath(new_path) != os.path.realpath(path):
                    changes.append(f"{row.plugin_id}: {path} -> {new_path}")
                    row.install_path = new_path
                    db.commit()
            except Exception as e:
                db.rollback()
                log.error("Could not move plugin %s into the typed layout: %s", row.plugin_id, e)
    finally:
        db.close()
    for c in changes:
        log.info("Plugin layout migration: %s", c)
    return changes
