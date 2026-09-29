"""
Spec compiler: BrokerSpec + member  ->  Job.

This is the "produce a job / execute a job" seam the roadmap (item 7) asks us to
establish early, so that moving execution onto a worker fleet later is a
deployment change, not a rewrite. The compiler is PURE: it takes a declarative
BrokerSpec and a member's resolved field values and produces a Job — an ordered
list of fully-resolved primitive steps with no remaining field references and no
broker-specific logic. It never touches a browser or the network, which is what
makes the whole interpretation layer testable without Docker.

An executor (executor.py, and later a Playwright-backed one) consumes a Job and
performs it. The Job is a plain, serializable data structure, so it can be
enqueued and handed to a remote worker unchanged.
"""

from dataclasses import dataclass, field
from typing import Optional

from .broker_spec import BrokerSpec, Step, KNOWN_FIELDS


class CompileError(Exception):
    pass


@dataclass
class JobStep:
    """A fully-resolved primitive action. No field references remain — `value`
    holds the actual member value where a step referenced one."""
    kind: str
    selector: str = ""
    value: str = ""
    url: str = ""
    text: str = ""
    timeout_ms: int = 8000
    optional: bool = False

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "selector": self.selector,
            "value": self.value,
            "url": self.url,
            "text": self.text,
            "timeout_ms": self.timeout_ms,
            "optional": self.optional,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "JobStep":
        return cls(
            kind=str(d.get("kind", "")),
            selector=str(d.get("selector", "")),
            value=str(d.get("value", "")),
            url=str(d.get("url", "")),
            text=str(d.get("text", "")),
            timeout_ms=int(d.get("timeout_ms", 8000)),
            optional=bool(d.get("optional", False)),
        )


@dataclass
class EmailJob:
    """A resolved email send — templates already filled with member values."""
    to_address: str
    subject: str
    body: str
    locale: str = "en"

    def to_dict(self) -> dict:
        return {
            "to_address": self.to_address,
            "subject": self.subject,
            "body": self.body,
            "locale": self.locale,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EmailJob":
        return cls(
            to_address=str(d.get("to_address", "")),
            subject=str(d.get("subject", "")),
            body=str(d.get("body", "")),
            locale=str(d.get("locale", "en")),
        )


@dataclass
class Job:
    """
    A compiled, executable opt-out for one (broker × member). Serializable and
    self-contained: an executor (local or remote worker) can run it with no
    further reference to the spec or the member.
    """
    broker_id: str
    broker_name: str
    member_id: str
    method: str                       # "form" | "email" | "manual"
    steps: list[JobStep] = field(default_factory=list)   # for form method
    email: Optional[EmailJob] = None                     # for email method
    success_selector: str = ""
    success_text: str = ""

    def to_dict(self) -> dict:
        d = {
            "broker_id": self.broker_id, "broker_name": self.broker_name,
            "member_id": self.member_id, "method": self.method,
            "success_selector": self.success_selector, "success_text": self.success_text,
            "steps": [s.to_dict() if hasattr(s, "to_dict") else vars(s) for s in self.steps],
        }
        if self.email:
            d["email"] = self.email.to_dict() if hasattr(self.email, "to_dict") else vars(self.email)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        steps = [
            JobStep.from_dict(s) if isinstance(s, dict) else s
            for s in d.get("steps", [])
        ]
        email_data = d.get("email")
        email = EmailJob.from_dict(email_data) if isinstance(email_data, dict) else None
        return cls(
            broker_id=str(d.get("broker_id", "")),
            broker_name=str(d.get("broker_name", "")),
            member_id=str(d.get("member_id", "")),
            method=str(d.get("method", "form")),
            steps=steps,
            email=email,
            success_selector=str(d.get("success_selector", "")),
            success_text=str(d.get("success_text", "")),
        )


def _render(template: str, fields: dict) -> str:
    """
    Fill a template's {field} placeholders from resolved member fields. Missing
    fields render as empty string rather than raising, so a partially-populated
    member still produces a usable (if sparser) message; the caller decides
    whether required fields were present.
    """
    out = template
    for key, val in fields.items():
        out = out.replace("{" + key + "}", str(val if val is not None else ""))
    return out


def compile_job(spec: BrokerSpec, member_fields: dict, member_id: str) -> Job:
    """
    Compile a BrokerSpec into an executable Job for one member.

    member_fields: a dict mapping KNOWN_FIELDS names to that member's values
                   (the engine resolves this from a FamilyMember; the compiler
                   stays decoupled from the ORM by taking a plain dict).

    Raises CompileError if the spec is invalid or references data it can't
    resolve. Validating here means a bad add-on fails fast at compile time, on
    the control plane, before any browser work is dispatched.
    """
    errs = spec.validate()
    if errs:
        raise CompileError(f"invalid broker spec '{spec.broker_id}': {errs}")

    job = Job(
        broker_id=spec.broker_id, broker_name=spec.name,
        member_id=member_id, method=spec.method,
        success_selector=spec.success_selector, success_text=spec.success_text,
    )

    if spec.method == "manual":
        return job  # nothing to resolve; the engine queues it for a human

    if spec.method == "email":
        e = spec.email
        # Confirm required fields are actually present for this member.
        missing = [f for f in (e.require_fields or []) if not member_fields.get(f)]
        if missing:
            raise CompileError(
                f"member is missing fields required by '{spec.broker_id}' email: {missing}")
        job.email = EmailJob(
            to_address=e.to_address,
            subject=_render(e.subject_template, member_fields),
            body=_render(e.body_template, member_fields),
            locale=e.locale,
        )
        return job

    # method == "form": resolve each step, substituting field references.
    steps: list[JobStep] = []
    # If the spec has an opt_out_url and doesn't start with a navigate, prepend one.
    if spec.opt_out_url and not (spec.steps and spec.steps[0].kind == "navigate"):
        steps.append(JobStep(kind="navigate", url=spec.opt_out_url))

    for s in spec.steps:
        value = s.value
        text = s.text
        if s.kind in ("fill", "select") and s.field:
            if s.field not in KNOWN_FIELDS:
                raise CompileError(f"step references unknown field: {s.field}")
            resolved = member_fields.get(s.field)
            if resolved is None and not s.optional:
                raise CompileError(
                    f"member has no value for required field '{s.field}' "
                    f"(broker '{spec.broker_id}')")
            value = "" if resolved is None else str(resolved)
        elif s.kind == "click_matching" and s.field:
            if s.field not in KNOWN_FIELDS:
                raise CompileError(f"click_matching references unknown field: {s.field}")
            resolved = member_fields.get(s.field)
            if resolved is None and not s.optional:
                raise CompileError(
                    f"member has no value for required field '{s.field}' "
                    f"(broker '{spec.broker_id}')")
            if not text:
                text = "" if resolved is None else str(resolved)

        steps.append(JobStep(
            kind=s.kind, selector=s.selector, value=value, url=s.url,
            text=text, timeout_ms=s.timeout_ms, optional=s.optional,
        ))

    job.steps = steps
    return job
