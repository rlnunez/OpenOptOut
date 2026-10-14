"""
Live hand-off: a person finishes a step in the real page.

Two kinds of session share this machinery:

  captcha   an opt-out stopped at a CAPTCHA (keyed by the CaptchaChallenge)
  step      an opt-out stopped for a person (keyed by the RemovalRequest):
            a pause_for_human step ("pick your listing", "enter the code we
            texted you", "answer the question") or a form OpenOptOut wasn't
            sure how to fill. The Checklist offers "Do it here".

Both run the same opt-out again from the start, show the page live where it
stopped, let the person click and type in it, and carry on by themselves when
the person says they're done. A CAPTCHA met during a step session is solved
in the same live page.

When an opt-out stops at a CAPTCHA, the CAPTCHAs page offers "Solve it here".
That starts a live session:

  1. A browser is opened just for this, and the same opt-out runs again from
     the start with the same details (the saved combination on the challenge).
  2. When it reaches the CAPTCHA it waits. The person sees the page (a picture
     refreshed about once a second) and clicks, types and scrolls in it.
  3. When they press "I've solved it" (or the CAPTCHA reports solved), the
     opt-out carries on by itself from that exact page and finishes.

Nothing from the session is stored: frames are made on request and never
written to disk. A session ends after 10 minutes without the person, or when
the opt-out finishes. Only people who can see that family member can open it.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger(__name__)

VIEWPORT = {"width": 1280, "height": 800}
IDLE_LIMIT = 600          # seconds a session waits for the person
MAX_SESSIONS = 3

STATES = {
    "starting": "Opening the site…",
    "replaying": "Filling in the opt-out form again, up to the CAPTCHA…",
    "replaying_step": "Filling in the opt-out form again, up to the step that needs you…",
    "waiting_for_you_step": "Your turn: do the step below in the page, then press \"I've done this step\".",
    "done_step": "Done. OpenOptOut finished the opt-out.",
    "waiting_for_you": "Your turn: solve the CAPTCHA in the picture below, then press \"I've solved it\".",
    "continuing": "Thanks! Finishing the opt-out…",
    "done": "Done. The opt-out was sent.",
    "needs_you": "The site needs something else from you. It's on your Checklist.",
    "failed": "That didn't work. You can try again, or finish it on the site yourself.",
    "timed_out": "The session closed after 10 minutes without an answer. You can start it again.",
    "cancelled": "Stopped.",
}
ACTIVE = {"starting", "replaying", "waiting_for_you", "continuing"}
KINDS = ("captcha", "step")


class LiveSession:
    def __init__(self, ref_id: int, user_id: int, kind: str = "captcha"):
        self.kind = kind
        self.ref_id = ref_id
        self.challenge_id = ref_id    # older name, for the CAPTCHA kind
        self.user_id = user_id
        self.state = "starting"
        self.detail = ""
        self.prompt = ""              # what the person is asked to do now (step kind)
        self.prompt_kind = ""         # "captcha" | "pause" | "form"
        self.page = None
        self.solved = None            # asyncio.Event, made on the loop
        self.cancelled = False
        self.started = time.monotonic()
        self.touched = time.monotonic()

    def message(self) -> str:
        if self.kind == "step":
            if self.state == "replaying":
                return STATES["replaying_step"]
            if self.state == "waiting_for_you" and self.prompt_kind != "captcha":
                return STATES["waiting_for_you_step"]
            if self.state == "done":
                return STATES["done_step"]
        return STATES[self.state]

    def info(self) -> dict:
        return {"challenge_id": self.ref_id, "ref_id": self.ref_id, "kind": self.kind,
                "state": self.state, "message": self.message(),
                # The step's own instruction (already in the person's language).
                "prompt": self.prompt if self.state == "waiting_for_you" else "",
                "prompt_kind": self.prompt_kind if self.state == "waiting_for_you" else "",
                "detail": self.detail, "active": self.state in ACTIVE,
                "can_interact": self.state == "waiting_for_you" and self.page is not None}


class LiveManager:
    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = threading.Lock()
        self.sessions: dict[int, LiveSession] = {}

    # ── loop ──────────────────────────────────────────────────────────────────
    def _ensure_loop(self):
        with self._lock:
            if self._loop is None:
                self._loop = asyncio.new_event_loop()
                threading.Thread(target=self._loop.run_forever, name="live-captcha", daemon=True).start()
        return self._loop

    def _call(self, coro, timeout=10):
        return asyncio.run_coroutine_threadsafe(coro, self._ensure_loop()).result(timeout=timeout)

    # ── public API (called from request handlers) ─────────────────────────────
    # `ref` is the CaptchaChallenge id (kind "captcha") or the RemovalRequest id
    # (kind "step").
    def start(self, ref: int, user_id: int, runner=None, kind: str = "captcha") -> dict:
        s = self.sessions.get((kind, ref))
        if s and s.state in ACTIVE:
            s.touched = time.monotonic()
            return s.info()
        if sum(1 for x in self.sessions.values() if x.state in ACTIVE) >= MAX_SESSIONS:
            raise RuntimeError("Too many live sessions are open right now. Try again in a few minutes.")
        s = LiveSession(ref, user_id, kind)
        self.sessions[(kind, ref)] = s
        default = _run if kind == "captcha" else _run_step
        asyncio.run_coroutine_threadsafe((runner or default)(s), self._ensure_loop())
        return s.info()

    def status(self, ref: int, kind: str = "captcha") -> Optional[dict]:
        s = self.sessions.get((kind, ref))
        if s:
            s.touched = time.monotonic()
        return s.info() if s else None

    def frame(self, ref: int, kind: str = "captcha") -> Optional[bytes]:
        s = self.sessions.get((kind, ref))
        if not s or s.page is None or s.state not in ACTIVE:
            return None
        s.touched = time.monotonic()
        try:
            return self._call(s.page.screenshot(type="jpeg", quality=60), timeout=8)
        except Exception:
            return None

    def send_input(self, ref: int, ev: dict, kind: str = "captcha") -> bool:
        s = self.sessions.get((kind, ref))
        if not s or s.page is None or s.state != "waiting_for_you":
            return False
        s.touched = time.monotonic()
        return bool(self._call(_apply_input(s.page, ev), timeout=10))

    def solved(self, ref: int, kind: str = "captcha") -> bool:
        """The person says they're done (solved the CAPTCHA, or did the step)."""
        s = self.sessions.get((kind, ref))
        if not s or s.state != "waiting_for_you" or s.solved is None:
            return False
        self._ensure_loop().call_soon_threadsafe(s.solved.set)
        return True

    def cancel(self, ref: int, kind: str = "captcha") -> bool:
        s = self.sessions.get((kind, ref))
        if not s or s.state not in ACTIVE:
            return False
        s.cancelled = True
        if s.solved is not None:
            self._ensure_loop().call_soon_threadsafe(s.solved.set)
        return True


