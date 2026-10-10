#!/usr/bin/env bash
# ==============================================================================
# OpenOptOut — Automated Live Email Account Verification (OAuth & App Passwords)
# ==============================================================================
""":"
if command -v python3 >/dev/null 2>&1; then
  exec python3 "$0" "$@"
else
  exec python "$0" "$@"
fi
"""
import argparse
import json
import os
import smtplib
import ssl
import sys
import time

# Ensure backend package imports resolve
HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(HERE) if os.path.basename(HERE) == "tests" else HERE
REPO_ROOT = os.path.dirname(BACKEND_DIR)
for p in (BACKEND_DIR, REPO_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from core import oauth_engine as oe
    from core.provider_plugins import ensure_provider_plugin
    from core.settings_store import load_settings, save_settings
except ImportError:
    try:
        from app.core import oauth_engine as oe
        from app.core.provider_plugins import ensure_provider_plugin
        from app.core.settings_store import load_settings, save_settings
    except ImportError:
        oe = None
        ensure_provider_plugin = None
        load_settings = None
        save_settings = None

# Known SMTP server configurations for app passwords
SMTP_PRESETS = {
    "gmail": {"host": "smtp.gmail.com", "port": 587, "tls": "starttls"},
    "yahoo": {"host": "smtp.mail.yahoo.com", "port": 465, "tls": "ssl"},
    "outlook": {"host": "smtp-mail.outlook.com", "port": 587, "tls": "starttls"},
    "hotmail": {"host": "smtp-mail.outlook.com", "port": 587, "tls": "starttls"},
    "office365": {"host": "smtp.office365.com", "port": 587, "tls": "starttls"},
    "fastmail": {"host": "smtp.fastmail.com", "port": 465, "tls": "ssl"},
    "icloud": {"host": "smtp.mail.me.com", "port": 587, "tls": "starttls"},
}

# Built-in OAuth flows matching email_oauth.py
BUILTIN_FLOWS = {
    "gmail": oe.OAuthFlowDesc(
        "gmail",
        "https://accounts.google.com/o/oauth2/v2/auth",
        "https://oauth2.googleapis.com/token",
        "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly",
        use_pkce=True,
    ) if oe else None,
    "outlook": oe.OAuthFlowDesc(
        "outlook",
        "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "https://graph.microsoft.com/Mail.Send https://graph.microsoft.com/Mail.Read offline_access",
        use_pkce=True,
    ) if oe else None,
    "yahoo": oe.OAuthFlowDesc(
        "yahoo",
        "https://api.login.yahoo.com/oauth2/request_auth",
        "https://api.login.yahoo.com/oauth2/get_token",
        "mail-w",
        use_pkce=False,
    ) if oe else None,
}


def find_config(explicit_path=None):
    if explicit_path and os.path.isfile(explicit_path):
        return explicit_path
    candidates = [
        "test_email_accounts.json",
        ".test_email_accounts.json",
        os.path.join(REPO_ROOT, "test_email_accounts.json"),
        os.path.join(REPO_ROOT, ".test_email_accounts.json"),
        "/data/test_email_accounts.json",
        "/app/test_email_accounts.json",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def test_smtp_account(acc, settings, no_store):
    ref = acc.get("account_ref", "smtp-account")
    provider = (acc.get("provider") or "smtp").lower()
    user = (acc.get("username") or acc.get("user") or "").strip()
    pw = (acc.get("app_password") or acc.get("password") or "").strip()
    preset = SMTP_PRESETS.get(provider, {})
    host = (acc.get("smtp_host") or preset.get("host") or "").strip()
    port = int(acc.get("smtp_port") or preset.get("port") or 587)
    tls = (acc.get("smtp_tls") or preset.get("tls") or "starttls").lower()
    is_active = bool(acc.get("active", False))

    print(f"Account: '{ref}' [App Password / SMTP] (provider: {provider})")
    if not host or not user or not pw:
        print("  [✗] Missing host, username, or app password.")
        return False

    print(f"  Connecting to {host}:{port} via {tls.upper()}...")
    try:
        ctx = ssl.create_default_context()
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        if tls == "ssl":
            with smtplib.SMTP_SSL(host, port, timeout=20, context=ctx) as s:
                s.login(user, pw)
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                if tls == "starttls":
                    s.starttls(context=ctx)
                s.login(user, pw)
        print(f"  [✓] SMTP authentication successful with app password ({host}:{port}).")
    except smtplib.SMTPAuthenticationError as e:
        print(f"  [✗] SMTP authentication failed: Invalid username or app password ({e}).")
        return False
    except Exception as e:
        print(f"  [✗] SMTP connection error: {e}")
        return False

    if not no_store and load_settings and save_settings and oe:
        try:
            email_conf = settings.setdefault("email", {})
            if is_active or len(settings.get("email_credentials", {})) == 0:
                email_conf["provider"] = "smtp"
                email_conf["smtp_host"] = host
                email_conf["smtp_port"] = port
                email_conf["smtp_username"] = user
                email_conf["smtp_user"] = user
                email_conf["smtp_password_enc"] = oe._encrypt(pw)
                email_conf["smtp_tls"] = tls
            save_settings(settings)
            print(f"  [✓] Stored encrypted SMTP credentials in settings.")
        except Exception as e:
            print(f"  [!] Failed to store SMTP credentials in settings: {e}")

    return True


def test_oauth_account(acc, settings, no_store):
    ref = acc.get("account_ref", "oauth-account")
    provider = (acc.get("provider") or "").lower()
    client_id = acc.get("client_id", "").strip()
    client_secret = acc.get("client_secret", "").strip()
    refresh = acc.get("refresh_token", "").strip()
    is_active = bool(acc.get("active", False))

    print(f"Account: '{ref}' [OAuth 2.0] (provider: {provider})")
    if not client_id or not client_secret or not refresh:
        print("  [✗] Missing client_id, client_secret, or refresh_token.")
        return False

    flow = BUILTIN_FLOWS.get(provider)
    if not flow:
        print(f"  [✗] Unknown or unsupported OAuth provider: '{provider}'")
        return False

    client = oe.OAuthClient(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri="http://localhost/api/email-oauth/callback",
    )

    try:
        tokens = oe.refresh_token(flow, client, refresh)
        access_token = tokens.get("access_token", "")
        expires_at = tokens.get("expires_at", 0)
        if access_token:
            remaining = max(0, int(expires_at - time.time()))
            print(f"  [✓] OAuth token refresh successful (valid for {remaining}s).")
        else:
            print("  [✗] Provider returned empty access_token.")
            return False
    except Exception as e:
        print(f"  [✗] Token refresh failed against {provider} API: {e}")
        return False

    if ensure_provider_plugin:
        try:
            ok = ensure_provider_plugin(provider)
            if ok:
                print(f"  [✓] Bundled email plugin 'email-{provider}' verified & active.")
            else:
                print(f"  [!] Bundled plugin 'email-{provider}' could not be provisioned.")
        except Exception as e:
            print(f"  [!] Plugin provision warning: {e}")

    if not no_store and load_settings and save_settings:
        try:
            oe.store_tokens(settings, ref, tokens)
            if is_active:
                email_conf = settings.setdefault("email", {})
                email_conf["provider"] = provider
                email_conf["active_account_ref"] = ref
            save_settings(settings)
            print(f"  [✓] Stored encrypted OAuth credentials in settings for '{ref}'.")
        except Exception as e:
            print(f"  [!] Failed to store tokens in settings: {e}")

    return True


def main():
    parser = argparse.ArgumentParser(description="Test email accounts (OAuth & App Passwords) from config")
    parser.add_argument("--config", default=None, help="Path to test_email_accounts.json")
    parser.add_argument("--no-store", action="store_true", help="Do not save refreshed credentials to settings")
    args = parser.parse_args()

    config_path = find_config(args.config)
    print("\n=================================================================")
    print("  OpenOptOut Live Email Account Verification Probe")
    print("=================================================================\n")

    if not config_path:
        print("Config:      NOT FOUND [○]")
        print("Note:        No test_email_accounts.json detected. Skipping live email probe.")
        print("Tip:         To test real accounts, copy .test_email_accounts.example.json to")
        print("             test_email_accounts.json and populate credentials.")
        print("\nVERDICT: SKIPPED (no credentials provided)\n")
        return 0

    print(f"Config:      {config_path} [✓]")
    try:
        with open(config_path, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error:       Failed to parse JSON config: {e}")
        return 1

    accounts = data.get("accounts", [])
    if not accounts:
        print("Warning:     Config contains no accounts.")
        return 0

    print(f"Accounts:    {len(accounts)} configured for testing\n")
    all_passed = True
    settings = load_settings() if (load_settings and not args.no_store) else {}

    for idx, acc in enumerate(accounts, start=1):
        print(f"[{idx}/{len(accounts)}] Processing:")
        acc_type = (acc.get("type") or "").lower()
        if not acc_type:
            if acc.get("app_password") or acc.get("password"):
                acc_type = "app_password"
            else:
                acc_type = "oauth"

        if acc_type in ("app_password", "smtp"):
            ok = test_smtp_account(acc, settings, args.no_store)
        else:
            ok = test_oauth_account(acc, settings, args.no_store)

        if not ok:
            all_passed = False
        print()

    if all_passed:
        print("VERDICT: PASS — All configured email accounts verified successfully!\n")
        return 0
    else:
        print("VERDICT: FAIL — One or more email accounts failed verification.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
