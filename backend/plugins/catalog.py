"""
OpenOptOut Community Catalog & Marketplace Client.

Implements Roadmap Item 8 / Proposal catalog-design.md:
- Fetches and caches canonical index.json from the OpenOptOut Community Marketplace
  (default: https://rlnunez.github.io/openoptout-market/index.json).
- Supports ETag / If-None-Match HTTP caching with a 4-hour TTL.
- Enforces strict SHA-256 integrity verification on all package downloads.
- Path-traversal resistant archive extraction, static code inspection, and permission review.
- Enforces Marketplace Invariant 1 (Declarative Pure Data: zero executable code in broker add-ons).
- Decorates catalog listings with installation and update status.
"""

import hashlib
import json
import logging
import os
import re
import shutil
import stat
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from typing import Any, Dict, List, Optional, Tuple

from . import layout
from .code_inspector import inspect_plugin_code, summarize
from .permissions import PLUGIN_TYPES, PluginManifest
from ..core.dns_guard import safe_dns_context
from ..core.version import get_version

log = logging.getLogger(__name__)

class CatalogError(Exception):
    """Catalog operational or validation exception with an associated HTTP status code."""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

DEFAULT_CATALOG_URL = "https://rlnunez.github.io/openoptout-market/index.json"
FALLBACK_CATALOG_URL = "https://raw.githubusercontent.com/rlnunez/openoptout-market/main/public/index.json"
DEFAULT_CATALOG_CHECK_HOURS = 12
DEFAULT_INSTALLED_CHECK_HOURS = 24

DEFAULT_UPDATE_SETTINGS = {
    "catalog_check_hours": DEFAULT_CATALOG_CHECK_HOURS,
    "installed_update_check_hours": DEFAULT_INSTALLED_CHECK_HOURS,
    "allow_prereleases": False,
}

MAX_PACKAGE_DOWNLOAD_BYTES = 50 * 1024 * 1024   # 50 MB
MAX_PACKAGE_EXTRACTED_BYTES = 200 * 1024 * 1024 # 200 MB
MAX_PACKAGE_FILES = 5000

PROHIBITED_DATA_EXTENSIONS = frozenset([
    ".py", ".pyc", ".pyo", ".pyd", ".sh", ".bash", ".zsh", ".exe", ".bin",
    ".so", ".dylib", ".dll", ".bat", ".cmd", ".vbs", ".ps1", ".jar"
])


def get_update_settings() -> dict:
    """Retrieve marketplace discovery and developer repo update settings."""
    from ..core.settings_store import load_settings
    settings = load_settings()
    cfg = settings.get("plugins_updates", {})
    return {
        "catalog_check_hours": max(1, min(168, int(cfg.get("catalog_check_hours", DEFAULT_CATALOG_CHECK_HOURS)))),
        "installed_update_check_hours": max(1, min(168, int(cfg.get("installed_update_check_hours", DEFAULT_INSTALLED_CHECK_HOURS)))),
        "allow_prereleases": bool(cfg.get("allow_prereleases", False)),
    }


def save_update_settings(new_settings: dict) -> dict:
    """Save marketplace discovery and developer repo update settings."""
    from ..core.settings_store import load_settings, save_settings
    settings = load_settings()
    current = settings.get("plugins_updates", {})
    if "catalog_check_hours" in new_settings and new_settings["catalog_check_hours"] is not None:
        current["catalog_check_hours"] = max(1, min(168, int(new_settings["catalog_check_hours"])))
    if "installed_update_check_hours" in new_settings and new_settings["installed_update_check_hours"] is not None:
        current["installed_update_check_hours"] = max(1, min(168, int(new_settings["installed_update_check_hours"])))
    if "allow_prereleases" in new_settings and new_settings["allow_prereleases"] is not None:
        current["allow_prereleases"] = bool(new_settings["allow_prereleases"])
    settings["plugins_updates"] = current
    save_settings(settings)
    return get_update_settings()


def get_catalog_url() -> str:
    """Resolve configured catalog index URL or default to the community marketplace."""
    from ..core.settings_store import load_settings
    settings = load_settings()
    custom_url = settings.get("catalog", {}).get("url")
    if custom_url and isinstance(custom_url, str) and custom_url.strip():
        return custom_url.strip()
    env_url = os.getenv("OPENOPTOUT_CATALOG_URL")
    if env_url and env_url.strip():
        return env_url.strip()
    return DEFAULT_CATALOG_URL


def get_catalog_cache_path() -> str:
    """Location of the cached catalog index."""
    root = layout.plugins_root()
    try:
        os.makedirs(root, exist_ok=True)
        test_file = os.path.join(root, ".write_test")
        with open(test_file, "w") as f:
            f.write("")
        os.remove(test_file)
        return os.path.join(root, ".catalog_cache.json")
    except (OSError, PermissionError):
        return os.path.join(tempfile.gettempdir(), "openoptout_catalog_cache.json")


