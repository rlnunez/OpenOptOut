"""
Encrypted backups, kept locally and copied to the places an admin chooses.

What a backup holds (one .oobackup file):
  * the database: a consistent copy of the SQLite file (still SQLCipher-
    encrypted), or a pg_dump for PostgreSQL
  * the settings file (OAuth tokens and passwords inside it stay encrypted)
  * installed plugins (built-in ones are skipped; they come with the app)
  * the keys needed to read all of that on a new server (SECRET_KEY,
    DB_ENCRYPTION_KEY, FIELD_ENCRYPTION_KEY), so a restore needs only the file
    and the backup passphrase

How it's protected: the whole bundle is encrypted with AES-256-GCM, using a
key derived from the backup passphrase with scrypt. It's written in 4 MiB
frames, each authenticated with its position and whether it's the last one,
so a truncated, reordered or altered file is refused. Without the passphrase
nobody (including whoever stores the file) can read it. Lose the passphrase
and the backups can't be restored.

Where it goes (any number of destinations, each tested before saving):
  folder     a local folder or a mounted network drive (NFS / SMB)
  sftp       an SFTP server (password or private key; host key pinned)
  s3         S3-compatible storage: Amazon S3, Google Cloud Storage (HMAC keys),
             Backblaze B2, Wasabi, MinIO...
  gdrive     Google Drive (an "OpenOptOut backups" folder; drive.file access only)
  onedrive   OneDrive (the app's own folder)
  dropbox    Dropbox (the app's own folder)

Each destination keeps the newest `keep` backups and deletes older ones that
OpenOptOut made. Runs on a schedule (daily or weekly) and on demand.

Restore (server stopped):
    python -m app.core.backup restore FILE.oobackup --to /data
"""

import base64
import hashlib
import io
import json
import logging
import os
import secrets
import shutil
import struct
import tarfile
import tempfile
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

MAGIC = b"OOBACKUP1\n"
FRAME = 4 * 1024 * 1024
SCRYPT = {"n": 2 ** 15, "r": 8, "p": 1}
DEFAULT_KDF = "scrypt"
PBKDF2_ITERATIONS = 210_000
PREFIX = "openoptout-backup-"
SUFFIX = ".oobackup"
DEFAULTS = {"enabled": False, "schedule": "daily", "hour": 3, "keep": 14, "destinations": [],
            "include_plugins": True}


def settings_of(cfg: dict) -> dict:
    out = json.loads(json.dumps(DEFAULTS))
    out.update((cfg or {}).get("backups") or {})
    return out


# ── Encryption (NIST SP 800-38D AES-GCM + NIST SP 800-132 PBKDF2 / scrypt) ───

def _key(passphrase: str, salt: bytes, kdf: dict) -> bytes:
    kdf_type = (kdf or {}).get("kdf", "scrypt")
    if kdf_type in ("pbkdf2", "pbkdf2_sha256"):
        iterations = (kdf or {}).get("iterations", PBKDF2_ITERATIONS)
        return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, iterations, dklen=32)
    return hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, n=kdf.get("n", SCRYPT["n"]), r=kdf.get("r", SCRYPT["r"]), p=kdf.get("p", SCRYPT["p"]),
                          maxmem=128 * 1024 * 1024, dklen=32)


def encrypt_file(src: str, dst: str, passphrase: str, kdf_type: Optional[str] = None) -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not passphrase or len(passphrase) < 12:
        raise ValueError("The backup passphrase must be at least 12 characters.")
    selected_kdf = kdf_type or DEFAULT_KDF
    salt, prefix = secrets.token_bytes(16), secrets.token_bytes(8)
    if selected_kdf in ("pbkdf2", "pbkdf2_sha256"):
        kdf_info = {"kdf": "pbkdf2_sha256", "iterations": PBKDF2_ITERATIONS}
    else:
        kdf_info = {"kdf": "scrypt", **SCRYPT}
    header = {**kdf_info, "salt": base64.b64encode(salt).decode(), "frame": FRAME,
              "created": datetime.utcnow().isoformat() + "Z"}
    hdr = json.dumps(header, sort_keys=True).encode() + b"\n"
    aes = AESGCM(_key(passphrase, salt, header))
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        fo.write(MAGIC + hdr)
        idx = 0
        chunk = fi.read(FRAME)
        while True:
            nxt = fi.read(FRAME)
            last = not nxt
            nonce = prefix + struct.pack(">I", idx)
            aad = MAGIC + hdr + struct.pack(">I?", idx, last)
            ct = aes.encrypt(nonce, chunk, aad)
            fo.write(struct.pack(">I", len(ct)) + nonce + ct)
            if last:
                break
            chunk, idx = nxt, idx + 1


