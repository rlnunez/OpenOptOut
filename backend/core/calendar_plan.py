"""
Calendar-based scheduling.

  run_allowed()   is today an opt-out day? (weekdays chosen, holidays skipped)
  upcoming()      what's coming up for the given people: opt-out days, checks,
                  legal deadlines, skipped dates
  to_ics()        the same as an iCalendar feed people can subscribe to

The feed is reached by a private link (a random token per account, stored
only as a hash), because calendar apps can't sign in. It shows first names
and site names only: no addresses, phone numbers or emails.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def clean_days(days) -> Optional[list]:
    if not days:
        return None
    out = sorted({int(d) for d in days if str(d).lstrip("-").isdigit() and 0 <= int(d) <= 6})
    return out if out and len(out) < 7 else None      # all seven = no limit


def clean_dates(dates) -> list:
    out = set()
    for d in dates or []:
        try:
            out.add(date.fromisoformat(str(d).strip()[:10]).isoformat())
        except ValueError:
            continue
    return sorted(out)


def _tz(sc: dict):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(sc.get("timezone") or "America/Chicago")
    except Exception:
        return None


def local_today(sc: dict, now: Optional[datetime] = None) -> date:
    now = now or datetime.utcnow()
    tz = _tz(sc)
    if tz is None:
        return now.date()
    from datetime import timezone
    return now.replace(tzinfo=timezone.utc).astimezone(tz).date()


def run_allowed(sc: dict, day: date) -> tuple:
    """(allowed, reason) for sending opt-outs on this local date."""
    if day.isoformat() in set(sc.get("skip_dates") or []):
        return False, f"{day.isoformat()} is a day off"
    days = sc.get("run_days")
    if days and day.weekday() not in days:
        return False, f"opt-outs don't go out on {DAY_NAMES[day.weekday()]}s"
    return True, ""


def _first(name: str) -> str:
    return (name or "").split(" ")[0] or "Someone"


def upcoming(db, member_ids: Iterable[int], sc: dict, start: Optional[date] = None, days: int = 60,
             now: Optional[datetime] = None) -> list:
    """Events from start for `days` days, oldest first."""
    from ..models.database import RemovalRequest
    from .timeline import build
    start = start or local_today(sc, now)
    end = start + timedelta(days=days)
    ev = []
    if sc.get("enabled"):
        t = sc.get("run_time", "02:00")
        d = start
        while d < end:
            ok, why = run_allowed(sc, d)
            if ok:
                ev.append({"date": d.isoformat(), "kind": "run", "title": "Opt-outs go out", "time": t})
            elif d.isoformat() in set(sc.get("skip_dates") or []):
                ev.append({"date": d.isoformat(), "kind": "skip", "title": "Day off: no opt-outs"})
            d += timedelta(days=1)
    ids = list(member_ids)
    reqs = db.query(RemovalRequest).filter(RemovalRequest.member_id.in_(ids)).all() if ids else []
    for r in reqs:
        site = r.broker.name if r.broker else "a site"
        who = _first(r.member.full_name if r.member else "")
        if r.recheck_after and start <= r.recheck_after.date() < end:
            ev.append({"date": r.recheck_after.date().isoformat(), "kind": "check",
                       "title": f"Check again: {site} ({who})", "request_id": r.id})
        st = getattr(r.status, "value", r.status)
        if st in ("sent", "submitted"):
            cycles = build(db, r, now=now)["cycles"]
            last = cycles[-1] if cycles else {}
            due = last.get("due_by")
            if due and not last.get("replied_at") and not last.get("removed_at"):
                dd = datetime.fromisoformat(due).date()
                if start <= dd < end:
                    ev.append({"date": dd.isoformat(), "kind": "deadline",
                               "title": f"Legal deadline: {site} must answer ({who})", "request_id": r.id})
    order = {"skip": 0, "run": 1, "deadline": 2, "check": 3}
    ev.sort(key=lambda e: (e["date"], order[e["kind"]], e["title"]))
    return ev


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def to_ics(events: list, name: str = "OpenOptOut", now: Optional[datetime] = None) -> str:
    now = now or datetime.utcnow()
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//OpenOptOut//Removal calendar//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-CALNAME:{_esc(name)}"]
    for e in events:
        d = date.fromisoformat(e["date"])
        uid = hashlib.sha256(f"{e['kind']}|{e['date']}|{e['title']}".encode()).hexdigest()[:24]
        lines += ["BEGIN:VEVENT", f"UID:{uid}@openoptout", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}",
                  f"SUMMARY:{_esc(e['title'])}", "TRANSP:TRANSPARENT", f"CATEGORIES:{e['kind'].upper()}",
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    # RFC 5545: CRLF line endings, lines folded at 75 octets.
    out = []
    for ln in lines:
        b = ln.encode("utf-8")
        while len(b) > 75:
            cut = 75
            while (b[cut] & 0xC0) == 0x80:
                cut -= 1
            out.append(b[:cut].decode("utf-8"))
            b = b" " + b[cut:]
        out.append(b.decode("utf-8"))
    return "\r\n".join(out) + "\r\n"


def token_hash(token: str) -> str:
    return hashlib.sha256((token or "").encode()).hexdigest()
