"""
Encrypted backups. See core/backup.py. Super administrators only: a backup
holds everything, including the keys that unlock the database.

  GET    /api/backups                     settings, destinations (no secrets), history, local files
  PUT    /api/backups                     schedule: enabled, daily/weekly, hour, keep, include_plugins
  POST   /api/backups/passphrase          set it, or {"generate": true} (shown once)
  POST   /api/backups/destinations        add a destination
  PUT    /api/backups/destinations/{id}   change it
  DELETE /api/backups/destinations/{id}
  POST   /api/backups/destinations/{id}/test     write, list and delete a small test file
  POST   /api/backups/destinations/{id}/connect  sign in to Google Drive / OneDrive / Dropbox
  POST   /api/backups/run                 back up now (background)
  GET    /api/backups/files/{name}        download a local copy (still encrypted)
  POST   /api/backups/files/{name}/verify check it decrypts with the saved passphrase
"""

import json
import os
import secrets
import threading
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..core.auth import require_super_admin
from ..core.settings_store import load_settings, SETTINGS_FILE
from ..core import backup as bk
from ..core import oauth_engine as oe

router = APIRouter(prefix="/api/backups", tags=["backups"])
_RUN = {"running": False}
_LOCK = threading.Lock()

SECRET_FIELDS = {"password": "password_enc", "private_key": "private_key_enc", "secret_key": "secret_enc",
                 "rclone_config": "config_enc"}
PUBLIC_FIELDS = {
    "folder": ("path",),
    "sftp": ("host", "port", "username", "path", "host_key"),
    "s3": ("endpoint", "region", "bucket", "prefix", "access_key"),
    "gdrive": (), "onedrive": (), "dropbox": (),
    "rclone": ("remote", "path"),
}
LABELS = {"folder": "Folder or network drive", "sftp": "SFTP server", "s3": "S3-compatible storage",
          "gdrive": "Google Drive", "onedrive": "OneDrive", "dropbox": "Dropbox",
          "rclone": "Other cloud storage (rclone)"}


def _save(cfg):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def _public(d: dict) -> dict:
    out = {k: d.get(k) for k in ("id", "kind", "label", "enabled", "connected", "host_key_seen")}
    out.update({k: d.get(k) for k in PUBLIC_FIELDS.get(d.get("kind"), ())})
    out["has_secret"] = any(d.get(v) for v in SECRET_FIELDS.values())
    out["kind_label"] = LABELS.get(d.get("kind"), d.get("kind"))
    out["needs_connect"] = d.get("kind") in bk.CLOUD and not d.get("connected")
    return out


def _local_files():
    d = bk.LOCAL_DIR
    if not os.path.isdir(d):
        return []
    out = []
    for n in sorted(os.listdir(d), reverse=True):
        if n.startswith(bk.PREFIX) and n.endswith(bk.SUFFIX):
            st = os.stat(os.path.join(d, n))
            out.append({"name": n, "size": st.st_size, "modified": datetime.utcfromtimestamp(st.st_mtime).isoformat() + "Z"})
    return out


@router.get("")
def get_all(_=Depends(require_super_admin)):
    cfg = load_settings()
    s = bk.settings_of(cfg)
    return {"enabled": s["enabled"], "schedule": s["schedule"], "hour": s["hour"], "keep": s["keep"],
            "include_plugins": s["include_plugins"], "has_passphrase": bool(s.get("passphrase_enc")),
            "destinations": [_public(d) for d in s["destinations"]],
            "history": (cfg.get("backups_history") or [])[:20], "files": _local_files(),
            "running": _RUN["running"], "local_dir": bk.LOCAL_DIR, "kinds": LABELS}


class ScheduleIn(BaseModel):
    enabled: bool = False
    schedule: str = "daily"
    hour: int = 3
    keep: int = 14
    include_plugins: bool = True