def decrypt_file(src: str, dst: str, passphrase: str) -> dict:
    """Decrypt to dst. Raises ValueError on a wrong passphrase or a damaged file."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.exceptions import InvalidTag
    with open(src, "rb") as fi:
        if fi.read(len(MAGIC)) != MAGIC:
            raise ValueError("This isn't an OpenOptOut backup file.")
        hdr = fi.readline()
        header = json.loads(hdr)
        aes = AESGCM(_key(passphrase, base64.b64decode(header["salt"]), header))
        idx, done = 0, False
        with open(dst, "wb") as fo:
            while True:
                lb = fi.read(4)
                if not lb:
                    break
                (n,) = struct.unpack(">I", lb)
                nonce = fi.read(12)
                ct = fi.read(n)
                if len(ct) != n:
                    raise ValueError("The backup file is cut short.")
                if struct.unpack(">I", nonce[8:])[0] != idx:
                    raise ValueError("The backup file's parts are out of order.")
                last = fi.peek(1)[:1] == b"" if hasattr(fi, "peek") else False
                try:
                    pt = aes.decrypt(nonce, ct, MAGIC + hdr + struct.pack(">I?", idx, last))
                except InvalidTag:
                    if idx == 0:
                        raise ValueError("Wrong passphrase, or the file was changed.")
                    raise ValueError("The backup file was changed or damaged.")
                fo.write(pt)
                done = last
                idx += 1
        if not done:
            raise ValueError("The backup file is cut short.")
    return header


# ── What goes in ──────────────────────────────────────────────────────────────

def _sqlite_snapshot(dest: str) -> str:
    """Consistent copy of the live SQLite file (pages stay SQLCipher-encrypted)."""
    from ..models.database import engine, DATABASE_URL
    from .encryption import extract_sqlite_path
    path = extract_sqlite_path(DATABASE_URL)
    if not path or not os.path.isfile(path):
        raise RuntimeError("database file not found")
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        try:
            cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass
        cur.execute("BEGIN IMMEDIATE")      # writers wait while we copy
        try:
            shutil.copyfile(path, dest)
        finally:
            raw.rollback()
    finally:
        raw.close()
    return os.path.basename(path)


def _pg_dump(dest: str) -> None:
    import subprocess
    from ..models.database import DATABASE_URL
    if not shutil.which("pg_dump"):
        raise RuntimeError("pg_dump isn't installed in this container")
    subprocess.run(["pg_dump", "--format=custom", "--file", dest, DATABASE_URL], check=True, timeout=3600,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def build_bundle(work: str, cfg: dict, include_db: bool = True) -> str:
    """Create the plain tar.gz bundle in `work`; returns its path."""
    from .settings_store import SETTINGS_FILE
    from ..models.database import DATABASE_URL
    s = settings_of(cfg)
    stage = os.path.join(work, "stage")
    os.makedirs(stage, exist_ok=True)
    manifest = {"made_by": "OpenOptOut", "created": datetime.utcnow().isoformat() + "Z", "parts": []}
    try:
        from .version import version_string
        manifest["version"] = version_string()
    except Exception:
        pass
    if include_db:
        if DATABASE_URL.startswith("sqlite"):
            name = _sqlite_snapshot(os.path.join(stage, "database.sqlite"))
            manifest["parts"].append({"part": "database", "file": "database.sqlite", "kind": "sqlite", "name": name})
        else:
            _pg_dump(os.path.join(stage, "database.pgdump"))
            manifest["parts"].append({"part": "database", "file": "database.pgdump", "kind": "pg_dump"})
    if os.path.isfile(SETTINGS_FILE):
        shutil.copyfile(SETTINGS_FILE, os.path.join(stage, "settings.json"))
        manifest["parts"].append({"part": "settings", "file": "settings.json"})
    if s.get("include_plugins", True):
        try:
            from ..plugins import layout
            root = layout.plugins_root()
            if os.path.isdir(root):
                def skip(d, names):
                    return [n for n in names if layout.is_bundled_copy(os.path.join(d, n))
                            or n in ("__pycache__", ".sock")]
                shutil.copytree(root, os.path.join(stage, "plugins"), ignore=skip, symlinks=False)
                manifest["parts"].append({"part": "plugins", "file": "plugins/"})
        except Exception as e:
            log.info("plugins not included in backup: %s", e)
    keys = {k: os.getenv(k) for k in ("SECRET_KEY", "DB_ENCRYPTION_KEY", "FIELD_ENCRYPTION_KEY") if os.getenv(k)}
    with open(os.path.join(stage, "keys.json"), "w") as f:
        json.dump(keys, f)
    manifest["parts"].append({"part": "keys", "file": "keys.json", "names": sorted(keys)})
    with open(os.path.join(stage, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    out = os.path.join(work, "bundle.tar.gz")
    with tarfile.open(out, "w:gz") as tar:
        tar.add(stage, arcname="openoptout-backup")
    shutil.rmtree(stage, ignore_errors=True)
    return out


# ── Destinations ──────────────────────────────────────────────────────────────

class Destination:
    kind = ""

    def __init__(self, conf: dict, cfg: dict):
        self.conf, self.cfg = conf, cfg

    def upload(self, path: str, name: str) -> None: ...
    def names(self) -> list: ...
    def delete(self, name: str) -> None: ...

    def test(self) -> None:
        """Write, list and delete a tiny file."""
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        tmp.write(b"OpenOptOut backup test\n"); tmp.close()
        name = f"{PREFIX}test-{secrets.token_hex(4)}.txt"
        try:
            self.upload(tmp.name, name)
            if name not in self.names(include_tests=True):
                raise RuntimeError("the test file didn't show up")
            self.delete(name)
        finally:
            os.unlink(tmp.name)


class FolderDest(Destination):
    kind = "folder"

    def _dir(self):
        d = self.conf.get("path") or ""
        if not d or not os.path.isabs(d):
            raise RuntimeError("enter the full path of the folder")
        os.makedirs(d, exist_ok=True)
        return d

    def upload(self, path, name):
        d = self._dir()
        tmp = os.path.join(d, "." + name + ".part")
        shutil.copyfile(path, tmp)
        os.replace(tmp, os.path.join(d, name))

    def names(self, include_tests=False):
        return sorted(n for n in os.listdir(self._dir()) if n.startswith(PREFIX)
                      and (n.endswith(SUFFIX) or include_tests))

    def delete(self, name):
        os.remove(os.path.join(self._dir(), os.path.basename(name)))


class SFTPDest(Destination):
    kind = "sftp"

    def _client(self):
        try:
            import paramiko
        except ImportError:
            raise RuntimeError("SFTP needs the paramiko package (included in the Docker image)")
        from .oauth_engine import _decrypt
        c = self.conf
        t = paramiko.Transport((c["host"], int(c.get("port") or 22)))
        t.start_client(timeout=20)
        key = t.get_remote_server_key()
        fp = "SHA256:" + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")
        pinned = c.get("host_key")
        if pinned and pinned != fp:
            t.close()
            raise RuntimeError(f"the server's identity changed (expected {pinned}, got {fp}); "
                               "if that's expected, clear the saved host key")
        self.conf["host_key_seen"] = fp
        pw = _decrypt(c["password_enc"]) if c.get("password_enc") else None
        pk = None
        if c.get("private_key_enc"):
            pk_text = _decrypt(c["private_key_enc"])
            for cls in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
                try:
                    pk = cls.from_private_key(io.StringIO(pk_text)); break
                except Exception:
                    continue
        t.auth_password(c["username"], pw) if pk is None else t.auth_publickey(c["username"], pk)
        return t, paramiko.SFTPClient.from_transport(t)

    def _dir(self):
        return (self.conf.get("path") or ".").rstrip("/") or "/"

    def upload(self, path, name):
        t, sftp = self._client()
        try:
            try:
                sftp.stat(self._dir())
            except IOError:
                sftp.mkdir(self._dir())
            tmp = f"{self._dir()}/.{name}.part"
            sftp.put(path, tmp)
            try:
                sftp.posix_rename(tmp, f"{self._dir()}/{name}")
            except Exception:
                sftp.rename(tmp, f"{self._dir()}/{name}")
        finally:
            sftp.close(); t.close()

    def names(self, include_tests=False):
        t, sftp = self._client()
        try:
            return sorted(n for n in sftp.listdir(self._dir()) if n.startswith(PREFIX)
                          and (n.endswith(SUFFIX) or include_tests))
        finally:
            sftp.close(); t.close()

    def delete(self, name):
        t, sftp = self._client()
        try:
            sftp.remove(f"{self._dir()}/{os.path.basename(name)}")
        finally:
            sftp.close(); t.close()


class S3Dest(Destination):
    """S3-compatible object storage with AWS Signature V4 (no extra libraries)."""
    kind = "s3"

    def _base(self):
        c = self.conf
        ep = (c.get("endpoint") or "").rstrip("/") or f"https://s3.{c.get('region') or 'us-east-1'}.amazonaws.com"
        if not ep.startswith("https://"):
            raise RuntimeError("the storage address must start with https://")
        return ep

    def _req(self, method, key="", query=None, body=b"", body_path=None):
        import hmac
        import requests
        from urllib.parse import quote, urlparse
        from .oauth_engine import _decrypt
        c = self.conf
        region = c.get("region") or "us-east-1"
        access, secret = c["access_key"], _decrypt(c["secret_enc"])
        bucket = c["bucket"]
        prefix = (c.get("prefix") or "").strip("/")
        obj = "/".join(p for p in (prefix, key) if p) if key else ""   # no key: the bucket itself (listing)
        base = self._base()
        host = urlparse(base).netloc
        path = "/" + quote(bucket) + ("/" + quote(obj) if obj else "")
        q = "&".join(f"{quote(k, safe='')}={quote(str(v), safe='')}" for k, v in sorted((query or {}).items()))
        now = datetime.utcnow()
        amz, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
        if body_path:
            h = hashlib.sha256()
            with open(body_path, "rb") as f:
                for blk in iter(lambda: f.read(1 << 20), b""):
                    h.update(blk)
            payload_hash = h.hexdigest()
        else:
            payload_hash = hashlib.sha256(body).hexdigest()
        headers = {"host": host, "x-amz-content-sha256": payload_hash, "x-amz-date": amz}
        signed = ";".join(sorted(headers))
        canon = "\n".join([method, path, q, "".join(f"{k}:{headers[k]}\n" for k in sorted(headers)), signed, payload_hash])
        scope = f"{day}/{region}/s3/aws4_request"
        sts = "\n".join(["AWS4-HMAC-SHA256", amz, scope, hashlib.sha256(canon.encode()).hexdigest()])
        k = ("AWS4" + secret).encode()
        for part in (day, region, "s3", "aws4_request"):
            k = hmac.new(k, part.encode(), hashlib.sha256).digest()
        sig = hmac.new(k, sts.encode(), hashlib.sha256).hexdigest()
        headers["Authorization"] = f"AWS4-HMAC-SHA256 Credential={access}/{scope}, SignedHeaders={signed}, Signature={sig}"
        url = base + path + (("?" + q) if q else "")
        data = open(body_path, "rb") if body_path else (body or None)
        try:
            r = requests.request(method, url, headers=headers, data=data, timeout=600)
        finally:
            if body_path:
                data.close()
        if r.status_code >= 300:
            raise RuntimeError(f"storage answered {r.status_code}: {r.text[:200]}")
        return r

    def upload(self, path, name):
        self._req("PUT", name, body_path=path)

    def names(self, include_tests=False):
        import re
        prefix = (self.conf.get("prefix") or "").strip("/")
        p = (prefix + "/" if prefix else "") + PREFIX
        r = self._req("GET", "", query={"list-type": "2", "prefix": p})
        keys = re.findall(r"<Key>(.*?)</Key>", r.text)
        out = [k.rsplit("/", 1)[-1] for k in keys]
        return sorted(n for n in out if n.endswith(SUFFIX) or include_tests)

    def delete(self, name):
        self._req("DELETE", os.path.basename(name))


# OAuth cloud drives. Tokens are kept encrypted with the email OAuth tokens
# (account_ref "bkp-<id>"), and refreshed when they expire.
CLOUD = {
    "gdrive": {"auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
               "token_url": "https://oauth2.googleapis.com/token",
               "scopes": "https://www.googleapis.com/auth/drive.file", "client_key": "gmail", "pkce": True},
    "onedrive": {"auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
                 "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                 "scopes": "offline_access Files.ReadWrite.AppFolder", "client_key": "outlook", "pkce": True},
    "dropbox": {"auth_url": "https://www.dropbox.com/oauth2/authorize",
                "token_url": "https://api.dropboxapi.com/oauth2/token",
                "scopes": "files.content.write files.content.read files.metadata.read",
                "client_key": "dropbox", "pkce": True, "extra": "token_access_type=offline"},
}


def cloud_flow(kind: str):
    from .oauth_engine import OAuthFlowDesc
    c = CLOUD[kind]
    return OAuthFlowDesc(provider_key=f"backup-{kind}", auth_url=c["auth_url"], token_url=c["token_url"],
                         scopes=c["scopes"], use_pkce=c["pkce"], extra_params=c.get("extra", ""))


class CloudDest(Destination):
    def _token(self) -> str:
        from . import oauth_engine as oe
        from .settings_store import load_settings, save_settings
        ref = self.conf.get("account_ref")
        s = load_settings()
        toks = oe.load_tokens(s, ref) if ref else None
        if not toks:
            raise RuntimeError("this storage account isn't connected yet; press Connect")
        if oe.is_expired(toks):
            client = oe.OAuthClient(toks.get("client_id", ""), toks.get("client_secret", ""), "")
            new = oe.refresh_token(cloud_flow(self.kind), client, toks["refresh_token"])
            oe.store_tokens(s, ref, new)
            save_settings(s)
            toks = new
        return toks["access_token"]

    def _h(self, extra=None):
        h = {"Authorization": f"Bearer {self._token()}"}
        h.update(extra or {})
        return h


class GDriveDest(CloudDest):
    kind = "gdrive"
    API = "https://www.googleapis.com/drive/v3"

    def _folder(self):
        import requests
        if self.conf.get("folder_id"):
            return self.conf["folder_id"]
        q = "name='OpenOptOut backups' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        r = requests.get(f"{self.API}/files", params={"q": q, "fields": "files(id)"}, headers=self._h(), timeout=30)
        r.raise_for_status()
        files = r.json().get("files") or []
        if files:
            fid = files[0]["id"]
        else:
            r = requests.post(f"{self.API}/files", json={"name": "OpenOptOut backups",
                                                         "mimeType": "application/vnd.google-apps.folder"},
                              headers=self._h(), timeout=30)
            r.raise_for_status()
            fid = r.json()["id"]
        self.conf["folder_id"] = fid
        return fid

    def _list(self):
        import requests
        r = requests.get(f"{self.API}/files", params={"q": f"'{self._folder()}' in parents and trashed=false",
                                                      "fields": "files(id,name)", "pageSize": 1000},
                         headers=self._h(), timeout=30)
        r.raise_for_status()
        return r.json().get("files") or []

    def upload(self, path, name):
        import requests
        size = os.path.getsize(path)
        r = requests.post("https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable",
                          json={"name": name, "parents": [self._folder()]},
                          headers=self._h({"X-Upload-Content-Type": "application/octet-stream",
                                           "X-Upload-Content-Length": str(size)}), timeout=30)
        r.raise_for_status()
        with open(path, "rb") as f:
            u = requests.put(r.headers["Location"], data=f, headers={"Content-Length": str(size)}, timeout=3600)
        if u.status_code >= 300:
            raise RuntimeError(f"Google Drive answered {u.status_code}")

    def names(self, include_tests=False):
        return sorted(f["name"] for f in self._list() if f["name"].startswith(PREFIX)
                      and (f["name"].endswith(SUFFIX) or include_tests))

    def delete(self, name):
        import requests
        for f in self._list():
            if f["name"] == name:
                requests.delete(f"{self.API}/files/{f['id']}", headers=self._h(), timeout=30).raise_for_status()


class OneDriveDest(CloudDest):
    kind = "onedrive"
    API = "https://graph.microsoft.com/v1.0/me/drive/special/approot"

    def upload(self, path, name):
        import requests
        r = requests.post(f"{self.API}:/{name}:/createUploadSession", json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
                          headers=self._h(), timeout=30)
        r.raise_for_status()
        url, size, chunk = r.json()["uploadUrl"], os.path.getsize(path), 320 * 1024 * 30
        with open(path, "rb") as f:
            pos = 0
            while pos < size:
                data = f.read(chunk)
                end = pos + len(data) - 1
                u = requests.put(url, data=data, headers={"Content-Range": f"bytes {pos}-{end}/{size}"}, timeout=600)
                if u.status_code >= 300:
                    raise RuntimeError(f"OneDrive answered {u.status_code}")
                pos = end + 1

    def names(self, include_tests=False):
        import requests
        r = requests.get(f"{self.API}/children", headers=self._h(), timeout=30)
        r.raise_for_status()
        return sorted(i["name"] for i in r.json().get("value", []) if i["name"].startswith(PREFIX)
                      and (i["name"].endswith(SUFFIX) or include_tests))

    def delete(self, name):
        import requests
        requests.delete(f"{self.API}:/{name}", headers=self._h(), timeout=30).raise_for_status()


class DropboxDest(CloudDest):
    kind = "dropbox"

    def upload(self, path, name):
        import requests
        size = os.path.getsize(path)
        arg = json.dumps({"path": f"/{name}", "mode": "overwrite"})
        if size <= 140 * 1024 * 1024:
            with open(path, "rb") as f:
                r = requests.post("https://content.dropboxapi.com/2/files/upload", data=f, timeout=3600,
                                  headers=self._h({"Dropbox-API-Arg": arg, "Content-Type": "application/octet-stream"}))
            if r.status_code >= 300:
                raise RuntimeError(f"Dropbox answered {r.status_code}: {r.text[:200]}")
            return
        with open(path, "rb") as f:
            r = requests.post("https://content.dropboxapi.com/2/files/upload_session/start", data=f.read(FRAME * 2),
                              headers=self._h({"Content-Type": "application/octet-stream"}), timeout=600)
            r.raise_for_status()
            sid, off = r.json()["session_id"], f.tell()
            while True:
                data = f.read(FRAME * 2)
                if not data:
                    break
                cur = json.dumps({"cursor": {"session_id": sid, "offset": off}})
                requests.post("https://content.dropboxapi.com/2/files/upload_session/append_v2", data=data,
                              headers=self._h({"Dropbox-API-Arg": cur, "Content-Type": "application/octet-stream"}),
                              timeout=600).raise_for_status()
                off += len(data)
            fin = json.dumps({"cursor": {"session_id": sid, "offset": off}, "commit": {"path": f"/{name}", "mode": "overwrite"}})
            requests.post("https://content.dropboxapi.com/2/files/upload_session/finish", data=b"",
                          headers=self._h({"Dropbox-API-Arg": fin, "Content-Type": "application/octet-stream"}),
                          timeout=600).raise_for_status()

    def names(self, include_tests=False):
        import requests
        r = requests.post("https://api.dropboxapi.com/2/files/list_folder", json={"path": ""},
                          headers=self._h(), timeout=30)
        r.raise_for_status()
        return sorted(e["name"] for e in r.json().get("entries", []) if e["name"].startswith(PREFIX)
                      and (e["name"].endswith(SUFFIX) or include_tests))

    def delete(self, name):
        import requests
        requests.post("https://api.dropboxapi.com/2/files/delete_v2", json={"path": f"/{name}"},
                      headers=self._h(), timeout=30).raise_for_status()


class RcloneDest(Destination):
    """
    Anything rclone can reach: Proton Drive, Box, pCloud, MEGA, Backblaze,
    iCloud Drive, WebDAV/Nextcloud and dozens more. The admin pastes the
    remote's section from their rclone.conf (made with `rclone config` on
    any computer); it's kept encrypted and written to a private temp file only
    while rclone runs. Backups are already encrypted before rclone sees them.
    """
    kind = "rclone"
    _REMOTE = __import__("re").compile(r"^[A-Za-z0-9_.-]{1,64}$")

    def _remote(self):
        r = (self.conf.get("remote") or "").strip().rstrip(":")
        if not self._REMOTE.match(r):
            raise RuntimeError("enter the remote's name exactly as it appears in [brackets] in the config")
        path = (self.conf.get("path") or "").strip().strip("/")
        if ".." in path.split("/"):
            raise RuntimeError("the folder can't contain '..'")
        return f"{r}:{path}" if path else f"{r}:"

    def _run(self, *args, timeout=3600):
        import subprocess
        exe = shutil.which("rclone")
        if not exe:
            raise RuntimeError("rclone isn't installed on this server (it's included in the Docker image; "
                               "elsewhere install it from rclone.org)")
        from .oauth_engine import _decrypt
        conf_text = _decrypt(self.conf["config_enc"]) if self.conf.get("config_enc") else ""
        if not conf_text.strip():
            raise RuntimeError("paste the remote's settings from rclone.conf")
        fd, conf_path = tempfile.mkstemp(prefix="oo-rclone-", suffix=".conf")
        try:
            os.chmod(conf_path, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(conf_text)
            res = subprocess.run([exe, "--config", conf_path, "--retries", "2", "--low-level-retries", "3", *args],
                                 capture_output=True, text=True, timeout=timeout,
                                 env={"PATH": os.environ.get("PATH", ""), "HOME": tempfile.gettempdir()})
        finally:
            try:
                os.unlink(conf_path)
            except OSError:
                pass
        if res.returncode != 0:
            last = (res.stderr or res.stdout or "").strip().splitlines()[-1:] or ["rclone failed"]
            raise RuntimeError(f"rclone: {last[0][:300]}")
        return res.stdout

    def _dest(self, name):
        base = self._remote()
        return base + ("" if base.endswith(":") else "/") + os.path.basename(name)

    def upload(self, path, name):
        self._run("copyto", path, self._dest(name))

    def names(self, include_tests=False):
        out = self._run("lsf", "--files-only", self._remote(), timeout=300)
        return sorted(n for n in out.splitlines() if n.startswith(PREFIX)
                      and (n.endswith(SUFFIX) or include_tests))

    def delete(self, name):
        self._run("deletefile", self._dest(name), timeout=300)


KINDS = {"folder": FolderDest, "sftp": SFTPDest, "s3": S3Dest, "gdrive": GDriveDest,
         "onedrive": OneDriveDest, "dropbox": DropboxDest, "rclone": RcloneDest}
LOCAL_DIR = os.getenv("BACKUP_DIR") or os.path.join(os.path.dirname(os.getenv("SETTINGS_FILE") or "./x"), "backups")


def destination(conf: dict, cfg: dict) -> Destination:
    cls = KINDS.get(conf.get("kind"))
    if cls is None:
        raise ValueError(f"unknown backup destination: {conf.get('kind')}")
    return cls(conf, cfg)


def passphrase(cfg: dict) -> str:
    from .oauth_engine import _decrypt
    enc = settings_of(cfg).get("passphrase_enc")
    return _decrypt(enc) if enc else ""


# ── Running a backup ──────────────────────────────────────────────────────────

def run_backup(cfg: dict, now=None, bundle=None, local_dir=None) -> dict:
    """
    Make one encrypted backup, keep it in the local backups folder, copy it to
    every enabled destination, and prune old copies. Returns a result dict.
    """
    now = now or datetime.utcnow()
    s = settings_of(cfg)
    pw = passphrase(cfg)
    if not pw:
        return {"ok": False, "error": "Set a backup passphrase first."}
    local_dir = local_dir or LOCAL_DIR
    os.makedirs(local_dir, exist_ok=True)
    name = f"{PREFIX}{now:%Y%m%d-%H%M%S}{SUFFIX}"
    result = {"ok": True, "name": name, "started": now.isoformat() + "Z", "destinations": []}
    with tempfile.TemporaryDirectory(prefix="oobk-") as work:
        plain = bundle(work, cfg) if bundle else build_bundle(work, cfg)
        enc = os.path.join(local_dir, name)
        encrypt_file(plain, enc, pw)
        os.remove(plain)
    result["size"] = os.path.getsize(enc)
    h = hashlib.sha256()
    with open(enc, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    result["sha256"] = h.hexdigest()
    keep = max(1, int(s.get("keep") or 14))
    _prune_local(local_dir, keep)
    for conf in s.get("destinations", []):
        if not conf.get("enabled", True):
            continue
        entry = {"id": conf.get("id"), "kind": conf.get("kind"), "label": conf.get("label") or conf.get("kind")}
        try:
            d = destination(conf, cfg)
            d.upload(enc, name)
            old = [n for n in d.names() if n != name][:-(keep - 1)] if keep > 1 else [n for n in d.names() if n != name]
            for n in old:
                try:
                    d.delete(n)
                except Exception as e:
                    log.info("couldn't remove old backup %s from %s: %s", n, entry["label"], e)
            entry["ok"] = True
        except Exception as e:
            entry["ok"], entry["error"] = False, str(e)[:300]
            result["ok"] = False
        result["destinations"].append(entry)
    result["finished"] = datetime.utcnow().isoformat() + "Z"
    return result


def _prune_local(d: str, keep: int):
    names = sorted(n for n in os.listdir(d) if n.startswith(PREFIX) and n.endswith(SUFFIX))
    for n in names[:-keep]:
        try:
            os.remove(os.path.join(d, n))
        except OSError:
            pass


def due(cfg: dict, now=None) -> bool:
    now = now or datetime.utcnow()
    s = settings_of(cfg)
    if not s.get("enabled") or not s.get("passphrase_enc"):
        return False
    last = (cfg or {}).get("backups_last_run")
    every = timedelta(days=7 if s.get("schedule") == "weekly" else 1) - timedelta(hours=1)
    if last:
        try:
            if now - datetime.fromisoformat(last.rstrip("Z")) < every:
                return False
        except ValueError:
            pass
    return now.hour >= int(s.get("hour") or 0)


def verify_file(path: str, pw: str) -> dict:
    """Decrypt to a temp file and read the manifest. Raises ValueError if it can't."""
    with tempfile.TemporaryDirectory(prefix="oobk-v-") as work:
        plain = os.path.join(work, "b.tar.gz")
        header = decrypt_file(path, plain, pw)
        with tarfile.open(plain, "r:gz") as tar:
            m = tar.extractfile("openoptout-backup/manifest.json")
            manifest = json.load(m) if m else {}
    return {"header": header, "manifest": manifest}