def normalize_date_version(v: str) -> str:
    """
    Normalize CalVer / date-based version formats into dot-separated numerical versions.
    Supports:
    - ISO dates: '2026-10-31' -> '2026.10.31'
    - ISO dates with prereleases or patch: '2026-10-31-rc1' -> '2026.10.31-rc1', '2026-10-31.1' -> '2026.10.31.1'
    - Compact dates: '20261031' -> '2026.10.31'
    - Standard semver strings ('1.2.3', 'v1.2.3') are returned unchanged (with 'v' stripped).
    """
    clean = re.sub(r"^[vV]", "", (v or "").strip())
    # Match YYYY-MM-DD pattern at start
    m_iso = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})(.*)$", clean)
    if m_iso:
        y, m, d, rest = m_iso.groups()
        if rest.startswith("-") and not rest.startswith("-0") and not rest[1:2].isdigit():
            return f"{y}.{int(m)}.{int(d)}{rest}"
        elif rest.startswith("."):
            return f"{y}.{int(m)}.{int(d)}{rest}"
        elif rest.startswith("-") and rest[1:].isdigit():
            return f"{y}.{int(m)}.{int(d)}.{rest[1:]}"
        return f"{y}.{int(m)}.{int(d)}{rest}"

    # Match YYYYMMDD compact (8 digits starting with year >= 2000)
    m_compact = re.match(r"^(\d{4})(\d{2})(\d{2})(.*)$", clean)
    if m_compact and int(m_compact.group(1)) >= 2000:
        y, m, d, rest = m_compact.groups()
        return f"{y}.{int(m)}.{int(d)}{rest}"

    return clean


def parse_semver(v: str) -> tuple:
    """
    Parse '1.2.3', 'v1.2.3', date versions ('2026.10.31', '2026-10-31', '20261031'),
    or pre-releases like '1.2.3-rc1' into comparable tuple.
    Follows SemVer 2.0.0 precedence:
    A normal version has higher precedence than a pre-release version with the same
    major, minor, and patch (e.g. 1.0.0-rc1 < 1.0.0).
    However, 1.0.1-rc1 > 1.0.0.
    """
    clean = normalize_date_version(v)
    clean = re.sub(r"^[vV]", "", (clean or "").strip())
    clean = clean.split("+")[0]  # strip build metadata
    prerelease_part = None
    if "-" in clean:
        parts_main, prerelease_part = clean.split("-", 1)
    else:
        parts_main = clean

    nums = []
    for x in parts_main.split("."):
        m = re.match(r"^(\d+)", x)
        nums.append(int(m.group(1)) if m else 0)
    while len(nums) < 4:
        nums.append(0)

    if prerelease_part is None:
        return (nums[0], nums[1], nums[2], nums[3], 1, ())

    pre_tokens = []
    for token in prerelease_part.split("."):
        if token.isdigit():
            pre_tokens.append((0, int(token)))
        else:
            pre_tokens.append((1, token.lower()))
    return (nums[0], nums[1], nums[2], nums[3], 0, tuple(pre_tokens))


def is_prerelease_version(v: str) -> bool:
    """True if string indicates a pre-release version or tag."""
    clean = normalize_date_version(v)
    clean = re.sub(r"^[vV]", "", (clean or "").strip()).split("+")[0]
    if "-" in clean:
        return True
    return bool(re.search(r"(?:alpha|beta|rc|dev|preview)", clean, re.IGNORECASE))


