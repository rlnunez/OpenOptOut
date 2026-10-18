"""
SSO sign-in policy — ONE set of rules for every external login method
(OIDC: Google/Microsoft/Okta/…, LDAP, SIP2 library cards, SAML).

Before this module, external logins skipped the administrator's registration
rules, Google accepted any Google account, unverified emails could claim an
existing account, and a provider's default role could hand out super admin.
Every external login now passes through evaluate_sso_login().

Rules, in order:
  1. The IdP must supply a usable email.
  2. If the IdP says the email is UNVERIFIED, deny (prevents claiming someone
     else's account by asserting their address).
  3. Google must positively verify the email.
  4. Per-provider allowed_domains: the email's domain must match. For Google the
     `hd` (hosted domain) claim must ALSO match — a personal Google account can
     be registered with any address (e.g. you@yourlibrary.org) and still be
     "verified", so only `hd` proves it's a real Workspace account.
  5. Per-provider required_groups: the user must be in at least one (lets an
     admin say "only members of library-staff may log in"). Applies to existing
     users too, so removing someone from the group revokes SSO access.
  6. Existing users: allowed (their account is linked to this provider).
  7. New users:
     - never the first account (the first admin is created by the setup wizard);
     - Microsoft multi-tenant (common/organizations/consumers) requires
       allowed_domains, or anyone with any Microsoft account could join;
     - registration mode invite/admin_only blocks new SSO users unless the
       provider has auto_provision enabled (on by default for institution
       directories — LDAP, SIP2, SAML — off by default for OIDC);
     - registration mode "domain" applies its domain list;
     - with the residents-only address check on, new accounts start on the
       sign-up page, not a sign-in button (unless auto_provision);
     - the role comes from the provider's default_role, but SUPER ADMIN IS
       NEVER AUTO-GRANTED — it's capped to "parent" and an admin can promote
       the account manually.

Pure logic (no DB, no network) so every rule is unit-tested directly.
"""

from dataclasses import dataclass

# Institution-controlled directories: the admin configured exactly which
# directory users come from, so new users are expected by default.
DIRECTORY_PROVIDERS = {"ldap", "sip2", "saml"}
MS_MULTI_TENANT = ("common", "organizations", "consumers")
SSO_ASSIGNABLE_ROLES = {"parent", "member"}   # never super_admin


@dataclass
class Decision:
    allowed: bool
    reason: str = ""
    role: str = ""            # role for a NEW user
    downgraded: bool = False  # True if a super_admin default_role was capped


def _list(v) -> list:
    if isinstance(v, (list, tuple, set)):
        items = v
    else:
        items = str(v or "").split(",")
    return [str(i).strip().lower() for i in items if str(i).strip()]


def _deny(reason: str) -> Decision:
    return Decision(False, reason)


def _ms_multi_tenant(cfg: dict) -> bool:
    tenant = str(cfg.get("tenant_id", "")).strip().lower()
    disc = str(cfg.get("discovery_url", "")).lower()
    return tenant in MS_MULTI_TENANT or any(f"/{t}/" in disc for t in MS_MULTI_TENANT)


def auto_provision_enabled(provider: str, cfg: dict) -> bool:
    if "auto_provision" in cfg:
        return bool(cfg.get("auto_provision"))
    return provider in DIRECTORY_PROVIDERS


def evaluate_sso_login(result, provider_cfg: dict, registration_cfg: dict,
                       user_exists: bool, user_count: int) -> Decision:
    provider = str(getattr(result, "provider", "") or "")
    cfg = provider_cfg or {}
    reg = registration_cfg or {}

    # 1. usable email
    email = str(getattr(result, "email", "") or "").strip().lower()
    if "@" not in email:
        return _deny("The sign-in provider did not supply a usable email address.")
    domain = email.rsplit("@", 1)[-1]

    # 2. explicitly unverified
    verified = getattr(result, "email_verified", None)
    if verified is False:
        return _deny("Your email address is not verified with the sign-in provider.")

    # 3. Google must positively verify
    if provider == "google" and verified is not True:
        return _deny("Google did not confirm this email address is verified.")

    # 4. allowed domains (+ Google hosted-domain proof)
    allowed = _list(cfg.get("allowed_domains"))
    if allowed:
        if domain not in allowed:
            return _deny(f"Sign-in is restricted to: {', '.join(allowed)}.")
        if provider == "google":
            hd = str(getattr(result, "hd", "") or "").strip().lower()
            if hd not in allowed:
                return _deny("This is not an account in your organization's Google "
                             "Workspace (a personal Google account can't be used).")

    # 5. required groups
    required = _list(cfg.get("required_groups"))
    if required:
        groups = {str(g).strip().lower() for g in (getattr(result, "groups", None) or [])}
        if not groups.intersection(required):
            return _deny("Your account is not in a group permitted to use this system.")

    # 5.5 SIP2 patron eligibility rules
    if provider == "sip2":
        elig_cfg = cfg.get("eligibility_rules")
        raw_profile = getattr(result, "raw_profile", None)
        if elig_cfg and raw_profile is not None:
            from .sip2_rules import evaluate_sip2_eligibility
            eligible, reason = evaluate_sip2_eligibility(
                elig_cfg, raw_profile, date_format=cfg.get("date_format", "auto")
            )
            if not eligible:
                return _deny(f"Your library account is not eligible to sign in: {reason}")

    # 5.6 Microsoft multi-tenant without allowed domains cannot sign in to
    # existing accounts either — otherwise anyone could put an existing user's
    # (or admin's) email address on a Microsoft account they control and take
    # over that account.
    if provider == "microsoft" and _ms_multi_tenant(cfg) and not allowed:
        return _deny("This Microsoft sign-in accepts any organization's accounts; an "
                     "administrator must set allowed domains before anyone can sign in.")

    # 6. existing user — linked login
    if user_exists:
        if verified is not True and not allowed and not auto_provision_enabled(provider, cfg):
            return _deny("The sign-in provider did not confirm this email address is verified. "
                         "Cannot link to an existing account without email verification.")
        return Decision(True, "existing account")

    # 7. new user
    if user_count == 0:
        return _deny("Setup isn't finished. Create the administrator account first.")

    mode = str(reg.get("mode", "open")).lower()
    closed = mode in ("invite", "admin_only") or bool(reg.get("require_invite"))
    if closed and not auto_provision_enabled(provider, cfg):
        return _deny("New accounts aren't open for self-registration. Ask an "
                     "administrator to invite you or enable sign-up for this provider.")

    # Residents-only sign-up: the address is checked on the sign-up page, so a
    # new account can't start from a sign-in button. Linking afterwards works
    # (rule 6). Directories the admin set to create accounts are exempt.
    if reg.get("address_check") and not auto_provision_enabled(provider, cfg):
        return _deny("To join, create an account on the sign-up page first. It asks for your "
                     "home address. After that you can use this sign-in button too.")

    if mode == "domain":
        gdomains = _list(reg.get("allowed_domains"))
        if gdomains and domain not in gdomains:
            return _deny(f"Registration is restricted to: {', '.join(gdomains)}.")

    wanted = str(cfg.get("default_role", "parent") or "parent").strip().lower()
    if wanted in SSO_ASSIGNABLE_ROLES:
        return Decision(True, "new account", role=wanted)
    return Decision(True, "new account", role="parent",
                    downgraded=(wanted in ("super_admin", "manager")))
