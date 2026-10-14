"""
Deleting a person completely.

A family member's details reach many tables (identities, opt-out requests and
everything hanging off them, search results, inboxes, schedules). The models
don't cascade all of these, so deleting just the account fails or leaves
personal details behind. delete_person removes every row about them, children
first, then the profile, then the account. Rows that only *mention* the
account (who created something, who resolved a CAPTCHA) are kept, unlinked.
"""
from __future__ import annotations


def delete_person(db, user) -> None:
    from ..models import database as m
    from .mailboxes import purge_for_user
    member = db.query(m.FamilyMember).filter(m.FamilyMember.user_id == user.id).first()
    purge_for_user(db, user.id)

    def gone(model, *conds):
        db.query(model).filter(*conds).delete(synchronize_session=False)

    if member is not None:
        req_ids = [r.id for r in db.query(m.RemovalRequest.id).filter(m.RemovalRequest.member_id == member.id)]
        if req_ids:
            for model in (m.ConfirmationLink, m.RequestEvent, m.RequestVariant, m.VerificationCheck,
                          m.CaptchaChallenge, m.EmailLog, m.AutomationLog, m.WebSearchHit):
                gone(model, model.request_id.in_(req_ids))
            if hasattr(m, "NoticeSent"):
                gone(m.NoticeSent, m.NoticeSent.request_id.in_(req_ids))
            gone(m.RemovalRequest, m.RemovalRequest.id.in_(req_ids))
        for model in (m.Identity, m.ContactAddress, m.DiscoveryResult, m.MemberScheduleConfig, m.PrivacyScoreSnapshot,
                      m.WebSearchHit, m.CaptchaChallenge, m.AutomationLog):
            gone(model, model.member_id == member.id)
        db.query(m.UsageEvent).filter(m.UsageEvent.member_id == member.id).update(
            {m.UsageEvent.member_id: None}, synchronize_session=False)
        gone(m.FamilyMember, m.FamilyMember.id == member.id)

    gone(m.ProfileAccess, (m.ProfileAccess.managed_id == user.id) | (m.ProfileAccess.manager_id == user.id))
    gone(m.ManagerScope, m.ManagerScope.user_id == user.id)
    gone(m.InviteCode, m.InviteCode.created_by == user.id)
    if hasattr(m, "NoticeSent"):
        gone(m.NoticeSent, m.NoticeSent.user_id == user.id)
    gone(m.TermsAcceptance, (m.TermsAcceptance.user_id == user.id) | (m.TermsAcceptance.subject_user_id == user.id))
    for model, col in ((m.User, "branch_override_by"), (m.User, "created_by_id"), (m.InstalledPlugin, "enabled_by"),
                       (m.PluginAuditLog, "actor_id"), (m.ProfileAccess, "granted_by"),
                       (m.MemberScheduleConfig, "updated_by_id"), (m.CaptchaChallenge, "resolved_by"),
                       (m.UsageEvent, "user_id")):
        c = getattr(model, col)
        db.query(model).filter(c == user.id).update({c: None}, synchronize_session=False)
    db.expire_all()
    gone(m.User, m.User.id == user.id)