def extract_version_from_tag(tag: str, plugin_id: Optional[str] = None) -> Optional[str]:
    """
    Extract clean SemVer or CalVer (date) version string from a Git tag.
    Supports:
    - Standard SemVer: 'v1.0.2', '1.0.2', 'v1.0.2-rc1'
    - CalVer / dates: '2026.10.31', 'v2026-10-31', '2026-10-31', '20261031', '2026-10-31-rc1'
    - Monorepo prefixed tags: 'whitepages-v1.0.2', 'whitepages-2026-10-31', 'whitepages/v2026.10.31'
    Rejects tags prefixed with other plugin identifiers.
    """
    tag = (tag or "").strip()
    if not tag:
        return None

    # Version pattern: standard semver OR ISO date YYYY-MM-DD OR compact date YYYYMMDD
    ver_pattern = r"(?:\d+\.\d+(?:\.\d+)*(?:-[0-9A-Za-z.-]+)?|\d{4}-\d{1,2}-\d{1,2}(?:-[0-9A-Za-z.-]+|\.\d+)?|\d{8}(?:-[0-9A-Za-z.-]+|\.\d+)?)"

    if plugin_id:
        p_id = plugin_id.lower()
        t_lower = tag.lower()
        prefix_pattern = rf"^{re.escape(p_id)}[-/@]v?({ver_pattern})$"
        m = re.match(prefix_pattern, t_lower)
        if m:
            matched_len = len(tag) - len(m.group(1))
            return tag[matched_len:]

        # Reject tags prefixed by another plugin
        if re.match(rf"^[a-z0-9_-]+[-/@]v?{ver_pattern}$", t_lower):
            return None

    # Standalone / generic tag
    m = re.match(rf"^v?({ver_pattern})$", tag, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def is_newer_version(candidate: str, current: str) -> bool:
    """True if candidate is strictly newer than current according to SemVer."""
    return parse_semver(candidate) > parse_semver(current)


def fetch_remote_catalog(url: str, etag: Optional[str] = None) -> Tuple[Optional[dict], Optional[str], Optional[str]]:
    """
    Fetch catalog index from remote endpoint using safe_dns_context and ETag caching.
    Returns (catalog_data, new_etag, error_message).
    If HTTP 304 (Not Modified), catalog_data is None and error_message is None.
    """
    headers = {
        "User-Agent": f"OpenOptOut/{get_version()} (Marketplace Client)",
        "Accept": "application/json",
    }
    if etag:
        headers["If-None-Match"] = etag

    req = urllib.request.Request(url, headers=headers)
    try:
        with safe_dns_context():
            with urllib.request.urlopen(req, timeout=15) as resp:
                new_etag = resp.headers.get("ETag")
                raw = resp.read()
                data = json.loads(raw.decode("utf-8"))
                if not isinstance(data, dict) or "plugins" not in data:
                    return None, None, "Invalid catalog format: missing 'plugins' list"
                return data, new_etag, None
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return None, etag, None
        return None, None, f"HTTP Error {e.code}: {e.reason}"
    except Exception as e:
        return None, None, f"Network error fetching catalog: {e}"


def get_catalog(
    db: Optional[Any] = None,
    force_refresh: bool = False,
    search: Optional[str] = None,
    category: Optional[str] = None
) -> dict:
    """
    Retrieve available catalog plugins, checking local cache TTL and enriching entries
    with installation status, current versions, and update flags.
    """
    cache_path = get_catalog_cache_path()
    cached: Optional[dict] = None
    cached_etag: Optional[str] = None
    cached_at: float = 0.0

    if os.path.isfile(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                c_data = json.load(f)
                cached = c_data.get("data")
                cached_etag = c_data.get("etag")
                cached_at = c_data.get("cached_at", 0.0)
        except Exception as e:
            log.warning("Could not read catalog cache: %s", e)

    now = time.time()
    catalog_ttl = get_update_settings()["catalog_check_hours"] * 3600
    is_stale = (now - cached_at) > catalog_ttl
    target_url = get_catalog_url()
    catalog_data = cached
    cache_status = "hit"
    offline = False

    if force_refresh or is_stale or not cached:
        remote_data, new_etag, err = fetch_remote_catalog(target_url, etag=cached_etag if not force_refresh else None)
        if err:
            log.warning("Failed to fetch primary catalog at %s: %s", target_url, err)
            # Try fallback raw GitHub URL if primary Pages URL failed
            if target_url == DEFAULT_CATALOG_URL:
                remote_data, new_etag, err_fallback = fetch_remote_catalog(FALLBACK_CATALOG_URL)
                if remote_data:
                    err = None

        if remote_data:
            catalog_data = remote_data
            cache_status = "refreshed"
            try:
                os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "data": catalog_data,
                        "etag": new_etag,
                        "cached_at": now,
                    }, f)
            except Exception as e:
                log.warning("Could not write catalog cache: %s", e)
        elif err:
            if cached:
                cache_status = "offline_stale"
                offline = True
            else:
                catalog_data = {"schema_version": "1.0", "plugins": [], "error": err}
                cache_status = "error"
                offline = True
        else:
            # 304 Not Modified
            cache_status = "not_modified"
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "data": cached,
                        "etag": cached_etag,
                        "cached_at": now,
                    }, f)
            except Exception:
                pass

    plugins_list = list(catalog_data.get("plugins", []) if catalog_data else [])

    # Index installed plugins from DB for fast lookup
    installed_map: Dict[str, InstalledPlugin] = {}
    if db is not None:
        try:
            for row in db.query(InstalledPlugin).all():
                installed_map[row.plugin_id] = row
        except Exception as e:
            log.warning("Could not query InstalledPlugin table: %s", e)

    enriched_plugins = []
    q = (search or "").strip().lower()
    cat_filter = (category or "").strip().lower()

    for p in plugins_list:
        p_id = p.get("id", "")
        p_type = p.get("type", "brokers")

        if cat_filter and cat_filter != "all" and p_type.lower() != cat_filter:
            continue

        if q:
            name_match = q in p.get("name", "").lower()
            desc_match = q in p.get("description", "").lower()
            author_match = q in p.get("author", "").lower()
            id_match = q in p_id.lower()
            if not (name_match or desc_match or author_match or id_match):
                continue

        inst = installed_map.get(p_id)
        is_installed = inst is not None
        inst_ver = inst.version if inst else None
        cat_ver = p.get("version", "1.0.0")
        has_update = is_installed and is_newer_version(cat_ver, inst_ver or "0.0.0")

        item = dict(p)
        item["is_installed"] = is_installed
        item["installed_version"] = inst_ver
        item["has_update"] = has_update
        item["enabled"] = inst.enabled if inst else False
        item["status"] = inst.status if inst else "uninstalled"
        enriched_plugins.append(item)

    # Sort: Updates available first, then Tier 1 curated, then alphabetical
    enriched_plugins.sort(key=lambda x: (not x["has_update"], x.get("tier", 2), x.get("name", "").lower()))

    return {
        "catalog_url": target_url,
        "schema_version": catalog_data.get("schema_version", "1.0") if catalog_data else "1.0",
        "generated_at": catalog_data.get("generated_at") if catalog_data else None,
        "cache_status": cache_status,
        "offline": offline,
        "plugins": enriched_plugins,
        "total_available": len(enriched_plugins),
    }


