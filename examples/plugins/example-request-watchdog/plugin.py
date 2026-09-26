"""
Example Request Watchdog.

Demonstrates the broker-read and request-lifecycle capabilities added for
plugins that want to interact with the opt-out pipeline itself, not just
observe it.

Key security properties on display:
  - broker.get / broker.history return only IDs, enums, and counts — never a
    member's name, address, phone, or email.
  - request.get_status returns only status/timestamps — same PII exclusion.
  - request.mark_failed is a HIGH-RISK write: it requires the request_write
    permission, and the host logs a before/after diff of the status change to
    the audit trail (visible to the super admin), tagged with this plugin's id
    and the reason string this plugin supplies.

This plugin only DEMONSTRATES the calls on a periodic event; wire in your own
logic for identifying which requests are actually stuck before marking them
failed in a real deployment.
"""

from privacyshield_sdk import Plugin, manifest

plugin = Plugin(manifest(
    id="example-request-watchdog",
    name="Example Request Watchdog",
    version="1.0.0",
    author="PrivacyShield",
    description="Checks broker stats and can mark stuck requests failed.",
    permissions=["receive_events", "broker_read", "request_read", "request_write", "storage"],
    hooks=["on_event"],
    methods=["broker.get", "broker.history", "request.get_status",
             "request.mark_failed", "storage.get", "storage.set", "log"],
    events=["tick"],
    timeout_seconds=10,
))


@plugin.on_event
def handle_tick(event):
    """
    Example flow on a periodic 'tick' event:
      1. Read a broker's aggregate history (counts only — no member data).
      2. Look up a specific request's status by id (also PII-free).
      3. If it looks stuck, mark it failed with a stated reason. This call is
         audit-logged by the host with the before/after status.

    This is illustrative — a real watchdog would track its own list of
    request ids to check (e.g. via plugin.storage) rather than hardcoding one.
    """
    if event.event_type != "tick":
        return {"ok": True}

    # Example: check broker id 1's aggregate stats (counts only).
    history = plugin.brokers.history(1)
    if history:
        plugin.log.info(
            f"broker 1: {history['pending_count']} pending, "
            f"{history['failed_count']} failed, {history['confirmed_count']} confirmed"
        )

    # Example: look up a specific request this plugin has been tracking via
    # its own storage (never member PII — just an id it remembered).
    tracked_id = plugin.storage.get("watching_request_id")
    if tracked_id:
        status = plugin.requests.get_status(int(tracked_id))
        if status and status["status"] == "sent":
            # Illustrative stuck-request threshold check would go here.
            # If genuinely stuck, mark it failed with a clear, auditable reason:
            # result = plugin.requests.mark_failed(int(tracked_id), reason="stuck >30d with no confirmation")
            # plugin.log.info(f"marked request {tracked_id} failed: {result}")
            pass

    return {"ok": True}


if __name__ == "__main__":
    plugin.run()
