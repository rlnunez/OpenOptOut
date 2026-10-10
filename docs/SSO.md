# Single sign-on (SSO) setup

OpenOptOut supports several ways for staff to sign in with accounts they already have. All of them go through one shared set of access rules, so an administrator's restrictions apply no matter which method a person uses.

| Method | Good for |
|---|---|
| **OIDC — Google** | Google Workspace organizations |
| **OIDC — Microsoft** | Microsoft 365 / Entra ID organizations |
| **OIDC — Okta, Auth0, Keycloak, custom** | Any OIDC identity provider |
| **SAML 2.0** | Universities (Shibboleth / InCommon), ADFS, Entra, Okta, home-lab Keycloak or Authentik |
| **LDAP** | On-premises directories (Active Directory) |
| **Library card (SIP2)** | Patrons signing in with their library card |

All are configured on the **Branding** page, under sign-in providers.

## Access rules (apply to every method)

- **Allowed email domains.** Only addresses in these domains can sign in.
- **Required groups.** The person must be in at least one listed group. For universities using SAML, this can be an affiliation such as `staff,faculty`. It also applies to existing accounts, so removing someone from the group revokes their sign-in.
- **Registration mode** (open / domain / invite / admin-only) applies to new sign-ups. To let a trusted identity provider create accounts even when registration is closed, enable "create accounts for new users" on that provider. This is on by default for SAML, LDAP, and SIP2, and off for OIDC.
- **Super admin is never granted automatically.** New SSO accounts get the provider's default role (parent or member). Promote administrators manually.
- **The first account** is always created by the setup wizard, never by SSO.

## Google Workspace

Set **Allowed email domains** to your Workspace domain. This matters: anyone can create a personal Google account using an address like `name@yourlibrary.org`, and Google marks it "verified". OpenOptOut checks Google's hosted-domain (`hd`) claim, which only genuine Workspace accounts carry. Without an allowed domain, any Google account can sign in, and the settings page warns you.

## Microsoft 365 / Entra ID

Use your own **tenant ID**. The values `common`, `organizations`, and `consumers` accept accounts from any organization, so new users are refused until you also set allowed domains.

## SAML 2.0

1. On the Branding page, open **SAML 2.0 single sign-on**.
2. Set **Public base URL** to the address people use to reach OpenOptOut (for example `https://privacy.example.edu`). Do this first, because the URLs below are built from it and must match what your IdP registers.
3. Register OpenOptOut at your identity provider. Most IdPs can import the **SP metadata URL** directly. Otherwise enter the **Entity ID** and the **ACS URL** (HTTP-POST binding).
4. Give OpenOptOut your IdP's metadata, by URL (easiest) or by pasting XML.
5. Make sure your IdP releases an email attribute (`mail`), and a display name and groups/affiliation if you use group rules. Common attribute names are recognized automatically; override them under "Attribute names" if needed.
6. Set who may sign in, enable SAML, and save. A sign-in button appears on the login page.

**Security properties:** responses must be signed; each sign-in request is single-use and expires after 10 minutes (no replays); responses the IdP sends without a matching request are rejected; audience and validity are checked. Signature checking uses pysaml2 with the `xmlsec1` tool (included in the Docker image).

### Home lab examples

- **Keycloak:** Clients → Import client → paste the SP metadata URL. Add a mapper that sends the user's email as `mail`. The IdP metadata URL is `https://<keycloak>/realms/<realm>/protocol/saml/descriptor`.
- **Authentik:** create a SAML provider using the Entity ID and ACS URL, then use the provider's metadata download URL in OpenOptOut.

### Universities (Shibboleth / InCommon)

Your campus identity team registers the SP (usually from the metadata URL). Ask them to release `mail`, `displayName`, and `eduPersonAffiliation`, then set **Required groups** to `staff,faculty` (or whichever affiliations should have access).

## LDAP / Active Directory

Choose a **connection security** mode:

| Mode | Port | Notes |
|---|---|---|
| **LDAPS** (recommended) | 636 | Encrypted from the first byte. For AD Global Catalog over TLS, use 3269. |
| **StartTLS** | 389 | Connects, then upgrades to TLS before any password is sent. |
| **None** | 389 | Unencrypted. Every staff password crosses the network in clear text. |

