"""
Auth helpers: password hashing, JWT, current-user dependency,
and the central access-control check used by every data endpoint.
"""

from datetime import datetime, timedelta
from typing import Optional, List
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from ..models.database import get_db, User, FamilyMember, ProfileAccess, UserRole
import os

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
ALGORITHM  = "HS256"
TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 1440))

pwd_context   = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

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
# frontend's 401 redirect loop.
_oauth2_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


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
    Super admins, and managers granted "view all members' data", see everyone.
    Everyone else sees themselves + explicit grants.
    """
    if user.is_super_admin or _has(user, "members.view_all"):
        return [m.id for m in db.query(FamilyMember.id).all()]

    accessible_user_ids = {user.id}

    # add everyone this user has been explicitly granted access to
    grants = db.query(ProfileAccess).filter(
        ProfileAccess.manager_id == user.id,
        ProfileAccess.can_view == True,
    ).all()
    for g in grants:
        accessible_user_ids.add(g.managed_id)

    # translate user IDs → family member IDs
    members = db.query(FamilyMember).filter(
        FamilyMember.user_id.in_(accessible_user_ids)
    ).all()
    return [m.id for m in members]


def assert_can_view(db: Session, user: User, member_id: int) -> FamilyMember:
    """Raise 403 if user cannot view this family member. Returns the member."""
    member = db.query(FamilyMember).filter(FamilyMember.id == member_id).first()
    if not member:
        raise HTTPException(404, "Profile not found")

    if user.is_super_admin or _has(user, "members.view_all"):
        return member

    allowed = get_accessible_member_ids(db, user)
    if member_id not in allowed:
        raise HTTPException(403, "You don't have access to this profile")
    return member


def assert_can_edit(db: Session, user: User, member_id: int) -> FamilyMember:
    """Raise 403 if user cannot edit this family member. Returns the member."""
    member = assert_can_view(db, user, member_id)

    if user.is_super_admin or _has(user, "members.edit_all"):
        return member

    # own profile is always editable
    if member.user_id == user.id:
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