@router.put("")
def put_schedule(body: ScheduleIn, _=Depends(require_super_admin)):
    if body.schedule not in ("daily", "weekly"):
        raise HTTPException(400, "Choose daily or weekly.")
    cfg = load_settings()
    s = bk.settings_of(cfg)
    if body.enabled and not s.get("passphrase_enc"):
        raise HTTPException(400, "Set a backup passphrase before turning on automatic backups.")
    s.update(enabled=body.enabled, schedule=body.schedule, hour=max(0, min(23, body.hour)),
             keep=max(1, min(365, body.keep)), include_plugins=body.include_plugins)
    cfg["backups"] = s
    _save(cfg)
    return {"ok": True}


class PassIn(BaseModel):
    passphrase: str = ""
    generate: bool = False


@router.post("/passphrase")
def set_passphrase(body: PassIn, _=Depends(require_super_admin)):
    pw = body.passphrase
    if body.generate:
        words = secrets.token_urlsafe(24)
        pw = "-".join(words[i:i + 6] for i in range(0, 24, 6))
    if len(pw) < 12:
        raise HTTPException(400, "Use at least 12 characters. A few random words works well.")
    cfg = load_settings()
    s = bk.settings_of(cfg)
    s["passphrase_enc"] = oe._encrypt(pw)
    cfg["backups"] = s
    _save(cfg)
    return {"ok": True, "passphrase": pw if body.generate else None,
            "message": ("Write this passphrase down and keep it somewhere safe, away from this server. "
                        "Without it, no backup can be restored.")}


class DestIn(BaseModel):
    kind: str
    label: str = ""
    enabled: bool = True
    path: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    private_key: Optional[str] = None
    host_key: Optional[str] = None
    endpoint: Optional[str] = None
    region: Optional[str] = None
    bucket: Optional[str] = None
    prefix: Optional[str] = None
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    remote: Optional[str] = None
    rclone_config: Optional[str] = None


def _apply(d: dict, body: DestIn):
    if body.kind not in bk.KINDS:
        raise HTTPException(400, "Unknown kind of storage.")
    d["kind"], d["label"], d["enabled"] = body.kind, (body.label or LABELS[body.kind])[:80], body.enabled
    for k in PUBLIC_FIELDS[body.kind]:
        v = getattr(body, k)
        if v is not None:
            d[k] = v.strip() if isinstance(v, str) else v
    for k, enc in SECRET_FIELDS.items():
        v = getattr(body, k)
        if v:
            d[enc] = oe._encrypt(v)
    if body.kind == "folder" and not os.path.isabs(d.get("path") or ""):
        raise HTTPException(400, "Enter the folder's full path, like /mnt/nas/openoptout.")
    if body.kind == "sftp" and not (d.get("host") and d.get("username")):
        raise HTTPException(400, "Enter the server address and user name.")
    if body.kind == "s3" and not (d.get("bucket") and d.get("access_key") and d.get("secret_enc")):
        raise HTTPException(400, "Enter the bucket, access key and secret key.")
    if body.kind == "rclone" and not (d.get("remote") and d.get("config_enc")):
        raise HTTPException(400, "Enter the remote's name and paste its settings from rclone.conf.")


@router.post("/destinations")
def add_dest(body: DestIn, _=Depends(require_super_admin)):
    cfg = load_settings()
    s = bk.settings_of(cfg)
    d = {"id": secrets.token_hex(4)}
    _apply(d, body)
    s["destinations"].append(d)
    cfg["backups"] = s
    _save(cfg)
    return _public(d)


def _find(s, dest_id):
    for d in s["destinations"]:
        if d.get("id") == dest_id:
            return d
    raise HTTPException(404, "That storage place is gone.")


@router.put("/destinations/{dest_id}")
def edit_dest(dest_id: str, body: DestIn, _=Depends(require_super_admin)):
    cfg = load_settings()
    s = bk.settings_of(cfg)
    d = _find(s, dest_id)
    _apply(d, body)
    cfg["backups"] = s
    _save(cfg)
    return _public(d)


@router.delete("/destinations/{dest_id}")
def delete_dest(dest_id: str, _=Depends(require_super_admin)):
    cfg = load_settings()
    s = bk.settings_of(cfg)
    d = _find(s, dest_id)
    s["destinations"].remove(d)
    if d.get("account_ref"):
        (cfg.get("email_credentials") or {}).pop(d["account_ref"], None)
    cfg["backups"] = s
    _save(cfg)
    return {"ok": True}