MANAGER = LiveManager()


# ── input ─────────────────────────────────────────────────────────────────────

ALLOWED_KEYS = {"Enter", "Tab", "Backspace", "Delete", "Escape", "ArrowUp", "ArrowDown", "ArrowLeft",
                "ArrowRight", "Space", "Home", "End", "PageUp", "PageDown"}


async def _apply_input(page, ev: dict) -> bool:
    kind = ev.get("type")
    if kind == "click":
        x = max(0, min(VIEWPORT["width"], float(ev.get("x", 0))))
        y = max(0, min(VIEWPORT["height"], float(ev.get("y", 0))))
        await page.mouse.click(x, y)
    elif kind == "text":
        text = str(ev.get("text", ""))[:200]
        await page.keyboard.type(text, delay=40)
    elif kind == "key":
        key = str(ev.get("key", ""))
        if key not in ALLOWED_KEYS:
            return False
        await page.keyboard.press(key)
    elif kind == "scroll":
        await page.mouse.wheel(0, max(-2000, min(2000, float(ev.get("dy", 0)))))
    else:
        return False
    return True


async def _captcha_token_present(page) -> bool:
    try:
        return bool(await page.evaluate(
            "() => ['g-recaptcha-response','h-captcha-response','cf-turnstile-response']"
            ".some(n => [...document.getElementsByName(n)].some(e => (e.value || '').length > 20))"))
    except Exception:
        return False


