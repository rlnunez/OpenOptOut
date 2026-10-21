"""
Built-in data plugins: language packs and opt-out letters.

Every language except English ships as a language-pack plugin in
plugins/bundled/languages/. At startup each is copied into
<plugins_root>/languages/ and registered as an installed plugin, so it shows
on the Plugins page and an admin can turn it off (the language then falls back
to English) or install their own pack for the same language, which wins.

  * New packs are installed and turned on.
  * Updated packs (an app upgrade) are refreshed in place.
  * A pack an admin turned off stays off; an admin's own pack with the same id
    is never replaced.
"""
import json
import logging
import os
from datetime import datetime

log = logging.getLogger(__name__)


def sync_builtin_languages(db) -> dict:
    return sync_builtin_data(db, "languages")


def sync_builtin_letters(db) -> dict:
    """Built-in opt-out letters (plugins/bundled/letters/), installed the same
    way as language packs: turned on, refreshed on upgrade, an admin's choice
    to turn one off kept, an admin's own letter plugin never replaced."""
    stats = sync_builtin_data(db, "letters")
    try:
        from ..core.legal_letters import reload
        reload()
    except Exception:
        pass
    return stats


def sync_builtin_data(db, ptype: str) -> dict:
    from . import layout
    try:
        from ..models.database import InstalledPlugin
    except (ImportError, ValueError):
        from models.database import InstalledPlugin
    stats = {"installed": 0, "updated": 0, "skipped": 0}
    root = layout.plugins_root()
    for found in layout.scan(layout.BUNDLED_ROOT):
        m = found.manifest if found.valid else None
        if m is None or m.effective_type != ptype:
            continue
        try:
            row = db.query(InstalledPlugin).filter(InstalledPlugin.plugin_id == m.id).first()
            if row is not None and os.path.isdir(row.install_path or "") \
                    and not layout.is_bundled_copy(row.install_path):
                stats["skipped"] += 1          # an admin's own pack
                continue
            dest = layout.sync_bundled(found.path, root, m)
            if row is None:
                db.add(InstalledPlugin(
                    plugin_id=m.id, name=m.name, version=m.version, author=m.author,
                    description=m.description, manifest_json=json.dumps(m.to_dict()),
                    granted_permissions="[]", enabled=True, status="data", install_path=dest,
                    enabled_at=datetime.utcnow(), code_hash=layout.dir_hash(dest)))
                db.commit()
                stats["installed"] += 1
            elif row.version != m.version or row.install_path != dest or row.code_hash != layout.dir_hash(dest):
                row.version, row.name, row.description = m.version, m.name, m.description
                row.manifest_json = json.dumps(m.to_dict())
                row.install_path, row.code_hash = dest, layout.dir_hash(dest)
                db.commit()
                stats["updated"] += 1
        except Exception as e:
            db.rollback()
            log.error("Could not install built-in %s plugin %s: %s", ptype, m.id, e)
    if stats["installed"] or stats["updated"]:
        log.info("Built-in %s plugins: %s", ptype, stats)
    return stats


import re

_URL_RE = re.compile(r"(?:https?|ftp)://[^\s<>\"\x27]+", re.IGNORECASE)
_DANGEROUS_URI_RE = re.compile(r"\b(?:javascript:[^\s]|vbscript:[^\s]|file://|data:[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+|data:;base64)", re.IGNORECASE)
_DANGEROUS_TAG_RE = re.compile(r"<\s*(?:script|iframe|object|embed|svg|form|input|button)\b", re.IGNORECASE)


def is_safe_translation_string(k: str, v: str) -> tuple[bool, str]:
    """Ensure a translation does not introduce dangerous URI schemes, raw HTML elements, or unprompted URLs."""
    if _DANGEROUS_URI_RE.search(v) and not _DANGEROUS_URI_RE.search(k):
        return False, f"prohibited URI scheme in translation: {v[:60]!r}"
    if _DANGEROUS_TAG_RE.search(v) and not _DANGEROUS_TAG_RE.search(k):
        return False, f"prohibited HTML element tag in translation: {v[:60]!r}"
    if _URL_RE.search(v) and not _URL_RE.search(k):
        return False, f"unprompted external URL in translation: {v[:60]!r}"
    return True, ""


def inspect_language_pack(plugin_dir: str) -> dict:
    """
    Validate language pack JSON files for well-formedness and safety.
    Rejects packs containing unprompted URLs, executable scripts, dangerous HTML tags, or URI schemes.
    """
    errors = []
    # Check texts.json
    texts_path = os.path.join(plugin_dir, "texts.json")
    if os.path.isfile(texts_path):
        try:
            with open(texts_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                errors.append("texts.json must be a JSON object mapping English phrases to translations")
            else:
                for k, v in data.items():
                    if isinstance(v, str):
                        safe, err = is_safe_translation_string(k, v)
                        if not safe:
                            errors.append(f"texts.json: {err}")
                            if len(errors) >= 5:
                                break
        except Exception as e:
            errors.append(f"texts.json could not be parsed: {e}")

    # Check messages.json / translations.json
    for name in ("messages.json", "translations.json"):
        msg_path = os.path.join(plugin_dir, name)
        if os.path.isfile(msg_path):
            try:
                with open(msg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    errors.append(f"{name} must be a JSON object")
                else:
                    for k, v in data.items():
                        if isinstance(v, str):
                            safe, err = is_safe_translation_string(k, v)
                            if not safe:
                                errors.append(f"{name}: {err}")
                                if len(errors) >= 5:
                                    break
            except Exception as e:
                errors.append(f"{name} could not be parsed: {e}")

    return {"valid": len(errors) == 0, "errors": errors}
