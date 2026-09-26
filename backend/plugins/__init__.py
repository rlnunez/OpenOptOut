"""
PrivacyShield plugin system.

Process-isolated, gRPC-based plugin architecture with OS-level sandboxing and
capability-gated permissions. See docs/PLUGINS.md for the full design and
security model.

Public entry points:
    init_plugin_system()  — construct + start the manager (called at app startup)
    get_manager()         — access the running manager for hook dispatch
"""

import os
import logging

from .manager import PluginManager, get_manager, set_manager
from .storage import make_storage_backend
from .settings_access import PluginSettingsAccessor

log = logging.getLogger(__name__)


def init_plugin_system():
    """
    Wire up and start the plugin manager. Safe to call once at startup.
    Reads configuration from settings; degrades gracefully if gRPC is missing.
    """
    from ..core.settings_store import load_settings
    from ..models.database import SessionLocal

    settings = load_settings()
    pcfg = settings.get("plugins", {})

    if not pcfg.get("enabled", False):
        log.info("Plugin system disabled in settings — not starting.")
        return None

    plugins_dir  = os.getenv("PLUGINS_DIR", pcfg.get("plugins_dir", "/data/plugins"))
    storage_mode = pcfg.get("storage_mode", "db")   # "db" | "file"
    storage_root = os.getenv("PLUGIN_STORAGE_DIR", "/data/plugin_storage")

    os.makedirs(plugins_dir, exist_ok=True)

    storage_backend = make_storage_backend(
        storage_mode, session_factory=SessionLocal, storage_root=storage_root
    )

    def _save_settings(s):
        from ..core.settings_store import SETTINGS_FILE
        import json
        with open(SETTINGS_FILE, "w") as f:
            json.dump(s, f, indent=2)

    settings_accessor = PluginSettingsAccessor(load_settings, _save_settings)

    manager = PluginManager(
        plugins_dir=plugins_dir,
        session_factory=SessionLocal,
        storage_backend=storage_backend,
        settings_accessor=settings_accessor,
    )
    set_manager(manager)
    manager.start()
    return manager


__all__ = ["init_plugin_system", "get_manager", "set_manager", "PluginManager"]
