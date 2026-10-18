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


def _parse_dt(val) -> Optional[datetime]:
    if not val:
        return None
    val_str = str(val).strip()
    if val_str.endswith("Z"):
        val_str = val_str[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(val_str)
    except Exception:
        return None


def _to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        from datetime import timezone
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def clean_maintenance_windows(windows) -> list:
    """Clean, validate, and sort scheduled downtime/maintenance windows."""
    out = []
    seen_ids = set()
    for w in windows or []:
        if not isinstance(w, dict):
            continue
        start_dt = _parse_dt(w.get("start"))
        end_dt = _parse_dt(w.get("end"))
        if not start_dt or not end_dt:
            continue
        if _to_utc_naive(end_dt) <= _to_utc_naive(start_dt):
            continue
        wid = str(w.get("id") or "").strip()
        if not wid or wid in seen_ids:
            import secrets, time
            wid = f"mw-{int(time.time())}-{secrets.token_hex(4)}"
        seen_ids.add(wid)
        desc = str(w.get("description") or "Host server updates and backups").strip()[:400]
        out.append({
            "id": wid,
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "description": desc or "Host server updates and backups",
        })
    out.sort(key=lambda x: x["start"])
    return out


def is_in_maintenance_window(sc: dict, now: Optional[datetime] = None) -> tuple:
    """Return (True, active_window_dict) if now falls in a scheduled window, else (False, None)."""
    now = now or datetime.utcnow()
    now_naive = _to_utc_naive(now)
    for w in sc.get("maintenance_windows") or []:
        s_dt = _parse_dt(w.get("start"))
        e_dt = _parse_dt(w.get("end"))
        if s_dt and e_dt:
            if _to_utc_naive(s_dt) <= now_naive < _to_utc_naive(e_dt):
                return True, w
    return False, None


def get_maintenance_notice(sc: dict, now: Optional[datetime] = None) -> Optional[dict]:
    """
    Return downtime notice information for users if a maintenance window is currently
    active or scheduled within maintenance_notice_hours (and notice hours > 0).
    If maintenance_notice_hours <= 0, advance notices are disabled (returns active only).
    """
    now = now or datetime.utcnow()
    now_naive = _to_utc_naive(now)
    try:
        notice_hours = int(sc.get("maintenance_notice_hours", 24))
    except (ValueError, TypeError):
        notice_hours = 24

    # 1. Active window
    in_maint, active_win = is_in_maintenance_window(sc, now=now)
    if in_maint and active_win:
        return {
            "status": "active",
            "window": active_win,
            "message": active_win.get("description") or "Host server updates and backups",
            "start": active_win.get("start"),
            "end": active_win.get("end"),
            "notice_hours": notice_hours,
            "hours_until": 0.0,
        }

    # 2. Advance notice disabled if <= 0
    if notice_hours <= 0:
        return None

    # 3. Upcoming windows starting within notice_hours
    horizon = now_naive + timedelta(hours=notice_hours)
    upcoming_eligible = []
    for w in sc.get("maintenance_windows") or []:
        s_dt = _parse_dt(w.get("start"))
        e_dt = _parse_dt(w.get("end"))
        if s_dt and e_dt:
            s_naive = _to_utc_naive(s_dt)
            e_naive = _to_utc_naive(e_dt)
            if now_naive <= s_naive <= horizon and e_naive > now_naive:
                diff_sec = (s_naive - now_naive).total_seconds()
                upcoming_eligible.append((diff_sec, w))

    if not upcoming_eligible:
        return None

    upcoming_eligible.sort(key=lambda x: x[0])
    diff_sec, next_win = upcoming_eligible[0]
    hours_until = max(0.0, round(diff_sec / 3600.0, 1))

    return {
        "status": "upcoming",
        "window": next_win,
        "message": next_win.get("description") or "Host server updates and backups",
        "start": next_win.get("start"),
        "end": next_win.get("end"),
        "notice_hours": notice_hours,
        "hours_until": hours_until,
    }



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


def run_allowed(sc: dict, day: date, now: Optional[datetime] = None) -> tuple:
    """(allowed, reason) for sending opt-outs on this local date."""
    in_maint, win = is_in_maintenance_window(sc, now)
    if in_maint and win:
        return False, f"Maintenance window active: {win.get('description', 'Downtime')}"
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
    if ids and db is not None:
        from ..models.database import RemovalRequest
        from .timeline import build
        reqs = db.query(RemovalRequest).filter(RemovalRequest.member_id.in_(ids)).all()
    else:
        reqs = []
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
    # Maintenance windows (scheduled downtime)
    for w in sc.get("maintenance_windows") or []:
        s_dt = _parse_dt(w.get("start"))
        e_dt = _parse_dt(w.get("end"))
        if not s_dt or not e_dt:
            continue
        w_start_d = s_dt.date()
        w_end_d = e_dt.date()
        if w_start_d < end and w_end_d >= start:
            cur = max(w_start_d, start)
            last = min(w_end_d, end - timedelta(days=1))
            d_cursor = cur
            while d_cursor <= last:
                ev.append({
                    "id": w.get("id"),
                    "date": d_cursor.isoformat(),
                    "end_date": w_end_d.isoformat(),
                    "kind": "maintenance",
                    "title": f"Maintenance: {w.get('description') or 'Host updates & backups'}",
                    "start_time": s_dt.strftime("%H:%M"),
                    "end_time": e_dt.strftime("%H:%M"),
                    "start_iso": w.get("start"),
                    "end_iso": w.get("end"),
                    "description": w.get("description", "Host server updates and backups"),
                })
                d_cursor += timedelta(days=1)

    order = {"skip": 0, "maintenance": 1, "run": 2, "deadline": 3, "check": 4}
    ev.sort(key=lambda e: (e["date"], order[e["kind"]], e["title"]))
    return ev


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def to_ics(events: list, name: str = "OpenOptOut", now: Optional[datetime] = None) -> str:
    now = now or datetime.utcnow()
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//OpenOptOut//Removal calendar//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-CALNAME:{_esc(name)}"]
    seen_uids = set()
    for e in events:
        uid = hashlib.sha256(f"{e.get('id') or e['kind']}|{e.get('start_iso') or e['date']}|{e['title']}".encode()).hexdigest()[:24]
        if uid in seen_uids:
            continue
        seen_uids.add(uid)
        if e.get("kind") == "maintenance" and e.get("start_iso") and e.get("end_iso"):
            s_dt = _parse_dt(e["start_iso"])
            e_dt = _parse_dt(e["end_iso"])
            if s_dt and e_dt:
                s_stamp = _to_utc_naive(s_dt).strftime("%Y%m%dT%H%M%SZ")
                e_stamp = _to_utc_naive(e_dt).strftime("%Y%m%dT%H%M%SZ")
                lines += ["BEGIN:VEVENT", f"UID:{uid}@openoptout", f"DTSTAMP:{stamp}",
                          f"DTSTART:{s_stamp}", f"DTEND:{e_stamp}",
                          f"SUMMARY:{_esc(e['title'])}",
                          f"DESCRIPTION:{_esc(e.get('description', ''))}",
                          "TRANSP:OPAQUE", "CATEGORIES:MAINTENANCE",
                          "END:VEVENT"]
                continue
        d = date.fromisoformat(e["date"])
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
