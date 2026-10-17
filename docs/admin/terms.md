# Terms and limits

OpenOptOut tells people plainly what it can and can't do before they rely on it. The AGPL's "no warranty" sections (15 and 16) cover the software, but only the person who installs it ever reads the license. These screens reach everyone else.

**Everything here is a draft that no lawyer has reviewed yet**, like the opt-out letters. Have your own terms checked before you rely on them. This isn't legal advice.

## What people see

| Who | When | What | Kept as |
|---|---|---|---|
| Admins (super admin) | First sign-in, before setup | **"Before you start: what OpenOptOut can and can't do."** It covers: it can't remove everything; brokers decide; mistakes can happen despite the safeguards; no warranty; the server is yours, and so is the duty to set terms for the people you serve; not legal advice. The admin ticks a box to accept. | `limits`, `LIMITS_VERSION` |
| Everyone else | First sign-in | **"How OpenOptOut works for you."** It covers: what's sent to brokers and what never is; that removal is a best effort; where details are stored; and how to stop. | `notice`, `NOTICE_VERSION` |
| Everyone | First sign-in after the operator's terms are turned on, and again after each change | **The operator's own terms** (Admin → Terms) | `operator_terms`, its version |
| A parent adding someone without a sign-in | Each time | *"I'm allowed to ask brokers to remove this person's details: they've agreed, or I'm their parent or legal guardian."* Adding someone fails without it. | `acting_for`, per person added |

The wording of the first two is in `frontend/src/components/TermsGate.jsx`, translated in every language pack. **Changing it means raising `LIMITS_VERSION` or `NOTICE_VERSION` in `backend/core/terms.py`**, so everyone is asked again.

"Who runs this" (for example *The Rivera family* or *Riverside Public Library*) is asked in the last setup step and can be changed on the Terms page. People see it in the notice: *"The Rivera family uses OpenOptOut to…"*. Left blank, the wording stays general.

## The operator's terms (Admin → Terms)

If you run OpenOptOut for other people, you're the one offering it to them, so the terms are yours to write. **Start from the draft** fills in `backend/core/legal_templates/terms_template.md` with your name and contact details. It has notes in square brackets for what only you can say:

- who on your staff can see people's details;
- how long backups keep them;
- the liability limits that apply where you are.

The terms can't be turned on until every note is filled in.

- **Version numbers** go up when what people see changes: the text, the name or the contact. Changes made while the terms were off count too. Saving without changes, or turning the terms off and on again, keeps the same version, so nobody is asked twice.
- **Accepting.** A screen can only accept the version that's current, so someone reading old terms when you save new ones is asked again.
- **The sign-in page's Terms link** opens `/terms`. It shows your terms when they're on. When they're off, it shows the link set under Branding (if any) and the general notice.
- **The draft is in English.** Translate your terms into the languages your community reads; they're shown exactly as you wrote them.

## What's stored

Each acceptance is a `terms_acceptances` row: who accepted (user id), what kind, which version, and when. It never holds a name or a detail. When a person is removed, their rows go too (`core/people.delete_person`).

## Limits

- **The screens are a notice, not a lock.** They appear in the app. They don't block the API or scheduled opt-outs, so an upgrade never stops removals that are already running. Admins of existing installs are asked at their next sign-in.
- **Not legal review.** None of this has been reviewed by a lawyer.
