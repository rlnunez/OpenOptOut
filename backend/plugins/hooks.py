"""
Plugin hook integration helpers.

Thin, safe wrappers the core engines call. Each one:
  - is a no-op if the plugin system isn't running
  - never raises into the calling engine (plugins must not break core flows)

This keeps plugin awareness out of the core engine logic — the engines call
one of these functions at a natural boundary and carry on regardless of the
result.
"""

import logging

log = logging.getLogger(__name__)


def try_plugin_fill_form(broker: dict, page_html: str, fields: dict):
    """
    Ask plugins if any wants to handle this broker's form. Returns a dict of
    browser actions if handled, else None (engine uses its default strategy).
    """
    try:
        from . import get_manager
        mgr = get_manager()
        if not mgr:
            return None
        return mgr.dispatch_fill_form(broker, page_html, fields)
    except Exception as e:
        log.debug("plugin fill_form skipped: %s", e)
        return None


def try_plugin_parse_email(email: dict, tracking_keys: list):
    """Ask plugins to parse an email. Returns a match dict if handled, else None."""
    try:
        from . import get_manager
        mgr = get_manager()
        if not mgr:
            return None
        return mgr.dispatch_parse_email(email, tracking_keys)
    except Exception as e:
        log.debug("plugin parse_email skipped: %s", e)
        return None


def fire_event(event_type: str, entity_id: str = "", data: dict = None):
    """Broadcast a lifecycle event to plugins. Fire-and-forget, never raises."""
    try:
        from . import get_manager
        mgr = get_manager()
        if not mgr:
            return
        mgr.dispatch_event(event_type, entity_id=entity_id, data=data or {})
    except Exception as e:
        log.debug("plugin event %s skipped: %s", event_type, e)
