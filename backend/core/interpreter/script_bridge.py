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

    # Not enough to act on -> let the caller fall back to the legacy engine.
    has_actionable = any(s.kind in ("fill", "submit") for s in steps)
    if not has_actionable:
        return None

    opt_out_url = getattr(script, "search_url", None) or getattr(broker, "opt_out_url", "") or ""

    spec = BrokerSpec(
        broker_id=str(getattr(broker, "id", "") or getattr(broker, "name", "broker")),
        name=getattr(broker, "name", "broker"),
        method="form",
        opt_out_url=opt_out_url,
        steps=steps,
        success_selector=getattr(script, "success_selector", "") or "",
        success_text=getattr(script, "success_text", "") or "",
    )
    # Only return it if it validates; otherwise fall back rather than run a bad spec.
    errs = spec.validate()
    if errs:
        log.info("broker %s spec-from-script invalid, using legacy engine: %s",
                 broker.name, errs)
        return None
    return spec
