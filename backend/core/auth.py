"""
Auth helpers: password hashing, JWT, current-user dependency,
and the central access-control check used by every data endpoint.
"""

from datetime import datetime, timedelta
from typing import Optional, List
import os, hmac, hashlib, base64

try:
    import jwt
    from jwt.exceptions import PyJWTError as JWTError
except ImportError:
    try:
        from jose import JWTError, jwt
    except ImportError:
        class JWTError(Exception): pass
        jwt = None

try:
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
except ImportError:
    pwd_context = None

try:
    from fastapi import Depends, HTTPException, status
    from fastapi.security import OAuth2PasswordBearer
    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")
    _oauth2_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)
except ImportError:
    def Depends(x=None): return x
    class HTTPException(Exception):
        def __init__(self, status_code: int = 400, detail: str = ""):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail
    class _Status:
        HTTP_401_UNAUTHORIZED = 401
    status = _Status()
    oauth2_scheme = None
    _oauth2_optional = None

try:
    from sqlalchemy.orm import Session
except ImportError:
    Session = None

try:
    from ..models.database import get_db, User, FamilyMember, ProfileAccess, UserRole, ManagerScope, Branch
except (ImportError, ValueError):
    try:
        from models.database import get_db, User, FamilyMember, ProfileAccess, UserRole, ManagerScope, Branch
    except (ImportError, ValueError):
        get_db = None
        class _ModelPlaceholder:
            def __init__(self, name):
                self._name = name
            def __getattr__(self, item):
                return self
            def __str__(self):
                return self._name
            def __repr__(self):
                return self._name
            def in_(self, *args, **kwargs):
                return self
            def __eq__(self, other):
                return self
            def __ne__(self, other):
                return self
        User = _ModelPlaceholder("User")
        FamilyMember = _ModelPlaceholder("FamilyMember")
        ProfileAccess = _ModelPlaceholder("ProfileAccess")
        UserRole = _ModelPlaceholder("UserRole")
        ManagerScope = _ModelPlaceholder("ManagerScope")
        Branch = _ModelPlaceholder("Branch")

import secrets

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
ALGORITHM  = "HS256"
TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 1440))

# bcrypt only uses the first 72 BYTES of a password — anything past that is
# silently ignored (not an error, not a truncation warning), which means two
# different long passwords sharing the same first 72 bytes would be treated
# as identical, and a user who thinks they set a 100-character password only
# really has the first 72 bytes' worth of it. Reject anything over the limit
# up front (see validate_password_length below) rather than let that happen
# quietly. This is a byte count, not a character count — accented or non-Latin
# characters take more than one byte each in UTF-8, so the same limit allows
# noticeably fewer characters for those passwords.
MAX_PASSWORD_BYTES = 72


# ── Password / token helpers ──────────────────────────────────────────────────

def validate_password_length(password: Optional[str]) -> Optional[str]:
    """Pydantic field_validator for every request model that accepts a password
    the app will hash. Raising ValueError here becomes a clean 422 with a
    readable message, instead of a raw crash out of passlib/bcrypt."""
    if password and len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Password is too long ({len(password.encode('utf-8'))} bytes; "
            f"the limit is {MAX_PASSWORD_BYTES} bytes — fewer characters if it "
            "contains accented or non-Latin characters, which take more than "
            "one byte each)."
        )
    return password

def get_password_pepper() -> bytes:
    """
    Return the HMAC pepper key used to harden password hashes against offline brute-force attacks.
    Priority:
    1. PASSWORD_PEPPER environment variable
    2. Derived from SECRET_KEY (via HMAC-SHA256 key separation)
    """
    pepper = os.getenv("PASSWORD_PEPPER")
    if pepper:
        return pepper.encode("utf-8")
    sec = os.getenv("SECRET_KEY") or SECRET_KEY or "openoptout-default-pepper-key"
    return hmac.new(b"openoptout-password-pepper-derivation", sec.encode("utf-8"), hashlib.sha256).digest()


def _pepper_password(password: str) -> str:
    """
    Apply PBKDF2-HMAC-SHA256 peppering to plaintext password before bcrypt.
    Produces a 44-character Base64 string (32-byte binary digest) which safely
    fits inside bcrypt's 72-byte ceiling while making offline dictionary/GPU
    cracking impossible without the server pepper key.
    Uses PBKDF2-HMAC with 100,000 iterations as recommended by NIST and CodeQL
    (CWE-327: py/weak-sensitive-data-hashing) for sensitive password inputs.
    """
    key = get_password_pepper()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), key, 100_000)
    return base64.b64encode(digest).decode("ascii")