def _verify_archive_entry(info: zipfile.ZipInfo, p_type: str) -> Optional[str]:
    name = info.filename
    parts = name.split("/")
    if name.startswith("/") or "\\" in name or ".." in parts or (len(name) > 1 and name[1] == ":"):
        return f"unsafe path in zip package: {name!r}"
    if stat.S_ISLNK(info.external_attr >> 16):
        return f"symbolic links are forbidden in catalog packages: {name!r}"

    # Invariant 1: Declarative Pure Data Invariant
    # Data-only types (brokers, themes, languages, letters) must contain zero executable scripts
    is_data_type = p_type in ("brokers", "themes", "languages", "letters") or PLUGIN_TYPES.get(p_type, {}).get("data_only")
    if is_data_type:
        _, ext = os.path.splitext(name.lower())
        if ext in PROHIBITED_DATA_EXTENSIONS:
            return f"Marketplace Invariant Violation: '{p_type}' packages are data-only and may not contain executable '{ext}' files ({name})"

    return None


def download_and_verify_package(url: str, expected_sha256: str, p_type: str) -> Tuple[str, str]:
    """
    Download a package archive to a temp directory and assert SHA-256 integrity.
    Returns (temp_dir, zip_path).
    """
    tmp = tempfile.mkdtemp(prefix="openoptout-pkg-")
    zip_path = os.path.join(tmp, "package.zip")
    hasher = hashlib.sha256()
    size = 0

    headers = {"User-Agent": f"OpenOptOut/{get_version()} (Marketplace Client)"}
    req = urllib.request.Request(url, headers=headers)

    try:
        with safe_dns_context():
            with urllib.request.urlopen(req, timeout=30) as resp:
                with open(zip_path, "wb") as f:
                    while chunk := resp.read(65536):
                        size += len(chunk)
                        if size > MAX_PACKAGE_DOWNLOAD_BYTES:
                            shutil.rmtree(tmp, ignore_errors=True)
                            raise CatalogError(f"Package archive exceeds {MAX_PACKAGE_DOWNLOAD_BYTES // (1024 * 1024)} MB limit", 413)
                        hasher.update(chunk)
                        f.write(chunk)
    except urllib.error.HTTPError as e:
        shutil.rmtree(tmp, ignore_errors=True)
        raise CatalogError(f"Failed to download package: {e.reason}", e.code)
    except CatalogError:
        raise
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        raise CatalogError(f"Network error downloading package: {e}", 502)

    actual_sha = hasher.hexdigest().lower()
    expected_clean = (expected_sha256 or "").strip().lower()
    if expected_clean and actual_sha != expected_clean:
        shutil.rmtree(tmp, ignore_errors=True)
        raise CatalogError(f"SHA-256 integrity check failed. Expected {expected_clean}, calculated {actual_sha}", 400)

    return tmp, zip_path


def extract_package_safely(zip_path: str, extract_to: str, p_type: str) -> str:
    """
    Extract package with path traversal and Invariant 1 checks.
    Returns path to the directory containing manifest.json.
    """
    try:
        with zipfile.ZipFile(zip_path) as z:
            infos = z.infolist()
            if len(infos) > MAX_PACKAGE_FILES:
                raise CatalogError(f"Package has more than {MAX_PACKAGE_FILES} files", 400)
            if sum(i.file_size for i in infos) > MAX_PACKAGE_EXTRACTED_BYTES:
                raise CatalogError("Package exceeds maximum extracted size limit", 400)

            for info in infos:
                problem = _verify_archive_entry(info, p_type)
                if problem:
                    raise CatalogError(problem, 400)

            z.extractall(extract_to)
    except zipfile.BadZipFile:
        raise CatalogError("Package archive could not be parsed as a valid zip file", 400)

    # Locate manifest.json: at root or in top-level directory
    manifest_dir = None
    for root, dirs, files in os.walk(extract_to):
        dirs.sort()
        if "manifest.json" in files:
            manifest_dir = root
            break

    if not manifest_dir:
        raise CatalogError("Package does not contain a manifest.json file", 400)

    return manifest_dir


