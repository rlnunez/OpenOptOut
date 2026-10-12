"""
Detailed removal report as a PDF.

For the people the viewer may see: the privacy score (start, now, trend),
totals, then one section per person with every site's progress (sent,
replied, removed, found again, next check), sites past their legal deadline,
and what still needs a person. Dates and site names only; no addresses,
phone numbers or emails are printed.
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Iterable, Optional
from xml.sax.saxutils import escape

STATUS_TEXT = {
    "pending": "Waiting to send", "sent": "Sent", "submitted": "Sent", "confirmed": "Removed",
    "rejected": "Refused", "failed": "Didn't work", "needs_manual": "Needs you", "recheck_due": "Check again",
}


def _d(v) -> str:
    from .regional import format_date
    return format_date(v)


def gather(db, member_ids: Iterable[int], now: Optional[datetime] = None) -> dict:
    """Everything the PDF shows, as plain data (also handy for tests)."""
    from ..models.database import FamilyMember, RemovalRequest
    from .timeline import build
    from .compliance import classify
    from . import privacy_score as ps
    now = now or datetime.utcnow()
    ids = list(member_ids)
    score = ps.report(db, ids)
    people = []
    for m in db.query(FamilyMember).filter(FamilyMember.id.in_(ids)).order_by(FamilyMember.id).all() if ids else []:
        rows = []
        for r in db.query(RemovalRequest).filter(RemovalRequest.member_id == m.id).all():
            if r.broker is not None and getattr(r.broker, "is_test", False):
                continue
            t = build(db, r, now=now)
            last = t["cycles"][-1] if t["cycles"] else {}
            rows.append({
                "site": t["broker"], "status": STATUS_TEXT.get(t["status"], t["status"]),
                "state": ps.site_state(r), "rounds": len(t["cycles"]),
                "sent": last.get("sent_at"), "replied": last.get("replied_at"), "removed": last.get("removed_at"),
                "found_again": next((c["found_again_at"] for c in reversed(t["cycles"]) if c.get("found_again_at")), None),
                "next_check": t["next_check"], "deadline": last.get("due_by"),
                "verdict": classify(last, now) if last else "not_sent",
                "needs_you": t["status"] == "needs_manual",
            })
        rows.sort(key=lambda x: ({"exposed": 0, "waiting": 1, "gone": 2}[x["state"]], x["site"].lower()))
        sc = next((p for p in score["people"] if p["member_id"] == m.id), None)
        people.append({"name": m.full_name, "score": sc, "rows": rows})
    return {"generated_at": now, "score": score["family"], "people": people}


def render(data: dict, title: str = "Removal report") -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                    PageBreak, KeepTogether)
    from reportlab.graphics.shapes import Drawing, PolyLine, Line, String

    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=20, spaceAfter=4, alignment=0)
    H2 = ParagraphStyle("h2", parent=ss["Heading2"], spaceBefore=12, spaceAfter=6)
    P = ParagraphStyle("p", parent=ss["Normal"], fontSize=10, leading=14)
    SMALL = ParagraphStyle("s", parent=P, fontSize=8.5, leading=11, textColor=colors.HexColor("#475569"))
    CELL = ParagraphStyle("c", parent=P, fontSize=8.5, leading=10.5)
    INK, MUTED, LINE = colors.HexColor("#0f172a"), colors.HexColor("#64748b"), colors.HexColor("#cbd5e1")
    ACCENT = colors.HexColor("#4f46e5")

    buf = io.BytesIO()

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(0.75 * inch, 0.5 * inch, "OpenOptOut · contains personal information, keep it private")
        canvas.drawRightString(letter[0] - 0.75 * inch, 0.5 * inch, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                            topMargin=0.75 * inch, bottomMargin=0.8 * inch, title=title, author="OpenOptOut")
    story = [Paragraph(escape(title), H1),
             Paragraph(f"Made {_d(data['generated_at'])} · {len(data['people'])} "
                       f"{'person' if len(data['people']) == 1 else 'people'}", SMALL), Spacer(1, 10)]

    f = data["score"]
    if f["now"] is not None:
        line = f"<b>Privacy score: {f['now']} / 100</b>"
        if f["start"] is not None:
            ch = f["now"] - f["start"]
            line += f" (started at {f['start']} on {_d(f['start_day'])}"
            line += f", {'up' if ch > 0 else 'down'} {abs(ch)})" if ch else ")"
        story.append(Paragraph(line, P))
        story.append(Paragraph("100 means none of the sites we know about still show the people in this report. "
                               "Bigger sites count for more.", SMALL))
        hist = [h for h in f["history"] if h["score"] is not None]
        if len(hist) >= 2:
            W, Ht = 6.5 * inch, 0.9 * inch
            dr = Drawing(W, Ht + 14)
            xs = lambda i: 4 + i * (W - 8) / (len(hist) - 1)
            ys = lambda v: 10 + (v / 100) * (Ht - 10)
            dr.add(Line(4, ys(50), W - 4, ys(50), strokeColor=LINE, strokeWidth=0.5, strokeDashArray=[2, 3]))
            pts = []
            for i, h in enumerate(hist):
                pts += [xs(i), ys(h["score"])]
            dr.add(PolyLine(pts, strokeColor=ACCENT, strokeWidth=2))
            dr.add(String(4, 0, _d(hist[0]["day"]), fontSize=7, fillColor=MUTED))
            dr.add(String(W - 4, 0, _d(hist[-1]["day"]), fontSize=7, fillColor=MUTED, textAnchor="end"))
            story += [Spacer(1, 4), dr]
    else:
        story.append(Paragraph("No privacy score yet: nothing has been sent.", P))

    allrows = [r for p in data["people"] for r in p["rows"]]
    tot = {"gone": 0, "waiting": 0, "exposed": 0}
    for r in allrows:
        tot[r["state"]] += 1
    missed = [(p["name"], r) for p in data["people"] for r in p["rows"] if r["verdict"] in ("overdue", "late")]
    again = [(p["name"], r) for p in data["people"] for r in p["rows"] if r["found_again"]]
    need = [(p["name"], r) for p in data["people"] for r in p["rows"] if r["needs_you"]]
    summary = Table([["Removed", "Waiting for a reply", "Still listed", "Missed deadline", "Came back"],
                     [tot["gone"], tot["waiting"], tot["exposed"], len(missed), len(again)]],
                    colWidths=[1.3 * inch] * 5)
    summary.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica", 8), ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
        ("FONT", (0, 1), (-1, 1), "Helvetica-Bold", 16), ("TEXTCOLOR", (0, 1), (-1, 1), INK),
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, LINE), ("TOPPADDING", (0, 1), (-1, 1), 4)]))
    story += [Spacer(1, 10), summary]

    if need:
        story.append(Paragraph("Needs a person", H2))
        story.append(Paragraph("These sites need someone to finish the opt-out (a CAPTCHA, a phone call, a form). "
                               "They're on the Checklist page.", SMALL))
        story.append(Paragraph("; ".join(f"{escape(r['site'])} ({escape(n)})" for n, r in need), P))
    if missed:
        story.append(Paragraph("Missed legal deadlines", H2))
        story.append(Paragraph("Sites that didn't answer within the days the law gives them. The Deadline report "
                               "page has a file to attach to a complaint.", SMALL))
        t = Table([["Site", "Person", "Sent", "Due", "Answered"]] +
                  [[Paragraph(escape(r["site"]), CELL), Paragraph(escape(n), CELL), _d(r["sent"]), _d(r["deadline"]),
                    _d(r["replied"] or r["removed"]) if r["verdict"] == "late" else "No answer"] for n, r in missed],
                  colWidths=[2 * inch, 1.5 * inch, 1 * inch, 1 * inch, 1 * inch], repeatRows=1)
        t.setStyle(_table_style(colors, INK, MUTED, LINE))
        story.append(t)

    for p in data["people"]:
        story.append(PageBreak())
        sc = p["score"]["now"]["score"] if p["score"] else None
        story.append(Paragraph(escape(p["name"]), ParagraphStyle("pn", parent=H2, fontSize=15, spaceBefore=0)))
        if sc is not None:
            start = p["score"]["start"]
            txt = f"Privacy score {sc} / 100"
            if start:
                txt += f" · started at {start['score']} on {_d(start['day'])}"
            story.append(Paragraph(txt, P))
        if not p["rows"]:
            story.append(Paragraph("Nothing sent yet.", P))
            continue
        head = ["Site", "Status", "Sent", "Replied", "Removed", "Came back", "Next check"]
        body = [[Paragraph(escape(r["site"]) + (f" <font size=7 color='#64748b'>(round {r['rounds']})</font>"
                                               if r["rounds"] > 1 else ""), CELL),
                 Paragraph(escape(r["status"]), CELL), _d(r["sent"]), _d(r["replied"]), _d(r["removed"]),
                 _d(r["found_again"]), _d(r["next_check"])] for r in p["rows"]]
        t = Table([head] + body, colWidths=[1.75 * inch, 0.95 * inch] + [0.76 * inch] * 5, repeatRows=1)
        t.setStyle(_table_style(colors, INK, MUTED, LINE))
        story.append(t)

    story += [Spacer(1, 14), Paragraph("Sent = the request went out. Replied = the site wrote back or a confirmation "
                                       "link was clicked. Removed = the site confirmed, or a later check found nothing. "
                                       "Came back = a check found the listing again after it was removed.", SMALL)]
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def _table_style(colors, INK, MUTED, LINE):
    from reportlab.platypus import TableStyle
    return TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8), ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5), ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, LINE), ("LINEBELOW", (0, 1), (-1, -1), 0.25, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ])
