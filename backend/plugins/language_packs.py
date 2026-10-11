"""
Built-in language packs.

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
    from . import layout
    try:
        from ..models.database import InstalledPlugin
    except (ImportError, ValueError):
        from models.database import InstalledPlugin
    stats = {"installed": 0, "updated": 0, "skipped": 0}
    root = layout.plugins_root()
    for found in layout.scan(layout.BUNDLED_ROOT):
        m = found.manifest if found.valid else None
        if m is None or m.effective_type != "languages":
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
            log.error("Could not install built-in language pack %s: %s", m.id, e)
    if stats["installed"] or stats["updated"]:
        log.info("Built-in language packs: %s", stats)
    return stats