def install_from_catalog(
    plugin_id: str,
    db: Any,
    current_user: Any = None,
    is_update: bool = False
) -> dict:
    """
    Download, verify SHA-256 checksum, inspect, and install/update a plugin from the community catalog.
    Installed plugins are registered in status='stopped' and enabled=False until approved by admin.
    """
    try:
        from ..models.database import InstalledPlugin, PluginAuditLog
    except ImportError:
        InstalledPlugin = None
        PluginAuditLog = None

    cat = get_catalog(db=db, force_refresh=False)
    entry = next((p for p in cat.get("plugins", []) if p.get("id") == plugin_id), None)
    if not entry:
        raise CatalogError(f"Plugin '{plugin_id}' not found in community catalog", 404)

    archive_url = entry.get("archive_url")
    if not archive_url:
        raise CatalogError(f"Plugin '{plugin_id}' does not specify a download archive_url", 400)

    sha256 = entry.get("sha256", "")
    p_type = entry.get("type", "brokers")
    min_core = entry.get("min_core_version")
    if min_core and is_newer_version(min_core, get_version()):
        raise CatalogError(f"Plugin requires OpenOptOut version {min_core} or higher (current: {get_version()})", 400)

    # 1. Download & verify SHA-256
    tmp_dir, zip_path = download_and_verify_package(archive_url, sha256, p_type)

    try:
        extract_dir = os.path.join(tmp_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        manifest_dir = extract_package_safely(zip_path, extract_dir, p_type)

        manifest = layout.read_manifest(manifest_dir)
        if manifest.id != plugin_id:
            raise CatalogError(f"Package manifest ID '{manifest.id}' does not match catalog ID '{plugin_id}'", 400)

        errs = manifest.validate() + layout.content_errors(manifest_dir, manifest)
        if errs:
            raise CatalogError(f"Package manifest validation failed: {'; '.join(errs)}", 400)

        # 2. Type-specific inspection
        if manifest.effective_type == "brokers":
            from .broker_addon import validate_broker_spec_file
            spec_file = manifest.spec_file or "spec.json"
            spec, spec_errs = validate_broker_spec_file(manifest_dir, spec_file)
            if spec_errs or not spec:
                raise CatalogError(f"Broker spec validation failed: {'; '.join(spec_errs)}", 400)

        # 3. Static code inspection for executable plugins
        if not PLUGIN_TYPES.get(manifest.effective_type, {}).get("data_only"):
            insp = summarize(inspect_plugin_code(manifest_dir, manifest))
            if insp.get("error_count", 0) > 0:
                reasons = [f["reason"] for f in insp.get("findings", []) if f.get("severity") == "error"]
                raise CatalogError(f"Static code inspection failed: {'; '.join(reasons)}", 400)

        # 4. Resolve destination
        root = layout.plugins_root()
        target_dir = layout.install_dir(root, manifest)
        existing_row = None
        if db is not None and InstalledPlugin is not None:
            existing_row = db.query(InstalledPlugin).filter(InstalledPlugin.plugin_id == plugin_id).first()

        if is_update and not existing_row:
            raise CatalogError(f"Cannot update '{plugin_id}': not currently installed", 400)

        if not is_update and existing_row:
            raise CatalogError(f"Plugin '{plugin_id}' is already installed (v{existing_row.version})", 409)

        # 5. Move files into place
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)
        os.makedirs(os.path.dirname(os.path.abspath(target_dir)), exist_ok=True)
        shutil.move(manifest_dir, target_dir)

        # 6. Database record
        actor_id = getattr(current_user, "id", None)
        code_hash = layout.dir_hash(target_dir)

        if is_update:
            if existing_row:
                existing_row.version = manifest.version
                existing_row.name = manifest.name
                existing_row.description = manifest.description
                existing_row.author = manifest.author
                existing_row.manifest_json = json.dumps(manifest.to_dict())
                existing_row.code_hash = code_hash
                if db is not None:
                    db.commit()
            if db is not None and PluginAuditLog is not None:
                db.add(PluginAuditLog(
                    plugin_id=plugin_id,
                    action="catalog_update",
                    actor_id=actor_id,
                    detail=f"Updated to version {manifest.version} from catalog ({archive_url})"
                ))
                db.commit()
            return {
                "success": True,
                "action": "update",
                "plugin_id": plugin_id,
                "version": manifest.version,
                "message": f"Successfully updated '{manifest.name}' to version {manifest.version}.",
            }
        else:
            if db is not None and InstalledPlugin is not None:
                row = InstalledPlugin(
                    plugin_id=manifest.id,
                    name=manifest.name,
                    version=manifest.version,
                    author=manifest.author,
                    description=manifest.description,
                    manifest_json=json.dumps(manifest.to_dict()),
                    granted_permissions="[]",
                    enabled=False,
                    install_path=target_dir,
                    status="stopped",
                    code_hash=code_hash,
                )
                db.add(row)
                db.commit()
            if db is not None and PluginAuditLog is not None:
                db.add(PluginAuditLog(
                    plugin_id=plugin_id,
                    action="catalog_install",
                    actor_id=actor_id,
                    detail=f"Installed version {manifest.version} from catalog ({archive_url})"
                ))
                db.commit()
            return {
                "success": True,
                "action": "install",
                "plugin_id": plugin_id,
                "version": manifest.version,
                "message": f"Successfully installed '{manifest.name}' v{manifest.version}. Enable it from the Installed tab.",
            }

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Developer Git Repository Update Checking ──────────────────────────────────