PROBLEMS = {
    "no_browser": "The server's browser isn't installed. An administrator can check the System logs.",
    "slow": "The site took too long to answer.",
    "unreachable": "The site couldn't be reached.",
    "other": "Something went wrong on the server. An administrator can check the System logs.",
}


def _plain(e: Exception) -> str:
    """What went wrong, for the person (the full error goes to the log)."""
    t = str(e)
    if "Executable doesn't exist" in t or "playwright install" in t:
        return PROBLEMS["no_browser"]
    if "Timeout" in t or "timeout" in t:
        return PROBLEMS["slow"]
    if "net::" in t or "NS_ERROR" in t:
        return PROBLEMS["unreachable"]
    return PROBLEMS["other"]


# ── the session itself ────────────────────────────────────────────────────────

def _person_solver(s: LiveSession):
    async def solver(challenge: dict) -> dict:
        # A CAPTCHA the person already solved still shows its widget; if the
        # page holds an answer, carry on without asking again.
        if s.page is not None and await _captcha_token_present(s.page):
            return {"solved": True, "by_person": True}
        s.prompt, s.prompt_kind = "", "captcha"
        if not await _wait_for_person(s):
            return {"defer_to_human": True}
        return {"solved": True, "by_person": True}
    return solver


async def _wait_for_person(s: LiveSession) -> bool:
    """Wait until the person says they're done. False if they cancelled or left."""
    s.solved = asyncio.Event()
    s.state, s.touched = "waiting_for_you", time.monotonic()
    while True:
        try:
            await asyncio.wait_for(s.solved.wait(), timeout=15)
            break
        except asyncio.TimeoutError:
            if time.monotonic() - s.touched > IDLE_LIMIT:
                s.state = "timed_out"
                return False
    if s.cancelled:
        return False
    s.state = "continuing"
    return True


def _person_step(s: LiveSession):
    """The executor's person_hook: show the step's instruction with the live
    page, and carry on from the same page once the person has done it."""
    async def hook(info: dict) -> bool:
        s.prompt, s.prompt_kind = str(info.get("text") or ""), str(info.get("kind") or "pause")
        return await _wait_for_person(s)
    return hook


async def _run_step(s: LiveSession) -> None:
    """A person picks up an opt-out that stopped for them (a pause_for_human
    step or a form OpenOptOut wasn't sure about), on the same page."""
    from playwright.async_api import async_playwright
    from ..models.database import SessionLocal, RemovalRequest
    from .settings_store import load_settings
    from . import optout_engine as oe
    from .combinations import IdentityCombo
    db = SessionLocal()
    try:
        req = db.query(RemovalRequest).filter(RemovalRequest.id == s.ref_id).first()
        if req is None or not req.handoff_enc:
            s.state, s.detail = "failed", "there's nothing to pick up for this opt-out any more"
            return
        try:
            combo = IdentityCombo(**json.loads(req.handoff_enc).get("combo") or {})
        except Exception:
            combo = None
        cfg = load_settings()
        async with async_playwright() as p:
            browser, _ = await oe._launch_browser(p)
            try:
                context = await oe._fresh_context(browser)
                page = await context.new_page()
                await page.set_viewport_size(VIEWPORT)
                s.page = page
                s.state = "replaying"
                res = await oe._run_form_via_interpreter(req, page, cfg, db, combo=combo,
                                                         captcha_solver_override=_person_solver(s),
                                                         person_hook_override=_person_step(s))
                if s.state == "timed_out" or s.cancelled:
                    s.state = "cancelled" if s.cancelled else s.state
                    return
                finish_step(db, req, res, s.user_id)
                s.state = "done" if res.ok else ("needs_you" if res.needs_manual else "failed")
                s.detail = "" if res.ok else (res.detail or "")[:200]
            finally:
                s.page = None
                await browser.close()
    except Exception as e:
        log.warning("Live step session for request %s failed: %s", s.ref_id, e)
        s.state, s.detail = "failed", _plain(e)
    finally:
        db.close()


