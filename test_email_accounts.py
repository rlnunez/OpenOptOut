#!/usr/bin/env bash
# ==============================================================================
# OpenOptOut — Automated Live Email OAuth Account Verification
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

# Built-in flows matching email_oauth.py
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


def main():
    parser = argparse.ArgumentParser(description="Test email OAuth accounts from config")
    parser.add_argument("--config", default=None, help="Path to test_email_accounts.json")
    parser.add_argument("--no-store", action="store_true", help="Do not save refreshed tokens to settings")
    args = parser.parse_args()

    config_path = find_config(args.config)
    print("\n=================================================================")
    print("  OpenOptOut Live Email OAuth Account Verification Probe")
    print("=================================================================\n")

    if not config_path:
        print("Config:      NOT FOUND [○]")
        print("Note:        No test_email_accounts.json detected. Skipping live OAuth probe.")
        print("Tip:         To test real accounts, copy .test_email_accounts.example.json to")
        print("             test_email_accounts.json and populate credentials.")
        print("\nVERDICT: SKIPPED (no credentials provided)\n")
        return 0

    print(f"Config:      {config_path} [✓]")
    if not oe:
        print("Error:       Core oauth_engine module could not be imported.")
        return 1

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
        ref = acc.get("account_ref", f"account-{idx}")
        provider = (acc.get("provider") or "").lower()
        client_id = acc.get("client_id", "").strip()
        client_secret = acc.get("client_secret", "").strip()
        refresh = acc.get("refresh_token", "").strip()
        is_active = bool(acc.get("active", False))

        print(f"Account [{idx}/{len(accounts)}]: '{ref}' (provider: {provider})")
        if not client_id or not client_secret or not refresh:
            print("  [✗] Missing client_id, client_secret, or refresh_token.")
            all_passed = False
            continue

        flow = BUILTIN_FLOWS.get(provider)
        if not flow:
            print(f"  [✗] Unknown or unsupported email provider: '{provider}'")
            all_passed = False
            continue

        client = oe.OAuthClient(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri="http://localhost/api/email-oauth/callback",
        )

        # 1. Live token refresh probe
        try:
            tokens = oe.refresh_token(flow, client, refresh)
            access_token = tokens.get("access_token", "")
            expires_at = tokens.get("expires_at", 0)
            if access_token:
                remaining = max(0, int(expires_at - time.time()))
                print(f"  [✓] OAuth token refresh successful (valid for {remaining}s).")
            else:
                print("  [✗] Provider returned empty access_token.")
                all_passed = False
                continue
        except Exception as e:
            print(f"  [✗] Token refresh failed against {provider} API: {e}")
            all_passed = False
            continue

        # 2. Bundled email plugin provision probe
        if ensure_provider_plugin:
            try:
                ok = ensure_provider_plugin(provider)
                if ok:
                    print(f"  [✓] Bundled email plugin 'email-{provider}' verified & active.")
                else:
                    print(f"  [!] Bundled plugin 'email-{provider}' could not be provisioned.")
            except Exception as e:
                print(f"  [!] Plugin provision warning: {e}")

        # 3. Store into settings if requested
        if not args.no_store and load_settings and save_settings:
            try:
                oe.store_tokens(settings, ref, tokens)
                if is_active or len(accounts) == 1:
                    email_conf = settings.setdefault("email", {})
                    email_conf["provider"] = provider
                    email_conf["active_account_ref"] = ref
                save_settings(settings)
                print(f"  [✓] Stored credentials encrypted in settings for '{ref}'.")
            except Exception as e:
                print(f"  [!] Failed to store tokens in settings: {e}")

        print()

    if all_passed:
        print("VERDICT: PASS — All configured email OAuth accounts refreshed successfully!\n")
        return 0
    else:
        print("VERDICT: FAIL — One or more email OAuth accounts failed verification.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())

