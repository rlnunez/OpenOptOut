"""
Example Custom Broker Form Filler.

Demonstrates the fill_form hook: providing a bespoke opt-out strategy for a
specific broker whose form the built-in engine handles poorly.

Key security property: the plugin NEVER drives a browser itself. It receives
the broker context (and, because it requested read_pii, the member's field
values) and returns a list of browser ACTIONS. The host executes those actions
in its own sandboxed Playwright context. This keeps the browser — and the
network access it implies — inside the host, not the untrusted plugin.

This example targets a fictional broker "dataclear.example" with a two-step
form. Adapt the selectors and logic for real brokers.
"""

from privacyshield_sdk import Plugin, manifest, FormResult

plugin = Plugin(manifest(
    id="example-broker-filler",
    name="Example Custom Broker Form Filler",
    version="1.0.0",
    author="PrivacyShield",
    description="Custom form strategy for dataclear.example.",
    permissions=["fill_forms", "read_pii", "storage"],
    hooks=["fill_form"],
    methods=["storage.get", "storage.set", "log"],
    timeout_seconds=15,
))

# Only handle this specific broker; let the default engine handle everything else.
TARGET_BROKERS = {"dataclear.example", "dataclear"}


@plugin.fill_form
def fill(ctx):
    """
    ctx has:
      ctx.broker_id, ctx.broker_name, ctx.opt_out_url
      ctx.page_html   — current DOM (for inspecting structure)
      ctx.fields      — {"first_name", "last_name", "email", "address", ...}
                        (values present because we requested read_pii)
      ctx.broker_meta — {"method", "difficulty", ...}

    Return FormResult(handled=True, actions=[...]) to take over, or
    FormResult(handled=False) to let the default engine run.
    """
    name = (ctx.broker_name or "").lower()
    if not any(t in name for t in TARGET_BROKERS):
        return FormResult(handled=False)  # not our broker

    plugin.log.info(f"Custom-filling form for {ctx.broker_name}")

    f = ctx.fields
    actions = [
        # Step 1 — identity fields
        FormResult.fill("#firstName", f.get("first_name", "")),
        FormResult.fill("#lastName",  f.get("last_name", "")),
        FormResult.fill("#email",     f.get("email", "")),
        FormResult.fill("#address",   f.get("address", "")),
        FormResult.select("#state",   f.get("state", "")),
        # Step 2 — reason + submit
        FormResult.select("#reason", "ccpa_deletion"),
        FormResult.click("#agreeCheckbox"),
        FormResult.wait(500),
        FormResult.click("button[type=submit]"),
        FormResult.wait(2000),
    ]

    return FormResult(
        handled=True,
        actions=actions,
        success_selector="text=Your request has been received",
    )


if __name__ == "__main__":
    plugin.run()