# ── Restore (command line, server stopped) ────────────────────────────────────

def restore(path: str, pw: str, to_dir: str) -> dict:
    """Decrypt and unpack a backup into to_dir (database, settings, plugins, keys)."""
    os.makedirs(to_dir, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="oobk-r-") as work:
        plain = os.path.join(work, "b.tar.gz")
        decrypt_file(path, plain, pw)
        with tarfile.open(plain, "r:gz") as tar:
            for m in tar.getmembers():
                if m.name.startswith("/") or ".." in m.name.split("/") or m.issym() or m.islnk():
                    raise ValueError("unsafe path in backup")
            tar.extractall(work, filter="data") if hasattr(tarfile, "data_filter") else tar.extractall(work)  # nosec B202
        root = os.path.join(work, "openoptout-backup")
        with open(os.path.join(root, "manifest.json")) as f:
            manifest = json.load(f)
        for name in os.listdir(root):
            src, dst = os.path.join(root, name), os.path.join(to_dir, name)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copyfile(src, dst)
    return manifest


def _cli(argv=None):
    import argparse
    import getpass
    p = argparse.ArgumentParser(prog="backup", description="OpenOptOut encrypted backups")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("restore", help="unpack a backup (stop the server first)")
    r.add_argument("file"); r.add_argument("--to", required=True)
    v = sub.add_parser("verify", help="check a backup can be decrypted")
    v.add_argument("file")
    a = p.parse_args(argv)
    pw = os.getenv("BACKUP_PASSPHRASE") or getpass.getpass("Backup passphrase: ")
    if a.cmd == "verify":
        info = verify_file(a.file, pw)
        print("OK: backup from", info["manifest"].get("created"), "with", [x["part"] for x in info["manifest"].get("parts", [])])
    else:
        m = restore(a.file, pw, a.to)
        print(f"Restored into {a.to}: {[x['part'] for x in m.get('parts', [])]}")
        print("Next: put database.* where DATABASE_URL points, settings.json where SETTINGS_FILE points, "
              "plugins/ in the plugins folder, and set the keys from keys.json in your .env. See docs/BACKUPS.md.")


if __name__ == "__main__":
    _cli()
