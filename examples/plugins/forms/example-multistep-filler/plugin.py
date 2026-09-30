"""
Example Multi-Step Broker Form Filler (Roadmap Item 3 Reference Plugin).

Demonstrates handling complex, multi-page broker flows:
  Stage 1: Search Directory (fill full name and city, press Enter)
  Stage 2: Select Profile (match record using click_matching based on city/state)
  Stage 3: Fill Opt-Out Form inside an embedded iframe, submit, and verify removal confirmation.

Key Security Property:
The plugin NEVER touches the network or drives a browser directly.
It receives rich page context from the host and yields structured BrowserActions,
which the host executes in its secure sandboxed Playwright container.
"""

from openoptout_sdk import Plugin, manifest, FormResult

plugin = Plugin(manifest(
    id="example-multistep-filler",
    name="Example Multi-Step Wizard Broker Filler",
    version="1.0.0",
    author="OpenOptOut",
    description="Multi-page broker wizard handler.",
    permissions=["fill_forms", "read_pii", "storage"],
    hooks=["fill_form"],
    methods=["storage.get", "storage.set", "log"],
    timeout_seconds=20,
))

TARGET_BROKERS = {"multipage-records.example", "wizard-broker", "complexsearch"}


@plugin.fill_form
def fill(ctx):
    """
    ctx provides rich page context:
      ctx.broker_id, ctx.broker_name, ctx.opt_out_url
      ctx.current_url  — current page URL (tracks multi-page navigation)
      ctx.page_title   — current document title
      ctx.has_iframes  — True if embedded frames were detected on the page
      ctx.stage_index  — 0 for initial page, incremented on multi-stage flows
      ctx.page_html    — current page DOM
      ctx.fields       — patron fields (e.g. first_name, last_name, email, city, state)
    """
    name = (ctx.broker_name or "").lower()
    if not any(t in name for t in TARGET_BROKERS):
        return FormResult(handled=False)

    f = ctx.fields
    stage = ctx.stage_index
    plugin.log.info(f"Multi-step filler active for {ctx.broker_name} (Stage {stage + 1})")

    # Stage 0: Search Directory Page
    if stage == 0:
        actions = [
            FormResult.fill("#search-name", f.get("full_name") or f"{f.get('first_name', '')} {f.get('last_name', '')}".strip()),
            FormResult.fill("#search-city", f.get("city", "")),
            FormResult.press("#search-city", "Enter"),
            FormResult.wait(2000),
        ]
        return FormResult(
            handled=True,
            actions=actions,
            next_stage=True,  # Request next stage after results page renders
        )

    # Stage 1: Select Profile Matching Patron
    elif stage == 1:
        # Match listing row containing the patron's city or state
        target_loc = f.get("city") or f.get("state") or "View Record"
        actions = [
            FormResult.scroll("#search-results"),
            FormResult.click_matching(".result-row", target_loc),
            FormResult.wait(1500),
        ]
        return FormResult(
            handled=True,
            actions=actions,
            next_stage=True,
        )

    # Stage 2: Final Removal Request Submission (Inside iframe)
    else:
        actions = []
        if ctx.has_iframes:
            actions.append(FormResult.frame("iframe#optout-form-frame"))

        actions.extend([
            FormResult.fill("#optout-email", f.get("email", "")),
            FormResult.check("#certify-checkbox"),
            FormResult.click("button[type=submit]"),
            FormResult.wait(2000),
        ])

        if ctx.has_iframes:
            actions.append(FormResult.frame("main"))

        return FormResult(
            handled=True,
            actions=actions,
            next_stage=False,
            success_selector=".removal-confirmed, text=Request Received",
        )


if __name__ == "__main__":
    plugin.run()