def get_plugin_updates_cache_path() -> str:
    """Location of the cached developer repo updates."""
    root = layout.plugins_root()
    try:
        os.makedirs(root, exist_ok=True)
        return os.path.join(root, ".plugin_updates_cache.json")
    except (OSError, PermissionError):
        return os.path.join(tempfile.gettempdir(), "openoptout_plugin_updates_cache.json")


def fetch_github_repo_releases(repo_slug: str, etag: Optional[str] = None) -> Tuple[Optional[List[dict]], Optional[str], Optional[str]]:
    """
    Fetch releases (or tags fallback) from a GitHub repository using safe_dns_context and ETag caching.
    Returns (releases_list, new_etag, error_message).
    If HTTP 304 (Not Modified), releases_list is None.
    """
    slug = re.sub(r"^https?://github\.com/", "", (repo_slug or "").strip().rstrip("/"))
    slug = re.sub(r"\.git$", "", slug)
    parts = slug.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None, None, f"Invalid GitHub repository slug: {repo_slug!r}"

    headers = {
        "User-Agent": f"OpenOptOut/{get_version()} (Plugin Updater)",
        "Accept": "application/vnd.github.v3+json",
    }
    github_token = os.getenv("GITHUB_TOKEN")
    if github_token and github_token.strip():
        headers["Authorization"] = f"Bearer {github_token.strip()}"

    if etag:
        headers["If-None-Match"] = etag

    url = f"https://api.github.com/repos/{slug}/releases?per_page=30"
    req = urllib.request.Request(url, headers=headers)
    try:
        with safe_dns_context():
            with urllib.request.urlopen(req, timeout=15) as resp:
                new_etag = resp.headers.get("ETag")
                raw = resp.read()
                data = json.loads(raw.decode("utf-8"))
                if isinstance(data, list) and len(data) > 0:
                    return data, new_etag, None
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return None, etag, None
        if e.code not in (404, 403):
            return None, None, f"HTTP Error {e.code} fetching releases: {e.reason}"
    except Exception as e:
        return None, None, f"Network error fetching releases: {e}"

    # Fallback to tags API if releases are empty or 404
    tags_url = f"https://api.github.com/repos/{slug}/tags?per_page=30"
    req_tags = urllib.request.Request(tags_url, headers=headers)
    try:
        with safe_dns_context():
            with urllib.request.urlopen(req_tags, timeout=15) as resp:
                new_etag = resp.headers.get("ETag")
                raw = resp.read()
                tags_data = json.loads(raw.decode("utf-8"))
                if isinstance(tags_data, list):
                    synth_releases = []
                    for t in tags_data:
                        t_name = t.get("name", "")
                        synth_releases.append({
                            "tag_name": t_name,
                            "name": t_name,
                            "prerelease": is_prerelease_version(t_name),
                            "html_url": f"https://github.com/{slug}/releases/tag/{t_name}",
                        })
                    return synth_releases, new_etag, None
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return None, etag, None
        return None, None, f"HTTP Error {e.code} fetching tags: {e.reason}"
    except Exception as e:
        return None, None, f"Network error fetching tags: {e}"

    return [], None, None