@router.post("/destinations/{dest_id}/test")
def test_dest(dest_id: str, _=Depends(require_super_admin)):
    cfg = load_settings()
    s = bk.settings_of(cfg)
    d = _find(s, dest_id)
    try:
        bk.destination(d, cfg).test()
    except Exception as e:
        return {"ok": False, "message": f"That didn't work: {str(e)[:300]}"}
    # Remember what the SFTP server presented the first time (host key pinning)
    # and the Drive folder we created.
    cfg = load_settings()
    s2 = bk.settings_of(cfg)
    d2 = _find(s2, dest_id)
    if d.get("host_key_seen") and not d2.get("host_key"):
        d2["host_key"] = d["host_key_seen"]
    if d.get("folder_id"):
        d2["folder_id"] = d["folder_id"]
    cfg["backups"] = s2
    _save(cfg)
    return {"ok": True, "message": "It works: a test file was written, found and removed."}


@router.post("/destinations/{dest_id}/connect")
def connect_dest(dest_id: str, _=Depends(require_super_admin)):
    from .email_oauth import _PENDING, _client
    cfg = load_settings()
    s = bk.settings_of(cfg)
    d = _find(s, dest_id)
    if d.get("kind") not in bk.CLOUD:
        raise HTTPException(400, "Only Google Drive, OneDrive and Dropbox sign in.")
    key = bk.CLOUD[d["kind"]]["client_key"]
    try:
        client = _client(cfg, key)
    except HTTPException:
        hint = {"gmail": "the Google sign-in app you use for Gmail (enable the Google Drive API in the same project)",
                "outlook": "the Microsoft sign-in app you use for Outlook (add the Files.ReadWrite.AppFolder permission)",
                "dropbox": "a Dropbox app (Settings → Email → OAuth apps, provider 'dropbox')"}[key]
        raise HTTPException(400, f"First register {hint}, with OpenOptOut's sign-in return address.")
    url, pending = oe.begin_authorization(bk.cloud_flow(d["kind"]), client, f"bkp-{dest_id}")
    _PENDING[pending.state] = pending
    return {"authorize_url": url}


def _run_backup():
    try:
        cfg = load_settings()
        res = bk.run_backup(cfg)
        cfg = load_settings()
        hist = [res] + (cfg.get("backups_history") or [])
        cfg["backups_history"] = hist[:50]
        if res.get("name"):
            cfg["backups_last_run"] = datetime.utcnow().isoformat() + "Z"
        _save(cfg)
    finally:
        with _LOCK:
            _RUN["running"] = False


@router.post("/run")
def run_now(_=Depends(require_super_admin)):
    if not bk.passphrase(load_settings()):
        raise HTTPException(400, "Set a backup passphrase first.")
    with _LOCK:
        if _RUN["running"]:
            return {"started": False, "message": "A backup is already running."}
        _RUN["running"] = True
    threading.Thread(target=_run_backup, daemon=True).start()
    return {"started": True, "message": "Backing up now. This usually takes under a minute."}


def _local(name: str) -> str:
    base = os.path.basename(name)
    if base != name or not (base.startswith(bk.PREFIX) and base.endswith(bk.SUFFIX)):
        raise HTTPException(400, "Not a backup file name.")
    path = os.path.join(bk.LOCAL_DIR, base)
    if not os.path.isfile(path):
        raise HTTPException(404, "That backup isn't on this server any more.")
    return path


@router.get("/files/{name}")
def download(name: str, _=Depends(require_super_admin)):
    return FileResponse(_local(name), media_type="application/octet-stream", filename=name)


@router.post("/files/{name}/verify")
def verify(name: str, _=Depends(require_super_admin)):
    try:
        info = bk.verify_file(_local(name), bk.passphrase(load_settings()))
    except ValueError as e:
        return {"ok": False, "message": str(e)}
    parts = [p["part"] for p in info["manifest"].get("parts", [])]
    return {"ok": True, "message": f"This backup opens with your passphrase and holds: {', '.join(parts)}."}