def finish_step(db, req, res, user_id: int, now: Optional[datetime] = None) -> None:
    """Record what a live step session achieved. A session that didn't finish
    leaves the opt-out on the Checklist as it was; it is never marked failed."""
    from ..models.database import RequestStatus, AutomationLog
    from .settings_store import load_settings
    now = now or datetime.utcnow()
    if res.ok:
        req.status = RequestStatus.sent
        req.sent_at = now
        days = load_settings().get("scheduler", {}).get("recheck_interval_days", 90)
        req.recheck_after = now + timedelta(days=days)
        req.notes = "Finished live: a person did the step that needed them, and OpenOptOut sent the rest."
        req.handoff_enc = None
        try:
            from .broker_health import record_success
            record_success(db, req.broker_id)
        except Exception:
            pass
    elif res.needs_manual and res.human_instruction:
        req.notes = res.human_instruction     # a different step now needs them
    db.add(AutomationLog(request_id=req.id, member_id=req.member_id, broker_id=req.broker_id,
                         action="step_live", status="success" if res.ok else "needs_manual",
                         detail=("live hand-off: " + (res.detail or ("finished" if res.ok else "didn't finish")))[:500],
                         duration_ms=0))
    db.commit()


async def _run(s: LiveSession) -> None:
    from playwright.async_api import async_playwright
    from ..models.database import SessionLocal, CaptchaChallenge
    from .settings_store import load_settings
    from . import optout_engine as oe
    from .combinations import IdentityCombo
    db = SessionLocal()
    try:
        ch = db.query(CaptchaChallenge).filter(CaptchaChallenge.id == s.challenge_id).first()
        if ch is None or ch.request is None:
            s.state, s.detail = "failed", "the challenge is gone"
            return
        req = ch.request
        combo = None
        if ch.combo_enc:
            try:
                combo = IdentityCombo(**json.loads(ch.combo_enc))
            except Exception:
                combo = None
        cfg = load_settings()
        async with async_playwright() as p:
            browser, _ = await oe._launch_browser(p)
            try:
                context = await oe._fresh_context(browser)
                page = await context.new_page()
                await page.set_viewport_size(VIEWPORT)
                s.page = page
                s.state = "replaying"
                res = await oe._run_form_via_interpreter(req, page, cfg, db, combo=combo,
                                                         captcha_solver_override=_person_solver(s))
                if s.state in ("timed_out",) or s.cancelled:
                    s.state = "cancelled" if s.cancelled else s.state
                    return
                finish(db, ch, req, res, s.user_id)
                s.state = ("done" if res.ok else "needs_you" if res.needs_manual and not res.needs_captcha
                           else "failed")
                s.detail = "" if res.ok else (res.detail or "")[:200]
            finally:
                s.page = None
                await browser.close()
    except Exception as e:
        log.warning("Live CAPTCHA session %s failed: %s", s.challenge_id, e)
        s.state, s.detail = "failed", _plain(e)
    finally:
        db.close()


def finish(db, ch, req, res, user_id: int, now: Optional[datetime] = None) -> None:
    """Record what the live session achieved, like a normal run would."""
    from ..models.database import RequestStatus, AutomationLog
    from .settings_store import load_settings
    now = now or datetime.utcnow()
    if res.ok:
        req.status = RequestStatus.sent
        req.sent_at = now
        days = load_settings().get("scheduler", {}).get("recheck_interval_days", 90)
        req.recheck_after = now + timedelta(days=days)
        req.notes = "Finished live after a person solved the CAPTCHA."
        ch.status, ch.resolved_by, ch.resolved_at = "resolved", user_id, now
        ch.notes = "Solved live by a person; the opt-out finished on its own."
        try:
            from .broker_health import record_success
            record_success(db, req.broker_id)
        except Exception:
            pass
    elif res.needs_manual and not res.needs_captcha:
        req.status = RequestStatus.needs_manual
        req.notes = res.human_instruction or req.notes
        ch.status, ch.resolved_by, ch.resolved_at = "resolved", user_id, now
        ch.notes = "CAPTCHA solved live; the site then needed something only a person can do."
    db.add(AutomationLog(request_id=req.id, member_id=req.member_id, broker_id=req.broker_id,
                         action="captcha_live", status="success" if res.ok else "failure",
                         detail=("live hand-off: " + (res.detail or ("finished" if res.ok else "didn't finish")))[:500],
                         duration_ms=0))
    db.commit()
