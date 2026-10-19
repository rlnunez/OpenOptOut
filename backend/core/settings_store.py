"""
Thin helpers used by scheduler.py to read settings and decrypt passwords
without importing the full FastAPI router (avoids circular imports).
"""

import json, os, base64, logging
try:
    from cryptography.fernet import Fernet, MultiFernet
except ImportError:
    Fernet = None
    MultiFernet = None

log = logging.getLogger(__name__)

_DEFAULT_SETTINGS_FILE = "./openoptout_settings.json"
_LEGACY_SETTINGS_FILE = "./privacyshield_settings.json"
SETTINGS_FILE = os.getenv("SETTINGS_FILE") or (
    _LEGACY_SETTINGS_FILE if os.path.exists(_LEGACY_SETTINGS_FILE) and not os.path.exists(_DEFAULT_SETTINGS_FILE) else _DEFAULT_SETTINGS_FILE
)


def load_settings() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return {}
    with open(SETTINGS_FILE) as f:
        return json.load(f)


def save_settings(data: dict) -> None:
    """Atomically write settings JSON to disk using a temporary file."""
    import tempfile
    dir_name = os.path.dirname(os.path.abspath(SETTINGS_FILE))
    os.makedirs(dir_name, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix="settings_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, SETTINGS_FILE)
        _hsts_cache["mtime"] = None
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise


_hsts_cache: dict = {"mtime": None, "path": None, "enabled": False}


def is_hsts_enabled(s: dict | None = None) -> bool:
    """Return True if HTTP Strict Transport Security (HSTS) is enabled via settings or HSTS env var."""
    if s is not None:
        sec_hsts = s.get("security", {}).get("hsts")
        if isinstance(sec_hsts, bool):
            return sec_hsts
        dep_hsts = s.get("deployment", {}).get("hsts")
        if isinstance(dep_hsts, bool):
            return dep_hsts
        return os.getenv("HSTS", "").strip().lower() in ("1", "true", "on", "yes")

    try:
        mtime = os.path.getmtime(SETTINGS_FILE) if os.path.exists(SETTINGS_FILE) else -1
    except OSError:
        mtime = -1
    if _hsts_cache["mtime"] == mtime and _hsts_cache["path"] == SETTINGS_FILE:
        if _hsts_cache["enabled"] is not None:
            return _hsts_cache["enabled"]
    try:
        data = load_settings() if mtime != -1 else {}
    except Exception:
        data = {}
    sec_hsts = data.get("security", {}).get("hsts")
    dep_hsts = data.get("deployment", {}).get("hsts")
    if isinstance(sec_hsts, bool):
        val = sec_hsts
    elif isinstance(dep_hsts, bool):
        val = dep_hsts
    else:
        val = None
    _hsts_cache["mtime"] = mtime
    _hsts_cache["path"] = SETTINGS_FILE
    _hsts_cache["enabled"] = val
    if val is not None:
        return val
    return os.getenv("HSTS", "").strip().lower() in ("1", "true", "on", "yes")


MIN_SECRET_KEY_CHARS = 128
MAX_SECRET_KEY_CHARS = 512

FORBIDDEN_SECRET_KEYS = frozenset({
    "",
    "change-me-please",
    "change-me-please-32-chars-minimum",
    "change-me-to-a-long-random-string",
    "change-me-in-production-use-a-long-random-string",
    "openoptout-default-pepper-key",
    "changeme",
    "secret",
    "default",
})

_secret_file_cache: dict = {"mtime": None, "path": None, "key": None}
_USING_BOOTSTRAP_KEY: bool = False


def get_secret_key_file_path() -> str:
    """Return the path to the persistent master secret key file."""
    override = (os.getenv("SECRET_KEY_FILE") or "").strip()
    if override:
        return override
    base_dir = os.path.dirname(os.path.abspath(SETTINGS_FILE))
    return os.path.join(base_dir, "secret.key")


def read_secret_key_file() -> str | None:
    """Read the master secret key from secret.key if it exists and is non-empty."""
    path = get_secret_key_file_path()
    try:
        mtime = os.path.getmtime(path) if os.path.exists(path) else -1
    except OSError:
        mtime = -1
    if mtime == -1:
        _secret_file_cache["mtime"] = -1
        _secret_file_cache["path"] = path
        _secret_file_cache["key"] = None
        return None
    if _secret_file_cache["mtime"] == mtime and _secret_file_cache["path"] == path:
        return _secret_file_cache["key"]
    try:
        with open(path, "r", encoding="utf-8") as f:
            val = f.read().replace("\x00", "").strip()
    except OSError:
        val = ""
    _secret_file_cache["mtime"] = mtime
    _secret_file_cache["path"] = path
    _secret_file_cache["key"] = val or None
    return _secret_file_cache["key"]


def is_valid_secret_key(key: str | None) -> bool:
    """Return True only when key is non-empty and not one of the known example/placeholder values."""
    if not key or not isinstance(key, str):
        return False
    cleaned = key.replace("\x00", "").strip()
    if not cleaned or cleaned.lower() in FORBIDDEN_SECRET_KEYS:
        return False
    return True


def is_valid_user_secret_key(key: str | None) -> bool:
    """Return True when a user-entered secret key is between MIN_SECRET_KEY_CHARS (128)
    and MAX_SECRET_KEY_CHARS (512) characters long, not a placeholder, and has sufficient character diversity."""
    if not is_valid_secret_key(key):
        return False
    cleaned = key.replace("\x00", "").strip()
    if len(cleaned) < MIN_SECRET_KEY_CHARS or len(cleaned) > MAX_SECRET_KEY_CHARS:
        return False
    if len(set(cleaned)) < 8:
        return False
    return True


def get_secret_key() -> str:
    file_key = read_secret_key_file()
    if file_key and is_valid_secret_key(file_key):
        return file_key
    key = (os.getenv("SECRET_KEY") or "").strip()
    if not is_valid_secret_key(key):
        raise RuntimeError(
            "SECRET_KEY is missing or set to a publicly known example value. "
            "Set a strong random SECRET_KEY in .env or configure a 128+ character key in secret.key."
        )
    return key


def ensure_bootstrap_secret_key() -> str:
    """Ensure the server has a valid, persistent master key on startup.

    Order of precedence:
      1. A valid key already in secret.key → use it.
      2. A valid SECRET_KEY in the environment (set by the installer's .env, a
         Docker/K8s secret, etc.) → use it.
      3. Neither → generate a strong 128+ character key and PERSIST it to
         secret.key (0600). This makes the key a first-boot artifact for every
         install path — the installer, a manual `docker compose up`, or an
         automated test — so the app never runs on a throwaway key and the
         web-UI master-key step becomes optional (rotation only).

    Only if the key location can't be written (e.g. a read-only filesystem) do
    we fall back to an in-memory ephemeral key for this process.
    """
    global _USING_BOOTSTRAP_KEY
    file_key = read_secret_key_file()
    if file_key and is_valid_user_secret_key(file_key):
        os.environ["SECRET_KEY"] = file_key
        _USING_BOOTSTRAP_KEY = False
        return file_key
    env_key = (os.getenv("SECRET_KEY") or "").strip()
    if is_valid_secret_key(env_key):
        _USING_BOOTSTRAP_KEY = False
        return env_key

    import secrets
    n_bytes = secrets.randbelow(65) + 64  # random length: 128..256 hex chars
    generated = secrets.token_hex(n_bytes)
    path = get_secret_key_file_path()
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        # Exclusive create so concurrent workers can't clobber each other; the
        # first worker writes, the rest read back its key below.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, (generated + "\n").encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        _secret_file_cache["mtime"] = None
        os.environ["SECRET_KEY"] = generated
        _USING_BOOTSTRAP_KEY = False
        log.warning(
            "No master key was configured; generated and persisted a key at %s (0600). "
            "Set a custom key from the admin UI to rotate it.", path)
        return generated
    except FileExistsError:
        # Another worker created it first — adopt that key so every worker agrees.
        _secret_file_cache["mtime"] = None
        existing = read_secret_key_file()
        if existing and is_valid_user_secret_key(existing):
            os.environ["SECRET_KEY"] = existing
            _USING_BOOTSTRAP_KEY = False
            return existing
        os.environ["SECRET_KEY"] = generated
        _USING_BOOTSTRAP_KEY = True
        return generated
    except OSError as e:
        # Read-only key location: keep working this process with an in-memory key.
        os.environ["SECRET_KEY"] = generated
        _USING_BOOTSTRAP_KEY = True
        log.warning(
            "No master key configured and %s is not writable (%s); using a temporary in-memory key "
            "for this process. Configure a master key in the environment or the admin UI to persist one.",
            path, e)
        return generated


def get_security_key_files() -> list[str]:
    """Return all detected on-disk files storing security keys (master key, field key, DB key, search secret, .env)."""
    files = []
    sk_path = get_secret_key_file_path()
    if os.path.isfile(sk_path):
        files.append(sk_path)

    # Configured dedicated key files
    for var in ("FIELD_ENCRYPTION_KEY_FILE", "DB_ENCRYPTION_KEY_FILE", "SQLCIPHER_KEY_FILE", "SEARXNG_SECRET_FILE"):
        f = (os.getenv(var) or "").strip()
        if f and os.path.isfile(f) and f not in files:
            files.append(f)

    # Look for .env file associated with the installation
    env_override = (os.getenv("ENV_FILE") or "").strip()
    if env_override and os.path.isfile(env_override) and env_override not in files:
        files.append(env_override)
    elif not os.getenv("SECRET_KEY_FILE"):
        # When not running under an isolated test override, inspect deployment .env files
        sk_dir = os.path.dirname(os.path.abspath(sk_path))
        candidates = [
            os.path.join(sk_dir, ".env"),
            os.path.join(os.path.dirname(sk_dir), ".env"),
        ]
        for c in candidates:
            if os.path.isfile(c) and c not in files:
                files.append(c)
                break
    return files


def get_secret_key_status() -> dict:
    """Inspect all security key files and their filesystem permissions for the admin banner and settings UI."""
    import stat, shlex
    path = get_secret_key_file_path()
    file_exists = os.path.exists(path)
    file_key = read_secret_key_file() if file_exists else None
    has_valid_file_key = is_valid_user_secret_key(file_key)
    mode_octal = None
    permissions_secure = False
    if file_exists:
        try:
            st = os.stat(path)
            imode = stat.S_IMODE(st.st_mode)
            mode_octal = f"0{imode:03o}"
            # Permissions are secure only when group and world have zero access (e.g. 0600 or 0400)
            permissions_secure = (imode & 0o077) == 0
        except OSError:
            mode_octal = "unknown"
            permissions_secure = False

    # Check all key files (secret.key, field/DB key files, .env)
    insecure_files = []
    key_files_status = []
    for kf in get_security_key_files():
        try:
            st = os.stat(kf)
            imode = stat.S_IMODE(st.st_mode)
            mo = f"0{imode:03o}"
            sec = (imode & 0o077) == 0
            key_files_status.append({"path": kf, "mode_octal": mo, "permissions_secure": sec})
            if not sec:
                insecure_files.append({"path": kf, "mode_octal": mo})
        except OSError:
            key_files_status.append({"path": kf, "mode_octal": "unknown", "permissions_secure": False})
            insecure_files.append({"path": kf, "mode_octal": "unknown"})

    if insecure_files:
        permissions_secure = False

    env_key = (os.getenv("SECRET_KEY") or "").strip()
    active_len = len(file_key) if (file_key and is_valid_secret_key(file_key)) else (len(env_key) if is_valid_secret_key(env_key) else 0)
    needs_key = not has_valid_file_key
    permissions_insecure = bool((has_valid_file_key and not permissions_secure) or insecure_files)

    target_paths = [f["path"] for f in insecure_files] if insecure_files else [path]
    primary_target = target_paths[0]
    qpath = shlex.quote(primary_target)

    return {
        "file_path": path,
        "file_exists": file_exists,
        "has_valid_file_key": has_valid_file_key,
        "using_bootstrap_key": _USING_BOOTSTRAP_KEY,
        "min_length": MIN_SECRET_KEY_CHARS,
        "max_length": MAX_SECRET_KEY_CHARS,
        "active_key_length": active_len,
        "mode_octal": mode_octal or (insecure_files[0]["mode_octal"] if insecure_files else "0600"),
        "permissions_secure": permissions_secure if file_exists else (len(insecure_files) == 0),
        "needs_key": needs_key,
        "permissions_insecure": permissions_insecure,
        "banner_required": bool(needs_key or permissions_insecure),
        "insecure_files": [f["path"] for f in insecure_files],
        "key_files": key_files_status,
        "commands": {
            "linux": " && ".join(f"chmod 600 {shlex.quote(p)}" for p in target_paths),
            "docker": " && ".join(f"docker compose exec api chmod 600 {shlex.quote(p)}" for p in target_paths),
            "windows": " ; ".join(f'icacls "{p}" /inheritance:r /grant:r "$($env:USERNAME):(R,W)"' for p in target_paths),
        },
    }


def _fernet_for_key(raw: str):
    if Fernet is None:
        raise RuntimeError("cryptography package is required for password encryption")
    _kb = raw.encode() or b"\0"
    padded = (_kb * (32 // len(_kb) + 1))[:32]
    return Fernet(base64.urlsafe_b64encode(padded))


def save_secret_key_file(new_key: str) -> dict:
    """Validate and persist a 128-512 character master key to secret.key.
    Initial file permissions are set to 0644 (unless already locked down to 0600)
    so the administrator can lock down permissions using the displayed commands."""
    global _USING_BOOTSTRAP_KEY
    cleaned = (new_key or "").replace("\x00", "").strip()
    if len(cleaned) < MIN_SECRET_KEY_CHARS:
        raise ValueError(f"Master secret key must be at least {MIN_SECRET_KEY_CHARS} characters long (got {len(cleaned)}).")
    if len(cleaned) > MAX_SECRET_KEY_CHARS:
        raise ValueError(f"Master secret key must be {MAX_SECRET_KEY_CHARS} characters or fewer (got {len(cleaned)}).")
    if not is_valid_secret_key(cleaned):
        raise ValueError("Master secret key cannot be a placeholder or example value.")
    if len(set(cleaned)) < 8:
        raise ValueError("Master secret key must contain at least 8 distinct characters for sufficient entropy.")

    # Re-encrypt any stored SMTP password in settings before rotating the key
    old_plain_smtp = None
    try:
        s = load_settings()
        enc_pw = s.get("email", {}).get("smtp_password_enc")
        if enc_pw:
            old_plain_smtp = decrypt_password(enc_pw)
    except Exception:
        s = None

    path = get_secret_key_file_path()
    dir_name = os.path.dirname(os.path.abspath(path))
    os.makedirs(dir_name, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(cleaned + "\n")
        f.flush()
        os.fsync(f.fileno())
    try:
        # Leave group/world read bit (0644) until the administrator runs chmod 600
        os.chmod(path, 0o644)
    except OSError:
        pass

    _secret_file_cache["mtime"] = None
    os.environ["SECRET_KEY"] = cleaned
    _USING_BOOTSTRAP_KEY = False

    if s is not None and old_plain_smtp:
        try:
            s.setdefault("email", {})["smtp_password_enc"] = _fernet_for_key(cleaned).encrypt(old_plain_smtp.encode()).decode()
            save_settings(s)
        except Exception:
            pass

    return get_secret_key_status()


def _make_procedural_bmp_data_url(seed_bytes: bytes, idx: int) -> tuple[str, bytes]:
    """Generate a vibrant, high-entropy 48x36 24-bit BMP image seeded from OS cryptographic
    randomness (lava-lamp plasma + noise) so image-based key generation works even offline."""
    import math, struct
    w, h = 48, 36
    row_stride = (w * 3 + 3) & ~3
    pixel_data = bytearray(row_stride * h)
    p1 = (seed_bytes[0] / 255.0) * 6.28
    p2 = (seed_bytes[1] / 255.0) * 6.28
    p3 = (seed_bytes[2] / 255.0) * 6.28
    f1 = 1.5 + (seed_bytes[3] % 5) * 0.6
    f2 = 1.5 + (seed_bytes[4] % 5) * 0.6
    hue_shift = idx * 51
    n_len = len(seed_bytes)
    pos = 0
    for y in range(h):
        row_off = y * row_stride
        ny = y / h
        for x in range(w):
            nx = x / w
            v = (
                math.sin(nx * f1 * 6.28 + p1)
                + math.cos(ny * f2 * 6.28 + p2)
                + math.sin((nx + ny) * 4.5 + p3)
            )
            noise = seed_bytes[pos % n_len]
            pos += 1
            r = int((math.sin(v + p1) * 0.5 + 0.5) * 210 + (noise & 0x2F) + hue_shift) & 0xFF
            g = int((math.cos(v * 1.3 + p2) * 0.5 + 0.5) * 210 + ((noise >> 2) & 0x2F)) & 0xFF
            b = int((math.sin(v * 1.7 + p3) * 0.5 + 0.5) * 210 + ((noise >> 4) & 0x2F)) & 0xFF
            px_off = row_off + x * 3
            pixel_data[px_off] = b
            pixel_data[px_off + 1] = g
            pixel_data[px_off + 2] = r
    file_size = 54 + len(pixel_data)
    header = struct.pack(
        "<2sIHHI IIIHHIIIIII",
        b"BM", file_size, 0, 0, 54,
        40, w, h, 1, 24, 0, len(pixel_data), 2835, 2835, 0, 0
    )
    raw_bmp = header + bytes(pixel_data)
    b64 = base64.b64encode(raw_bmp).decode("ascii")
    return f"data:image/bmp;base64,{b64}", raw_bmp


def generate_entropy_images(count: int = 8) -> list[dict]:
    """Fetch 8-12 free random images from license-free mirrors (Lorem Picsum / Unsplash)
    or synthesize cryptographic lava-lamp frames if offline/blocked, extracting high-entropy byte chunks."""
    import concurrent.futures, hashlib, urllib.parse, urllib.request
    count = max(4, min(12, int(count or 8)))
    themes = [
        "Crimson Lava Nebula",
        "Bioluminescent Deep",
        "Solar Flare Plasma",
        "Aurora Borealis Drift",
        "Quantum Interference",
        "Prismatic Thermal Wave",
        "Supernova Remnant",
        "Galactic Core Stream",
        "Atmospheric Scattering",
        "Electromagnetic Flux",
        "Vortex Turbulence",
        "Cosmic Ray Cascade",
    ]

    def _fetch_one_image(i: int) -> dict:
        seed_entropy = os.urandom(128)
        raw_bytes = None
        data_url = None
        source_type = "lava-lamp-rng"
        label = themes[i % len(themes)]
        # Attempt to pull a license-free public image from Unsplash mirror (Lorem Picsum)
        seed_id = hashlib.sha256(seed_entropy[:16]).hexdigest()[:10]
        url = f"https://picsum.photos/seed/{seed_id}/96/72"
        try:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme != "https":
                raise ValueError(f"Disallowed URL scheme: {parsed.scheme}")
            req = urllib.request.Request(url, headers={"User-Agent": "OpenOptOut-KeyGen/1.0"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:  # nosec: B310 -- scheme is validated to https
                ctype = resp.headers.get("Content-Type", "image/jpeg")
                fetched = resp.read(65536)
                if len(fetched) > 128 and ctype.startswith("image/"):
                    raw_bytes = fetched + seed_entropy
                    b64 = base64.b64encode(fetched).decode("ascii")
                    data_url = f"data:{ctype};base64,{b64}"
                    source_type = "web-image"
                    label = f"Unsplash Photo #{seed_id[:6]}"
        except Exception:
            raw_bytes = None

        if not raw_bytes or not data_url:
            data_url, bmp_bytes = _make_procedural_bmp_data_url(seed_entropy, i)
            raw_bytes = bmp_bytes + seed_entropy

        digest = hashlib.sha512(raw_bytes).hexdigest()
        return {
            "id": f"img-{i + 1}-{digest[:8]}",
            "index": i + 1,
            "label": label,
            "source_type": source_type,
            "byte_length": len(raw_bytes),
            "data_url": data_url,
            "sha512": digest,
            "chunks": [digest[j:j + 16] for j in range(0, 128, 16)],
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(count, 8)) as executor:
        items = list(executor.map(_fetch_one_image, range(count)))
    return items


def _fernet():
    if Fernet is None:
        raise RuntimeError("cryptography package is required for password encryption")
    raw = get_secret_key()
    from .hkdf import hkdf_derive
    hkdf_key = base64.urlsafe_b64encode(hkdf_derive(raw.encode(), info=b"openoptout:settings:v1"))
    fernet_primary = Fernet(hkdf_key)

    # Legacy key: padded raw secret (retained for backward-compatible decryption of existing secrets)
    _kb = raw.encode() or b"\0"
    padded = (_kb * (32 // len(_kb) + 1))[:32]
    fernet_legacy = Fernet(base64.urlsafe_b64encode(padded))

    if MultiFernet is not None:
        return MultiFernet([fernet_primary, fernet_legacy])
    return fernet_primary


def encrypt_password(plain: str) -> str:
    if not plain:
        return ""
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_password(enc: str) -> str:
    try:
        return _fernet().decrypt(enc.encode()).decode()
    except Exception:
        return ""