**Certificates are always verified.** There is intentionally no "ignore certificate errors" option: the server sends each person's real password over this connection, so an unverified connection would let anyone on the network collect passwords. Instead:

- If your directory's certificate comes from a public CA, nothing extra is needed.
- If it comes from your organization's **internal CA** (typical for Active Directory) or is **self-signed** (common in home labs), paste the CA certificate (PEM, `-----BEGIN CERTIFICATE-----`) into **CA certificate**. On Windows, export the root CA certificate as "Base-64 encoded X.509".
- The host name you enter must match a name on the directory's certificate.

### Auto-renewing certificates (Let's Encrypt, internal ACME)

Short-lived certificates work without any maintenance, because OpenOptOut trusts the **issuing CA**, not the server's own certificate. Every connection re-checks the chain, host name, and dates, so each renewed certificate is accepted automatically. (Let's Encrypt certificates last 90 days and renew around day 60; the industry maximum falls to 47 days by 2029.)

- **Public CA (e.g. Let's Encrypt):** paste nothing. The container's built-in root certificates cover it. Rebuild the image occasionally so those roots stay current.
- **Internal CA (AD, step-ca, other internal ACME):** paste the **CA** certificate once.
- **Never paste the server's own certificate.** It would work until the next renewal and then silently break sign-in. The settings page refuses it and explains which CA certificate to use instead.

**Renewal monitoring:** a daily check reads the directory's live certificate. If it's close to expiry (which usually means automatic renewal has stopped working), super admins see a warning on the dashboard before sign-in breaks. The LDAP settings also show the certificate's expiry date, with a "Check now" button.

Use **Test connection** after saving. It reports the specific problem: the server can't be reached, the certificate isn't trusted, the name doesn't match the certificate, or the port isn't an LDAPS port.

Blank passwords are always refused. (Many directories, including Active Directory by default, treat a blank password as a successful "anonymous" bind, which would otherwise let anyone sign in as any user.)

## Library card (SIP2)

Turn on **TLS** (SIP2 over TLS, usually port 6443) unless the ILS is on an isolated internal network. Without it, card numbers and PINs cross the network readable.

The ILS certificate is **always verified**; there is no switch to turn that off. If the ILS uses an internal or self-signed CA, paste that **CA** certificate in the SIP2 settings (not the ILS server's own certificate, which would break at the next renewal). Older installs that had verification turned off are now verified too. If sign-in stops working after upgrading, **Test connection** will say so, and pasting the ILS's CA certificate fixes it.

Patrons see the same message whether the card number or the PIN was wrong, so the login form can't be used to discover which card numbers exist.

## Certificate reminders

A daily check covers every certificate sign-in depends on:

| Certificate | When you're warned |
|---|---|
| LDAP / Active Directory server | When it's close to expiry (auto-renewal has likely failed) |
| Library ILS (SIP2 over TLS) | Same |
| SAML identity provider signing certificate | From **30 days** before it expires |
| OpenOptOut's own HTTPS certificate (if using the built-in Caddy front door — see [docs/HTTPS.md](HTTPS.md)) | Same, once `HTTPS_MODE`/`DOMAIN` are set |

SAML signing certificates don't update themselves in OpenOptOut. When your identity provider switches to a new one, SAML sign-in stops until you upload the IdP's new metadata (or re-save, if you set it from a URL). If the metadata already includes the next certificate (a planned rollover), no warning is shown.

Warnings appear on the **dashboard** for super admins, and every super admin is **emailed** once at each milestone: 30, 14, 7, 3, and 1 day before expiry, and on expiry. Emails use the separate admin email account if one was set up in the setup wizard, otherwise the regular email settings. Email must be configured for reminders to be sent; the dashboard alerts work regardless.

## Behind a reverse proxy or HTTPS terminator

SSO redirects are built from the public URL. Set `FRONTEND_URL` (and for SAML, the Public base URL) to the exact external address, including `https://`.

This applies whether HTTPS is terminated by OpenOptOut's front door (Caddy/Traefik) or an external reverse proxy. See [`docs/HTTPS.md`](HTTPS.md) for configuration details.
