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
CATALOG_TTL_SECONDS = 14400  # 4 hours

MAX_PACKAGE_DOWNLOAD_BYTES = 50 * 1024 * 1024   # 50 MB
MAX_PACKAGE_EXTRACTED_BYTES = 200 * 1024 * 1024 # 200 MB
MAX_PACKAGE_FILES = 5000

PROHIBITED_DATA_EXTENSIONS = frozenset([
    ".py", ".pyc", ".pyo", ".pyd", ".sh", ".bash", ".zsh", ".exe", ".bin",
    ".so", ".dylib", ".dll", ".bat", ".cmd", ".vbs", ".ps1", ".jar"
])


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


def parse_semver(v: str) -> tuple:
    """Parse '1.2.3' or 'v1.2.3' into integer tuple for version comparison."""
    clean = re.sub(r"^[vV]", "", (v or "").strip())
    parts = []
    for x in clean.split("."):
        m = re.match(r"^(\d+)", x)
        parts.append(int(m.group(1)) if m else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


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
    is_stale = (now - cached_at) > CATALOG_TTL_SECONDS
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
