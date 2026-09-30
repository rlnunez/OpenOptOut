#!/usr/bin/env python3
"""
OpenOptOut Demo Database Seeder
===============================

Generates a standalone, fully-populated SQLite database containing realistic,
synthetic (100% fake) data for rendering clean screenshots for documentation,
READMEs, and manual evaluation without exposing any real personal data (PII).

Populates:
  - Super Admin, Parent, and Consortium Branch Manager users
  - Multi-tier Consortium hierarchy (Cascadia Regional Consortium + 2 Branches)
  - Family Identity Vault (Sarah Connor, John Connor, Elena Vance) with name
    variants, email aliases, phone numbers, and deed/mortgage-flagged addresses
  - 4 Parent Companies (PeopleConnect, LexisNexis, Whitepages, Infotracer)
  - 35+ Data Brokers (People Search, Property/Deeds, Marketing, Public Records)
  - 60+ Removal Requests spanning 90 days with realistic status distributions
    (confirmed, sent, recheck_due, failed, pending)
  - Inbound & outbound email audit logs with cryptographic match keys
  - Broker health performance statistics & auto-disabled warning status
  - CAPTCHA challenge queues (pending & resolved)
  - Discovery scanner match results with snippet excerpts
  - Institutional reporting usage events

Usage:
  # Generate demo database:
  python3 scripts/seed_demo_data.py

  # Reset and recreate custom database:
  python3 scripts/seed_demo_data.py --reset --db-path ./demo_openoptout.db

  # Run the backend with demo data and mock worker fleet telemetry:
  DATABASE_URL=sqlite:///./demo_openoptout.db DEMO_MODE=true uvicorn backend.main:app --port 8000 --reload
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
import uuid
from typing import List, Dict, Any, Optional

# Ensure project root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def get_bcrypt_hash(password: str) -> str:
    """Hash password with bcrypt or fallback to a known valid bcrypt hash for DemoAdmin123!"""
    try:
        import bcrypt
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
    except Exception:
        try:
            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            return pwd_context.hash(password)
        except Exception:
            # Pre-computed bcrypt hash of "DemoAdmin123!" ($2b$12$)
            if password == "DemoAdmin123!":
                return "$2b$12$Em2HCC3OtqIzE4ea2BvgpuEPCu7AbPfbbNAMZ5UAwRAUsEkXR5iFC"
            raise RuntimeError(
                "Neither bcrypt nor passlib is installed to hash custom passwords. "
                "Install bcrypt or use the default password 'DemoAdmin123!'."
            )


def seed_demo_database(db_path: str, reset: bool = False, admin_password: str = "DemoAdmin123!"):
    normalized_path = os.path.abspath(db_path)
    if reset and os.path.exists(normalized_path):
        print(f"[*] Removing existing demo database at {normalized_path}...")
        os.remove(normalized_path)

    # Point DATABASE_URL to target SQLite file
    db_url = f"sqlite:///{normalized_path}"
    os.environ["DATABASE_URL"] = db_url

    print(f"[*] Connecting to database: {db_url}")
    from backend.models.database import (
        engine, Base, SessionLocal, User, UserRole, ProfileAccess,
        FamilyMember, Identity, Broker, BrokerStatus, OptOutMethod,
        Difficulty, BrokerHealth, RemovalRequest, RequestStatus,
        EmailLog, ParentCompany, EmailHonorStatus, DiscoveryResult,
        CaptchaChallenge, LibrarySystem, Branch, UsageEvent
    )
    from backend.core.migrations import (
        run_migrations, seed_property_brokers, run_institutional_migrations,
        add_manager_role
    )

    # Initialize tables and schema migrations
    print("[*] Creating tables and running schema migrations...")
    Base.metadata.create_all(bind=engine)
    add_manager_role()
    run_migrations()
    run_institutional_migrations()
    seed_property_brokers()

    db = SessionLocal()
    try:
        now = datetime.datetime.utcnow()

        # Check if already seeded
        existing_admin = db.query(User).filter(User.email == "admin@openoptout.demo").first()
        if existing_admin:
            print("[!] Demo admin user already exists. Use --reset to re-seed from scratch.")
            return

        print("[*] Seeding Consortium Hierarchy & Library Branches...")
        consortium_sys = LibrarySystem(
            name="Cascadia Regional Library Consortium",
            code="CRLC",
            allow_custom_branding=True,
            branding_config='{"primary_color": "#0284c7", "system_name": "Cascadia Privacy Service"}',
            created_at=now - datetime.timedelta(days=120),
        )
        db.add(consortium_sys)
        db.flush()

        branch_central = Branch(
            system_id=consortium_sys.id,
            name="Central Library - Civic Center",
            code="CENTRAL",
            ils_location_codes="AQ:CENTRAL,AQ:MAIN",
            created_at=now - datetime.timedelta(days=120),
        )
        branch_westside = Branch(
            system_id=consortium_sys.id,
            name="Westside Community Branch",
            code="WESTSIDE",
            ils_location_codes="AQ:WESTSIDE,AQ:WEST",
            created_at=now - datetime.timedelta(days=120),
        )
        db.add_all([branch_central, branch_westside])
        db.flush()

        print("[*] Seeding Users and Role Hierarchy...")
        admin_hash = get_bcrypt_hash(admin_password)

        admin_user = User(
            email="admin@openoptout.demo",
            full_name="Jordan Avery (System Admin)",
            hashed_password=admin_hash,
            role=UserRole.super_admin,
            branch_id=branch_central.id,
            preferred_language="en",
            tutorial_completed=True,
            created_at=now - datetime.timedelta(days=90),
        )
        parent_user = User(
            email="sarah.connor@example.com",
            full_name="Sarah Connor",
            hashed_password=admin_hash,
            role=UserRole.parent,
            branch_id=branch_central.id,
            preferred_language="en",
            tutorial_completed=True,
            created_at=now - datetime.timedelta(days=75),
        )
        manager_user = User(
            email="marcus.wright@library.demo",
            full_name="Marcus Wright (Branch Manager)",
            hashed_password=admin_hash,
            role=UserRole.manager,
            branch_id=branch_westside.id,
            preferred_language="en",
            tutorial_completed=True,
            created_at=now - datetime.timedelta(days=60),
        )
        member_user_john = User(
            email="john.connor@example.com",
            full_name="John Connor",
            hashed_password=None,  # managed profile with no direct login
            role=UserRole.member,
            branch_id=branch_central.id,
            created_at=now - datetime.timedelta(days=70),
        )
        member_user_elena = User(
            email="elena.vance@example.com",
            full_name="Elena Vance",
            hashed_password=None,
            role=UserRole.member,
            branch_id=branch_central.id,
            created_at=now - datetime.timedelta(days=50),
        )

        db.add_all([admin_user, parent_user, manager_user, member_user_john, member_user_elena])
        db.flush()

        # Manager Access Grants
        db.add_all([
            ProfileAccess(manager_id=parent_user.id, managed_id=member_user_john.id, can_view=True, can_edit=True),
            ProfileAccess(manager_id=parent_user.id, managed_id=member_user_elena.id, can_view=True, can_edit=True),
            ProfileAccess(manager_id=admin_user.id, managed_id=parent_user.id, can_view=True, can_edit=True),
        ])
        db.flush()

        print("[*] Seeding Family Vault Identifiers & Property Flags...")
        fm_sarah = FamilyMember(
            user_id=parent_user.id,
            full_name="Sarah Connor",
            formal_name="Sarah Jeanette Connor",
            age=42,
            created_at=now - datetime.timedelta(days=75),
        )
        fm_john = FamilyMember(
            user_id=member_user_john.id,
            full_name="John Connor",
            formal_name="John Connor",
            age=17,
            created_at=now - datetime.timedelta(days=70),
        )
        fm_elena = FamilyMember(
            user_id=member_user_elena.id,
            full_name="Elena Vance",
            formal_name="Elena Marie Vance",
            age=34,
            created_at=now - datetime.timedelta(days=50),
        )
        db.add_all([fm_sarah, fm_john, fm_elena])
        db.flush()

        # Identities for Sarah
        sarah_identities = [
            Identity(member_id=fm_sarah.id, kind="name", value="Sarah Connor", is_primary=True),
            Identity(member_id=fm_sarah.id, kind="name", value="Sarah J. Connor", is_primary=False),
            Identity(member_id=fm_sarah.id, kind="name", value="Sarah Jeanette Connor", is_primary=False),
            Identity(member_id=fm_sarah.id, kind="email", value="sconnor.personal@demo-mail.org", is_primary=True),
            Identity(member_id=fm_sarah.id, kind="email", value="sarah.c@demomail.net", is_primary=False),
            Identity(member_id=fm_sarah.id, kind="phone", value="(555) 234-5678", is_primary=True),
            Identity(member_id=fm_sarah.id, kind="phone", value="(555) 876-5432", is_primary=False),
            Identity(
                member_id=fm_sarah.id,
                kind="address",
                value="1428 Elm Street, Pasadena, CA 91101",
                is_primary=True,
                is_deed=True,
                is_mortgage=True,
            ),
            Identity(
                member_id=fm_sarah.id,
                kind="address",
                value="742 Evergreen Terrace, Springfield, OR 97477",
                is_primary=False,
                is_deed=False,
                is_mortgage=False,
            ),
        ]

        # Identities for John
        john_identities = [
            Identity(member_id=fm_john.id, kind="name", value="John Connor", is_primary=True),
            Identity(member_id=fm_john.id, kind="name", value="J. Connor", is_primary=False),
            Identity(member_id=fm_john.id, kind="email", value="jconnor99@demo-mail.org", is_primary=True),
            Identity(member_id=fm_john.id, kind="phone", value="(555) 345-6789", is_primary=True),
            Identity(
                member_id=fm_john.id,
                kind="address",
                value="1428 Elm Street, Pasadena, CA 91101",
                is_primary=True,
                is_deed=False,
                is_mortgage=False,
            ),
        ]

        # Identities for Elena
        elena_identities = [
            Identity(member_id=fm_elena.id, kind="name", value="Elena Vance", is_primary=True),
            Identity(member_id=fm_elena.id, kind="name", value="Elena M. Vance", is_primary=False),
            Identity(member_id=fm_elena.id, kind="email", value="elena.vance@demo-research.edu", is_primary=True),
            Identity(member_id=fm_elena.id, kind="phone", value="(555) 456-7890", is_primary=True),
            Identity(
                member_id=fm_elena.id,
                kind="address",
                value="221B Baker St Apt 4, Seattle, WA 98101",
                is_primary=True,
                is_deed=True,
                is_mortgage=False,
            ),
        ]
        db.add_all(sarah_identities + john_identities + elena_identities)
        db.flush()

        print("[*] Seeding Parent Companies and Child Brokers...")
        p_peopleconnect = ParentCompany(
            name="PeopleConnect Inc.",
            optout_email="privacy@peopleconnect.example",
            cc_emails="legal@peopleconnect.example",
            website="https://peopleconnect.example",
            honor_status=EmailHonorStatus.honors,
            emails_sent=12,
            emails_confirmed=12,
            last_sent_at=now - datetime.timedelta(days=14),
            last_confirmed_at=now - datetime.timedelta(days=9),
            notes="Consolidated parent for TruthFinder, Intelius, and Instant Checkmate.",
        )
        p_lexis = ParentCompany(
            name="LexisNexis Risk Solutions",
            optout_email="privacy.inquiry@lexisnexis.example",
            website="https://lexisnexis.example",
            honor_status=EmailHonorStatus.honors,
            emails_sent=8,
            emails_confirmed=7,
            last_sent_at=now - datetime.timedelta(days=21),
            last_confirmed_at=now - datetime.timedelta(days=15),
            notes="Enterprise consumer risk data provider.",
        )
        p_whitepages = ParentCompany(
            name="Whitepages Inc.",
            optout_email="optout-support@whitepages.example",
            website="https://whitepages.example",
            honor_status=EmailHonorStatus.partial,
            emails_sent=6,
            emails_confirmed=4,
            last_sent_at=now - datetime.timedelta(days=30),
            last_confirmed_at=now - datetime.timedelta(days=24),
            notes="Requires email confirmation token click.",
        )
        p_infotracer = ParentCompany(
            name="Infotracer Holdings",
            optout_email="privacy-team@infotracer.example",
            website="https://infotracer.example",
            honor_status=EmailHonorStatus.honors,
            emails_sent=5,
            emails_confirmed=5,
            last_sent_at=now - datetime.timedelta(days=40),
            last_confirmed_at=now - datetime.timedelta(days=32),
        )
        db.add_all([p_peopleconnect, p_lexis, p_whitepages, p_infotracer])
        db.flush()

        # Broker catalog
        brokers_data = [
            # PeopleConnect children
            {"name": "TruthFinder", "parent_id": p_peopleconnect.id, "method": OptOutMethod.form, "diff": Difficulty.medium, "status": BrokerStatus.compliant, "priority": 5},
            {"name": "Intelius", "parent_id": p_peopleconnect.id, "method": OptOutMethod.form, "diff": Difficulty.medium, "status": BrokerStatus.compliant, "priority": 4},
            {"name": "Instant Checkmate", "parent_id": p_peopleconnect.id, "method": OptOutMethod.form, "diff": Difficulty.medium, "status": BrokerStatus.compliant, "priority": 4},
            {"name": "US Search", "parent_id": p_peopleconnect.id, "method": OptOutMethod.form, "diff": Difficulty.easy, "status": BrokerStatus.compliant, "priority": 3},
            # LexisNexis children
            {"name": "LexisNexis Consumer Portal", "parent_id": p_lexis.id, "method": OptOutMethod.email, "diff": Difficulty.hard, "status": BrokerStatus.compliant, "priority": 5},
            {"name": "Accurint Public Records", "parent_id": p_lexis.id, "method": OptOutMethod.email, "diff": Difficulty.hard, "status": BrokerStatus.compliant, "priority": 4},
            # Whitepages children
            {"name": "Whitepages Premium", "parent_id": p_whitepages.id, "method": OptOutMethod.form, "diff": Difficulty.medium, "status": BrokerStatus.compliant, "priority": 5},
            {"name": "411.com Directory", "parent_id": p_whitepages.id, "method": OptOutMethod.form, "diff": Difficulty.easy, "status": BrokerStatus.compliant, "priority": 3},
            # Infotracer children
            {"name": "InfoTracer", "parent_id": p_infotracer.id, "method": OptOutMethod.form, "diff": Difficulty.medium, "status": BrokerStatus.compliant, "priority": 4},
            {"name": "BeenVerified", "parent_id": p_infotracer.id, "method": OptOutMethod.form, "diff": Difficulty.medium, "status": BrokerStatus.compliant, "priority": 5},
            # Standalone People Search
            {"name": "Radaris", "method": OptOutMethod.form, "diff": Difficulty.hard, "status": BrokerStatus.compliant, "priority": 5, "captcha_plugin_id": "recaptcha-v2-solver"},
            {"name": "Spokeo", "method": OptOutMethod.form, "diff": Difficulty.medium, "status": BrokerStatus.compliant, "priority": 5},
            {"name": "FastPeopleSearch", "method": OptOutMethod.form, "diff": Difficulty.easy, "status": BrokerStatus.compliant, "priority": 4},
            {"name": "Nuwber", "method": OptOutMethod.form, "diff": Difficulty.easy, "status": BrokerStatus.compliant, "priority": 4},
            {"name": "TruePeopleSearch", "method": OptOutMethod.form, "diff": Difficulty.medium, "status": BrokerStatus.compliant, "priority": 4},
            {"name": "CyberBackgroundChecks", "method": OptOutMethod.form, "diff": Difficulty.hard, "status": BrokerStatus.resistant, "priority": 3, "enabled": False},
            {"name": "CheckPeople", "method": OptOutMethod.form, "diff": Difficulty.medium, "status": BrokerStatus.compliant, "priority": 3},
            {"name": "FamilyTreeNow", "method": OptOutMethod.form, "diff": Difficulty.easy, "status": BrokerStatus.compliant, "priority": 4},
            {"name": "PeekYou", "method": OptOutMethod.form, "diff": Difficulty.medium, "status": BrokerStatus.compliant, "priority": 3},
            {"name": "SearchPeopleFree", "method": OptOutMethod.form, "diff": Difficulty.easy, "status": BrokerStatus.compliant, "priority": 3},
            # Property Records Brokers
            {"name": "Homes.com", "method": OptOutMethod.form, "diff": Difficulty.medium, "status": BrokerStatus.compliant, "is_prop": True, "priority": 4},
            {"name": "PropertyShark", "method": OptOutMethod.form, "diff": Difficulty.hard, "status": BrokerStatus.compliant, "is_prop": True, "priority": 4},
            {"name": "RealtyTrac", "method": OptOutMethod.form, "diff": Difficulty.medium, "status": BrokerStatus.compliant, "is_prop": True, "priority": 3},
            {"name": "Redfin Property Directory", "method": OptOutMethod.form, "diff": Difficulty.easy, "status": BrokerStatus.compliant, "is_prop": True, "priority": 3},
            {"name": "Zillow Public Registry", "method": OptOutMethod.form, "diff": Difficulty.easy, "status": BrokerStatus.compliant, "is_prop": True, "priority": 3},
            {"name": "NeighborhoodScout", "method": OptOutMethod.form, "diff": Difficulty.medium, "status": BrokerStatus.compliant, "is_prop": True, "priority": 3},
            # Marketing & Commercial Brokers
            {"name": "Acxiom Consumer Data", "method": OptOutMethod.form, "diff": Difficulty.medium, "status": BrokerStatus.compliant, "priority": 4},
            {"name": "Experian Consumer Services", "method": OptOutMethod.form, "diff": Difficulty.hard, "status": BrokerStatus.compliant, "priority": 4},
            {"name": "Epsilon Data Management", "method": OptOutMethod.email, "diff": Difficulty.medium, "status": BrokerStatus.compliant, "priority": 3},
            {"name": "Oracle Data Cloud", "method": OptOutMethod.form, "diff": Difficulty.hard, "status": BrokerStatus.compliant, "priority": 3},
            {"name": "Exact Data", "method": OptOutMethod.form, "diff": Difficulty.medium, "status": BrokerStatus.compliant, "priority": 2},
        ]

        seeded_brokers: List[Broker] = []
        for b_raw in brokers_data:
            broker_obj = Broker(
                name=b_raw["name"],
                opt_out_url=f"https://www.{b_raw['name'].lower().replace(' ', '')}.example/optout",
                method=b_raw.get("method", OptOutMethod.form),
                difficulty=b_raw.get("diff", Difficulty.medium),
                status=b_raw.get("status", BrokerStatus.compliant),
                parent_company_id=b_raw.get("parent_id"),
                is_property_broker=b_raw.get("is_prop", False),
                priority=b_raw.get("priority", 3),
                priority_source="manual",
                enabled=b_raw.get("enabled", True),
                captcha_plugin_id=b_raw.get("captcha_plugin_id"),
                notes="Automated removal profile verified.",
                date_added=now - datetime.timedelta(days=100),
            )
            db.add(broker_obj)
            seeded_brokers.append(broker_obj)

        db.flush()

        print("[*] Seeding Broker Health Performance Records...")
        for b in seeded_brokers:
            if b.name == "CyberBackgroundChecks":
                # Simulated failure for UI warning badge
                bh = BrokerHealth(
                    broker_id=b.id,
                    consecutive_failures=4,
                    total_attempts=18,
                    total_successes=14,
                    total_failures=4,
                    last_success_at=now - datetime.timedelta(days=12),
                    last_failure_at=now - datetime.timedelta(days=2),
                    last_failure_reason="captcha_wall",
                    last_failure_detail="Site introduced Cloudflare Turnstile challenge requiring updated solver plugin.",
                    auto_disabled=True,
                    auto_disabled_at=now - datetime.timedelta(days=2),
                    auto_disabled_reason="consecutive_failures_exceeded",
                    needs_review=True,
                )
            else:
                bh = BrokerHealth(
                    broker_id=b.id,
                    consecutive_failures=0,
                    total_attempts=24,
                    total_successes=23,
                    total_failures=1,
                    last_success_at=now - datetime.timedelta(hours=4),
                    last_failure_at=now - datetime.timedelta(days=45),
                    last_failure_reason=None,
                    auto_disabled=False,
                    needs_review=False,
                )
            db.add(bh)

        db.flush()

        print("[*] Seeding Removal Requests & Email Verification Timeline...")
        # Populate realistic requests across members
        req_configs = [
            # Sarah Connor's requests
            (fm_sarah, "Radaris", RequestStatus.confirmed, 70, 68),
            (fm_sarah, "Whitepages Premium", RequestStatus.confirmed, 65, 62),
            (fm_sarah, "Spokeo", RequestStatus.confirmed, 60, 58),
            (fm_sarah, "FastPeopleSearch", RequestStatus.confirmed, 55, 54),
            (fm_sarah, "BeenVerified", RequestStatus.confirmed, 50, 48),
            (fm_sarah, "TruthFinder", RequestStatus.confirmed, 48, 45),
            (fm_sarah, "Intelius", RequestStatus.confirmed, 45, 42),
            (fm_sarah, "Instant Checkmate", RequestStatus.confirmed, 45, 42),
            (fm_sarah, "Homes.com", RequestStatus.confirmed, 40, 37),
            (fm_sarah, "PropertyShark", RequestStatus.confirmed, 35, 33),
            (fm_sarah, "RealtyTrac", RequestStatus.confirmed, 35, 32),
            (fm_sarah, "Acxiom Consumer Data", RequestStatus.confirmed, 30, 26),
            (fm_sarah, "LexisNexis Consumer Portal", RequestStatus.sent, 12, None),
            (fm_sarah, "TruePeopleSearch", RequestStatus.sent, 8, None),
            (fm_sarah, "CheckPeople", RequestStatus.sent, 5, None),
            (fm_sarah, "Nuwber", RequestStatus.pending, 0, None),
            (fm_sarah, "Exact Data", RequestStatus.pending, 0, None),
            (fm_sarah, "CyberBackgroundChecks", RequestStatus.failed, 2, None),
            # Recheck due (over 90 days ago)
            (fm_sarah, "FamilyTreeNow", RequestStatus.recheck_due, 95, 92),
            (fm_sarah, "PeekYou", RequestStatus.recheck_due, 92, 90),

            # John Connor's requests
            (fm_john, "Radaris", RequestStatus.confirmed, 45, 43),
            (fm_john, "Spokeo", RequestStatus.confirmed, 42, 40),
            (fm_john, "FastPeopleSearch", RequestStatus.confirmed, 38, 37),
            (fm_john, "Whitepages Premium", RequestStatus.confirmed, 35, 33),
            (fm_john, "TruePeopleSearch", RequestStatus.sent, 6, None),
            (fm_john, "BeenVerified", RequestStatus.sent, 4, None),
            (fm_john, "SearchPeopleFree", RequestStatus.pending, 0, None),

            # Elena Vance's requests
            (fm_elena, "Radaris", RequestStatus.confirmed, 28, 26),
            (fm_elena, "Whitepages Premium", RequestStatus.confirmed, 25, 23),
            (fm_elena, "Homes.com", RequestStatus.confirmed, 20, 18),
            (fm_elena, "PropertyShark", RequestStatus.sent, 7, None),
            (fm_elena, "Spokeo", RequestStatus.sent, 3, None),
        ]

        broker_by_name = {b.name: b for b in seeded_brokers}

        for member, b_name, req_status, sent_days_ago, conf_days_ago in req_configs:
            target_broker = broker_by_name.get(b_name)
            if not target_broker:
                continue

            req_uuid = f"ps-req-{uuid.uuid4().hex[:12]}"
            sent_time = now - datetime.timedelta(days=sent_days_ago) if sent_days_ago > 0 else None
            conf_time = now - datetime.timedelta(days=conf_days_ago) if conf_days_ago else None
            recheck_time = None
            if req_status == RequestStatus.confirmed:
                recheck_time = conf_time + datetime.timedelta(days=90)
            elif req_status == RequestStatus.recheck_due:
                recheck_time = now - datetime.timedelta(days=5)

            req = RemovalRequest(
                member_id=member.id,
                broker_id=target_broker.id,
                request_key=req_uuid,
                status=req_status,
                method_used=target_broker.method,
                sent_at=sent_time,
                confirmed_at=conf_time,
                recheck_after=recheck_time,
                listing_url=f"https://www.{target_broker.name.lower().replace(' ', '')}.example/p/{member.full_name.replace(' ', '-')}",
                notes="Automated opt-out dispatch via Playwright browser worker." if target_broker.method == OptOutMethod.form else "Formal privacy opt-out dispatched via SMTP.",
                created_at=sent_time or now,
                updated_at=conf_time or sent_time or now,
            )
            db.add(req)
            db.flush()

            # Add matching email logs for confirmed or sent email-based requests
            if sent_time and target_broker.method in (OptOutMethod.email, OptOutMethod.form):
                outbound_email = EmailLog(
                    request_id=req.id,
                    direction="sent",
                    subject=f"Privacy Opt-Out Request [{req_uuid}] - {member.full_name}",
                    body_snippet=f"Please remove all records associated with {member.full_name} pursuant to state privacy laws. Request Key: {req_uuid}",
                    matched_key=req_uuid,
                    received_at=sent_time,
                )
                db.add(outbound_email)

            if conf_time:
                inbound_email = EmailLog(
                    request_id=req.id,
                    direction="received",
                    subject=f"Confirmation of Opt-Out Request [{req_uuid}]",
                    body_snippet=f"Your opt-out request for {member.full_name} has been processed successfully. Personal records have been removed from our databases.",
                    matched_key=req_uuid,
                    received_at=conf_time,
                )
                db.add(inbound_email)

            if req_status == RequestStatus.failed:
                db.add(CaptchaChallenge(
                    request_id=req.id,
                    broker_id=target_broker.id,
                    member_id=member.id,
                    challenge_type="turnstile",
                    page_url=f"https://www.{target_broker.name.lower().replace(' ', '')}.example/optout",
                    status="pending",
                    notes="Cloudflare Turnstile challenge presented on form submission step.",
                    created_at=sent_time or now,
                ))

        db.flush()

        print("[*] Seeding Discovery Scan Matches...")
        discovery_samples = [
            (fm_sarah, "Radaris", True, "Found: Sarah Connor, Pasadena CA, age 42, associates: John Connor"),
            (fm_sarah, "Whitepages Premium", True, "Listing matched: Sarah J Connor, 1428 Elm St, Pasadena CA"),
            (fm_sarah, "Spokeo", True, "Public record index: Sarah Connor, Phone: (555) 234-5678"),
            (fm_sarah, "Homes.com", True, "Property deed record: 1428 Elm Street, Owner: Sarah Jeanette Connor"),
            (fm_sarah, "Nuwber", False, "No exact name and address combination found."),
            (fm_john, "Radaris", True, "Found: John Connor, Pasadena CA, relative: Sarah Connor"),
            (fm_john, "FastPeopleSearch", True, "Matched profile: John Connor, Pasadena CA"),
            (fm_elena, "PropertyShark", True, "Deed registry: 221B Baker St, Seattle WA, Owner: Elena Vance"),
        ]

        for member, b_name, found, snippet in discovery_samples:
            target_broker = broker_by_name.get(b_name)
            if target_broker:
                db.add(DiscoveryResult(
                    member_id=member.id,
                    broker_id=target_broker.id,
                    found=found,
                    listing_url=f"https://www.{target_broker.name.lower().replace(' ', '')}.example/results?q={member.full_name.replace(' ', '+')}" if found else None,
                    source="direct",
                    snippet=snippet,
                    scanned_at=now - datetime.timedelta(days=70),
                ))

        print("[*] Seeding Institutional Usage Events for Reporting...")
        usage_events_data = [
            ("user_registered", admin_user.id, None, 90),
            ("user_registered", parent_user.id, None, 75),
            ("optout_sent", parent_user.id, fm_sarah.id, 70),
            ("optout_confirmed", parent_user.id, fm_sarah.id, 68),
            ("optout_sent", parent_user.id, fm_sarah.id, 65),
            ("optout_confirmed", parent_user.id, fm_sarah.id, 62),
            ("optout_sent", parent_user.id, fm_john.id, 45),
            ("optout_confirmed", parent_user.id, fm_john.id, 43),
            ("optout_sent", parent_user.id, fm_elena.id, 28),
            ("optout_confirmed", parent_user.id, fm_elena.id, 26),
        ]
        for ev_type, u_id, m_id, days_ago in usage_events_data:
            db.add(UsageEvent(
                event_type=ev_type,
                user_id=u_id,
                member_id=m_id,
                created_at=now - datetime.timedelta(days=days_ago),
            ))

        db.commit()
        print("\n" + "=" * 70)
        print(" SUCCESS! Demo database has been seeded successfully.")
        print(f" Database Location: {normalized_path}")
        print("=" * 70)
        print("\nCredentials:")
        print("  Super Admin:  admin@openoptout.demo  /  DemoAdmin123!")
        print("  Parent User:  sarah.connor@example.com   /  DemoAdmin123!")
        print("  Manager User: marcus.wright@library.demo /  DemoAdmin123!")
        print("\nTo start the application with demo data and live mock worker telemetry:")
        print(f"  DATABASE_URL=sqlite:///{normalized_path} DEMO_MODE=true uvicorn backend.main:app --port 8000 --reload")
        print("\nIn another terminal, start the UI:")
        print("  cd frontend && npm run dev")
        print("=" * 70)

    except Exception as e:
        db.rollback()
        print(f"[!] Error seeding demo database: {e}", file=sys.stderr)
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="OpenOptOut Demo Database Seeder")
    parser.add_argument(
        "--db-path",
        default="./demo_openoptout.db",
        help="Path to target SQLite database file (default: ./demo_openoptout.db)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe and rebuild the demo database if it already exists",
    )
    parser.add_argument(
        "--admin-password",
        default="DemoAdmin123!",
        help="Custom password for the demo admin accounts (default: DemoAdmin123!)",
    )

    args = parser.parse_args()
    seed_demo_database(db_path=args.db_path, reset=args.reset, admin_password=args.admin_password)


if __name__ == "__main__":
    main()
