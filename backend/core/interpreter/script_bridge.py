"""
Bridge: build a declarative BrokerSpec from the existing Broker + BrokerScript
data, so the interpreter engine can run form opt-outs off the selectors already
stored per broker — no need to author new specs from scratch to migrate.

If a broker has a usable BrokerScript (at least a submit or a field selector),
spec_from_script() returns a BrokerSpec the interpreter can compile+execute.
If it doesn't, returns None and the caller falls back to the legacy engine.
"""

import json
import logging

from .broker_spec import BrokerSpec, Step

log = logging.getLogger(__name__)


def spec_from_script(broker, script) -> "BrokerSpec | None":
    """
    Translate a BrokerScript's stored selectors into a BrokerSpec's ordered
    steps. Field selectors map to `fill` steps bound to member fields; the
    submit selector to `submit`; success signal to `expect_success`; a
    requires_captcha flag inserts a `solve_captcha` step before submit. Any
    extra_steps JSON is appended as raw actions.

    Returns None if there's not enough to act on (no field/submit selectors),
    so the caller can fall back to the legacy combo engine.
    """
    if not script:
        return None

    steps: list[Step] = []

    # Field selector -> member field mapping (only add steps for selectors set).
    field_map = [
        ("name_selector",    "full_name"),
        ("email_selector",   "email"),
        ("address_selector", "address"),
        ("city_selector",    "city"),
        ("state_selector",   "state"),
        ("zip_selector",     "zip"),
    ]
    for attr, field in field_map:
        sel = getattr(script, attr, None)
        if sel:
            # name maps to full_name; others map 1:1. Mark optional so a missing
            # member value doesn't hard-fail the whole flow.
            steps.append(Step(kind="fill", selector=sel, field=field, optional=True))

    # CAPTCHA handoff before submit, if the script says the broker uses one.
    if getattr(script, "requires_captcha", False):
        steps.append(Step(kind="solve_captcha", selector=".g-recaptcha", optional=True))

    if getattr(script, "submit_selector", None):
        steps.append(Step(kind="submit", selector=script.submit_selector))

    # Success confirmation.
    if getattr(script, "success_selector", None):
        steps.append(Step(kind="expect_success", selector=script.success_selector))
    elif getattr(script, "success_text", None):
        steps.append(Step(kind="expect_success", text=script.success_text))

    # Append any extra raw steps stored as JSON.
    raw = getattr(script, "extra_steps", None)
    if raw:
        try:
            for a in json.loads(raw):
                if not isinstance(a, dict):
                    continue
                steps.append(Step(
                    kind=a.get("action", ""),
                    selector=a.get("selector", ""),
                    value=a.get("value", ""),
                    timeout_ms=int(a.get("timeout_ms", 8000) or 8000),
                    optional=bool(a.get("optional", False)),
                ))
        except Exception as e:
            log.warning("broker %s extra_steps parse failed: %s", broker.name, e)

    # Not enough to act on -> caller should fall back to heuristic spec or None.
    has_actionable = any(s.kind in ("fill", "submit") for s in steps)
    if not has_actionable:
        return None

    opt_out_url = getattr(script, "search_url", None) or getattr(broker, "opt_out_url", "") or ""

    import re
    raw_slug = str(getattr(broker, "id", "") or getattr(broker, "name", "broker"))
    broker_id = re.sub(r'[^a-zA-Z0-9_-]', '_', raw_slug).strip('_') or "broker"

    spec = BrokerSpec(
        broker_id=broker_id,
        name=getattr(broker, "name", "broker"),
        method="form",
        opt_out_url=opt_out_url,
        steps=steps,
        success_selector=getattr(script, "success_selector", "") or "",
        success_text=getattr(script, "success_text", "") or "",
    )
    # Only return it if it validates; otherwise None so caller can use heuristic fallback.
    errs = spec.validate()
    if errs:
        log.info("broker %s spec-from-script invalid: %s", broker.name, errs)
        return None
    return spec


def heuristic_spec_for_broker(broker) -> BrokerSpec:
    """
    Generate a declarative BrokerSpec with standard heuristic form steps for brokers
    that do not yet have an authored add-on or BrokerScript. Replaces the legacy
    combination engine's hardcoded selector heuristics with a clean, unified BrokerSpec.
    """
    import re
    raw_slug = str(getattr(broker, "id", "") or getattr(broker, "name", "broker"))
    broker_id = re.sub(r'[^a-zA-Z0-9_-]', '_', raw_slug).strip('_') or "broker"
    opt_out_url = getattr(broker, "opt_out_url", "") or "https://example.com/optout"

    steps = [
        Step(kind="fill", selector="input[name='firstName'], input[id*='first' i]", field="first_name", optional=True),
        Step(kind="fill", selector="input[name='lastName'], input[id*='last' i]", field="last_name", optional=True),
        Step(kind="fill", selector="input[name='name'], input[id*='fullname' i], input[name*='name' i]", field="full_name", optional=True),
        Step(kind="fill", selector="input[type='email'], input[name*='email' i]", field="email", optional=True),
        Step(kind="fill", selector="input[name*='address' i], input[id*='address' i]", field="address", optional=True),
        Step(kind="fill", selector="input[name*='city' i], input[id*='city' i]", field="city", optional=True),
        Step(kind="fill", selector="input[name*='state' i], select[name*='state' i]", field="state", optional=True),
        Step(kind="fill", selector="input[name*='zip' i], input[id*='zip' i]", field="zip", optional=True),
        Step(kind="submit", selector="button[type='submit'], input[type='submit'], button:has-text('Opt Out'), button:has-text('Remove'), button:has-text('Submit'), button:has-text('Request Removal')", optional=True),
    ]

    return BrokerSpec(
        broker_id=broker_id,
        name=getattr(broker, "name", "broker"),
        method="form",
        opt_out_url=opt_out_url,
        steps=steps,
        notes="Heuristic fallback spec automatically generated for unscripted broker",
    )


def get_or_build_broker_spec(broker, script=None, db=None) -> BrokerSpec:
    """
    Resolve the single authoritative BrokerSpec for this broker.
    1. Checks installed declarative Broker Add-on (Item 1).
    2. Checks compiled BrokerScript selectors (Item 2).
    3. Generates a heuristic BrokerSpec fallback if no explicit rules exist.
    Guaranteed to return a valid BrokerSpec so execution never requires legacy engines.
    """
    if db is not None:
        try:
            from ...plugins.broker_addon import get_broker_spec_for_broker
            spec = get_broker_spec_for_broker(db, broker)
            if spec:
                return spec
        except Exception:
            pass

    if script is not None:
        spec = spec_from_script(broker, script)
        if spec:
            return spec

    return heuristic_spec_for_broker(broker)

