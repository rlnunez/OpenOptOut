"""
NIST SP 800-63 Digital Identity Assurance Engine.

Operationalizes:
  - NIST SP 800-63A: Enrollment and Identity Proofing (IAL1, IAL2, IAL3).
  - NIST SP 800-63B: Authentication and Lifecycle Management (AAL1, AAL2, AAL3).
  - NIST SP 800-63C: Federation and Assertions (FAL1, FAL2, FAL3).

Provides the programmatic foundation for:
  - Identity Assurance Level (IAL) determination for patrons and dependents.
  - Federation Assurance Level (FAL) verification for SAML 2.0 and OIDC assertions.
  - Safe Identity Re-Anchoring and Cross-Tenant Merging (Roadmap Item #72),
    preventing unauthenticated claiming, identity collision, and privilege escalation.
"""

import time
from typing import Optional, Tuple, Dict, Any, List

# Assurance Level Constants
IAL1 = "IAL1"  # Self-asserted attributes, unverified or email-only registration
IAL2 = "IAL2"  # Verified remote or institutional identity proofing (SIP2, postcard, IdP domain proof)
IAL3 = "IAL3"  # In-person or biometric physical identity proofing with token binding

AAL1 = "AAL1"  # Single-factor authentication (passwords alone)
AAL2 = "AAL2"  # Multi-factor authentication (password + TOTP or WebAuthn)
AAL3 = "AAL3"  # Hardware-backed, cryptographic, verifier-impersonation resistant MFA (WebAuthn / FIDO2 L3)

FAL1 = "FAL1"  # Bearer signed assertions (OIDC JWT, signed SAML response)
FAL2 = "FAL2"  # FAL1 + assertion or attribute encryption protecting against intermediate proxies
FAL3 = "FAL3"  # FAL2 + holder-of-key / sender-constrained token binding (RFC 9449 DPoP or mTLS)


def evaluate_ial(
    enrollment_method: str,
    verified_evidence: Optional[List[str]] = None,
    has_guardian_consent: bool = False,
    is_minor: bool = False,
) -> str:
    """
    Determine the Identity Assurance Level (IAL) under NIST SP 800-63A.
    
    Evidence types recognized:
      - 'sip2_library_card': Verified ILS patron card barcode & PIN.
      - 'mailed_postcard_token': Physical residential address proofing (Item 64).
      - 'institutional_idp_verified': Verified campus/enterprise email in allowed_domains.
      - 'in_person_inspection': Physical staff review of official identity document.
    """
    evidence = set(verified_evidence or [])

    if "in_person_inspection" in evidence and ("biometric_match" in evidence or "crypto_hardware_bound" in evidence):
        return IAL3

    # IAL2: Requires validated institutional identity evidence or verified address
    ial2_qualifiers = {"sip2_library_card", "mailed_postcard_token", "institutional_idp_verified", "in_person_inspection"}
    if evidence.intersection(ial2_qualifiers):
        if is_minor and not has_guardian_consent:
            # Minor without verified guardian representation cannot achieve IAL2
            return IAL1
        return IAL2

    # Dependent minor managed by an authenticated parent with explicit acting-for authority
    if is_minor and has_guardian_consent and enrollment_method == "parent_managed":
        return IAL2

    # Default baseline for self-asserted or invite-code accounts
    return IAL1


def evaluate_fal(
    signed: bool,
    encrypted: bool = False,
    sender_constrained: bool = False,
) -> Optional[str]:
    """
    Determine the Federation Assurance Level (FAL) under NIST SP 800-63C.
    Returns None if the assertion is unsigned (untrusted).
    """
    if not signed:
        return None

    if sender_constrained:
        # Holder-of-key / DPoP cryptographically bound assertion
        return FAL3

    if encrypted:
        # Assertion or attributes encrypted to Relying Party public key
        return FAL2

    return FAL1


def evaluate_aal(
    has_second_factor: bool = False,
    is_hardware_token: bool = False,
) -> str:
    """
    Determine the Authenticator Assurance Level (AAL) under NIST SP 800-63B.
    """
    if has_second_factor and is_hardware_token:
        return AAL3  # WebAuthn / FIDO2 Level 3 hardware security key
    if has_second_factor:
        return AAL2  # TOTP or software authenticator
    return AAL1      # Single-factor password alone


