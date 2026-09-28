"""
Auth helpers: password hashing, JWT, current-user dependency,
and the central access-control check used by every data endpoint.
"""

from datetime import datetime, timedelta
from typing import Optional, List
import os

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

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
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

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

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
        if any(s.scope_type == "consortium" for s in scopes):
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
