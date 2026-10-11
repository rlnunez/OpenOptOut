# Backups

**Admin → Backups** (super administrators only) makes encrypted backups and copies them to the places you choose.

## What's in a backup

- **The database.** For SQLite, a consistent copy of the database file; it stays SQLCipher-encrypted inside the backup. For PostgreSQL, a `pg_dump`.
- **The settings file.** OAuth tokens and passwords in it stay encrypted.
- **Installed plugins.** Built-in ones are left out because they come with the app.
- **The keys that unlock it all:** `SECRET_KEY`, `DB_ENCRYPTION_KEY`, `FIELD_ENCRYPTION_KEY`. A restore on a new server then needs only the backup file and the passphrase.

## How it's protected

Everything is encrypted with **AES-256-GCM** before it leaves the server. The key comes from your **backup passphrase**, stretched with scrypt. The file is written in authenticated pieces, so a backup that was cut short, reordered or changed is refused.

Nobody can read a backup without the passphrase, including whoever stores it. Keep the passphrase somewhere that isn't the server. If it's lost, the backups can't be restored.

## Where backups can go

| Place | What you enter |
|---|---|
| Folder or network drive | A full path. To use a NAS, mount it into the container (`volumes: - /mnt/nas/openoptout:/backups`) and enter `/backups` |
| SFTP server | Address, port, user, password or private key, folder. The server's identity (host key) is remembered on the first test; a different key later is refused |
| S3-compatible storage | Bucket, keys, region, and optionally an address and folder. Works with Amazon S3, **Google Cloud Storage** (`https://storage.googleapis.com` with HMAC keys), Backblaze B2, Wasabi and MinIO |
| Google Drive | Press **Sign in**. Uses the Google sign-in app registered for Gmail; enable the *Google Drive API* in that Google Cloud project. Files go into an "OpenOptOut backups" folder, and OpenOptOut can only see files it made (`drive.file`) |
| OneDrive | Press **Sign in**. Uses the Microsoft app registered for Outlook; add the *Files.ReadWrite.AppFolder* permission. Files go into OpenOptOut's app folder |
| Dropbox | Register a Dropbox app (scoped access, *App folder*) under Settings → Email → OAuth apps with the provider name `dropbox`, then press **Sign in** |

Press **Test** after adding a place: OpenOptOut writes a small file there, finds it, and removes it.

A copy is always kept on the server too (`/data/backups`, or `BACKUP_DIR`). Every place keeps the newest *N* backups (14 by default). Older ones that OpenOptOut made are deleted; nothing else there is touched.

## Schedule

Daily or weekly at a chosen hour, or **Back up now**. History shows each run and how each place did. **Check it opens** decrypts a local copy with the saved passphrase to prove it's restorable.

## Restoring

1. Stop OpenOptOut (`docker compose stop api`).
2. Unpack the backup:
   ```
   docker compose run --rm api python -m app.core.backup restore /data/backups/openoptout-backup-YYYYMMDD-HHMMSS.oobackup --to /data/restore
   ```
   Enter the passphrase when asked (or set `BACKUP_PASSPHRASE`).
3. Put the pieces back:
   - `database.sqlite` where `DATABASE_URL` points (for PostgreSQL, `pg_restore` the `database.pgdump`)
   - `settings.json` where `SETTINGS_FILE` points
   - `plugins/` into the plugins folder
   - the values in `keys.json` into `.env`
4. Start OpenOptOut.

To check a file without restoring it: `python -m app.core.backup verify FILE`.
