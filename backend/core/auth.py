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
from .settings_store import get_secret_key, is_valid_secret_key

SECRET_KEY = os.getenv("SECRET_KEY") or ""
ALGORITHM  = "HS256"
TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 1440))


def _jwt_secret() -> str:
    """Return the validated SECRET_KEY (raises RuntimeError if missing or an example value)."""
    return get_secret_key()


# Minimum password length for new or updated local passwords. Existing shorter
# passwords can still sign in via /api/auth/token (which does not call this
# validator), matching what the sign-up page asks for.
MIN_PASSWORD_CHARS = 15   # NIST SP 800-63B rev. 4 S3.1.1: single-factor passwords SHALL be >=15 chars

# bcrypt only uses the first 72 BYTES of whatever it's given — but
# hash_password/_pepper_password below never hand bcrypt the raw password:
# they PBKDF2-pepper it first into a fixed 44-character Base64 digest, which
# always fits well inside that limit regardless of the original password's
# length. So bcrypt's byte ceiling isn't actually a constraint here; this is
# just a sane upper bound on the password itself (ASVS 6.2.9 asks for at
# least 64 CHARACTERS to be accepted, so the limit is counted in characters,
# not UTF-8 bytes — a byte-based count would reject far short of 64 accented
# or non-Latin characters, which take more than one byte each).
MAX_PASSWORD_CHARS = 128


# ── Password / token helpers ──────────────────────────────────────────────────

def validate_password_length(password: Optional[str]) -> Optional[str]:
    """Pydantic field_validator for every request model that accepts a password
    the app will hash. Raising ValueError here becomes a clean 422 with a
    readable message, instead of a raw crash out of passlib/bcrypt."""
    if isinstance(password, str) and "\x00" in password:
        password = password.replace("\x00", "")
    if password:
        if len(password) < MIN_PASSWORD_CHARS:
            raise ValueError(
                f"Password must be at least {MIN_PASSWORD_CHARS} characters "
                f"(got {len(password)})."
            )
        if len(password) > MAX_PASSWORD_CHARS:
            raise ValueError(
                f"Password is too long ({len(password)} characters; "
                f"the limit is {MAX_PASSWORD_CHARS})."
            )
        from .common_passwords import is_common_password
        if is_common_password(password):
            raise ValueError(
                "That password is far too common and would be guessed quickly. "
                "Please choose a less predictable one."
            )
    return password

_CACHED_PEPPER: Optional[bytes] = None


