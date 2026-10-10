"""
Database models for OpenOptOut.
Uses SQLite via SQLAlchemy — swap DATABASE_URL in .env for Postgres.

Role model:
  super_admin — full access to everything, all families
  parent      — has login, manages their own profile + explicitly granted profiles
  member      — optional login; managed by parent(s) via profile_access grants
"""

from sqlalchemy import (
    create_engine, Column, Integer, String, Text,
    DateTime, Boolean, ForeignKey, Enum as SAEnum, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import enum, os
from ..core.encryption import create_encrypted_engine, EncryptedText

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./privacy_pipeline.db")

engine = create_encrypted_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Enums ─────────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    super_admin = "super_admin"
    manager     = "manager"      # a parent plus permissions a super admin grants (core/access.py)
    parent      = "parent"
    member      = "member"

class BrokerStatus(str, enum.Enum):
    compliant    = "compliant"
    resistant    = "resistant"
    inconsistent = "inconsistent"
    undetermined = "undetermined"

class RequestStatus(str, enum.Enum):
    pending      = "pending"
    sent         = "sent"
    confirmed    = "confirmed"
    rejected     = "rejected"
    recheck_due  = "recheck_due"
    failed       = "failed"
    submitted    = "submitted"
    needs_manual = "needs_manual"

class OptOutMethod(str, enum.Enum):
    form   = "form"
    email  = "email"
    manual = "manual"
    phone  = "phone"

class Difficulty(str, enum.Enum):
    easy   = "easy"
    medium = "medium"
    hard   = "hard"


class EmailHonorStatus(str, enum.Enum):
    """Whether a parent company is known to honor email opt-out requests.
    Effectiveness tracking so operators learn which parents actually respond."""
    unknown    = "unknown"      # not yet attempted / no data
    honors     = "honors"       # confirmed removals came back
    partial    = "partial"      # some confirmed, some ignored
    ignores    = "ignores"      # sent but never confirmed
    bounces    = "bounces"      # the opt-out address itself fails


# ── Consortium hierarchy models ───────────────────────────────────────────────

class LibrarySystem(Base):
    """
    Independent library system within a consortium deployment (e.g. "Seattle Public Library").
    Can have one or many branches, and optional per-system custom branding when allowed by super admin.
    """
    __tablename__ = "library_systems"

    id                    = Column(Integer, primary_key=True, index=True)
    name                  = Column(String(100), nullable=False)
    code                  = Column(String(30), unique=True, index=True, nullable=False)
    allow_custom_branding = Column(Boolean, default=False, nullable=False)
    branding_config       = Column(Text, nullable=True)   # JSON string for custom branding overrides
    created_at            = Column(DateTime, default=datetime.utcnow)

    branches         = relationship("Branch", back_populates="system", cascade="all, delete-orphan")
    sip2_connections = relationship("SIP2Connection", back_populates="system")
    manager_scopes   = relationship("ManagerScope", back_populates="system")


class Branch(Base):
    """
    Physical branch location under a library system (e.g. "Central Library", "Ballard Branch").
    Maps ILS location codes parsed from SIP2 (e.g. field AQ) to this branch.
    """
    __tablename__ = "branches"

    id                  = Column(Integer, primary_key=True, index=True)
    system_id           = Column(Integer, ForeignKey("library_systems.id"), nullable=False, index=True)
    name                = Column(String(100), nullable=False)
    code                = Column(String(30), nullable=False, index=True)
    ils_location_codes  = Column(Text, nullable=True)   # comma-separated or JSON list of ILS codes
    created_at          = Column(DateTime, default=datetime.utcnow)

    system         = relationship("LibrarySystem", back_populates="branches")
    users          = relationship("User", back_populates="branch", foreign_keys="User.branch_id")
    manager_scopes = relationship("ManagerScope", back_populates="branch")


class SIP2Connection(Base):
    """
    Configured SIP2 / SIP2-over-TLS connection to an ILS.
    A consortium may have one shared ILS connection or separate connections per library system.
    Matches patron barcodes by prefix (or priority order) and extracts branch codes from the response.
    """
    __tablename__ = "sip2_connections"

    id                = Column(Integer, primary_key=True, index=True)
    system_id         = Column(Integer, ForeignKey("library_systems.id"), nullable=True, index=True)
    name              = Column(String(100), nullable=False)
    host              = Column(String(255), nullable=False)
    port              = Column(Integer, default=6001, nullable=False)
    use_tls           = Column(Boolean, default=False, nullable=False)
    ca_cert_pem       = Column(Text, nullable=True)
    ca_cert_path      = Column(String(255), nullable=True)
    institution_id    = Column(String(100), default="", nullable=False)
    ils_login         = Column(String(100), default="", nullable=False)
    ils_password_enc  = Column(Text, default="", nullable=False)
    barcode_prefix    = Column(String(50), nullable=True, index=True)
    branch_field_code = Column(String(10), default="AQ", nullable=False)  # configurable ILS location field (AQ, AF, etc.)
    email_domain      = Column(String(100), default="library.local", nullable=False)
    default_role      = Column(String(20), default="parent", nullable=False)
    timeout_seconds   = Column(Integer, default=10, nullable=False)
    enabled           = Column(Boolean, default=True, nullable=False)
    priority          = Column(Integer, default=10, nullable=False)
    eligibility_rules = Column(Text, default="", nullable=True)  # JSON-encoded rule tree
    date_format       = Column(String(30), default="auto", nullable=True)  # 'auto', 'MM/DD/YYYY', 'DD/MM/YYYY', 'YYYYMMDD', 'YYYY-MM-DD'
    map_patron_fields = Column(Boolean, default=False, nullable=False)
    field_mappings    = Column(Text, default="", nullable=True)  # JSON mapping dict (e.g. {"name": "AE", "email": "BE", "phone": "BF", "address": "BD"})
    forced_fields     = Column(Text, default='["library"]', nullable=False)  # JSON list of fields to force import (e.g. ["library"])
    patron_choice     = Column(Boolean, default=True, nullable=False)  # Require patron confirmation to import non-forced fields
    populate_vault    = Column(Boolean, default=False, nullable=False)
    created_at        = Column(DateTime, default=datetime.utcnow)

    system = relationship("LibrarySystem", back_populates="sip2_connections")


class ManagerScope(Base):
    """
    Restricts a manager's permissions to specific library systems or branches.
    scope_type can be:
      - 'consortium': full consortium-wide access
      - 'system': all branches in system_id
      - 'branch': specific branch_id
    """
    __tablename__ = "manager_scopes"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    scope_type = Column(String(20), nullable=False)   # 'consortium' | 'system' | 'branch'
    system_id  = Column(Integer, ForeignKey("library_systems.id"), nullable=True)
    branch_id  = Column(Integer, ForeignKey("branches.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user   = relationship("User", back_populates="manager_scopes")
    system = relationship("LibrarySystem", back_populates="manager_scopes")
    branch = relationship("Branch", back_populates="manager_scopes")


# ── Core user model ───────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id               = Column(Integer, primary_key=True, index=True)
    email            = Column(String, unique=True, index=True, nullable=False)
    hashed_password  = Column(String, nullable=True)   # null = member with no login
    auth_source      = Column(String, nullable=True)   # external provider, e.g. "saml", "oidc:google"
    full_name        = Column(String, nullable=False)
    role             = Column(SAEnum(UserRole), default=UserRole.member, nullable=False)
    unified_view     = Column(Boolean, default=True)   # parent pref: see all managed profiles at once
    # Superseded by the manager role's "plugins.upload" permission; kept only so
    # grants made before the role existed can be migrated (core/migrations.py).
    can_upload_plugins = Column(Boolean, default=False, nullable=False)
    # Manager permissions that differ from the manager defaults (JSON lists of
    # keys from core/access.py). Only meaningful for role == manager.
    permissions_granted = Column(Text, nullable=True)
    permissions_revoked = Column(Text, nullable=True)

    # Multi-tier library separation: consortium -> systems -> branches
    branch_id          = Column(Integer, ForeignKey("branches.id"), nullable=True)
    branch_source      = Column(String(20), default="sip2")   # 'sip2' | 'staff_override'
    branch_override_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    branch_override_at = Column(DateTime, nullable=True)

    # User interface localization & onboarding state (Roadmap Item 17)
    preferred_language     = Column(String(10), default="en", nullable=False)
    tutorial_completed     = Column(Boolean, default=False, nullable=False)
    pending_ils_import     = Column(Text, nullable=True)  # Staged ILS demographic fields waiting for patron confirmation
    accessibility_settings = Column(Text, nullable=True)  # JSON dict: {"high_contrast": bool, "large_text": bool, "reduced_motion": bool}

    # Multi-Factor Authentication (TOTP + FIDO2/WebAuthn/YubiKey)
    totp_secret_enc      = Column(Text, nullable=True)
    totp_enabled         = Column(Boolean, default=False, nullable=False)
    backup_codes         = Column(Text, nullable=True)       # JSON list of SHA-256 hashed recovery codes
    webauthn_credentials = Column(Text, nullable=True)       # JSON list of registered security keys/biometrics
    mfa_options_override = Column(Text, nullable=True)       # JSON dict: {"totp": bool, "webauthn": bool, "backup_codes": bool}


    created_at       = Column(DateTime, default=datetime.utcnow)
    created_by_id    = Column(Integer, ForeignKey("users.id"), nullable=True)  # who created this account

    # relationships
    created_by       = relationship("User", remote_side="User.id", foreign_keys=[created_by_id])
    family_member    = relationship("FamilyMember", back_populates="user", uselist=False)
    branch           = relationship("Branch", back_populates="users", foreign_keys=[branch_id])
    manager_scopes   = relationship("ManagerScope", back_populates="user", foreign_keys="ManagerScope.user_id", cascade="all, delete-orphan")

    # access grants where this user IS the manager
    managing         = relationship("ProfileAccess", foreign_keys="ProfileAccess.manager_id", back_populates="manager")
    # access grants where this user IS being managed
    managed_by       = relationship("ProfileAccess", foreign_keys="ProfileAccess.managed_id", back_populates="managed")

    @property
    def is_super_admin(self):
        return self.role == UserRole.super_admin

    @property
    def is_manager(self):
        return self.role == UserRole.manager

    @property
    def is_parent(self):
        # Managers keep everything a parent has; their extra permissions are
        # checked separately (core/access.py).
        return self.role in (UserRole.super_admin, UserRole.manager, UserRole.parent)

    @property
    def can_login(self):
        # A user can log in with a password (local) OR through a configured
        # external provider (auth_source set: "ldap", "sip2", "oidc:google",
        # "saml", ...). A managed family profile with neither cannot log in.
        return self.hashed_password is not None or bool(self.auth_source)


class ProfileAccess(Base):
    """
    Explicit grant: manager_id can view/edit the FamilyMember profile
    belonging to managed_id.

    Super_admin grants these. Examples:
      - Maria (parent) manages her own kids and Carlos
      - Carlos (parent) manages his own kids and Maria
    Both need separate rows.
    """
    __tablename__ = "profile_access"
    __table_args__ = (UniqueConstraint("manager_id", "managed_id"),)

    id                    = Column(Integer, primary_key=True, index=True)
    manager_id            = Column(Integer, ForeignKey("users.id"), nullable=False)
    managed_id            = Column(Integer, ForeignKey("users.id"), nullable=False)
    can_view              = Column(Boolean, default=True)
    can_edit              = Column(Boolean, default=True)
    granted_by            = Column(Integer, ForeignKey("users.id"), nullable=True)
    granted_at            = Column(DateTime, default=datetime.utcnow)
    # Per-grant child limit override (None = use system default)
    max_children_override = Column(Integer, nullable=True)

    manager = relationship("User", foreign_keys=[manager_id], back_populates="managing")
    managed = relationship("User", foreign_keys=[managed_id], back_populates="managed_by")


# ── Family / PII models ───────────────────────────────────────────────────────

class FamilyMember(Base):
    """
    One row per person whose data we're removing.
    Linked 1-to-1 with a User (which may or may not have login credentials).
    """
    __tablename__ = "family_members"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    full_name   = Column(String, nullable=False)
    formal_name = Column(EncryptedText, nullable=True)  # legal name — encrypted at rest
    age         = Column(Integer)
    created_at  = Column(DateTime, default=datetime.utcnow)

    user       = relationship("User", back_populates="family_member")
    identities = relationship("Identity", back_populates="member", cascade="all, delete-orphan")
    requests   = relationship("RemovalRequest", back_populates="member")


class Identity(Base):
    """PII variants for a family member: name spellings, emails, phones, addresses."""
    __tablename__ = "identities"

    id          = Column(Integer, primary_key=True, index=True)
    member_id   = Column(Integer, ForeignKey("family_members.id"), nullable=False)
    kind        = Column(String, nullable=False)   # 'name' | 'email' | 'phone' | 'address'
    value       = Column(EncryptedText, nullable=False)  # PII — encrypted at rest
    is_primary  = Column(Boolean, default=False)
    # Address-specific property flags (null/False for non-address kinds)
    is_deed     = Column(Boolean, default=False, nullable=True)      # name on deed at this address
    is_mortgage = Column(Boolean, default=False, nullable=True)      # had a mortgage at this address

    member = relationship("FamilyMember", back_populates="identities")


# ── Broker / request models ───────────────────────────────────────────────────

class ParentCompany(Base):
    """
    A parent/operator company that runs many themed front-sites (e.g. "Arrest
    Records", "Phone Lookup in <State>") sharing one data pool and usually one
    opt-out inbox. Grouping brokers under a parent lets a single email opt-out —
    which enumerates all the child sites — clear a whole family of listings at
    once, instead of fighting each front-site separately.

    Also carries effectiveness tracking (does this parent actually honor email
    opt-outs?) so operators learn which parents are worth emailing.
    """
    __tablename__ = "parent_companies"

    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String, unique=True, nullable=False, index=True)
    # Opt-out inbox(es). Primary is used as the To: address; extras (comma-sep)
    # can be CC'd for parents that list multiple privacy contacts.
    optout_email  = Column(String, nullable=True)
    cc_emails     = Column(String, nullable=True)   # comma-separated, optional
    # Language/locale the opt-out email must be written in for this parent.
    locale        = Column(String, default="en")
    website       = Column(String, nullable=True)
    notes         = Column(Text, nullable=True)
    date_added    = Column(DateTime, default=datetime.utcnow)
    is_test       = Column(Boolean, default=False, index=True)   # test-broker parent

    # ── Effectiveness tracking ──
    honor_status      = Column(SAEnum(EmailHonorStatus), default=EmailHonorStatus.unknown, index=True)
    emails_sent       = Column(Integer, default=0)
    emails_confirmed  = Column(Integer, default=0)   # removals we later verified
    emails_failed     = Column(Integer, default=0)   # bounced / rejected
    last_sent_at      = Column(DateTime, nullable=True)
    last_confirmed_at = Column(DateTime, nullable=True)

    children = relationship("Broker", back_populates="parent")


class Broker(Base):
    __tablename__ = "brokers"

    id                 = Column(Integer, primary_key=True, index=True)
    name               = Column(String, unique=True, nullable=False, index=True)
    opt_out_url        = Column(String)
    method             = Column(SAEnum(OptOutMethod), default=OptOutMethod.form)
    difficulty         = Column(SAEnum(Difficulty), default=Difficulty.medium)
    status             = Column(SAEnum(BrokerStatus), default=BrokerStatus.compliant)
    notes              = Column(Text)
    date_added         = Column(DateTime, default=datetime.utcnow)
    is_property_broker = Column(Boolean, default=False)   # uses formal name + deed/mortgage addresses
    # Dispatch priority (1=lowest .. 5=highest). Decides which brokers go first
    # within a member's daily throttle budget. A single source of truth: it holds
    # whatever value was last written — by the auto-derived default, a bulk rule,
    # or a manual admin edit. priority_source records which, for UI clarity and so
    # the rule-overwrite warning can say how many manual values it will replace.
    priority           = Column(Integer, default=3, index=True)   # 1..5
    priority_source    = Column(String, default="default")        # default | rule | manual
    # Health / enablement: a broker can be turned off manually by an admin or
    # automatically by the health monitor after repeated failures, so one broken
    # broker never keeps crashing runs or wasting resources. enabled brokers are
    # the only ones the batch runner will attempt.
    enabled            = Column(Boolean, default=True, index=True)
    # Test broker: created by the "test broker" admin tool to validate email
    # delivery against an operator-chosen address. Excluded from discovery and
    # scheduled runs (also kept disabled) — only fires via the explicit test send.
    is_test            = Column(Boolean, default=False, index=True)

    # Parent company this broker belongs to (if grouped). When set, an email
    # opt-out is addressed to the parent and enumerates all sibling child sites.
    parent_company_id = Column(Integer, ForeignKey("parent_companies.id"), nullable=True, index=True)

    # Optional preferred CAPTCHA solver plugin ID (e.g. "recaptcha-v2-solver").
    # When set, the opt-out engine invokes this solver first for challenges on this broker.
    captcha_plugin_id = Column(String(100), nullable=True)

    # Optional installed broker add-on plugin ID providing declarative spec / automation (Roadmap Item 1)
    plugin_id         = Column(String(100), nullable=True, index=True)

    requests = relationship("RemovalRequest", back_populates="broker")
    health   = relationship("BrokerHealth", back_populates="broker", uselist=False)
    parent   = relationship("ParentCompany", back_populates="children")


class BrokerHealth(Base):
    """
    Rolling health record for one broker's opt-out add-on. Updated after every
    attempt so the system can detect a broker that has started failing (its site
    changed, a form moved, a CAPTCHA wall appeared) and auto-disable it before it
    wastes more runs. Kept separate from Broker so health bookkeeping never
    muddies the broker's own definition.
    """
    __tablename__ = "broker_health"

    id                   = Column(Integer, primary_key=True, index=True)
    broker_id            = Column(Integer, ForeignKey("brokers.id"), unique=True, nullable=False, index=True)

    consecutive_failures = Column(Integer, default=0)   # reset to 0 on any success
    total_attempts       = Column(Integer, default=0)
    total_successes      = Column(Integer, default=0)
    total_failures       = Column(Integer, default=0)

    last_success_at      = Column(DateTime, nullable=True)
    last_failure_at      = Column(DateTime, nullable=True)
    last_failure_reason  = Column(String, nullable=True)   # classified: timeout|form_not_found|captcha|error
    last_failure_detail  = Column(Text, nullable=True)     # human-readable last error

    # Auto-disable bookkeeping. auto_disabled is True when the monitor turned the
    # broker off; needs_review flags it for the admin even if re-enabled.
    auto_disabled        = Column(Boolean, default=False)
    auto_disabled_at     = Column(DateTime, nullable=True)
    auto_disabled_reason = Column(String, nullable=True)
    needs_review         = Column(Boolean, default=False)

    updated_at           = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    broker = relationship("Broker", back_populates="health")


class RemovalRequest(Base):
    """
    One opt-out attempt per (family_member × broker).
    request_key is a UUID embedded in outgoing email subjects so inbound
    confirmations can be matched back to this row automatically.
    """
    __tablename__ = "removal_requests"

    id            = Column(Integer, primary_key=True, index=True)
    member_id     = Column(Integer, ForeignKey("family_members.id"), nullable=False)
    broker_id     = Column(Integer, ForeignKey("brokers.id"), nullable=False)
    request_key   = Column(String, index=True)
    status        = Column(SAEnum(RequestStatus), default=RequestStatus.pending)
    method_used   = Column(SAEnum(OptOutMethod))
    sent_at       = Column(DateTime)
    confirmed_at  = Column(DateTime)
    recheck_after = Column(DateTime)
    listing_url   = Column(String)
    notes         = Column(Text)
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    member = relationship("FamilyMember", back_populates="requests")
    broker = relationship("Broker", back_populates="requests")
    emails = relationship("EmailLog", back_populates="request")
    captcha_challenges = relationship("CaptchaChallenge", back_populates="request", cascade="all, delete-orphan")


class EmailLog(Base):
    __tablename__ = "email_logs"

    id           = Column(Integer, primary_key=True, index=True)
    # Nullable: parent-company opt-outs cover many brokers at once and are not
    # tied to a single removal request (matched_key="parent:<id>" instead).
    request_id   = Column(Integer, ForeignKey("removal_requests.id"), nullable=True)
    direction    = Column(String)    # 'sent' | 'received'
    subject      = Column(String)
    body_snippet = Column(Text)
    matched_key  = Column(String)
    received_at  = Column(DateTime, default=datetime.utcnow)

    request = relationship("RemovalRequest", back_populates="emails")


class CaptchaChallenge(Base):
    """
    CAPTCHA challenge queue for human-in-the-loop fallback (Item 4).
    When an automated run encounters a challenge that cannot be solved
    automatically by a solver plugin (or when a solver defers), execution
    pauses and records the challenge here for operator review and manual resolution.
    """
    __tablename__ = "captcha_challenges"

    id             = Column(Integer, primary_key=True, index=True)
    request_id     = Column(Integer, ForeignKey("removal_requests.id"), nullable=False, index=True)
    broker_id      = Column(Integer, ForeignKey("brokers.id"), nullable=False, index=True)
    member_id      = Column(Integer, ForeignKey("family_members.id"), nullable=False, index=True)
    challenge_type = Column(String(50), default="other")     # recaptcha_v2 | recaptcha_v3 | hcaptcha | turnstile | image | other
    site_key       = Column(String(255), nullable=True)
    page_url       = Column(String(1000), nullable=True)
    screenshot     = Column(String(500), nullable=True)       # path to screenshot on disk
    status         = Column(String(30), default="pending", index=True)   # pending | resolved | dismissed
    token          = Column(Text, nullable=True)             # solution token if injected or manually provided
    notes          = Column(Text, nullable=True)
    resolved_by    = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at    = Column(DateTime, nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    request  = relationship("RemovalRequest", back_populates="captcha_challenges")
    broker   = relationship("Broker")
    member   = relationship("FamilyMember")
    resolver = relationship("User")


def init_db():
    Base.metadata.create_all(bind=engine)


class MemberScheduleConfig(Base):
    """
    Per-member opt-out rate limit and scheduler preferences.
    Parents (or super_admin) can set these. If not set, system defaults apply.
    """
    __tablename__ = "member_schedule_configs"

    id                   = Column(Integer, primary_key=True, index=True)
    member_id            = Column(Integer, ForeignKey("family_members.id"), nullable=False, unique=True)
    max_optouts_per_day  = Column(Integer, nullable=True)   # None = use system default
    enabled              = Column(Boolean, default=True)    # pause opt-outs for this member
    from_display_name    = Column(String, nullable=True)    # e.g. "Sofia Nunez via OpenOptOut"
    notes                = Column(Text, nullable=True)
    updated_at           = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by_id        = Column(Integer, ForeignKey("users.id"), nullable=True)

    member     = relationship("FamilyMember", backref="schedule_config", uselist=False)
    updated_by = relationship("User", foreign_keys=[updated_by_id])


class SchedulerRun(Base):
    """Audit log of every scheduler execution."""
    __tablename__ = "scheduler_runs"

    id              = Column(Integer, primary_key=True, index=True)
    run_type        = Column(String, nullable=False)  # 'optout' | 'email_poll' | 'recheck'
    started_at      = Column(DateTime, default=datetime.utcnow)
    finished_at     = Column(DateTime, nullable=True)
    optouts_sent    = Column(Integer, default=0)
    emails_matched  = Column(Integer, default=0)
    rechecks_queued = Column(Integer, default=0)
    errors          = Column(Text, nullable=True)    # JSON list of error strings
    status          = Column(String, default="running")  # 'running' | 'done' | 'error'


# ── Broker automation models ──────────────────────────────────────────────────

class BrokerScript(Base):
    """
    Per-broker Playwright automation script.
    Stores CSS selectors and interaction steps for form-based opt-outs.
    Can be updated via the admin UI without code changes.
    """
    __tablename__ = "broker_scripts"

    id          = Column(Integer, primary_key=True, index=True)
    broker_id   = Column(Integer, ForeignKey("brokers.id"), nullable=False, unique=True)
    # Form field selectors
    search_url          = Column(String)     # URL to navigate to first (if different from opt_out_url)
    name_selector       = Column(String)     # CSS selector for name input
    email_selector      = Column(String)     # CSS selector for email input
    address_selector    = Column(String)     # CSS selector for address input
    city_selector       = Column(String)
    state_selector      = Column(String)
    zip_selector        = Column(String)
    submit_selector     = Column(String)     # CSS selector for submit button
    # Post-submit
    success_selector    = Column(String)     # selector that appears on success
    success_text        = Column(String)     # text to look for after submit
    requires_captcha    = Column(Boolean, default=False)
    requires_email_confirm = Column(Boolean, default=True)
    # Extra steps as JSON: [{"action": "click", "selector": "..."}, ...]
    extra_steps         = Column(Text)
    # Email template override (for email-method brokers)
    email_subject_tpl   = Column(String)     # supports {name}, {request_key}
    email_body_tpl      = Column(Text)
    # Meta
    last_verified       = Column(DateTime)
    verified_working    = Column(Boolean, default=None)  # None=untested
    notes               = Column(Text)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    broker = relationship("Broker", backref="script", uselist=False)


class DiscoveryResult(Base):
    """
    One row per (member × broker) discovery scan result.
    Records whether a listing was found and the URL.
    """
    __tablename__ = "discovery_results"

    id           = Column(Integer, primary_key=True, index=True)
    member_id    = Column(Integer, ForeignKey("family_members.id"), nullable=False)
    broker_id    = Column(Integer, ForeignKey("brokers.id"), nullable=False)
    found        = Column(Boolean, default=False)
    listing_url  = Column(String)
    source       = Column(String)    # 'google' | 'direct' | 'manual'
    snippet      = Column(Text)      # search result snippet for context
    scanned_at   = Column(DateTime, default=datetime.utcnow)
    scan_error   = Column(String)

    member = relationship("FamilyMember")
    broker = relationship("Broker")


class AutomationLog(Base):
    """
    Detailed log of every automation action — form fills, email sends, errors.
    Linked to a RemovalRequest.
    """
    __tablename__ = "automation_logs"

    id          = Column(Integer, primary_key=True, index=True)
    request_id  = Column(Integer, ForeignKey("removal_requests.id"), nullable=True)
    member_id   = Column(Integer, ForeignKey("family_members.id"), nullable=True)
    broker_id   = Column(Integer, ForeignKey("brokers.id"), nullable=True)
    action      = Column(String)     # 'discovery' | 'form_fill' | 'email_send' | 'captcha_blocked' | 'error'
    status      = Column(String)     # 'success' | 'failure' | 'skipped' | 'captcha'
    detail      = Column(Text)       # human-readable description
    screenshot  = Column(String)     # path to screenshot file (on failure)
    duration_ms = Column(Integer)    # how long the action took
    created_at  = Column(DateTime, default=datetime.utcnow)

    request = relationship("RemovalRequest")
    member  = relationship("FamilyMember")
    broker  = relationship("Broker")


# ── Institutional / white-label models ────────────────────────────────────────

class InviteCode(Base):
    """One-time or limited-use registration invite codes."""
    __tablename__ = "invite_codes"

    id           = Column(Integer, primary_key=True, index=True)
    code         = Column(String, unique=True, nullable=False, index=True)
    created_by   = Column(Integer, ForeignKey("users.id"), nullable=False)
    max_uses     = Column(Integer, default=1)        # 0 = unlimited
    uses         = Column(Integer, default=0)
    expires_at   = Column(DateTime, nullable=True)   # None = never
    role         = Column(SAEnum(UserRole), default=UserRole.parent)
    note         = Column(String, nullable=True)     # e.g. "For library staff batch Jan 2025"
    created_at   = Column(DateTime, default=datetime.utcnow)
    is_active    = Column(Boolean, default=True)


class UsageEvent(Base):
    """
    Lightweight event log for institutional reporting.
    One row per significant action — enroll, opt-out sent, confirmed, etc.
    """
    __tablename__ = "usage_events"

    id         = Column(Integer, primary_key=True, index=True)
    event_type = Column(String, nullable=False, index=True)
    # event_type values:
    #   user_registered, optout_sent, optout_confirmed, optout_failed,
    #   discovery_run, recheck_queued, broker_added
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=True)
    member_id  = Column(Integer, ForeignKey("family_members.id"), nullable=True)
    broker_id  = Column(Integer, ForeignKey("brokers.id"), nullable=True)
    meta       = Column(Text, nullable=True)   # JSON for extra context
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class InstalledPlugin(Base):
    """
    Registry of installed plugins. Code lives on disk under the plugins dir;
    this row tracks metadata, enablement, and granted permissions.

    A plugin is DISABLED by default on install — a super admin must explicitly
    enable it and thereby grant its requested permissions.
    """
    __tablename__ = "installed_plugins"

    id             = Column(Integer, primary_key=True, index=True)
    plugin_id      = Column(String, unique=True, nullable=False, index=True)  # manifest slug
    name           = Column(String, nullable=False)
    version        = Column(String, nullable=False)
    author         = Column(String, nullable=True)
    description    = Column(Text, nullable=True)
    manifest_json  = Column(Text, nullable=False)      # full manifest as JSON
    granted_permissions = Column(Text, nullable=True)  # JSON list actually granted
    enabled        = Column(Boolean, default=False)    # off until admin enables
    install_path   = Column(String, nullable=False)    # dir on disk
    installed_at   = Column(DateTime, default=datetime.utcnow)
    enabled_at     = Column(DateTime, nullable=True)
    enabled_by     = Column(Integer, ForeignKey("users.id"), nullable=True)
    # Health / supervision
    status         = Column(String, default="stopped") # stopped|running|crashed|disabled
    crash_count    = Column(Integer, default=0)
    last_error     = Column(Text, nullable=True)
    last_started   = Column(DateTime, nullable=True)
    needs_reapproval = Column(Boolean, default=False)  # set when a manifest-integrity violation occurs
    # SHA-256 of the plugin's files when it was installed (plugins/layout.py
    # dir_hash). The manager refuses to launch the plugin if they've changed.
    code_hash      = Column(String, nullable=True)


class PluginStorage(Base):
    """
    Per-plugin key/value storage (DB backend option). Namespaced by plugin_id
    so plugins cannot read each other's data.
    """
    __tablename__ = "plugin_storage"
    __table_args__ = (UniqueConstraint("plugin_id", "key", name="uq_plugin_key"),)

    id         = Column(Integer, primary_key=True, index=True)
    plugin_id  = Column(String, nullable=False, index=True)
    key        = Column(String, nullable=False)
    value      = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PluginAuditLog(Base):
    """
    Audit trail of plugin lifecycle and security-relevant events:
    install, enable, disable, permission grant, crash, auto-disable.
    """
    __tablename__ = "plugin_audit_logs"

    id         = Column(Integer, primary_key=True, index=True)
    plugin_id  = Column(String, nullable=False, index=True)
    action     = Column(String, nullable=False)   # installed|enabled|disabled|crashed|...
    detail     = Column(Text, nullable=True)
    actor_id   = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class PluginViolation(Base):
    """
    Runtime security violations detected by the plugin monitor:
    child-process spawn, external file write, network socket, memory abuse, etc.
    Surfaced in the admin UI so the super admin can see exactly what a plugin
    attempted, and used to auto-disable offenders.
    """
    __tablename__ = "plugin_violations"

    id         = Column(Integer, primary_key=True, index=True)
    plugin_id  = Column(String, nullable=False, index=True)
    vtype      = Column(String, nullable=False)   # child_process|external_file|network_socket|...
    severity   = Column(String, nullable=False)   # critical|high|medium
    detail     = Column(Text, nullable=True)
    action_taken = Column(String, nullable=True)  # auto_disabled|warned|lockdown_disabled
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