def _verify_raw(candidate: str, hashed: str) -> bool:
    """Check a candidate string directly against stored bcrypt hash."""
    if not candidate or not hashed:
        return False
    if pwd_context is not None:
        try:
            return pwd_context.verify(candidate, hashed)
        except Exception:
            return False
    try:
        import bcrypt
        return bcrypt.checkpw(candidate.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def hash_password(password: str, use_pepper: bool = True) -> str:
    """
    Hash a password using bcrypt (cost 12) with HMAC-SHA256 pepper pre-hashing.
    """
    raw = _pepper_password(password) if use_pepper else password
    if pwd_context is not None:
        return pwd_context.hash(raw)
    try:
        import bcrypt
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(raw.encode("utf-8"), salt).decode("utf-8")
    except Exception as e:
        raise RuntimeError("Neither passlib nor bcrypt is available to hash passwords") from e


def verify_password(plain: str, hashed: str) -> bool:
    """
    Verify password with backward compatibility:
    1. First tries modern HMAC-SHA256 peppered verification.
    2. If that fails, falls back to legacy unpeppered verification.
    """
    if not plain or not hashed:
        return False

    # 1. Modern verification (with server pepper)
    peppered = _pepper_password(plain)
    if _verify_raw(peppered, hashed):
        return True

    # 2. Backward compatibility fallback (unpeppered legacy bcrypt hash)
    if _verify_raw(plain, hashed):
        return True

    return False


def is_legacy_unpeppered_hash(plain: str, hashed: str) -> bool:
    """
    Check if a password matches only via legacy unpeppered verification,
    signaling that the stored hash should be upgraded to the peppered format.
    """
    if not plain or not hashed:
        return False
    peppered = _pepper_password(plain)
    if _verify_raw(peppered, hashed):
        return False
    return _verify_raw(plain, hashed)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    payload = {**data, "exp": datetime.utcnow() + (expires_delta or timedelta(minutes=TOKEN_EXPIRE_MINUTES))}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ── FastAPI dependencies ──────────────────────────────────────────────────────

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if not email:
            raise exc
    except JWTError:
        raise exc

    user = db.query(User).filter(User.email == email).first()
    if not user or not user.can_login:
        raise exc
    return user


# Optional auth: returns the user if a valid token is present, else None — never
# raises 401. Used by endpoints the login page must reach while logged out
# (branding config/banner), so a missing/expired token doesn't trigger the
# frontend's 401 redirect loop. Defined above with optional fallback.



def get_current_user_optional(
    token: Optional[str] = Depends(_oauth2_optional),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            return None
    except JWTError:
        return None
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.can_login:
        return None
    return user


def require_super_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_super_admin:
        raise HTTPException(status_code=403, detail="Super admin access required")
    return current_user


def require_parent(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_parent:
        raise HTTPException(status_code=403, detail="Parent or admin access required")
    return current_user


# ── Central access control ────────────────────────────────────────────────────

def _has(user: User, key: str) -> bool:
    from .access import has_permission
    return has_permission(user, key)


def get_accessible_member_ids(db: Session, user: User) -> List[int]:
    """
    Return the list of FamilyMember IDs this user is allowed to see.
    - Super admins and managers with 'consortium.cross_system' see everyone.
    - Scoped managers with 'members.view_all' see patrons within their assigned
      systems and branches, plus their own and explicitly shared profiles.
    - Regular users see only their own and explicitly shared profiles.
    """
    if user.is_super_admin or _has(user, "consortium.cross_system"):
        return [m.id for m in db.query(FamilyMember).all()]

    accessible_member_ids = set()

    # Manager with members.view_all: evaluate assigned scopes
    if _has(user, "members.view_all"):
        scopes = db.query(ManagerScope).filter(ManagerScope.user_id == user.id).all()
        if not scopes or any(s.scope_type == "consortium" for s in scopes):
            return [m.id for m in db.query(FamilyMember).all()]

        allowed_branch_ids = set()
        system_ids = {s.system_id for s in scopes if s.scope_type == "system" and s.system_id}
        if system_ids:
            branch_rows = db.query(Branch).filter(Branch.system_id.in_(system_ids)).all()
            for b in branch_rows:
                allowed_branch_ids.add(b.id)
        for s in scopes:
            if s.scope_type == "branch" and s.branch_id:
                allowed_branch_ids.add(s.branch_id)

        if allowed_branch_ids:
            scoped_user_ids = [
                u.id for u in db.query(User).filter(User.branch_id.in_(allowed_branch_ids)).all()
            ]
            if scoped_user_ids:
                scoped_members = db.query(FamilyMember).filter(
                    FamilyMember.user_id.in_(scoped_user_ids)
                ).all()
                for sm in scoped_members:
                    accessible_member_ids.add(sm.id)

    # Always include user's own profile and explicitly granted profiles
    accessible_user_ids = {user.id}
    grants = db.query(ProfileAccess).filter(
        ProfileAccess.manager_id == user.id,
        ProfileAccess.can_view == True,
    ).all()
    for g in grants:
        accessible_user_ids.add(g.managed_id)

    own_members = db.query(FamilyMember).filter(
        FamilyMember.user_id.in_(accessible_user_ids)
    ).all()
    for om in own_members:
        accessible_member_ids.add(om.id)

    return list(accessible_member_ids)


def manager_scope(db: Session, user: User):
    """
    The (system_ids, branch_ids) a scoped manager may act on, or None when the
    user is unrestricted: super admins, 'consortium.cross_system' holders, and
    managers with no scopes or a consortium-wide scope. branch_ids includes
    every branch of a scoped system.
    """
    if user.is_super_admin or _has(user, "consortium.cross_system"):
        return None
    scopes = db.query(ManagerScope).filter(ManagerScope.user_id == user.id).all()
    if not scopes or any(s.scope_type == "consortium" for s in scopes):
        return None
    system_ids = {s.system_id for s in scopes if s.scope_type == "system" and s.system_id}
    branch_ids = {s.branch_id for s in scopes if s.scope_type == "branch" and s.branch_id}
    if system_ids:
        branch_ids |= {b.id for b in db.query(Branch).filter(Branch.system_id.in_(system_ids)).all()}
    return system_ids, branch_ids


def assert_user_in_scope(db: Session, actor: User, target: User):
    """403 unless the target account's branch is within the actor's scopes.
    Unassigned accounts are outside every branch scope."""
    scope = manager_scope(db, actor)
    if scope is not None and target.branch_id not in scope[1]:
        raise HTTPException(403, "That account is outside the branches you manage")


def assert_system_in_scope(db: Session, actor: User, system_id: Optional[int]):
    """403 unless the whole library system is within the actor's scopes. A
    branch scope doesn't cover its system; None (a new system) is in no scope."""
    scope = manager_scope(db, actor)
    if scope is not None and system_id not in scope[0]:
        raise HTTPException(403, "That library system is outside the systems you manage")


def assert_branch_in_scope(db: Session, actor: User, branch_id: int):
    """403 unless the branch is within the actor's scopes."""
    scope = manager_scope(db, actor)
    if scope is not None and branch_id not in scope[1]:
        raise HTTPException(403, "That branch is outside the branches you manage")


def assert_can_view(db: Session, user: User, member_id: int) -> FamilyMember:
    """Raise 403 if user cannot view this family member. Returns the member."""
    member = db.query(FamilyMember).filter(FamilyMember.id == member_id).first()
    if not member:
        raise HTTPException(404, "Profile not found")

    if user.is_super_admin or _has(user, "consortium.cross_system"):
        return member

    allowed = get_accessible_member_ids(db, user)
    if member_id not in allowed:
        raise HTTPException(403, "You don't have access to this profile")
    return member


def assert_can_edit(db: Session, user: User, member_id: int) -> FamilyMember:
    """Raise 403 if user cannot edit this family member. Returns the member."""
    member = assert_can_view(db, user, member_id)

    if user.is_super_admin or _has(user, "consortium.cross_system"):
        return member

    # own profile is always editable
    if member.user_id == user.id:
        return member

    # if user has edit_all, check if member is within their accessible scope
    if _has(user, "members.edit_all"):
        allowed = get_accessible_member_ids(db, user)
        if member_id in allowed:
            return member

    # check explicit edit grant
    grant = db.query(ProfileAccess).filter(
        ProfileAccess.manager_id == user.id,
        ProfileAccess.managed_id == member.user_id,
        ProfileAccess.can_edit == True,
    ).first()
    if not grant:
        raise HTTPException(403, "You have view-only access to this profile")
    return member
