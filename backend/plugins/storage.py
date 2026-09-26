"""
Plugin storage backend.

Per your requirement, plugins can persist data to either the database or a
file, chosen by configuration. Both back the same interface the capability
broker expects. Storage is namespaced per plugin (plugin_id is part of every
key path), so one plugin can never read another's data.

DB backend  — a single plugin_storage table (key/value scoped by plugin_id).
File backend — one JSON file per plugin under a storage root.
"""

import os
import json
import threading
import logging
from typing import Optional

log = logging.getLogger(__name__)


class DBStorageBackend:
    """Key/value storage in the application database."""

    def __init__(self, session_factory):
        self._session_factory = session_factory

    def get(self, plugin_id: str, key: str) -> Optional[str]:
        from ..models.database import PluginStorage
        db = self._session_factory()
        try:
            row = db.query(PluginStorage).filter(
                PluginStorage.plugin_id == plugin_id,
                PluginStorage.key == key,
            ).first()
            return row.value if row else None
        finally:
            db.close()

    def set(self, plugin_id: str, key: str, value: str) -> None:
        from ..models.database import PluginStorage
        db = self._session_factory()
        try:
            row = db.query(PluginStorage).filter(
                PluginStorage.plugin_id == plugin_id,
                PluginStorage.key == key,
            ).first()
            if row:
                row.value = value
            else:
                db.add(PluginStorage(plugin_id=plugin_id, key=key, value=value))
            db.commit()
        finally:
            db.close()

    def delete(self, plugin_id: str, key: str) -> None:
        from ..models.database import PluginStorage
        db = self._session_factory()
        try:
            db.query(PluginStorage).filter(
                PluginStorage.plugin_id == plugin_id,
                PluginStorage.key == key,
            ).delete()
            db.commit()
        finally:
            db.close()

    def list(self, plugin_id: str, prefix: str) -> list[str]:
        from ..models.database import PluginStorage
        db = self._session_factory()
        try:
            q = db.query(PluginStorage.key).filter(PluginStorage.plugin_id == plugin_id)
            if prefix:
                q = q.filter(PluginStorage.key.like(f"{prefix}%"))
            return [r.key for r in q.all()]
        finally:
            db.close()


class FileStorageBackend:
    """Key/value storage in per-plugin JSON files. Thread-safe."""

    def __init__(self, storage_root: str):
        self.root = storage_root
        os.makedirs(self.root, exist_ok=True)
        self._locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def _lock_for(self, plugin_id: str) -> threading.Lock:
        with self._global_lock:
            if plugin_id not in self._locks:
                self._locks[plugin_id] = threading.Lock()
            return self._locks[plugin_id]

    def _path(self, plugin_id: str) -> str:
        # plugin_id is validated alphanumeric in the manifest, safe for a filename
        return os.path.join(self.root, f"{plugin_id}.json")

    def _read(self, plugin_id: str) -> dict:
        path = self._path(plugin_id)
        if not os.path.exists(path):
            return {}
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return {}

    def _write(self, plugin_id: str, data: dict) -> None:
        path = self._path(plugin_id)
        tmp  = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, path)

    def get(self, plugin_id: str, key: str) -> Optional[str]:
        with self._lock_for(plugin_id):
            return self._read(plugin_id).get(key)

    def set(self, plugin_id: str, key: str, value: str) -> None:
        with self._lock_for(plugin_id):
            data = self._read(plugin_id)
            data[key] = value
            self._write(plugin_id, data)

    def delete(self, plugin_id: str, key: str) -> None:
        with self._lock_for(plugin_id):
            data = self._read(plugin_id)
            data.pop(key, None)
            self._write(plugin_id, data)

    def list(self, plugin_id: str, prefix: str) -> list[str]:
        with self._lock_for(plugin_id):
            keys = list(self._read(plugin_id).keys())
            return [k for k in keys if not prefix or k.startswith(prefix)]


def make_storage_backend(mode: str, session_factory=None, storage_root: str = "/data/plugin_storage"):
    """
    Factory: choose DB or file storage.
      mode="db"   -> DBStorageBackend (needs session_factory)
      mode="file" -> FileStorageBackend (needs storage_root)
    """
    if mode == "db":
        if session_factory is None:
            raise ValueError("db storage requires a session_factory")
        log.info("Plugin storage backend: database")
        return DBStorageBackend(session_factory)
    else:
        log.info("Plugin storage backend: file (%s)", storage_root)
        return FileStorageBackend(storage_root)