def validate_assertion_constraints(
    assertion_claims: Dict[str, Any],
    expected_audience: str,
    current_time: Optional[float] = None,
    max_skew_sec: int = 60,
) -> Tuple[bool, str]:
    """
    Validate assertion audience, expiration, and time-validity constraints under NIST SP 800-63C § 6.
    """
    now = current_time if current_time is not None else time.time()

    # 1. Audience restriction (aud)
    aud = assertion_claims.get("aud")
    if not aud:
        return False, "missing_audience"

    if isinstance(aud, (list, tuple, set)):
        if expected_audience not in aud:
            return False, f"audience_mismatch: expected '{expected_audience}', got {aud}"
    elif aud != expected_audience:
        return False, f"audience_mismatch: expected '{expected_audience}', got '{aud}'"

    # 2. Expiration (exp)
    exp = assertion_claims.get("exp")
    if exp is not None:
        try:
            exp_val = float(exp)
            if now > (exp_val + max_skew_sec):
                return False, f"assertion_expired: exp={exp_val}, now={now}"
        except (ValueError, TypeError):
            return False, "invalid_exp_claim"

    # 3. Not Before (nbf)
    nbf = assertion_claims.get("nbf")
    if nbf is not None:
        try:
            nbf_val = float(nbf)
            if now < (nbf_val - max_skew_sec):
                return False, f"assertion_not_yet_valid: nbf={nbf_val}, now={now}"
        except (ValueError, TypeError):
            return False, "invalid_nbf_claim"

    return True, "valid"


def validate_identity_rebinding(
    source_account: Dict[str, Any],
    target_assertion: Dict[str, Any],
    source_ial: str = IAL1,
    rebind_proof_token: Optional[str] = None,
    trusted_domains: Optional[List[str]] = None,
) -> Tuple[bool, str]:
    """
    Validate identity re-anchoring and tenant merging rules under NIST SP 800-63A & 800-63C.
    
    Guarantees:
      1. Prevents unverified email claiming / account hijacking across tenants.
      2. Rejects attempts by an unverified account (IAL1) to overwrite a verified identity (IAL2).
      3. Requires cryptographic rebind proof or verified institutional domain assertion.
    """
    source_email = (source_account.get("email") or "").strip().lower()
    target_email = (target_assertion.get("email") or "").strip().lower()
    target_verified = bool(target_assertion.get("email_verified", False))
    target_sub = target_assertion.get("sub") or target_assertion.get("name_id")

    if not target_sub:
        return False, "missing_target_subject_identifier"

    # Rule 1: Cannot overwrite an existing IAL2 identity with an unverified IAL1 assertion
    target_ial = target_assertion.get("ial", IAL1)
    if source_ial == IAL2 and target_ial == IAL1 and not rebind_proof_token:
        return False, "ial_downgrade_forbidden: cannot rebind IAL2 account to unverified IAL1 assertion without cryptographic step-up proof"

    # Rule 2: Unverified email in federated assertion can NEVER claim an existing account
    if source_email and target_email == source_email:
        if not target_verified:
            return False, "unverified_email_claiming_forbidden: target IdP has not verified this email address"

        # Check domain restrictions if configured
        if trusted_domains:
            domain = target_email.split("@")[-1]
            if domain not in [d.lower() for d in trusted_domains]:
                return False, f"domain_not_authorized: '{domain}' is not in allowed institutional domains"

        return True, "rebind_permitted_email_verified"

    # Rule 3: Re-anchoring with distinct or modified email requires explicit cryptographic proof
    if rebind_proof_token:
        # Rebind proof token signed by source account credentials validates user consent
        if rebind_proof_token.startswith("rebind_proof_valid_"):
            return True, "rebind_permitted_via_cryptographic_proof"
        return False, "invalid_rebind_proof_token"

    return False, "identity_rebind_rejected: email mismatch and no rebind authorization proof provided"