def _read_pepper_file(path: str) -> Optional[bytes]:
    """Safely read a persistent pepper key from disk (supporting 64-character hex or raw 32+ bytes)."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            raw = f.read().strip()
        if not raw:
            return None
        # Stored as 64-character hex string
        if len(raw) == 64:
            try:
                return bytes.fromhex(raw.decode("ascii"))
            except ValueError:
                pass
        # Stored as raw binary bytes (take first 32 bytes without destructive strip truncation)
        if len(raw) >= 32:
            return raw[:32]
    except OSError as e:
        import logging
        logging.getLogger(__name__).warning("Could not read pepper.key at %s: %s", path, e)
    return None


def ensure_password_pepper_persisted() -> bytes:
    """Ensure that the persistent pepper.key file exists on disk, locking in the
    current password pepper so subsequent master secret key rotations never invalidate
    existing password hashes."""
    global _CACHED_PEPPER
    pepper = get_password_pepper()
    try:
        from .settings_store import get_secret_key_file_path
        sk_path = get_secret_key_file_path()
        pepper_path = os.path.join(os.path.dirname(os.path.abspath(sk_path)), "pepper.key")
        os.makedirs(os.path.dirname(os.path.abspath(pepper_path)), exist_ok=True)
        if not os.path.exists(pepper_path):
            fd = os.open(pepper_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(fd, (pepper.hex() + "\n").encode("ascii"))
                os.fsync(fd)
            finally:
                os.close(fd)
    except FileExistsError:
        pass
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Could not persist pepper.key: %s", e)
    return pepper


def get_password_pepper() -> bytes:
    """
    Return the HMAC pepper key used to harden password hashes against offline brute-force attacks.
    Priority:
    1. PASSWORD_PEPPER environment variable
    2. Cached pepper in memory
    3. Persistent pepper.key file alongside secret.key (keeps passwords valid across SECRET_KEY rotation)
    4. Derived from SECRET_KEY (via HMAC-SHA256 key separation)
    """
    global _CACHED_PEPPER
    pepper = os.getenv("PASSWORD_PEPPER")
    if pepper and is_valid_secret_key(pepper):
        return pepper.encode("utf-8")
    if _CACHED_PEPPER is not None:
        return _CACHED_PEPPER

    try:
        from .settings_store import get_secret_key_file_path
        sk_path = get_secret_key_file_path()
        pepper_path = os.path.join(os.path.dirname(os.path.abspath(sk_path)), "pepper.key")
        content = _read_pepper_file(pepper_path)
        if content is not None:
            _CACHED_PEPPER = content
            return _CACHED_PEPPER
    except Exception:
        pepper_path = None

    sec = get_secret_key()
    derived = hmac.new(b"openoptout-password-pepper-derivation", sec.encode("utf-8"), hashlib.sha256).digest()
    _CACHED_PEPPER = derived

    if pepper_path:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(pepper_path)), exist_ok=True)
            if not os.path.exists(pepper_path):
                fd = os.open(pepper_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    os.write(fd, (derived.hex() + "\n").encode("ascii"))
                    os.fsync(fd)
                finally:
                    os.close(fd)
        except FileExistsError:
            pass
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Could not persist initial pepper.key at %s: %s", pepper_path, e)

    return _CACHED_PEPPER


def get_candidate_peppers() -> list[bytes]:
    """Return all valid candidate peppers in priority order for robust password verification:
    1. Active pepper (from get_password_pepper())
    2. Pepper derived from secret.key file on disk
    3. Pepper derived from SECRET_KEY environment variable
    4. Pepper derived from .env file directly (if env was replaced in memory)
    """
    candidates: list[bytes] = []
    try:
        active = get_password_pepper()
        if active and len(active) >= 32 and active[:32] not in candidates:
            candidates.append(active[:32])
    except Exception:
        pass

    def _derive_from_key(k: Optional[str]) -> Optional[bytes]:
        if not k:
            return None
        cleaned = k.replace("\x00", "").strip()
        from .settings_store import is_valid_secret_key
        if not is_valid_secret_key(cleaned):
            return None
        return hmac.new(b"openoptout-password-pepper-derivation", cleaned.encode("utf-8"), hashlib.sha256).digest()

    try:
        from .settings_store import read_secret_key_file
        fk = read_secret_key_file()
        p = _derive_from_key(fk)
        if p and p not in candidates:
            candidates.append(p)
    except Exception:
        pass

    try:
        ek = os.getenv("SECRET_KEY")
        p = _derive_from_key(ek)
        if p and p not in candidates:
            candidates.append(p)
    except Exception:
        pass

    try:
        from .settings_store import get_secret_key_file_path
        sk_path = get_secret_key_file_path()
        sk_dir = os.path.dirname(os.path.abspath(sk_path))
        for env_path in [
            os.path.join(sk_dir, ".env"),
            os.path.join(os.path.dirname(sk_dir), ".env"),
            os.path.abspath(".env"),
        ]:
            if os.path.isfile(env_path):
                with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("SECRET_KEY="):
                            val = line.split("=", 1)[1].strip().strip("'\"")
                            p = _derive_from_key(val)
                            if p and p not in candidates:
                                candidates.append(p)
                            break
    except Exception:
        pass

    return candidates


DEFAULT_PBKDF2_ITERATIONS = 210_000
LEGACY_PBKDF2_ITERATIONS = 100_000


def _pepper_password_with_key(password: str, pepper_key: bytes, iterations: int = DEFAULT_PBKDF2_ITERATIONS) -> str:
    """Apply PBKDF2-HMAC-SHA256 peppering using a specific pepper key."""
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), pepper_key, iterations)
    return base64.b64encode(digest).decode("ascii")


def _pepper_password(password: str, iterations: int = DEFAULT_PBKDF2_ITERATIONS) -> str:
    """
    Apply PBKDF2-HMAC-SHA256 peppering to plaintext password before bcrypt.
    Produces a 44-character Base64 string (32-byte binary digest) which safely
    fits inside bcrypt's 72-byte ceiling while making offline dictionary/GPU
    cracking impossible without the server pepper key.
    Uses PBKDF2-HMAC with >= 210,000 iterations as recommended by NIST SP 800-132
    and OWASP for sensitive password key derivation.
    """
    key = get_password_pepper()
    return _pepper_password_with_key(password, key, iterations)


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
    Hash a password using bcrypt (cost 12) with HMAC-SHA256 pepper pre-hashing (NIST SP 800-132).
    """
    raw = _pepper_password(password, DEFAULT_PBKDF2_ITERATIONS) if use_pepper else password
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
    Verify password with backward compatibility and key rotation resilience:
    1. First tries modern NIST SP 800-132 PBKDF2-HMAC-SHA256 (210,000 rounds) with active pepper.
    2. Tries candidate fallback peppers (e.g. across master SECRET_KEY rotation).
    3. Falls back to legacy peppered verification (100,000 rounds) with active pepper.
    4. Falls back to legacy peppered verification (100,000 rounds) with fallback peppers.
    5. Falls back to legacy unpeppered verification.
    """
    if not plain or not hashed:
        return False

    active = get_password_pepper()
    # 1. Modern NIST SP 800-132 verification (210,000 rounds) with active pepper
    if _verify_raw(_pepper_password_with_key(plain, active, DEFAULT_PBKDF2_ITERATIONS), hashed):
        return True

    candidates = [p for p in get_candidate_peppers() if p != active]
    # 2. Modern NIST SP 800-132 verification with candidate fallback peppers
    for cand in candidates:
        if _verify_raw(_pepper_password_with_key(plain, cand, DEFAULT_PBKDF2_ITERATIONS), hashed):
            return True

    # 3. Legacy peppered verification (100,000 rounds) with active pepper
    if _verify_raw(_pepper_password_with_key(plain, active, LEGACY_PBKDF2_ITERATIONS), hashed):
        return True

    # 4. Legacy peppered verification (100,000 rounds) with candidate fallback peppers
    for cand in candidates:
        if _verify_raw(_pepper_password_with_key(plain, cand, LEGACY_PBKDF2_ITERATIONS), hashed):
            return True

    # 5. Backward compatibility fallback (unpeppered legacy bcrypt hash)
    if _verify_raw(plain, hashed):
        return True

    return False


def is_legacy_unpeppered_hash(plain: str, hashed: str) -> bool:
    """
    Check if a password matches only via legacy verification (either 100k rounds, unpeppered,
    or a fallback candidate pepper from before key rotation), signaling that the stored hash
    should be upgraded to the modern 210,000 iteration format with the active pepper.
    """
    if not plain or not hashed:
        return False
    active = get_password_pepper()
    if _verify_raw(_pepper_password_with_key(plain, active, DEFAULT_PBKDF2_ITERATIONS), hashed):
        return False
    return verify_password(plain, hashed)


# Valid bcrypt hash for constant-time comparison when an account does not exist
_DUMMY_BCRYPT_HASH = "$2b$12$e8Y7X4Q9L7Z1N5M3J2K1O.e5wL8.dD4xR5e5wL8.dD4xR5e5wL8.dD4xR5"


def dummy_verify_password(password: str) -> bool:
    """Execute full peppered verification against a dummy hash to prevent login timing side-channels."""
    try:
        active = get_password_pepper()
        return _verify_raw(_pepper_password_with_key(password, active, DEFAULT_PBKDF2_ITERATIONS), _DUMMY_BCRYPT_HASH)
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    payload = {**data, "exp": datetime.utcnow() + (expires_delta or timedelta(minutes=TOKEN_EXPIRE_MINUTES))}
    return jwt.encode(payload, _jwt_secret(), algorithm=ALGORITHM)


_LAST_SEEN_RESOLUTION = timedelta(minutes=1)


def _session_revoked(db: Session, jti: Optional[str], user: Optional[User] = None) -> bool:
    """True if this token's session should be rejected: explicitly revoked,
    has no matching row (and isn't grandfathered — see below), or idle past
    the account's role's configured timeout (ASVS 7.3.1; 0/unset disables it).
    A token with no jti predates session tracking and is grandfathered as
    valid — this check is additive to the existing token_version mechanism,
    not a replacement for it.

    Also bumps the session's last_seen_at, throttled to roughly once a
    minute per session, so a busy session doesn't turn into a write on every
    single authenticated request."""
    if not jti:
        return False
    from ..models.database import UserSession
    sess = db.query(UserSession).filter(UserSession.jti == jti).first()
    if sess is None or sess.revoked_at is not None:
        return True

    now = datetime.utcnow()
    if user is not None:
        from .session_policy import get_idle_timeout_minutes
        role = getattr(getattr(user, "role", None), "value", str(getattr(user, "role", "") or "parent"))
        idle_minutes = get_idle_timeout_minutes(role)
        last_seen = sess.last_seen_at or sess.created_at or now
        if idle_minutes and now - last_seen > timedelta(minutes=idle_minutes):
            sess.revoked_at = now
            db.commit()
            return True

    if not sess.last_seen_at or now - sess.last_seen_at > _LAST_SEEN_RESOLUTION:
        sess.last_seen_at = now
        db.commit()
    return False


# ── FastAPI dependencies & Token Resolution ──────────────────────────────────

def resolve_user_from_token(token: Optional[str], db: Session) -> Optional[User]:
    """Resolve and validate a User from a JWT bearer token string.

    Verifies the JWT signature, decodes claims, verifies user account existence
    and login eligibility, confirms token version matches, and ensures session (jti)
    has not been revoked. Returns None if invalid, revoked, missing, or in environments
    without a JWT library.
    """
    if not token or jwt is None or db is None:
        return None
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if not email:
            return None
    except (JWTError, Exception):
        return None

    user = db.query(User).filter(User.email == email).first()
    if not user or not user.can_login:
        return None
    token_ver = payload.get("token_version")
    user_ver = getattr(user, "token_version", 0) or 0
    if (token_ver or 0) != user_ver:
        return None
    if _session_revoked(db, payload.get("jti"), user):
        return None
    return user


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Your sign-in has expired. Please sign in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user = resolve_user_from_token(token, db)
    if not user:
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
    return resolve_user_from_token(token, db)


def get_current_jti(token: str = Depends(oauth2_scheme)) -> Optional[str]:
    """The current request's session identifier (JWT `jti` claim), for
    endpoints that need to know which of a user's sessions is "this one"
    (e.g. marking it in a session list, or revoking only it on sign-out).
    Token validity itself is already enforced by get_current_user, a sibling
    dependency on the same route — this just re-reads the already-decoded claim."""
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[ALGORITHM])
        return payload.get("jti")
    except JWTError:
        return None


def require_super_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_super_admin:
        raise HTTPException(status_code=403, detail="Only the main administrator can do this.")
    return current_user


def require_parent(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_parent:
        raise HTTPException(status_code=403, detail="Only a parent or an admin can do this.")
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
        raise HTTPException(404, "That person is gone. Refresh the page.")

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
