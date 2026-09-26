"""
Example Activity Tracker plugin.

Demonstrates the PrivacyShield plugin SDK:
  - declaring a manifest + permissions
  - the on_event hook (reacting to lifecycle events)
  - permission-gated storage (counting events)
  - reading a setting

This plugin only requests low-risk permissions (receive_events, storage,
settings_read). It never asks for read_pii, so any PII in events arrives
redacted — it works purely on counts and metadata.

Copy this directory as a starting point for your own plugin.
"""

from privacyshield_sdk import Plugin, manifest

plugin = Plugin(manifest(
    id="example-tracker",
    name="Example Activity Tracker",
    version="1.0.0",
    author="PrivacyShield",
    description="Counts opt-out and confirmation events per broker.",
    permissions=["receive_events", "storage"],
    hooks=["on_event"],
    methods=["storage.get", "storage.set", "log"],
    events=["optout_sent", "optout_failed", "confirmation_received"],
    max_memory_mb=128,
    max_cpu_seconds=15,
    timeout_seconds=10,
))


@plugin.on_event
def handle_event(event):
    """
    Called for every lifecycle event. event has:
      event.event_type  — e.g. "optout_sent", "confirmation_received", "optout_failed"
      event.entity_id   — the related request id
      event.data        — dict of metadata (PII redacted unless read_pii granted)
    """
    plugin.log.info(f"event: {event.event_type} broker={event.data.get('broker', '?')}")

    # Count events per type using the plugin's isolated storage.
    counter_key = f"count:{event.event_type}"
    current = int(plugin.storage.get(counter_key) or "0")
    plugin.storage.set(counter_key, str(current + 1))

    # Count per broker too
    broker = event.data.get("broker")
    if broker:
        bkey = f"broker:{broker}:{event.event_type}"
        bcount = int(plugin.storage.get(bkey) or "0")
        plugin.storage.set(bkey, str(bcount + 1))

    return {"ok": True, "message": f"counted {event.event_type}"}


if __name__ == "__main__":
    plugin.run()