def check_installed_plugins_updates(db: Optional[Any] = None, force_check: bool = False) -> Dict[str, dict]:
    """
    Check installed plugins directly against their developer's Git repositories for updates.
    Evaluates latest tags/releases, handles pre-releases according to admin settings,
    and batches GitHub API requests by repository slug.
    Returns map of plugin_id -> update_dict.
    """
    try:
        from ..models.database import InstalledPlugin
    except ImportError:
        InstalledPlugin = None

    settings = get_update_settings()
    allow_prereleases = settings["allow_prereleases"]
    check_interval = settings["installed_update_check_hours"] * 3600
    cache_path = get_plugin_updates_cache_path()
    now = time.time()

    cached_data: dict = {}
    if os.path.isfile(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
        except Exception as e:
            log.warning("Could not read plugin updates cache: %s", e)

    last_checked = cached_data.get("checked_at", 0.0)
    if not force_check and (now - last_checked) < check_interval and "updates" in cached_data:
        return cached_data.get("updates", {})

    installed_rows = []
    if db is not None and InstalledPlugin is not None:
        try:
            installed_rows = db.query(InstalledPlugin).all()
        except Exception as e:
            log.warning("Could not query InstalledPlugin: %s", e)
    elif InstalledPlugin is not None:
        try:
            from ..models.database import SessionLocal
            session = SessionLocal()
            try:
                installed_rows = session.query(InstalledPlugin).all()
            finally:
                session.close()
        except Exception as e:
            log.warning("Could not load SessionLocal for InstalledPlugin: %s", e)

    if not installed_rows:
        return {}

    # Build catalog map for repo resolution fallback
    cat = get_catalog(db=db, force_refresh=False)
    cat_map = {p.get("id"): p for p in cat.get("plugins", [])}

    repo_groups: Dict[str, List[Tuple[str, str, str]]] = {}
    plugin_repo_map: Dict[str, str] = {}
    updates: Dict[str, dict] = {}

    for row in installed_rows:
        p_id = row.plugin_id
        current_ver = row.version or "1.0.0"
        m_data = {}
        if row.manifest_json:
            try:
                m_data = json.loads(row.manifest_json)
            except Exception:
                pass

        repo = (m_data.get("repo") or m_data.get("repository") or "").strip()
        if not repo and p_id in cat_map:
            repo = (cat_map[p_id].get("repo") or "").strip()

        if not repo:
            src = m_data.get("source") or m_data.get("url") or ""
            m_gh = re.search(r"github\.com/([^/]+/[^/#?]+)", src)
            if m_gh:
                repo = m_gh.group(1).rstrip(".git")

        if repo:
            repo_slug = re.sub(r"^https?://github\.com/", "", repo).rstrip("/").rstrip(".git")
            plugin_repo_map[p_id] = repo_slug
            repo_groups.setdefault(repo_slug, []).append((p_id, row.name, current_ver))
        else:
            updates[p_id] = {
                "has_update": False,
                "current_version": current_ver,
                "latest_version": current_ver,
                "is_prerelease": False,
                "release_url": None,
                "repo": None,
                "checked_at": now,
            }

    repos_cache = cached_data.get("repos", {})

    for repo_slug, plugins in repo_groups.items():
        prev_repo_info = repos_cache.get(repo_slug, {})
        cached_etag = prev_repo_info.get("etag") if not force_check else None
        releases, new_etag, err = fetch_github_repo_releases(repo_slug, etag=cached_etag)

        if err:
            log.warning("Failed to fetch releases for %s: %s", repo_slug, err)
            releases = prev_repo_info.get("releases", [])
        elif releases is None:
            # 304 Not Modified
            releases = prev_repo_info.get("releases", [])
        else:
            repos_cache[repo_slug] = {
                "etag": new_etag,
                "releases": releases,
                "fetched_at": now,
            }

        for p_id, p_name, current_ver in plugins:
            candidates = []
            for rel in (releases or []):
                tag_name = rel.get("tag_name") or rel.get("name") or ""
                ver_str = extract_version_from_tag(tag_name, plugin_id=p_id)
                if not ver_str:
                    continue

                is_pre = bool(rel.get("prerelease")) or is_prerelease_version(ver_str)
                if is_pre and not allow_prereleases:
                    continue

                try:
                    sem_tuple = parse_semver(ver_str)
                    candidates.append((sem_tuple, ver_str, is_pre, rel.get("html_url")))
                except Exception:
                    continue

            candidates.sort(key=lambda c: c[0], reverse=True)

            if candidates and candidates[0][0] > parse_semver(current_ver):
                _, latest_ver, is_pre, rel_url = candidates[0]
                updates[p_id] = {
                    "has_update": True,
                    "current_version": current_ver,
                    "latest_version": latest_ver,
                    "is_prerelease": is_pre,
                    "release_url": rel_url,
                    "repo": repo_slug,
                    "checked_at": now,
                }
            else:
                updates[p_id] = {
                    "has_update": False,
                    "current_version": current_ver,
                    "latest_version": current_ver,
                    "is_prerelease": False,
                    "release_url": None,
                    "repo": repo_slug,
                    "checked_at": now,
                }

    save_data = {
        "checked_at": now,
        "allow_prereleases": allow_prereleases,
        "repos": repos_cache,
        "updates": updates,
    }
    try:
        os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(save_data, f, indent=2)
    except Exception as e:
        log.warning("Could not write plugin updates cache: %s", e)

    return updates


def get_cached_installed_updates() -> Dict[str, dict]:
    """Retrieve cached update information for installed plugins."""
    cache_path = get_plugin_updates_cache_path()
    if os.path.isfile(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("updates", {})
        except Exception:
            pass
    return {}


def run_periodic_plugin_checks():
    """
    Periodic job invoked by the background scheduler.
    1. Checks the community marketplace catalog for new plugins if catalog_check_hours have elapsed.
    2. Checks developer Git repositories of installed plugins for updates if installed_update_check_hours have elapsed.
    """
    settings = get_update_settings()
    now = time.time()

    # 1. Catalog discovery check
    cat_path = get_catalog_cache_path()
    last_cat_check = 0.0
    if os.path.isfile(cat_path):
        try:
            with open(cat_path, "r", encoding="utf-8") as f:
                c_data = json.load(f)
                last_cat_check = c_data.get("cached_at", 0.0)
        except Exception:
            pass

    cat_interval = settings["catalog_check_hours"] * 3600
    if (now - last_cat_check) >= cat_interval:
        try:
            log.info("Running scheduled marketplace catalog discovery check (interval %dh)", settings["catalog_check_hours"])
            get_catalog(force_refresh=True)
        except Exception as e:
            log.warning("Scheduled catalog refresh error: %s", e)

    # 2. Installed plugins developer repo check
    updates_path = get_plugin_updates_cache_path()
    last_inst_check = 0.0
    if os.path.isfile(updates_path):
        try:
            with open(updates_path, "r", encoding="utf-8") as f:
                u_data = json.load(f)
                last_inst_check = u_data.get("checked_at", 0.0)
        except Exception:
            pass

    inst_interval = settings["installed_update_check_hours"] * 3600
    if (now - last_inst_check) >= inst_interval:
        try:
            from ..models.database import SessionLocal
            db = SessionLocal()
            try:
                log.info("Running scheduled installed plugin update check against developer repos (interval %dh)", settings["installed_update_check_hours"])
                check_installed_plugins_updates(db=db, force_check=True)
            finally:
                db.close()
        except Exception as e:
            log.warning("Scheduled installed plugin update check error: %s", e)


def apply_pending_plugin_updates(
    db: Any,
    current_user: Any = None
) -> dict:
    """
    Check for pending plugin updates and apply them automatically.
    Intended to be called during scheduled maintenance windows when apply_plugin_updates is enabled.
    Updates are recorded in PluginAuditLog with action='maintenance_update'.
    """
    try:
        from ..models.database import InstalledPlugin, PluginAuditLog
    except ImportError:
        InstalledPlugin = None
        PluginAuditLog = None

    if db is None or InstalledPlugin is None:
        return {"applied": [], "failed": [], "skipped": []}

    installed = db.query(InstalledPlugin).all()
    if not installed:
        return {"applied": [], "failed": [], "skipped": []}

    # Retrieve current update status against developer repos and catalog
    updates = check_installed_plugins_updates(db=db, force_check=True)
    applied = []
    failed = []
    skipped = []

    actor_id = getattr(current_user, "id", None)

    for row in installed:
        p_id = row.plugin_id
        u_info = updates.get(p_id, {})
        if not u_info.get("has_update"):
            skipped.append(p_id)
            continue

        target_ver = u_info.get("latest_version")
        try:
            log.info("Maintenance window auto-updating plugin '%s' -> v%s", p_id, target_ver)
            res = install_from_catalog(p_id, db=db, current_user=current_user, is_update=True)
            if PluginAuditLog is not None:
                db.add(PluginAuditLog(
                    plugin_id=p_id,
                    action="maintenance_update",
                    actor_id=actor_id,
                    detail=f"Automated update to v{res.get('version', target_ver)} during scheduled maintenance window"
                ))
                db.commit()
            applied.append({
                "plugin_id": p_id,
                "version": res.get("version", target_ver),
                "name": row.name,
            })
        except Exception as e:
            log.warning("Failed to auto-update plugin '%s' in maintenance window: %s", p_id, e)
            if PluginAuditLog is not None:
                try:
                    db.add(PluginAuditLog(
                        plugin_id=p_id,
                        action="maintenance_update_failed",
                        actor_id=actor_id,
                        detail=f"Failed to update to v{target_ver} during maintenance window: {e}"
                    ))
                    db.commit()
                except Exception:
                    pass
            failed.append({
                "plugin_id": p_id,
                "target_version": target_ver,
                "error": str(e),
            })

    return {
        "applied": applied,
        "failed": failed,
        "skipped": skipped,
    }


